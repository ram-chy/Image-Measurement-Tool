"""
Generates assets/app.ico — the application / installer icon.

Run with:  python assets/make_icon.py
"""

from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 1024
OUT = Path(__file__).resolve().parent / "app.ico"


def _rounded_mask(size: int, radius: int) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, size - 1, size - 1), radius=radius, fill=255
    )
    return mask


def build() -> Image.Image:
    # ── Blue gradient background ─────────────────────────────────────────────
    top, bottom = (25, 118, 210), (13, 71, 161)   # #1976D2 → #0D47A1
    bg = Image.new("RGB", (SIZE, SIZE))
    draw = ImageDraw.Draw(bg)
    for y in range(SIZE):
        t = y / (SIZE - 1)
        draw.line(
            [(0, y), (SIZE, y)],
            fill=tuple(round(a + (b - a) * t) for a, b in zip(top, bottom)),
        )

    icon = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    icon.paste(bg, (0, 0), _rounded_mask(SIZE, 210))

    d = ImageDraw.Draw(icon)

    # ── White "photo" card ───────────────────────────────────────────────────
    card = (190, 165, 834, 645)
    d.rounded_rectangle(card, radius=52, fill=(255, 255, 255, 255))

    # sun
    d.ellipse((660, 250, 770, 360), fill=(255, 179, 0, 255))

    # mountains (kept inside the card)
    d.polygon(
        [(240, 620), (420, 405), (560, 620)],
        fill=(66, 165, 245, 255),
    )
    d.polygon(
        [(470, 620), (640, 430), (790, 620)],
        fill=(21, 101, 192, 255),
    )

    # ── Amber ruler strip ────────────────────────────────────────────────────
    ruler = (140, 700, 884, 862)
    d.rounded_rectangle(ruler, radius=42, fill=(255, 193, 7, 255))

    x = 190
    i = 0
    while x <= 834:
        length = 46 if i % 2 == 0 else 28
        d.rounded_rectangle(
            (x - 6, 712, x + 6, 712 + length),
            radius=6,
            fill=(78, 52, 46, 255),
        )
        x += 52
        i += 1

    return icon


def main():
    master = build()
    sizes = [16, 24, 32, 48, 64, 128, 256]
    master.save(OUT, format="ICO", sizes=[(s, s) for s in sizes])
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
