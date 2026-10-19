import sys, os, json, threading
import numpy as np
import sounddevice as sd
import soundfile as sf
from PySide6.QtCore import Qt, QObject, QTimer
from PySide6.QtGui import QIcon, QFont
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QGridLayout, QPushButton,
    QFileDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QSlider, QMessageBox, QScrollArea, QInputDialog, QMenu, QFrame,
    QDialog, QTabWidget, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView
)
from pynput import keyboard

CONFIG_FILE = "soundpad_config.json"

DARK_QSS = """
QMainWindow, QWidget#Central { background: #1a1b23; }
QLabel { color: #c9cbd6; font-size: 13px; font-weight: 500; }
QPushButton { color: #c9cbd6; }
QComboBox {
    background: #262834; color: #eaeaea; border: 1px solid #35384a;
    border-radius: 8px; padding: 6px 10px; min-height: 26px;
}
QComboBox QAbstractItemView {
    background: #262834; color: #eaeaea;
    selection-background-color: #5865f2;
}
QSlider::groove:horizontal { height: 6px; background: #262834; border-radius: 3px; }
QSlider::sub-page:horizontal {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #5865f2, stop:1 #8b5cf6);
    border-radius: 3px;
}
QSlider::handle:horizontal {
    background: #eaeaea; width: 16px; height: 16px;
    margin: -6px 0; border-radius: 8px;
}
QPushButton#Tool {
    background: #262834; color: #c9cbd6;
    border: 1px solid #35384a; border-radius: 8px;
    padding: 8px 14px; font-size: 13px;
}
QPushButton#Tool:hover { background: #2f3242; border-color: #5865f2; color: #fff; }
QPushButton#Stop {
    background: #ef4444; color: white; border: none; border-radius: 8px;
    padding: 8px 16px; font-weight: 600;
}
QPushButton#Pause {
    background: #262834; color: #c9cbd6; border: 1px solid #35384a;
    border-radius: 8px; padding: 8px 16px; font-weight: 600;
}
QPushButton#PauseActive {
    background: #5865f2; color: white; border: none;
    border-radius: 8px; padding: 8px 16px; font-weight: 600;
}
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { background: #1a1b23; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: #35384a; border-radius: 5px; min-height: 24px; }
"""

SOUND_BTN_QSS = """
QPushButton {
    background: #262834; color: #e6e8f0; border: 1px solid #35384a;
    border-radius: 12px; font-size: 14px; font-weight: 600;
    padding: 10px 8px; text-align: center;
}
QPushButton:hover { background: #2f3242; border-color: #5865f2; color: #ffffff; }
QPushButton:pressed { background: #5865f2; border-color: #8b5cf6; color: #ffffff; }
"""

LIGHT_QSS = """
QDialog { background: #f0f0f0; color: #000000; }
QLabel { color: #000000; font-size: 12px; font-weight: 500; }
QTabWidget::pane { border: 1px solid #cccccc; background: #f0f0f0; }
QTabBar::tab {
    background: #e0e0e0; color: #000000; padding: 6px 12px;
    border: 1px solid #cccccc; border-bottom: none;
}
QTabBar::tab:selected { background: #ffffff; }
QListWidget, QTableWidget {
    background: #ffffff; color: #000000; border: 1px solid #cccccc;
    gridline-color: #e0e0e0;
}
QHeaderView::section {
    background: #e0e0e0; color: #000000; padding: 4px; border: 1px solid #cccccc;
}
QPushButton {
    background: #e1e1e1; color: #000000; border: 1px solid #adadad;
    border-radius: 4px; padding: 4px 12px;
}
QPushButton:hover { background: #e5f1fb; border-color: #0078d7; }
QComboBox {
    background: #ffffff; color: #000000; border: 1px solid #cccccc;
    padding: 4px; border-radius: 2px;
}
"""

class AudioEngine(QObject):
    def __init__(self):
        super().__init__()
        self.sample_rate = 44100
        self.stream = None
        self.master_volume = 0.8
        self.active = []
        self.lock = threading.Lock()
        self.is_paused = False

    def set_device(self, device_index):
        self.stop()
        try:
            self.stream = sd.OutputStream(
                samplerate=self.sample_rate, blocksize=2048, channels=2,
                device=device_index, callback=self._cb)
            self.stream.start()
        except Exception as e:
            print("Аудио-ошибка:", e)

    def stop(self):
        if self.stream:
            try: self.stream.stop(); self.stream.close()
            except Exception: pass
            self.stream = None

    def _resample(self, data, orig_sr):
        if orig_sr == self.sample_rate: return data
        ratio = self.sample_rate / orig_sr
        new_len = int(len(data) * ratio)
        idx = np.linspace(0, len(data) - 1, new_len)
        return np.interp(idx, np.arange(len(data)), data)

    def play_file(self, path, volume=1.0):
        self.stop_all() 
        try:
            data, sr = sf.read(path, dtype="float32", always_2d=True)
        except Exception as e:
            print("Не прочитать:", e); return
        data = self._resample(data, sr)
        if data.shape[1] == 1:
            data = np.repeat(data, 2, axis=1)
        elif data.shape[1] > 2:
            data = data[:, :2]
        with self.lock:
            self.active.append({"data": data, "pos": 0, "volume": volume})

    def stop_all(self):
        with self.lock: self.active.clear()
        self.is_paused = False

    def toggle_pause(self):
        self.is_paused = not self.is_paused
        return self.is_paused

    def _cb(self, outdata, frames, time, status):
        outdata[:] = 0
        if self.is_paused: return
        with self.lock:
            done = []
            for s in self.active:
                rem = len(s["data"]) - s["pos"]
                take = min(rem, frames)
                outdata[:take] += s["data"][s["pos"]:s["pos"]+take] * s["volume"]
                s["pos"] += take
                if s["pos"] >= len(s["data"]): done.append(s)
            for d in done: self.active.remove(d)
        np.clip(outdata, -1, 1, out=outdata)
        outdata *= self.master_volume

def get_key_name(key):
    if hasattr(key, "char") and key.char:
        return key.char.lower()
    name = str(key).replace("Key.", "")
    if name.startswith("num_"): return name
    if name.startswith("f") and name[1:].isdigit(): return name
    return name

class KeyGrabberDialog(QDialog):
    def __init__(self, parent, title):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setStyleSheet(LIGHT_QSS)
        self.setFixedSize(350, 100)
        self.result_key = None
        layout = QVBoxLayout(self)
        self.lbl = QLabel("Нажмите нужную клавишу...")
        self.lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.lbl)
        
        self.listener = keyboard.Listener(on_press=self._on_press)
        self.listener.start()

    def _on_press(self, key):
        self.result_key = get_key_name(key)
        QTimer.singleShot(0, self.accept)
        return False

    def closeEvent(self, event):
        self.listener.stop()
        super().closeEvent(event)

class SettingsDialog(QDialog):
    def __init__(self, parent, engine):
        super().__init__(parent)
        self.parent = parent
        self.engine = engine
        self.setWindowTitle("Настройки")
        self.resize(700, 550)
        self.setStyleSheet(LIGHT_QSS)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        
        dev_tab = QWidget()
        dl = QVBoxLayout(dev_tab)
        dl.addWidget(QLabel("Устройство воспроизведения:"))
        self.out_combo = QComboBox()
        for i, d in enumerate(sd.query_devices()):
            if d["max_output_channels"] > 0:
                self.out_combo.addItem(f"{d['name']}", i)
                if i == self.parent.current_out_idx:
                    self.out_combo.setCurrentIndex(self.out_combo.count() - 1)
        dl.addWidget(self.out_combo)
        
        self.lbl_out = QLabel(f"Выбрано: {self.out_combo.currentText()}")
        self.lbl_out.setStyleSheet("color: #5865f2; font-weight: bold;")
        dl.addWidget(self.lbl_out)
        self.out_combo.currentIndexChanged.connect(
            lambda: self.lbl_out.setText(f"Выбрано: {self.out_combo.currentText()}"))
        
        lbl_hint = QLabel("⚠️ Звук идет в колонки. Для передачи в Discord нужен виртуальный кабель.")
        lbl_hint.setStyleSheet("color: #d9534f; font-size: 11px;")
        lbl_hint.setWordWrap(True)
        dl.addWidget(lbl_hint)
        tabs.addTab(dev_tab, "Устройства")

        hk_tab = QWidget()
        hl = QVBoxLayout(hk_tab)
        
        hl.addWidget(QLabel("Специальные горячие клавиши:"))
        self.hk_table = QTableWidget(0, 2)
        self.hk_table.setHorizontalHeaderLabels(["Действие", "Клавиша"])
        self.hk_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.hk_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        hl.addWidget(self.hk_table)
        
        btn_set_hk = QPushButton("Задать клавишу")
        btn_set_hk.clicked.connect(self._set_special_hotkey)
        hl.addWidget(btn_set_hk)
        
        hl.addSpacing(15)
        hl.addWidget(QLabel("Клавиши для кнопок со звуками:"))
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Кнопка", "Клавиша"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        hl.addWidget(self.table)
        
        btn_edit = QPushButton("Изменить клавишу кнопки")
        btn_edit.clicked.connect(self._edit_button_hotkey)
        hl.addWidget(btn_edit)
        
        tabs.addTab(hk_tab, "Горячие клавиши")
        layout.addWidget(tabs)

        bottom = QHBoxLayout()
        bottom.addStretch()
        btn_ok = QPushButton("OK")
        btn_ok.clicked.connect(self._save_settings)
        btn_cancel = QPushButton("Отмена")
        btn_cancel.clicked.connect(self.reject)
        bottom.addWidget(btn_ok)
        bottom.addWidget(btn_cancel)
        layout.addLayout(bottom)
        
        self._update_hk_table()
        self._refresh_table()

    def _update_hk_table(self):
        p = self.parent
        items = [
            ("Пауза / Продолжить", p.hotkey_pause),
            ("Стоп", p.hotkey_stop),
            ("Следующий трек", p.hotkey_next),
            ("Предыдущий трек", p.hotkey_prev),
            ("Мьют микрофона", p.hotkey_mute)
        ]
        self.hk_table.setRowCount(len(items))
        for i, (name, key) in enumerate(items):
            self.hk_table.setItem(i, 0, QTableWidgetItem(name))
            self.hk_table.setItem(i, 1, QTableWidgetItem(key or "—"))

    def _refresh_table(self):
        self.table.setRowCount(len(self.parent.buttons))
        for i, b in enumerate(self.parent.buttons):
            self.table.setItem(i, 0, QTableWidgetItem(b.text()))
            self.table.setItem(i, 1, QTableWidgetItem(b.hotkey or "—"))

    def _set_special_hotkey(self):
        row = self.hk_table.currentRow()
        if row < 0: return
        dlg = KeyGrabberDialog(self, "Нажмите клавишу")
        dlg.exec()
        if dlg.result_key:
            if row == 0: self.parent.hotkey_pause = dlg.result_key
            elif row == 1: self.parent.hotkey_stop = dlg.result_key
            elif row == 2: self.parent.hotkey_next = dlg.result_key
            elif row == 3: self.parent.hotkey_prev = dlg.result_key
            elif row == 4: self.parent.hotkey_mute = dlg.result_key
            self._update_hk_table()

    def _edit_button_hotkey(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self.parent.buttons): return
        b = self.parent.buttons[row]
        dlg = KeyGrabberDialog(self, f"Клавиша для '{b.text()}'")
        dlg.exec()
        if dlg.result_key:
            b.hotkey = dlg.result_key
            self._refresh_table()

    def _save_settings(self):
        idx = self.out_combo.currentData()
        if idx is not None:
            self.parent.current_out_idx = idx
            self.engine.set_device(idx)
            self.parent._save_config()
        self.accept()

class SoundButton(QPushButton):
    def __init__(self, label, engine, path=None, hotkey=None):
        super().__init__(label)
        self.engine = engine
        self.path = path
        self.hotkey = hotkey
        self.setMinimumHeight(76)
        self.setStyleSheet(SOUND_BTN_QSS)
        self.clicked.connect(self.play)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._menu)

    def play(self):
        if not self.path:
            QMessageBox.information(self, "Нет звука", "ПКМ -> Выбрать файл")
            return
        self.engine.play_file(self.path)

    def _menu(self, pos):
        m = QMenu(self)
        m.setStyleSheet("QMenu { background: #262834; color: white; } QMenu::item:selected { background: #5865f2; }")
        a1 = m.addAction("Выбрать файл...")
        a2 = m.addAction("Переименовать...")
        act = m.exec(self.mapToGlobal(pos))
        if act == a1:
            f, _ = QFileDialog.getOpenFileName(self, "Звук", "", "Аудио (*.wav *.mp3 *.flac *.ogg *.m4a)")
            if f:
                self.path = f
                self.setText(os.path.basename(f)[:18])
        elif act == a2:
            n, ok = QInputDialog.getText(self, "Имя", "Название:", text=self.text())
            if ok and n: self.setText(n)

    def to_dict(self):
        return {"label": self.text(), "path": self.path, "hotkey": self.hotkey}

class MainWindow(QMainWindow):
    ROWS, COLS = 4, 5

    def __init__(self):
        super().__init__()
        self.setWindowTitle("My SoundPad")
        self.resize(1000, 700)
        if os.path.exists("icon.png"):
            self.setWindowIcon(QIcon("icon.png"))
        self.engine = AudioEngine()
        self.buttons = []
        
        self.current_out_idx = None
        self.hotkey_pause = "f9"
        self.hotkey_stop = "f10"
        self.hotkey_next = "f11"
        self.hotkey_prev = "f12"
        self.hotkey_mute = "f8"
        
        self._build_ui()
        self._populate_devices()
        self._start_hotkeys()
        self._load_config()

    def _build_ui(self):
        central = QWidget(); central.setObjectName("Central")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(16, 16, 16, 16)

        header = QHBoxLayout()
        title = QLabel("My SoundPad")
        title.setStyleSheet("color:#ffffff; font-size:20px; font-weight:800;")
        header.addWidget(title)
        header.addStretch()
        btn_settings = QPushButton("Настройки")
        btn_settings.setObjectName("Tool")
        btn_settings.clicked.connect(self._open_settings)
        header.addWidget(btn_settings)
        root.addLayout(header)

        toolbar = QFrame()
        toolbar.setStyleSheet("QFrame{background:#20222e; border:1px solid #2b2e3d; border-radius:12px;}")
        tb = QHBoxLayout(toolbar)
        
        tb.addWidget(QLabel("Громкость:"))
        self.vol = QSlider(Qt.Horizontal)
        self.vol.setRange(0, 100); self.vol.setValue(80)
        self.vol.valueChanged.connect(lambda v: setattr(self.engine, "master_volume", v/100))
        tb.addWidget(self.vol, 1)
        
        self.btn_pause = QPushButton("Пауза")
        self.btn_pause.setObjectName("Pause")
        self.btn_pause.clicked.connect(self._toggle_pause)
        tb.addWidget(self.btn_pause)

        btn_stop = QPushButton("Стоп")
        btn_stop.setObjectName("Stop")
        btn_stop.clicked.connect(self.engine.stop_all)
        tb.addWidget(btn_stop)
        
        root.addWidget(toolbar)

        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        gw = QWidget(); gw.setStyleSheet("background: transparent;")
        self.grid = QGridLayout(gw); self.grid.setSpacing(10)
        for r in range(self.ROWS):
            for c in range(self.COLS):
                self._add_button(r, c, f"Звук {r*self.COLS+c+1}")
        scroll.setWidget(gw)
        root.addWidget(scroll, 1)

        self.status = QLabel("Готов")
        self.status.setStyleSheet("color:#6b7080; font-size:12px;")
        root.addWidget(self.status)

    def _add_button(self, r, c, label):
        b = SoundButton(label, self.engine)
        self.grid.addWidget(b, r, c)
        self.buttons.append(b)

    def _populate_devices(self):
        try:
            for i, d in enumerate(sd.query_devices()):
                if d["max_output_channels"] > 0:
                    if self.current_out_idx is None:
                        self.current_out_idx = i
                    break
            if self.current_out_idx is not None:
                self.engine.set_device(self.current_out_idx)
        except Exception as e:
            print("devices:", e)

    def _open_settings(self):
        dlg = SettingsDialog(self, self.engine)
        dlg.exec()

    def _toggle_pause(self):
        paused = self.engine.toggle_pause()
        if paused:
            self.btn_pause.setObjectName("PauseActive")
            self.btn_pause.setText("Продолжить")
        else:
            self.btn_pause.setObjectName("Pause")
            self.btn_pause.setText("Пауза")
        self.btn_pause.style().unpolish(self.btn_pause)
        self.btn_pause.style().polish(self.btn_pause)

    def _start_hotkeys(self):
        def on_press(key):
            name = get_key_name(key)
            
            # Обработка спец-клавиш через прямой вызов
            if self.hotkey_pause and name == self.hotkey_pause:
                self._toggle_pause(); return
            if self.hotkey_stop and name == self.hotkey_stop:
                self.engine.stop_all(); return
                
            # Обработка кнопок со звуками
            for b in self.buttons:
                if b.hotkey and b.hotkey == name:
                    self.engine.play_file(b.path)
                    return
                    
        self.listener = keyboard.Listener(on_press=on_press)
        self.listener.daemon = True
        self.listener.start()

    def _save_config(self):
        data = {
            "buttons": [b.to_dict() for b in self.buttons],
            "settings": {
                "current_out_idx": self.current_out_idx,
                "hotkey_pause": self.hotkey_pause,
                "hotkey_stop": self.hotkey_stop,
                "hotkey_next": self.hotkey_next,
                "hotkey_prev": self.hotkey_prev,
                "hotkey_mute": self.hotkey_mute
            }
        }
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        self.status.setText(f"Сохранено: {CONFIG_FILE}")

    def _load_config(self):
        if not os.path.exists(CONFIG_FILE): return
        try:
            with open(CONFIG_FILE, encoding="utf-8") as f: data = json.load(f)
            if isinstance(data, list): buttons_data = data; settings = {}
            else: buttons_data = data.get("buttons", []); settings = data.get("settings", {})
                
            self.current_out_idx = settings.get("current_out_idx", self.current_out_idx)
            self.hotkey_pause = settings.get("hotkey_pause", self.hotkey_pause)
            self.hotkey_stop = settings.get("hotkey_stop", self.hotkey_stop)
            self.hotkey_next = settings.get("hotkey_next", self.hotkey_next)
            self.hotkey_prev = settings.get("hotkey_prev", self.hotkey_prev)
            self.hotkey_mute = settings.get("hotkey_mute", self.hotkey_mute)
            
            for var in ["hotkey_pause", "hotkey_stop", "hotkey_next", "hotkey_prev", "hotkey_mute"]:
                val = getattr(self, var)
                if val and val.startswith("Key."):
                    setattr(self, var, val.replace("Key.", ""))

            if self.current_out_idx is not None:
                self.engine.set_device(self.current_out_idx)

            for i, item in enumerate(buttons_data):
                if i < len(self.buttons):
                    b = self.buttons[i]
                    b.setText(item.get("label", b.text()))
                    b.path = item.get("path")
                    hk = item.get("hotkey")
                    if hk and hk.startswith("Key."):
                        hk = hk.replace("Key.", "")
                    b.hotkey = hk
        except Exception as e:
            print("Ошибка загрузки конфига:", e)

    def closeEvent(self, e):
        self._save_config()
        self.engine.stop()
        try: self.listener.stop()
        except Exception: pass
        super().closeEvent(e)

def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(DARK_QSS)
    app.setFont(QFont("Segoe UI", 10))
    w = MainWindow(); w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()