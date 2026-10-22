"""Генерация иконки приложения и демонстрационного шаблона штампа."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
ASSETS.mkdir(exist_ok=True)

FONT_REGULAR = Path(r"C:\Windows\Fonts\segoeui.ttf")
FONT_BOLD = Path(r"C:\Windows\Fonts\segoeuib.ttf")
FONT_SEMIBOLD = Path(r"C:\Windows\Fonts\seguisb.ttf")


def font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    if path.exists():
        return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default(size=size)


def centered_text(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    text: str,
    fnt: ImageFont.FreeTypeFont,
    fill,
) -> None:
    left, top, right, bottom = box
    bbox = draw.textbbox((0, 0), text, font=fnt)
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    x = left + (right - left - width) / 2 - bbox[0]
    y = top + (bottom - top - height) / 2 - bbox[1]
    draw.text((x, y), text, font=fnt, fill=fill)


def make_icon(size: int = 512) -> Image.Image:
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # Тёмно-синяя скруглённая подложка.
    margin = round(size * 0.045)
    radius = round(size * 0.22)
    draw.rounded_rectangle(
        (margin, margin, size - margin, size - margin),
        radius=radius,
        fill=(15, 32, 55, 255),
    )
    # Лёгкий блик.
    draw.rounded_rectangle(
        (margin + 3, margin + 3, size - margin - 3, round(size * 0.52)),
        radius=radius - 3,
        fill=(23, 47, 79, 255),
    )

    # Лист документа.
    page = (
        round(size * 0.22),
        round(size * 0.14),
        round(size * 0.70),
        round(size * 0.86),
    )
    draw.rounded_rectangle(page, radius=round(size * 0.035), fill=(255, 255, 255, 255))
    # Загнутый уголок.
    fold = round(size * 0.13)
    draw.polygon(
        [
            (page[2] - fold, page[1]),
            (page[2], page[1] + fold),
            (page[2] - fold, page[1] + fold),
        ],
        fill=(213, 224, 238, 255),
    )
    # Строки текста.
    line_left = round(size * 0.28)
    line_right = round(size * 0.63)
    for index, width_factor in enumerate((1.0, 0.82, 0.93, 0.65)):
        y = round(size * (0.28 + index * 0.085))
        draw.rounded_rectangle(
            (line_left, y, line_left + (line_right - line_left) * width_factor, y + max(3, size // 85)),
            radius=3,
            fill=(44, 91, 155, 255),
        )

    # Красная печать в правом нижнем углу.
    cx, cy = round(size * 0.70), round(size * 0.69)
    r = round(size * 0.21)
    draw.ellipse(
        (cx - r, cy - r, cx + r, cy + r),
        outline=(224, 54, 64, 255),
        width=max(4, round(size * 0.022)),
    )
    draw.ellipse(
        (cx - r * 0.77, cy - r * 0.77, cx + r * 0.77, cy + r * 0.77),
        outline=(224, 54, 64, 255),
        width=max(2, round(size * 0.009)),
    )
    draw.arc(
        (cx - r * 0.58, cy - r * 0.58, cx + r * 0.58, cy + r * 0.58),
        start=200,
        end=340,
        fill=(224, 54, 64, 255),
        width=max(2, round(size * 0.009)),
    )
    # Звезда/галочка внутри.
    check = [
        (cx - r * 0.34, cy + r * 0.02),
        (cx - r * 0.08, cy + r * 0.28),
        (cx + r * 0.42, cy - r * 0.26),
    ]
    draw.line(check, fill=(224, 54, 64, 255), width=max(4, round(size * 0.032)), joint="curve")

    return image


def make_logo() -> Image.Image:
    image = make_icon(512)
    return image.resize((192, 192), Image.Resampling.LANCZOS)


def make_example_stamp() -> Image.Image:
    width, height = 1200, 760
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    ink = (28, 55, 96, 255)
    accent = (186, 45, 55, 255)
    thin = (70, 96, 132, 255)

    # Двойная рамка.
    draw.rounded_rectangle((18, 18, width - 18, height - 18), radius=28, outline=ink, width=9)
    draw.rounded_rectangle((40, 40, width - 40, height - 40), radius=18, outline=thin, width=3)

    f_small = font(FONT_SEMIBOLD, 46)
    f_title = font(FONT_BOLD, 94)
    f_mid = font(FONT_REGULAR, 61)
    f_bottom = font(FONT_SEMIBOLD, 44)

    centered_text(draw, (70, 66, width - 70, 150), "СОГЛАСОВАНО", f_small, ink)

    # Заголовок и декоративные линии вокруг подзаголовка.
    centered_text(draw, (70, 195, width - 70, 345), "В ПРОИЗВОДСТВЕ", f_title, ink)
    centered_text(draw, (70, 345, width - 70, 505), "РАБОТ", f_title, ink)
    centered_text(draw, (90, 505, width - 90, 585), "производственный штамп", f_mid, accent)

    draw.line((120, 630, width - 120, 630), fill=thin, width=3)
    centered_text(draw, (90, 650, width - 90, 720), "№ ____________     от ____________", f_bottom, ink)

    return image


def main() -> None:
    icon = make_icon(512)
    icon.save(ASSETS / "app_icon.png")
    icon.save(
        ASSETS / "app.ico",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    make_logo().save(ASSETS / "logo.png")
    make_example_stamp().save(ASSETS / "example_stamp.png")
    print("assets:", ", ".join(p.name for p in sorted(ASSETS.iterdir())))


if __name__ == "__main__":
    main()
