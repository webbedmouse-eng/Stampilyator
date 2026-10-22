"""Генерация PDF-примеров для проверки приложения."""

from __future__ import annotations

from pathlib import Path

import fitz
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

FONT_DIR = Path(r"C:\Windows\Fonts")
pdfmetrics.registerFont(TTFont("Arial", str(FONT_DIR / "arial.ttf")))
pdfmetrics.registerFont(TTFont("Arial-Bold", str(FONT_DIR / "arialbd.ttf")))

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "tests" / "samples"


def _header_footer(c: canvas.Canvas, width: float, height: float, title: str) -> None:
    c.setFillColorRGB(0.08, 0.16, 0.28)
    c.setFont("Arial-Bold", 14)
    c.drawString(22 * mm, height - 22 * mm, title)
    c.setStrokeColorRGB(0.65, 0.70, 0.78)
    c.setLineWidth(0.6)
    c.line(22 * mm, height - 27 * mm, width - 22 * mm, height - 27 * mm)
    c.setFont("Arial", 8)
    c.setFillColorRGB(0.35, 0.40, 0.48)
    c.drawString(22 * mm, 12 * mm, "Документ сформирован автоматически · тестовый пример")
    c.drawRightString(width - 22 * mm, 12 * mm, "Стр. 1")


def text_document(path: Path) -> None:
    width, height = A4
    c = canvas.Canvas(str(path), pagesize=A4)
    _header_footer(c, width, height, "АКТ О ПРИЁМКЕ РАБОТ")
    c.setFillColorRGB(0.1, 0.1, 0.1)
    c.setFont("Arial", 10)
    body = [
        "Объект: производственное здание, корпус № 1.",
        "Основание: договор подряда № 14/2026 от 12.01.2026.",
        "Работы выполнены в полном объёме и соответствуют проекту.",
        "",
        "Перечень выполненных работ:",
        "1. Устройство фундаментной плиты — 148 м².",
        "2. Монтаж металлокаркаса — 12,4 т.",
        "3. Устройство кровли — 310 м².",
        "",
        "Замечания: не выявлены.",
        "Срок выполнения: 15.02.2026 – 28.03.2026.",
    ]
    y = height - 42 * mm
    for line in body:
        c.drawString(24 * mm, y, line)
        y -= 7 * mm
    # Подписи слева, правая нижняя часть листа остаётся свободной.
    c.setFont("Arial-Bold", 10)
    c.drawString(24 * mm, 60 * mm, "Сдал:")
    c.drawString(24 * mm, 45 * mm, "Принял:")
    c.setFont("Arial", 9)
    c.drawString(45 * mm, 60 * mm, "________________ / Иванов И.И. /")
    c.drawString(45 * mm, 45 * mm, "________________ / Петров П.П. /")
    c.save()


def dense_document(path: Path) -> None:
    width, height = A4
    c = canvas.Canvas(str(path), pagesize=A4)
    _header_footer(c, width, height, "ВЕДОМОСТЬ ИСПОЛНИТЕЛЬНОЙ ДОКУМЕНТАЦИИ")
    # Таблица почти на весь лист.
    rows, cols = 24, 4
    left, top = 18 * mm, height - 34 * mm
    table_w = width - 36 * mm
    table_h = height - 55 * mm
    col_w = table_w / cols
    row_h = table_h / rows
    c.setStrokeColorRGB(0.15, 0.2, 0.28)
    c.setLineWidth(0.5)
    for row in range(rows + 1):
        y = top - row * row_h
        c.line(left, y, left + table_w, y)
    for col in range(cols + 1):
        x = left + col * col_w
        c.line(x, top, x, top - table_h)
    c.setFont("Arial", 7)
    c.setFillColorRGB(0.1, 0.1, 0.1)
    for row in range(rows):
        for col in range(cols):
            c.drawString(
                left + col * col_w + 2,
                top - (row + 1) * row_h + 5,
                f"Поз. {row + 1}.{col + 1}",
            )
    c.save()


def blank_document(path: Path) -> None:
    c = canvas.Canvas(str(path), pagesize=A4)
    c.setFillColorRGB(1, 1, 1)
    c.rect(0, 0, A4[0], A4[1], fill=1, stroke=0)
    c.save()


def rotated_document(path: Path) -> None:
    width, height = A4
    c = canvas.Canvas(str(path), pagesize=A4)
    _header_footer(c, width, height, "АКТ ОСВИДЕТЕЛЬСТВОВАНИЯ")
    c.setFillColorRGB(0.1, 0.1, 0.1)
    c.setFont("Arial", 10)
    for i in range(10):
        c.drawString(24 * mm, height - 45 * mm - i * 7 * mm, f"Строка содержания {i + 1}")
    c.save()

    document = fitz.open(path)
    document[0].set_rotation(90)
    document.saveIncr()
    document.close()


def photo_document(path: Path) -> None:
    width, height = A4
    c = canvas.Canvas(str(path), pagesize=A4)
    _header_footer(c, width, height, "ФОТООТЧЁТ")
    # Имитация фотографии в верхней половине.
    c.setFillColorRGB(0.35, 0.48, 0.62)
    c.rect(45 * mm, height - 150 * mm, width - 90 * mm, 95 * mm, fill=1, stroke=0)
    c.setFillColorRGB(0.95, 0.8, 0.35)
    c.circle(width / 2, height - 102 * mm, 18 * mm, fill=1, stroke=0)
    c.setFillColorRGB(0.1, 0.1, 0.1)
    c.setFont("Arial", 9)
    c.drawString(24 * mm, 55 * mm, "Фотофиксация выполненных работ.")
    c.save()


def multi_page(path: Path) -> None:
    width, height = A4
    c = canvas.Canvas(str(path), pagesize=A4)
    for page in range(1, 5):
        _header_footer(c, width, height, f"ПРИЛОЖЕНИЕ · ЛИСТ {page}")
        c.setFillColorRGB(0.1, 0.1, 0.1)
        c.setFont("Arial", 10)
        for i in range(8 + page):
            c.drawString(24 * mm, height - 45 * mm - i * 7 * mm, f"Пункт {page}.{i + 1}")
        c.showPage()
    c.save()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    text_document(OUT / "text_document.pdf")
    dense_document(OUT / "dense_document.pdf")
    blank_document(OUT / "blank_document.pdf")
    rotated_document(OUT / "rotated_document.pdf")
    photo_document(OUT / "photo_document.pdf")
    multi_page(OUT / "multi_page.pdf")
    print("samples:", ", ".join(p.name for p in sorted(OUT.glob("*.pdf"))))


if __name__ == "__main__":
    main()
