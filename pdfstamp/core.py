"""
Ядро приложения «Штампилятор».

Модуль не зависит от GUI и отвечает за:
  * чтение шаблона штампа и подготовку PNG с прозрачностью;
  * анализ видимого содержимого страниц PDF;
  * поиск свободного места, начиная с правого нижнего угла;
  * вставку изображения штампа с сохранением исходного PDF.
"""

from __future__ import annotations

import colorsys
import io
import math
import os
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import fitz  # PyMuPDF
import numpy as np
from PIL import Image, ImageColor, ImageOps

MM_TO_PT = 72.0 / 25.4
PT_TO_MM = 25.4 / 72.0

# Размер сетки занятости: 1 pt ≈ 0,35 мм.
_GRID_PT = 1.0
# Шаг перебора позиций: 2 pt ≈ 0,7 мм.
_STEP_PT = 2.0
# Максимальная сторона встроенного шаблона в пикселях.
_MAX_STAMP_PX = 2600
# Порог «белого» для необязательного удаления фона.
_WHITE_THRESHOLD = 244


_RU_COLORS = {
    "черный": "black",
    "чёрный": "black",
    "белый": "white",
    "красный": "red",
    "зеленый": "green",
    "зелёный": "green",
    "синий": "blue",
    "голубой": "deepskyblue",
    "желтый": "yellow",
    "жёлтый": "yellow",
    "серый": "gray",
    "оранжевый": "orange",
    "фиолетовый": "purple",
    "розовый": "pink",
    "коричневый": "brown",
    "бирюзовый": "turquoise",
}


def parse_color(value: str) -> tuple[int, int, int]:
    """Разбирает цвет в HTML/CSS, rgb(), hsl() и числовых форматах."""
    if value is None:
        raise StampError("Цвет текста не задан.")
    raw = str(value).strip().lower().replace("ё", "е")
    raw = _RU_COLORS.get(raw, raw)
    if not raw:
        raise StampError("Цвет текста не задан.")

    def component(part: str) -> int:
        part = part.strip()
        if part.endswith("%"):
            return max(0, min(255, round(float(part[:-1]) * 2.55)))
        return max(0, min(255, round(float(part))))

    match = re.fullmatch(r"rgba?\(([^)]*)\)", raw)
    if match:
        parts = [p for p in re.split(r"[,/\s]+", match.group(1).strip()) if p]
        if len(parts) < 3:
            raise StampError(f"Некорректный цвет: {value}")
        try:
            return tuple(component(p) for p in parts[:3])  # type: ignore[return-value]
        except (TypeError, ValueError) as exc:
            raise StampError(f"Некорректный цвет: {value}") from exc

    match = re.fullmatch(r"hsla?\(([^)]*)\)", raw)
    if match:
        parts = [p for p in re.split(r"[,/\s]+", match.group(1).strip()) if p]
        if len(parts) < 3:
            raise StampError(f"Некорректный цвет: {value}")
        try:
            hue = float(parts[0].rstrip("deg")) % 360.0
            saturation = float(parts[1].rstrip("%")) / 100.0
            lightness = float(parts[2].rstrip("%")) / 100.0
            rgb = colorsys.hls_to_rgb(hue / 360.0, lightness, saturation)
            return tuple(round(c * 255) for c in rgb)  # type: ignore[return-value]
        except (TypeError, ValueError) as exc:
            raise StampError(f"Некорректный цвет: {value}") from exc

    plain = re.fullmatch(r"\s*([0-9.]+)\s*[, ]\s*([0-9.]+)\s*[, ]\s*([0-9.]+)\s*", raw)
    if plain:
        try:
            return tuple(component(p) for p in plain.groups())  # type: ignore[return-value]
        except (TypeError, ValueError) as exc:
            raise StampError(f"Некорректный цвет: {value}") from exc

    if raw.startswith("0x"):
        raw = "#" + raw[2:]

    try:
        rgb = ImageColor.getrgb(raw)
    except (TypeError, ValueError) as exc:
        raise StampError(
            f"Некорректный цвет «{value}». Примеры: #000000, red, "
            "rgb(0,0,0), 0,0,0, hsl(0,100%,50%)."
        ) from exc
    if len(rgb) < 3:
        raise StampError(f"Некорректный цвет: {value}")
    return (int(rgb[0]), int(rgb[1]), int(rgb[2]))


class StampError(Exception):
    """Ожидаемая ошибка, которую можно показать пользователю."""


class CancelledError(StampError):
    """Обработка остановлена пользователем."""


@dataclass(frozen=True)
class StampOptions:
    width_mm: float = 60.0
    height_mm: float = 40.0
    margin_left_mm: float = 8.0
    margin_right_mm: float = 8.0
    margin_top_mm: float = 8.0
    margin_bottom_mm: float = 8.0
    clearance_mm: float = 3.0
    allow_overlap: bool = False
    ignore_title_block: bool = False
    add_text: bool = False
    text: str = ""
    text_gap_mm: float = 2.0
    text_font_size_pt: float = 9.0
    text_color: str = "#000000"
    remove_white_background: bool = False

    def validate(self) -> None:
        if not (0.5 <= self.width_mm <= 2000.0):
            raise StampError("Ширина штампа должна быть от 0,5 до 2000 мм.")
        if not (0.5 <= self.height_mm <= 2000.0):
            raise StampError("Высота штампа должна быть от 0,5 до 2000 мм.")
        for name, value in (
            ("слева", self.margin_left_mm),
            ("справа", self.margin_right_mm),
            ("сверху", self.margin_top_mm),
            ("снизу", self.margin_bottom_mm),
        ):
            if not (0.0 <= value <= 100.0):
                raise StampError(f"Отступ {name} должен быть от 0 до 100 мм.")
        if not (0.0 <= self.clearance_mm <= 100.0):
            raise StampError("Зазор до содержимого должен быть от 0 до 100 мм.")
        if self.add_text:
            text = self.text.strip()
            if not text:
                raise StampError("Введите текст под штампом.")
            if len(text) > 30:
                raise StampError(
                    "Текстовая строка должна быть не длиннее 30 символов."
                )
            if not (4.0 <= self.text_font_size_pt <= 72.0):
                raise StampError("Высота шрифта должна быть от 4 до 72 пт.")
            if not (0.0 <= self.text_gap_mm <= 50.0):
                raise StampError("Отступ текста от штампа — от 0 до 50 мм.")
            parse_color(self.text_color)


@dataclass(frozen=True)
class StampTemplate:
    path: Path
    png_bytes: bytes
    width_px: int
    height_px: int
    aspect: float  # ширина / высота


@dataclass(frozen=True)
class PdfInfo:
    path: Path
    page_count: int
    encrypted: bool
    needs_password: bool


@dataclass
class PagePlacement:
    page_number: int  # с единицы
    rect: fitz.Rect  # координаты видимой (повёрнутой) страницы
    overlap_ratio: float
    fallback: bool
    scaled: bool
    width_mm: float
    height_mm: float
    skipped: bool = False
    note: str = ""


@dataclass
class PdfResult:
    source: Path
    output: Path
    page_count: int
    placements: list[PagePlacement] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def fallback_pages(self) -> list[int]:
        return [p.page_number for p in self.placements if p.fallback]

    @property
    def scaled_pages(self) -> list[int]:
        return [p.page_number for p in self.placements if p.scaled]

    @property
    def skipped_pages(self) -> list[int]:
        return [p.page_number for p in self.placements if p.skipped]

    @property
    def stamped_pages(self) -> int:
        return sum(1 for p in self.placements if not p.skipped)


ProgressCallback = Callable[[int, int], None]
CancelCallback = Callable[[], bool]


def load_template(path: str | Path, remove_white_background: bool = False) -> StampTemplate:
    """Загружает шаблон, приводит его к RGBA и готовит PNG для PDF."""
    image_path = Path(path)
    if not image_path.is_file():
        raise StampError(f"Файл шаблона не найден:\n{image_path}")

    try:
        with Image.open(image_path) as source:
            source.load()
            image = ImageOps.exif_transpose(source)
            image = image.convert("RGBA")

            if remove_white_background:
                pixels = np.array(image, dtype=np.uint8)
                # Убираем именно почти белые пиксели, сохраняя цветные детали.
                rgb_min = pixels[:, :, :3].min(axis=2)
                mask = rgb_min >= _WHITE_THRESHOLD
                pixels[mask, 3] = 0
                image = Image.fromarray(pixels, mode="RGBA")

            # Ограничиваем разрешение: для штампа это не заметно, но PDF
            # остаётся компактным.
            width, height = image.size
            if max(width, height) > _MAX_STAMP_PX:
                ratio = _MAX_STAMP_PX / float(max(width, height))
                image = image.resize(
                    (max(1, round(width * ratio)), max(1, round(height * ratio))),
                    Image.Resampling.LANCZOS,
                )
                width, height = image.size

            if width <= 0 or height <= 0:
                raise StampError("Шаблон штампа пуст.")

            buffer = io.BytesIO()
            image.save(buffer, format="PNG", optimize=True)
            png_bytes = buffer.getvalue()
    except StampError:
        raise
    except Exception as exc:  # noqa: BLE001 - сообщение важно для пользователя
        raise StampError(
            f"Не удалось прочитать изображение шаблона:\n{image_path}\n\n{exc}"
        ) from exc

    return StampTemplate(
        path=image_path,
        png_bytes=png_bytes,
        width_px=width,
        height_px=height,
        aspect=width / float(height),
    )


def inspect_pdf(path: str | Path) -> PdfInfo:
    """Быстро проверяет PDF и возвращает число страниц."""
    pdf_path = Path(path)
    if not pdf_path.is_file():
        raise StampError(f"Файл не найден:\n{pdf_path}")
    try:
        document = fitz.open(pdf_path)
    except Exception as exc:  # noqa: BLE001
        raise StampError(f"Не удалось открыть PDF:\n{pdf_path}\n\n{exc}") from exc

    try:
        if not document.is_pdf:
            raise StampError(f"Файл не является PDF:\n{pdf_path}")
        needs_password = bool(document.needs_pass)
        encrypted = needs_password
        if needs_password and not document.authenticate(""):
            raise StampError(
                "PDF защищён паролем. Снимите защиту или сохраните копию без пароля."
            )
        return PdfInfo(
            path=pdf_path,
            page_count=document.page_count,
            encrypted=encrypted,
            needs_password=needs_password,
        )
    finally:
        document.close()


def build_output_path(
    source: str | Path,
    output_dir: str | Path | None = None,
    suffix: str = "_со_штампом",
) -> Path:
    """Подбирает свободное имя выходного PDF, чтобы не перезаписать файлы."""
    src = Path(source)
    folder = Path(output_dir) if output_dir else src.parent
    stem = f"{src.stem}{suffix}"
    candidate = folder / f"{stem}.pdf"
    counter = 2
    while candidate.exists():
        candidate = folder / f"{stem}_{counter}.pdf"
        counter += 1
    return candidate


def _find_arial_font() -> Path | None:
    """Ищет системный Arial (с запасными вариантами) для подписи под штампом."""
    windir = Path(os.environ.get("WINDIR", r"C:\Windows"))
    for name in ("arial.ttf", "segoeui.ttf", "DejaVuSans.ttf"):
        candidate = windir / "Fonts" / name
        if candidate.is_file():
            return candidate
    return None


def _caption_metrics(
    text: str, font: fitz.Font, font_size: float
) -> tuple[float, float]:
    if not text:
        return 0.0, 0.0
    width = float(font.text_length(text, font_size))
    height = float(font_size * max(1.0, font.ascender - font.descender))
    return width, height


def _insert_caption(
    page: fitz.Page,
    stamp_rect: fitz.Rect,
    text: str,
    font: fitz.Font,
    font_path: Path | None,
    font_size: float,
    gap_pt: float,
    color: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> None:
    """Вставляет строку по центру под штампом, с учётом поворота страницы."""
    text = text.strip()
    if not text:
        return
    width = float(font.text_length(text, font_size))
    x = stamp_rect.x0 + (stamp_rect.width - width) / 2.0
    y = stamp_rect.y1 + gap_pt + font.ascender * font_size
    point = fitz.Point(x, y)
    rotation = page.rotation
    if rotation:
        point = point * page.derotation_matrix
        page.set_rotation(0)
    try:
        page.insert_text(
            point,
            text,
            fontsize=font_size,
            fontname="ArialText" if font_path else "helv",
            fontfile=str(font_path) if font_path else None,
            color=color,
            overlay=True,
            rotate=rotation % 360,
        )
    finally:
        if rotation:
            page.set_rotation(rotation)


def _render_ink(page: fitz.Page, max_dim: float) -> tuple[np.ndarray, float, float]:
    """Рендерит видимую страницу и возвращает маску «есть краска».

    Геометрические bbox векторных путей для больших чертежей непригодны:
    рамка листа или длинная линия имеют bbox на всю страницу. Растровая маска
    учитывает только реально нарисованные пиксели.
    """
    zoom = min(1.5, 3200.0 / max(1.0, max_dim))
    zoom = max(0.25, zoom)
    pix = page.get_pixmap(
        matrix=fitz.Matrix(zoom, zoom),
        colorspace=fitz.csGRAY,
        alpha=False,
        annots=True,
    )
    raw = np.frombuffer(pix.samples, dtype=np.uint8)
    if pix.n == 1:
        gray = raw.reshape(pix.height, pix.width)
    else:
        gray = raw.reshape(pix.height, pix.width, pix.n)[:, :, :3].min(axis=2)
    ink = gray < 245
    return (
        ink,
        pix.width / max(0.001, page.rect.width),
        pix.height / max(0.001, page.rect.height),
    )


def _integral(mask: np.ndarray) -> np.ndarray:
    result = np.zeros((mask.shape[0] + 1, mask.shape[1] + 1), dtype=np.int32)
    result[1:, 1:] = mask.cumsum(axis=0).cumsum(axis=1)
    return result


def _query_areas(
    integral: np.ndarray,
    x0: np.ndarray,
    y0: np.ndarray,
    width_cells: int,
    height_cells: int,
) -> np.ndarray:
    x1 = x0 + width_cells
    y1 = y0 + height_cells
    return (
        integral[y1, x1]
        - integral[y0, x1]
        - integral[y1, x0]
        + integral[y0, x0]
    ).astype(np.float64)


def _ink_fraction(
    rect: fitz.Rect,
    ink: np.ndarray,
    scale_x: float,
    scale_y: float,
) -> float:
    height, width = ink.shape
    x0 = max(0, min(width, int(math.floor(rect.x0 * scale_x))))
    x1 = max(0, min(width, int(math.ceil(rect.x1 * scale_x))))
    y0 = max(0, min(height, int(math.floor(rect.y0 * scale_y))))
    y1 = max(0, min(height, int(math.ceil(rect.y1 * scale_y))))
    if x1 <= x0 or y1 <= y0:
        return 0.0
    return float(ink[y0:y1, x0:x1].mean())


def _title_block_rect(
    page_w: float,
    page_h: float,
    ink: np.ndarray,
    scale_x: float,
    scale_y: float,
) -> fitz.Rect | None:
    """Определяет стандартную зону основной надписи ГОСТ 2.104.

    Для чертежей это полоса 185×55 мм в правом нижнем углу, для текстовых
    документов — полоса высотой 40 мм по всей ширине листа. Зона учитывается
    только если в ней действительно есть изображение/линии.
    """
    mm = MM_TO_PT
    width_mm = page_w * PT_TO_MM
    height_mm = page_h * PT_TO_MM
    is_drawing = (
        width_mm * height_mm >= 420.0 * 297.0 * 0.85
        or min(width_mm, height_mm) >= 240.0
    )
    if is_drawing:
        rect = fitz.Rect(
            max(0.0, page_w - 190.0 * mm),
            max(0.0, page_h - 60.0 * mm),
            page_w,
            page_h,
        )
    else:
        rect = fitz.Rect(0.0, max(0.0, page_h - 45.0 * mm), page_w, page_h)

    if rect.width <= 1.0 or rect.height <= 1.0:
        return None
    if _ink_fraction(rect, ink, scale_x, scale_y) < 0.006:
        return None
    return rect


def _find_placement(
    page: fitz.Page,
    width_pt: float,
    height_pt: float,
    margin_left_pt: float,
    margin_right_pt: float,
    margin_top_pt: float,
    margin_bottom_pt: float,
    clearance_pt: float,
    allow_overlap: bool,
    ignore_title_block: bool,
    text_width_pt: float = 0.0,
    text_gap_pt: float = 0.0,
    text_height_pt: float = 0.0,
) -> PagePlacement:
    """Ищет положение штампа по пиксельной карте видимого содержимого."""
    page_rect = page.rect
    page_w = float(page_rect.width)
    page_h = float(page_rect.height)
    if page_w <= 2.0 or page_h <= 2.0:
        raise StampError("Страница PDF имеет нулевой размер.")

    left_margin = max(0.0, float(margin_left_pt))
    right_margin = max(0.0, float(margin_right_pt))
    top_margin = max(0.0, float(margin_top_pt))
    bottom_margin = max(0.0, float(margin_bottom_pt))

    left_margin = min(left_margin, page_w * 0.35)
    right_margin = min(right_margin, page_w * 0.35)
    top_margin = min(top_margin, page_h * 0.35)
    bottom_margin = min(bottom_margin, page_h * 0.35)
    if left_margin + right_margin >= page_w - 1.0:
        left_margin = right_margin = 0.0
    if top_margin + bottom_margin >= page_h - 1.0:
        top_margin = bottom_margin = 0.0

    available_w = page_w - left_margin - right_margin
    available_h = page_h - top_margin - bottom_margin
    if available_w <= 1.0 or available_h <= 1.0:
        left_margin = right_margin = top_margin = bottom_margin = 0.0
        available_w, available_h = page_w, page_h

    stamp_w = max(0.5, float(width_pt))
    stamp_h = max(0.5, float(height_pt))
    text_extra_h = (text_gap_pt + text_height_pt) if text_height_pt > 0 else 0.0
    scaled = False
    search_w = max(stamp_w, text_width_pt)
    search_h = stamp_h + text_extra_h
    if search_w > available_w or search_h > available_h:
        height_cap = max(0.5, available_h - text_extra_h)
        width_cap = max(0.5, available_w)
        scale = min(1.0, width_cap / max(0.5, stamp_w), height_cap / stamp_h)
        stamp_w = max(0.5, stamp_w * scale)
        stamp_h = max(0.5, stamp_h * scale)
        search_w = max(stamp_w, min(text_width_pt, available_w))
        search_h = stamp_h + text_extra_h
        scaled = True

    max_dim = max(page_w, page_h)
    ink, scale_x, scale_y = _render_ink(page, max_dim)
    pix_h, pix_w = ink.shape
    integral = _integral(ink.astype(np.uint8))

    title_block = (
        _title_block_rect(page_w, page_h, ink, scale_x, scale_y)
        if ignore_title_block
        else None
    )
    blocked = np.zeros((pix_h, pix_w), dtype=np.uint8)
    if title_block is not None:
        bx0 = max(0, min(pix_w, int(math.floor(title_block.x0 * scale_x))))
        bx1 = max(0, min(pix_w, int(math.ceil(title_block.x1 * scale_x))))
        by0 = max(0, min(pix_h, int(math.floor(title_block.y0 * scale_y))))
        by1 = max(0, min(pix_h, int(math.ceil(title_block.y1 * scale_y))))
        blocked[by0:by1, bx0:bx1] = 1
    blocked_integral = _integral(blocked)

    search_px_w = max(1, int(math.ceil(search_w * scale_x)))
    search_px_h = max(1, int(math.ceil(search_h * scale_y)))
    left_px = max(0, int(math.ceil(left_margin * scale_x)))
    right_px = max(0, int(math.ceil(right_margin * scale_x)))
    top_px = max(0, int(math.ceil(top_margin * scale_y)))
    bottom_px = max(0, int(math.ceil(bottom_margin * scale_y)))

    min_x = left_px
    max_x = pix_w - search_px_w - right_px
    min_y = top_px
    max_y = pix_h - search_px_h - bottom_px
    if max_x < min_x:
        min_x = 0
        max_x = max(0, pix_w - search_px_w)
    if max_y < min_y:
        min_y = 0
        max_y = max(0, pix_h - search_px_h)

    step_x = max(1, int(round(_STEP_PT * scale_x)))
    step_y = max(1, int(round(_STEP_PT * scale_y)))
    xs = np.arange(min_x, max_x + 1, step_x, dtype=np.int32)
    ys = np.arange(min_y, max_y + 1, step_y, dtype=np.int32)
    if xs.size == 0 or int(xs[-1]) != max_x:
        xs = np.append(xs, np.int32(max_x))
    if ys.size == 0 or int(ys[-1]) != max_y:
        ys = np.append(ys, np.int32(max_y))

    x0 = xs[None, :]
    y0 = ys[:, None]
    ink_areas = _query_areas(integral, x0, y0, search_px_w, search_px_h)
    blocked_areas = _query_areas(
        blocked_integral, x0, y0, search_px_w, search_px_h
    )

    clear_x = max(0, int(math.ceil(clearance_pt * scale_x)))
    clear_y = max(0, int(math.ceil(clearance_pt * scale_y)))
    cx0 = np.maximum(0, x0 - clear_x)
    cy0 = np.maximum(0, y0 - clear_y)
    cx1 = np.minimum(pix_w, x0 + search_px_w + clear_x)
    cy1 = np.minimum(pix_h, y0 + search_px_h + clear_y)
    clear_areas = (
        integral[cy1, cx1]
        - integral[cy0, cx1]
        - integral[cy1, cx0]
        + integral[cy0, cx0]
    ).astype(np.int64)

    point_x = x0.astype(np.float64) / scale_x
    point_y = y0.astype(np.float64) / scale_y
    right_slack = np.maximum(0.0, page_w - right_margin - (point_x + search_w))
    bottom_slack = np.maximum(0.0, page_h - bottom_margin - (point_y + search_h))
    distance2 = right_slack * right_slack + bottom_slack * bottom_slack

    allowed = blocked_areas <= 0.0
    ink_free = (ink_areas <= 0.0) & allowed
    clear_free = (clear_areas <= 0) & allowed
    skipped = False
    clearance_reduced = False

    if not allowed.any():
        skipped = True
        pool = allowed
    elif clear_free.any():
        pool = clear_free
    elif ink_free.any():
        pool = ink_free
        clearance_reduced = True
    elif allow_overlap:
        minimum = float(ink_areas[allowed].min())
        pool = (ink_areas <= minimum + 1e-6) & allowed
    else:
        skipped = True
        minimum = float(ink_areas[allowed].min())
        pool = (ink_areas <= minimum + 1e-6) & allowed

    score = np.where(pool, distance2, np.inf)
    index = np.unravel_index(int(np.argmin(score)), score.shape)
    row, col = index
    cell_x = int(xs[col])
    cell_y = int(ys[row])

    left = cell_x / scale_x
    top = cell_y / scale_y
    left = max(left_margin, min(left, page_w - right_margin - search_w))
    top = max(top_margin, min(top, page_h - bottom_margin - search_h))
    left = max(0.0, left)
    top = max(0.0, top)
    footprint = fitz.Rect(left, top, left + search_w, top + search_h)
    stamp_left = footprint.x0 + (search_w - stamp_w) / 2.0
    stamp_rect = fitz.Rect(
        stamp_left, footprint.y0, stamp_left + stamp_w, footprint.y0 + stamp_h
    )

    overlap = float(ink_areas[row, col]) / max(1.0, search_px_w * search_px_h)
    if not allow_overlap and overlap > 0.0:
        skipped = True

    width_mm = stamp_w * PT_TO_MM
    height_mm = stamp_h * PT_TO_MM
    notes: list[str] = []
    if scaled:
        notes.append(
            f"Размер уменьшен до {width_mm:.1f}×{height_mm:.1f} мм, "
            "чтобы штамп поместился на листе."
        )
    if skipped:
        if title_block is not None:
            notes.append(
                "Свободное место вне области основной надписи не найдено — "
                "страница оставлена без штампа."
            )
        else:
            notes.append(
                "Свободное место не найдено — страница оставлена без штампа. "
                "Включите «Разрешить частичное перекрытие содержимого», чтобы "
                "поставить штамп в точке с минимальным наложением."
            )
    elif allow_overlap and overlap > 0.0:
        notes.append(
            "Штамп размещён в точке с минимальным перекрытием содержимого "
            f"≈ {overlap * 100:.1f}%."
        )
    elif clearance_reduced:
        notes.append(
            "Свободное место найдено; заданный зазор до содержимого уменьшен."
        )
    else:
        notes.append("Свободное место найдено.")

    return PagePlacement(
        page_number=0,
        rect=stamp_rect,
        overlap_ratio=overlap,
        fallback=bool(not skipped and overlap > 0.0),
        scaled=scaled,
        width_mm=width_mm,
        height_mm=height_mm,
        skipped=skipped,
        note=" ".join(notes),
    )


def stamp_pdf(
    source: str | Path,
    output: str | Path,
    template: StampTemplate,
    options: StampOptions,
    progress: ProgressCallback | None = None,
    cancel: CancelCallback | None = None,
) -> PdfResult:
    """Добавляет штамп на каждую страницу PDF и сохраняет результат."""
    options.validate()
    source_path = Path(source)
    output_path = Path(output)
    if source_path.resolve() == output_path.resolve():
        raise StampError("Выходной файл не должен совпадать с исходным.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    document: fitz.Document | None = None
    temp_path: Path | None = None
    placements: list[PagePlacement] = []

    try:
        document = fitz.open(source_path)
        if not document.is_pdf:
            raise StampError(f"Файл не является PDF:\n{source_path}")
        if document.needs_pass and not document.authenticate(""):
            raise StampError("PDF защищён паролем — обработка невозможна.")
        if document.page_count <= 0:
            raise StampError("В PDF нет страниц.")

        total = document.page_count
        width_pt = options.width_mm * MM_TO_PT
        height_pt = options.height_mm * MM_TO_PT
        margin_left_pt = options.margin_left_mm * MM_TO_PT
        margin_right_pt = options.margin_right_mm * MM_TO_PT
        margin_top_pt = options.margin_top_mm * MM_TO_PT
        margin_bottom_pt = options.margin_bottom_mm * MM_TO_PT
        clearance_pt = options.clearance_mm * MM_TO_PT

        caption_text = options.text.strip() if options.add_text else ""
        caption_font_path = _find_arial_font()
        try:
            caption_font = (
                fitz.Font(fontfile=str(caption_font_path))
                if caption_font_path
                else fitz.Font("helv")
            )
        except Exception:  # noqa: BLE001
            caption_font_path = None
            caption_font = fitz.Font("helv")
        caption_width, caption_height = _caption_metrics(
            caption_text, caption_font, options.text_font_size_pt
        )
        caption_gap_pt = options.text_gap_mm * MM_TO_PT
        caption_color = (
            tuple(c / 255.0 for c in parse_color(options.text_color))
            if caption_text
            else (0.0, 0.0, 0.0)
        )

        for index, page in enumerate(document):
            if cancel and cancel():
                raise CancelledError("Обработка отменена.")

            placement = _find_placement(
                page,
                width_pt,
                height_pt,
                margin_left_pt,
                margin_right_pt,
                margin_top_pt,
                margin_bottom_pt,
                clearance_pt,
                options.allow_overlap,
                options.ignore_title_block,
                caption_width,
                caption_gap_pt,
                caption_height,
            )
            placement.page_number = index + 1

            if not placement.skipped:
                # Прямоугольник найден в видимой системе. insert_image ожидает
                # систему координат страницы без /Rotate, поэтому возвращаемся
                # назад. Поворот страницы временно снимаем: так PyMuPDF корректно
                # обрабатывает и ненулевой /Rotate, и смещённый /CropBox.
                rotation = page.rotation
                pdf_rect = (
                    placement.rect * page.derotation_matrix
                    if rotation
                    else placement.rect
                )
                if rotation:
                    page.set_rotation(0)
                try:
                    page.insert_image(
                        pdf_rect,
                        stream=template.png_bytes,
                        overlay=True,
                        rotate=rotation % 360,
                        keep_proportion=False,
                    )
                finally:
                    if rotation:
                        page.set_rotation(rotation)
                if caption_text:
                    _insert_caption(
                        page,
                        placement.rect,
                        caption_text,
                        caption_font,
                        caption_font_path,
                        options.text_font_size_pt,
                        caption_gap_pt,
                        caption_color,
                    )
            placements.append(placement)

            if progress:
                progress(index + 1, total)

        if cancel and cancel():
            raise CancelledError("Обработка отменена.")

        temp_path = output_path.with_name(
            f".{output_path.stem}.{uuid.uuid4().hex}.tmp.pdf"
        )
        document.save(
            temp_path,
            garbage=3,
            deflate=True,
            clean=False,
            deflate_images=False,
            deflate_fonts=True,
        )
        document.close()
        document = None
        os.replace(temp_path, output_path)
        temp_path = None
    except CancelledError:
        raise
    except StampError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise StampError(f"Ошибка обработки «{source_path.name}»:\n{exc}") from exc
    finally:
        if document is not None:
            try:
                document.close()
            except Exception:  # noqa: BLE001
                pass
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass

    warnings: list[str] = []
    fallback_pages = [p.page_number for p in placements if p.fallback]
    scaled_pages = [p.page_number for p in placements if p.scaled]
    skipped_pages = [p.page_number for p in placements if p.skipped]
    if skipped_pages:
        warnings.append(
            "Страницы без штампа (нет свободного места): "
            + _format_pages(skipped_pages)
        )
    if fallback_pages:
        warnings.append(
            "Страницы с перекрытием содержимого: "
            + _format_pages(fallback_pages)
        )
    if scaled_pages:
        warnings.append(
            "Страницы, где штамп уменьшен: " + _format_pages(scaled_pages)
        )

    return PdfResult(
        source=source_path,
        output=output_path,
        page_count=len(placements),
        placements=placements,
        warnings=warnings,
    )


def _format_pages(pages: list[int], limit: int = 12) -> str:
    if len(pages) <= limit:
        return ", ".join(str(p) for p in pages)
    return ", ".join(str(p) for p in pages[:limit]) + f" … (всего {len(pages)})"
