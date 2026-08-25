"""
Generates assets/icon.ico for Video Analyzer.

Run:  python assets/make_icon.py

Drawn at 1024px and downsampled to each icon size, so the small sizes stay
crisp. Re-run this if the icon ever needs changing - do not hand-edit the .ico.
"""

from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 1024
OUT = Path(__file__).parent / "icon.ico"
ICO_SIZES = [256, 128, 64, 48, 32, 24, 16]

# Palette
TOP = (99, 102, 241)        # indigo-500
BOTTOM = (124, 58, 237)     # violet-600
WHITE = (255, 255, 255, 255)
AMBER = (251, 191, 36, 255)
INK = (30, 27, 75, 255)     # indigo-950, for the lens


def gradient_background():
    """Vertical indigo-to-violet gradient, clipped to a rounded square."""
    base = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    grad = Image.new("RGBA", (SIZE, SIZE))
    painter = ImageDraw.Draw(grad)
    for y in range(SIZE):
        t = y / (SIZE - 1)
        painter.line(
            [(0, y), (SIZE, y)],
            fill=(
                round(TOP[0] + (BOTTOM[0] - TOP[0]) * t),
                round(TOP[1] + (BOTTOM[1] - TOP[1]) * t),
                round(TOP[2] + (BOTTOM[2] - TOP[2]) * t),
                255,
            ),
        )
    mask = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, SIZE - 1, SIZE - 1], radius=int(SIZE * 0.22), fill=255
    )
    base.paste(grad, (0, 0), mask)
    return base


def draw_sprockets(painter):
    """Film-strip perforations along the top and bottom - reads as 'video'."""
    hole_w, hole_h = int(SIZE * 0.082), int(SIZE * 0.058)
    radius = int(hole_h * 0.32)
    margin = int(SIZE * 0.072)
    count = 5
    gap = (SIZE - 2 * margin - count * hole_w) / (count - 1)
    for i in range(count):
        x = margin + i * (hole_w + gap)
        for y in (int(SIZE * 0.088), int(SIZE * 0.854)):
            painter.rounded_rectangle(
                [x, y, x + hole_w, y + hole_h], radius=radius, fill=WHITE
            )


def draw_play(painter):
    """Centre play triangle, nudged right so it reads as centred by eye."""
    cx, cy = SIZE * 0.425, SIZE * 0.455
    r = SIZE * 0.200
    painter.polygon(
        [
            (cx - r * 0.72, cy - r),
            (cx - r * 0.72, cy + r),
            (cx + r * 0.98, cy),
        ],
        fill=WHITE,
    )


def draw_magnifier(layer):
    """Amber magnifying glass, bottom-right - the 'analyzer' half of the name."""
    painter = ImageDraw.Draw(layer)
    cx, cy = SIZE * 0.650, SIZE * 0.605
    r = SIZE * 0.140
    ring = int(SIZE * 0.054)

    # Handle first, so the ring sits on top of it. Kept short so the tip stays
    # clear of the rounded corner and the bottom sprocket row.
    hx, hy = cx + r * 0.72, cy + r * 0.72
    tip = SIZE * 0.070
    painter.line(
        [(hx, hy), (hx + tip, hy + tip)],
        fill=AMBER, width=int(SIZE * 0.060),
    )

    # Dark lens so the ring never blends into the play triangle behind it.
    painter.ellipse([cx - r, cy - r, cx + r, cy + r], fill=INK)
    painter.ellipse(
        [cx - r, cy - r, cx + r, cy + r], outline=AMBER, width=ring
    )


def build():
    icon = gradient_background()
    painter = ImageDraw.Draw(icon)
    draw_sprockets(painter)
    draw_play(painter)

    glass = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw_magnifier(glass)
    icon = Image.alpha_composite(icon, glass)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    icon.save(OUT, format="ICO", sizes=[(s, s) for s in ICO_SIZES])

    preview = Path(__file__).parent / "icon-preview.png"
    icon.resize((512, 512), Image.LANCZOS).save(preview)
    print(f"wrote {OUT}")
    print(f"wrote {preview}")


if __name__ == "__main__":
    build()
