"""Draws the application icon (assets/battery_monitoring.ico)."""
import os
import sys

from PIL import Image, ImageDraw

SIZES = [16, 20, 24, 32, 40, 48, 64, 128, 256]


def draw(size: int = 256) -> Image.Image:
    supersample = 4
    s = size * supersample / 64
    img = Image.new("RGBA", (size * supersample, size * supersample), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((2 * s, 2 * s, 62 * s, 62 * s), radius=14 * s, fill=(0, 103, 192, 255))
    white = (255, 255, 255, 255)
    d.rounded_rectangle((10 * s, 20 * s, 49 * s, 44 * s), radius=5 * s, outline=white, width=round(4 * s))
    d.rounded_rectangle((50 * s, 27 * s, 55 * s, 37 * s), radius=2 * s, fill=white)
    d.rectangle((16 * s, 26 * s, 37 * s, 38 * s), fill=(63, 213, 104, 255))
    return img.resize((size, size), Image.LANCZOS)


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else os.path.join("assets", "battery_monitoring.ico")
    os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
    draw(256).save(target, sizes=[(n, n) for n in SIZES])
    print(f"Written: {target}")


if __name__ == "__main__":
    main()
