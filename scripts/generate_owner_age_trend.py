from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "slide2_owner_age_distribution_trend.png"
FONT_REGULAR = ROOT / "backend" / "app" / "static" / "fonts" / "NotoSansKR-Regular.ttf"
FONT_BOLD = ROOT / "backend" / "app" / "static" / "fonts" / "NotoSansKR-Bold.ttf"

W, H = 2000, 1050
YEARS = [2005, 2010, 2015, 2020, 2025]
UNDER_40 = [17.9, 14.7, 9.0, 7.2, 5.5]
OVER_60 = [58.3, 60.9, 68.3, 73.3, 78.8]

CANVAS = "#FBFBF8"
INK = "#1B241D"
MUTE = "#9AA49B"
HAIR = "#E1E4DB"
PRIMARY = "#2E9E57"
WARN = "#C26B2E"
WHITE = "#FFFFFF"


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    path = FONT_BOLD if bold else FONT_REGULAR
    return ImageFont.truetype(str(path), size=size)


def text_size(draw: ImageDraw.ImageDraw, text: str, face: ImageFont.FreeTypeFont) -> tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=face)
    return box[2] - box[0], box[3] - box[1]


def draw_legend(draw: ImageDraw.ImageDraw, x: int, y: int, color: str, label: str) -> int:
    draw.line((x, y + 18, x + 54, y + 18), fill=color, width=7)
    draw.ellipse((x + 19, y + 7, x + 41, y + 29), fill=color, outline=WHITE, width=4)
    face = font(28, bold=True)
    draw.text((x + 70, y), label, font=face, fill=INK)
    width, _ = text_size(draw, label, face)
    return 70 + width


def main() -> None:
    image = Image.new("RGB", (W, H), CANVAS)
    draw = ImageDraw.Draw(image)

    left, right = 150, 1860
    top, bottom = 120, 900
    y_max = 90
    xs = [left + i * (right - left) / (len(YEARS) - 1) for i in range(len(YEARS))]

    def y_pos(value: float) -> float:
        return bottom - value / y_max * (bottom - top)

    draw.text((left, 40), "단위: %", font=font(25), fill=MUTE)
    first_width = draw_legend(draw, 740, 37, PRIMARY, "40대 이하")
    draw_legend(draw, 740 + first_width + 90, 37, WARN, "60대 이상")

    for tick in range(0, y_max + 1, 10):
        y = y_pos(tick)
        draw.line((left, y, right, y), fill=HAIR, width=2)
        label = str(tick)
        face = font(24)
        tw, th = text_size(draw, label, face)
        draw.text((left - 30 - tw, y - th / 2), label, font=face, fill=MUTE)

    draw.line((left, bottom, right, bottom), fill="#C7CDBF", width=3)
    for x, year in zip(xs, YEARS):
        label = str(year)
        face = font(26)
        tw, _ = text_size(draw, label, face)
        draw.text((x - tw / 2, bottom + 35), label, font=face, fill=MUTE)

    over_points = [(xs[i], y_pos(value)) for i, value in enumerate(OVER_60)]
    under_points = [(xs[i], y_pos(value)) for i, value in enumerate(UNDER_40)]
    draw.line(over_points, fill=WARN, width=8, joint="curve")
    draw.line(under_points, fill=PRIMARY, width=8, joint="curve")

    for points, values, color, labels_above in (
        (over_points, OVER_60, WARN, True),
        (under_points, UNDER_40, PRIMARY, False),
    ):
        for (x, y), value in zip(points, values):
            draw.ellipse((x - 18, y - 18, x + 18, y + 18), fill=CANVAS)
            draw.ellipse((x - 13, y - 13, x + 13, y + 13), fill=color)
            label = f"{value:.1f}%"
            face = font(27, bold=True)
            tw, th = text_size(draw, label, face)
            label_y = y - th - 30 if labels_above else y + 24
            draw.text((x - tw / 2, label_y), label, font=face, fill=INK)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    image.save(OUT, format="PNG", optimize=True, dpi=(180, 180))
    print(OUT)
    print(f"size={image.size}, mode={image.mode}")
    print(f"under_40={UNDER_40}")
    print(f"over_60={OVER_60}")


if __name__ == "__main__":
    main()
