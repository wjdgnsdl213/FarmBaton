from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "slide2_owner_age_distribution_trend.png"
FONT_REGULAR = ROOT / "backend" / "app" / "static" / "fonts" / "NotoSansKR-Regular.ttf"
FONT_BOLD = ROOT / "backend" / "app" / "static" / "fonts" / "NotoSansKR-Bold.ttf"

W, H = 2400, 1350
YEARS = [2005, 2010, 2015, 2020, 2025]
UNDER_40 = [17.9, 14.7, 9.0, 7.2, 5.5]
OVER_60 = [58.3, 60.9, 68.3, 73.3, 78.8]

CANVAS = "#FBFBF8"
INK = "#1B241D"
BODY = "#66706A"
MUTE = "#9AA49B"
HAIR = "#E1E4DB"
PRIMARY = "#2E9E57"
PRIMARY_DEEP = "#1F8047"
WARN = "#C26B2E"
WARN_DEEP = "#92400E"
FOREST = "#13301C"
WHITE = "#FFFFFF"


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_BOLD if bold else FONT_REGULAR), size=size)


def text_size(draw: ImageDraw.ImageDraw, text: str, face: ImageFont.FreeTypeFont) -> tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=face)
    return box[2] - box[0], box[3] - box[1]


def pill(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, color: str) -> None:
    face = font(29, bold=True)
    tw, th = text_size(draw, text, face)
    x, y = xy
    draw.rounded_rectangle((x, y, x + tw + 54, y + th + 30), radius=18, fill=color)
    draw.text((x + 27, y + 11), text, font=face, fill=WHITE)


def main() -> None:
    image = Image.new("RGB", (W, H), CANVAS)
    draw = ImageDraw.Draw(image)

    # Header
    draw.text((130, 92), "경영주 고령화 추세", font=font(29, bold=True), fill=PRIMARY)
    draw.text((130, 145), "농가 경영주의 고령화, 20년 추이", font=font(65, bold=True), fill=INK)
    draw.text(
        (130, 235),
        "40대 이하 비중은 줄고, 60대 이상 비중은 빠르게 늘었습니다",
        font=font(31),
        fill=BODY,
    )

    # FarmBaton wordmark treatment, kept understated for PPT use.
    brand = "FarmBaton"
    brand_face = font(36, bold=True)
    bw, _ = text_size(draw, brand, brand_face)
    draw.rounded_rectangle((W - 130 - bw - 52, 92, W - 130, 156), radius=18, fill=FOREST)
    draw.text((W - 130 - bw - 26, 99), brand, font=brand_face, fill=WHITE)

    # Plot geometry
    left, right = 230, 2145
    top, bottom = 390, 1100
    y_max = 90
    xs = [left + i * (right - left) / (len(YEARS) - 1) for i in range(len(YEARS))]

    def y_pos(value: float) -> float:
        return bottom - value / y_max * (bottom - top)

    # Grid and axes
    for tick in range(0, y_max + 1, 10):
        y = y_pos(tick)
        draw.line((left, y, right, y), fill=HAIR, width=2)
        label = f"{tick}"
        tw, th = text_size(draw, label, font(24))
        draw.text((left - 34 - tw, y - th / 2), label, font=font(24), fill=MUTE)

    draw.text((left - 115, top - 66), "단위: %", font=font(24), fill=MUTE)
    draw.line((left, bottom, right, bottom), fill="#C7CDBF", width=3)

    for x, year in zip(xs, YEARS):
        label = str(year)
        tw, _ = text_size(draw, label, font(26, bold=year == 2025))
        draw.text((x - tw / 2, bottom + 35), label, font=font(26, bold=year == 2025), fill=INK if year == 2025 else MUTE)

    # Subtle area fills
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    over_points = [(xs[i], y_pos(v)) for i, v in enumerate(OVER_60)]
    under_points = [(xs[i], y_pos(v)) for i, v in enumerate(UNDER_40)]
    od.polygon(over_points + [(right, bottom), (left, bottom)], fill=(194, 107, 46, 16))
    od.polygon(under_points + [(right, bottom), (left, bottom)], fill=(46, 158, 87, 14))
    image = Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(image)

    # Series lines
    draw.line(over_points, fill=WARN, width=8, joint="curve")
    draw.line(under_points, fill=PRIMARY, width=8, joint="curve")

    for points, values, color in (
        (over_points, OVER_60, WARN, ),
        (under_points, UNDER_40, PRIMARY, ),
    ):
        for i, ((x, y), value) in enumerate(zip(points, values)):
            radius = 14 if i < len(points) - 1 else 19
            draw.ellipse((x - radius - 5, y - radius - 5, x + radius + 5, y + radius + 5), fill=CANVAS)
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color)
            value_text = f"{value:.1f}%"
            face = font(29, bold=i in (0, len(points) - 1))
            tw, th = text_size(draw, value_text, face)
            if values is OVER_60:
                ty = y - 57 - th
            else:
                ty = y + 36
            draw.text((x - tw / 2, ty), value_text, font=face, fill=INK)

    # Direct labels and deterministic 20-year percentage-point changes.
    over_change = OVER_60[-1] - OVER_60[0]
    under_change = UNDER_40[-1] - UNDER_40[0]
    pill(draw, (right - 350, y_pos(OVER_60[-1]) - 138), "60대 이상", WARN_DEEP)
    draw.text(
        (right - 118, y_pos(OVER_60[-1]) - 70),
        f"+{over_change:.1f}%p",
        font=font(31, bold=True),
        fill=WARN_DEEP,
        anchor="ra",
    )
    pill(draw, (right - 370, y_pos(UNDER_40[-1]) - 158), "40대 이하", PRIMARY_DEEP)
    draw.text(
        (right - 118, y_pos(UNDER_40[-1]) - 90),
        f"{under_change:.1f}%p",
        font=font(31, bold=True),
        fill=PRIMARY_DEEP,
        anchor="ra",
    )

    # Footer/source
    draw.line((130, 1240, W - 130, 1240), fill=HAIR, width=2)
    draw.text(
        (130, 1266),
        "자료: 사용자 제공 통계표 · 농가 경영주 연령 분포(2005~2025)",
        font=font(22),
        fill=MUTE,
    )
    draw.text((W - 130, 1266), "FarmBaton", font=font(22, bold=True), fill=FOREST, anchor="ra")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    image.save(OUT, format="PNG", optimize=True, dpi=(180, 180))
    print(OUT)
    print(f"size={image.size}, mode={image.mode}")
    print(f"over_60_change={over_change:.1f}%p, under_40_change={under_change:.1f}%p")


if __name__ == "__main__":
    main()
