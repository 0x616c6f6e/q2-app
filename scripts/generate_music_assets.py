"""Generate original geometric artwork and controls; requires Pillow, no external artwork/fonts."""

from pathlib import Path
from PIL import Image, ImageDraw

DEST = Path(__file__).resolve().parents[1] / "apps/music-player/assets"
INK = "#f1e8d5"
ACCENT = "#f0aa70"


def asset(name, size, paint):
    """Supersample simple vector geometry to keep small controls smooth."""
    scale = 4
    image = Image.new("RGBA", (size[0] * scale, size[1] * scale))
    draw = ImageDraw.Draw(image)

    class Pen:
        def line(self, xy, fill=INK, width=2):
            draw.line([(x * scale, y * scale) for x, y in xy], fill=fill, width=width * scale)

        def box(self, xy, fill, radius=0, outline=None, width=1):
            draw.rounded_rectangle(
                tuple(v * scale for v in xy), radius * scale, fill=fill, outline=outline, width=width * scale
            )

        def circle(self, xy, fill=None, outline=None, width=1):
            draw.ellipse(tuple(v * scale for v in xy), fill=fill, outline=outline, width=width * scale)

        def poly(self, xy, fill=INK):
            draw.polygon([(x * scale, y * scale) for x, y in xy], fill=fill)

    paint(Pen())
    image.resize(size, Image.Resampling.LANCZOS).save(DEST / (name + ".png"))


def cover(p, variant):
    colors = [
        ("#293e39", "#bd815c", "#edc39a"),
        ("#203b52", "#648b9f", "#d4e3d9"),
        ("#40394e", "#b18c9a", "#f1d1ad"),
    ][variant]
    p.box((0, 0, 255, 255), colors[0], 24)
    # Original imaginary album covers: sunset, tidal rings and midnight geometry.
    p.circle((120, 30, 218, 128), colors[2])
    for i in range(9):
        y = 126 + i * 14
        p.line([(0, y + 35), (80, y - variant * 9), (160, y + 12), (256, y - 40)], colors[1], 2)
    p.line([(22, 28), (76, 28)], INK, 3)
    p.circle((84, 25, 90, 31), ACCENT)
    p.line([(22, 229), (232, 229)], colors[2], 1)


def control(p, name):
    active = name in ("play", "pause")
    p.circle((1, 1, 63, 63), ACCENT if active else "#1b2927")
    color = "#172420" if active else INK
    if name == "play":
        p.poly([(26, 20), (26, 44), (44, 32)], color)
    elif name == "pause":
        p.box((23, 21, 28, 43), color, 1)
        p.box((36, 21, 41, 43), color, 1)
    elif name in ("prev", "next"):
        points = [(40, 21), (40, 43), (24, 32)]
        if name == "next":
            points = [(64 - x, y) for x, y in points]
        p.poly(points, color)
        x = 21 if name == "prev" else 43
        p.line([(x, 21), (x, 43)], color, 3)
    elif name == "back":
        p.line([(37, 21), (26, 32), (37, 43)], color, 3)
    elif name == "more":
        for x in (22, 32, 42):
            p.circle((x - 2, 30, x + 2, 34), color)
    elif name in ("heart", "heart-on"):
        c = ACCENT if name == "heart-on" else color
        p.poly(
            [
                (19, 26),
                (22, 21),
                (28, 21),
                (32, 26),
                (36, 21),
                (42, 21),
                (45, 26),
                (43, 33),
                (32, 44),
                (21, 33),
            ],
            c,
        )
        if name == "heart":
            p.poly(
                [(23, 27), (26, 25), (32, 31), (38, 25), (41, 27), (39, 32), (32, 39), (25, 32)], "#1b2927"
            )
    elif name in ("queue", "library", "lyrics"):
        for y, end in ((23, 43), (32, 39), (41, 35)):
            p.line([(23, y), (end, y)], color, 2)
            if name != "lyrics":
                p.circle((17, y - 1, 19, y + 1), ACCENT)
    elif name == "repeat":
        p.line([(22, 27), (42, 27), (38, 22)], color, 2)
        p.line([(42, 37), (22, 37), (26, 42)], color, 2)
    elif name == "shuffle":
        p.line([(20, 24), (25, 24), (39, 40), (44, 40), (40, 35)], color, 2)
        p.line([(20, 40), (25, 40), (39, 24), (44, 24), (40, 19)], color, 2)
    elif name in ("plus", "minus"):
        p.line([(22, 32), (42, 32)], color, 2)
        if name == "plus":
            p.line([(32, 22), (32, 42)], color, 2)


def main():
    DEST.mkdir(parents=True, exist_ok=True)
    for index in range(3):
        asset("cover-" + str(index + 1), (256, 256), lambda p, i=index: cover(p, i))
    for name in (
        "play",
        "pause",
        "prev",
        "next",
        "back",
        "more",
        "heart",
        "heart-on",
        "queue",
        "library",
        "lyrics",
        "repeat",
        "shuffle",
        "plus",
        "minus",
    ):
        asset(name, (64, 64), lambda p, n=name: control(p, n))
    asset("rail", (512, 8), lambda p: p.box((0, 0, 511, 7), "#34423c", 3))
    asset("fill", (512, 8), lambda p: p.box((0, 0, 511, 7), ACCENT, 3))
    asset("row", (512, 88), lambda p: p.box((0, 0, 511, 87), "#1b2927", 14))

    def icon(p):
        p.box((0, 0, 127, 127), "#263d35", 30)
        for r in (42, 34, 26):
            p.circle((64 - r, 64 - r, 64 + r, 64 + r), outline="#516b59")
        p.circle((47, 47, 81, 81), ACCENT)
        p.circle((60, 60, 68, 68), "#172420")
        p.line([(91, 25), (91, 72), (81, 82)], INK, 4)

    asset("icon", (128, 128), icon)


if __name__ == "__main__":
    main()
