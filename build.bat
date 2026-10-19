@echo off
chcp 65001 >nul
echo === Генерация иконки ===
python icon_gen.py

echo === Сборка .exe (2-5 минут) ===
python -m PyInstaller --noconfirm --clean --onefile --windowed ^  --name "MySoundPad" ^
  --icon "icon.ico" ^
  --add-data "icon.png;." ^
  --hidden-import soundfile ^
  --hidden-import sounddevice ^
  soundpad.py

echo.
echo === ГОТОВО! Файл: dist\MySoundPad.exe ===
pause