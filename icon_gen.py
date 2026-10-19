from PIL import Image, ImageDraw

def make_icon(size=256):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    radius = int(size * 0.22)
    bg = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    bd = ImageDraw.Draw(bg)
    for y in range(size):
        t = y / size
        bd.line([(0, y), (size, y)], fill=(int(20 + t * 15), int(22 + t * 18), int(35 + t * 55), 255))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size-1, size-1], radius=radius, fill=255)
    img.paste(bg, (0, 0), mask)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([2, 2, size-3, size-3], radius=radius-2,
                        outline=(88, 101, 242, 255), width=max(2, size//64))
    bars, bar_w, gap = 5, int(size * 0.09), int(size * 0.055)
    total = bars * bar_w + (bars - 1) * gap
    start_x = (size - total) // 2
    bottom = int(size * 0.78)
    heights = [0.35, 0.6, 0.85, 0.55, 0.75]
    for i, h in enumerate(heights):
        x0 = start_x + i * (bar_w + gap)
        x1 = x0 + bar_w
        y1 = bottom
        y0 = int(bottom - size * 0.5 * h)
        for yy in range(y0, y1):
            t = (yy - y0) / max(1, (y1 - y0))
            d.line([(x0, yy), (x1, yy)],
                   fill=(int(88 + t * 60), int(200 - t * 120), int(255 - t * 40), 255))
        d.ellipse([x0, y0 - bar_w//2, x1, y0 + bar_w//2], fill=(88, 200, 255, 255))
    return img

if __name__ == "__main__":
    img = make_icon(256)
    img.save("icon.png")
    img.save("icon.ico", sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
    print("Иконка создана: icon.ico и icon.png")