"""Generate assets/icon.ico (mic in a circle) at standard Windows sizes."""
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent / "assets" / "icon.ico"
SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def draw(size: int) -> Image.Image:
    s = size / 64.0
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # circle
    d.ellipse((6 * s, 6 * s, 58 * s, 58 * s), fill=(0, 140, 220, 255))
    # mic body + cradle + stem (white)
    w = max(1, int(3 * s))
    d.rounded_rectangle((26 * s, 16 * s, 38 * s, 36 * s), radius=5 * s, fill="white")
    d.arc((20 * s, 24 * s, 44 * s, 42 * s), start=20, end=160, fill="white", width=w)
    d.line((32 * s, 42 * s, 32 * s, 48 * s), fill="white", width=w)
    d.line((25 * s, 48 * s, 39 * s, 48 * s), fill="white", width=w)
    return img


if __name__ == "__main__":
    OUT.parent.mkdir(exist_ok=True)
    frames = [draw(s[0]) for s in SIZES]
    frames[-1].save(OUT, format="ICO", sizes=SIZES, append_images=frames[:-1])
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")
