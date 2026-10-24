"""Редактор собственного штампа: рамка, строки, шрифт, подписи и сохранение PNG."""

from __future__ import annotations

import math
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QImage,
    QPainter,
    QPen,
    QPolygonF,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFontComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .core import StampError, parse_color

MM_PER_INCH = 25.4
MAX_WIDTH_MM = 100.0
MAX_HEIGHT_MM = 70.0
MIN_WIDTH_MM = 10.0
MIN_HEIGHT_MM = 10.0
DEFAULT_INK = "#332A7A"
DEFAULT_FONT = "Arial"
DEFAULT_FONT_SIZE_PT = 14.0


def application_dir() -> Path:
    """Каталог рядом с EXE (в исходниках — корень проекта)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


@dataclass(slots=True)
class TextLine:
    text: str = ""
    font_family: str = DEFAULT_FONT
    font_size_pt: float = DEFAULT_FONT_SIZE_PT
    bold: bool = False
    italic: bool = False
    underline: bool = False
    alignment: str = "center"


@dataclass(slots=True)
class SignatureImage:
    """Рукописная подпись: положение и размеры в миллиметрах поля."""

    image: QImage
    x_mm: float
    y_mm: float
    width_mm: float
    height_mm: float
    rotation_deg: float = 0.0


@dataclass(slots=True)
class StampDesign:
    width_mm: float = MAX_WIDTH_MM
    height_mm: float = MAX_HEIGHT_MM
    ink_color: str = DEFAULT_INK
    border_mm: float = 1.0
    padding_mm: float = 4.0
    lines: list[TextLine | str] = field(
        default_factory=lambda: [TextLine(text="СОГЛАСОВАНО")]
    )
    signature: SignatureImage | None = None


def _px(mm: float, dpi: float) -> float:
    return mm / MM_PER_INCH * dpi


def _as_line(line: TextLine | str) -> TextLine:
    return line if isinstance(line, TextLine) else TextLine(text=str(line))


def _design_lines(design: StampDesign) -> list[TextLine]:
    return [line for line in map(_as_line, design.lines) if line.text.strip()]


def _frame_geometry(
    design: StampDesign, dpi: float
) -> tuple[int, int, QRectF, QRectF, float]:
    width = max(1, int(round(_px(design.width_mm, dpi))))
    height = max(1, int(round(_px(design.height_mm, dpi))))
    pen_width = max(0.0, _px(design.border_mm, dpi))
    if pen_width > 0:
        half = pen_width / 2.0
        frame = QRectF(
            half, half, max(0.0, width - pen_width), max(0.0, height - pen_width)
        )
    else:
        frame = QRectF(0.0, 0.0, float(width), float(height))
    pad = max(0.0, _px(design.padding_mm, dpi))
    inner = frame.adjusted(pad, pad, -pad, -pad)
    return width, height, frame, inner, pen_width


def _make_font(line: TextLine, dpi: float) -> QFont:
    font = QFont(line.font_family)
    font.setPixelSize(max(1, int(round(line.font_size_pt / 72.0 * dpi))))
    font.setBold(line.bold)
    font.setItalic(line.italic)
    font.setStyleStrategy(QFont.PreferAntialias)
    return font


def _line_metrics(line: TextLine, dpi: float) -> tuple[TextLine, QFont, QFontMetricsF]:
    font = _make_font(line, dpi)
    return line, font, QFontMetricsF(font)


def signature_half_extents(signature: SignatureImage) -> tuple[float, float]:
    angle = math.radians(signature.rotation_deg)
    cos_a = abs(math.cos(angle))
    sin_a = abs(math.sin(angle))
    half_w = (signature.width_mm * cos_a + signature.height_mm * sin_a) / 2.0
    half_h = (signature.width_mm * sin_a + signature.height_mm * cos_a) / 2.0
    return half_w, half_h


def content_required_size(design: StampDesign) -> tuple[float, float]:
    """Минимальный внешний размер рамки по тексту, отступам и толщине рамки."""
    lines = _design_lines(design)
    if not lines:
        return MIN_WIDTH_MM, MIN_HEIGHT_MM
    dpi = 300.0
    metrics = [_line_metrics(line, dpi) for line in lines]
    text_width = max(fm.horizontalAdvance(line.text) for line, _font, fm in metrics)
    heights = [fm.height() for _line, _font, fm in metrics]
    gap = max(1.0, max(heights) * 0.25)
    text_height = sum(heights) + gap * (len(heights) - 1)
    width = (
        text_width / dpi * MM_PER_INCH
        + 2.0 * max(0.0, design.padding_mm)
        + max(0.0, design.border_mm)
        + 0.2
    )
    height = (
        text_height / dpi * MM_PER_INCH
        + 2.0 * max(0.0, design.padding_mm)
        + max(0.0, design.border_mm)
        + 0.2
    )
    return (
        max(MIN_WIDTH_MM, min(MAX_WIDTH_MM, round(width, 1))),
        max(MIN_HEIGHT_MM, min(MAX_HEIGHT_MM, round(height, 1))),
    )


def validate_design(design: StampDesign) -> None:
    """Проверяет, что все строки помещаются в рамку с учётом отступа."""
    if not (MIN_WIDTH_MM <= design.width_mm <= MAX_WIDTH_MM):
        raise StampError(
            f"Ширина штампа — от {MIN_WIDTH_MM:g} до {MAX_WIDTH_MM:g} мм."
        )
    if not (MIN_HEIGHT_MM <= design.height_mm <= MAX_HEIGHT_MM):
        raise StampError(
            f"Высота штампа — от {MIN_HEIGHT_MM:g} до {MAX_HEIGHT_MM:g} мм."
        )
    if not (0.0 <= design.border_mm <= 10.0):
        raise StampError("Толщина рамки — от 0 до 10 мм.")
    if not (0.0 <= design.padding_mm <= 30.0):
        raise StampError("Отступ рамки от текста — от 0 до 30 мм.")
    parse_color(design.ink_color)
    lines = _design_lines(design)
    if not lines:
        raise StampError("Добавьте хотя бы одну непустую строку текста.")

    dpi = 300.0
    _width, _height, _frame, inner, _pen = _frame_geometry(design, dpi)
    if inner.width() < 5 or inner.height() < 5:
        raise StampError(
            "Рамка и отступ не оставляют места для текста. Уменьшите отступ "
            "или толщину рамки."
        )

    metrics = [_line_metrics(line, dpi) for line in lines]
    for line, _font, fm in metrics:
        if not (4.0 <= line.font_size_pt <= 72.0):
            raise StampError("Размер шрифта — от 4 до 72 пт.")
        width = fm.horizontalAdvance(line.text)
        if width > inner.width() + 0.5:
            raise StampError(
                f"Строка «{line.text}» не помещается по ширине. Уменьшите шрифт "
                "или увеличьте ширину/отступ."
            )
    heights = [fm.height() for _line, _font, fm in metrics]
    gap = max(1.0, max(heights) * 0.25)
    total_height = sum(heights) + gap * (len(heights) - 1)
    if total_height > inner.height() + 0.5:
        raise StampError(
            "Строки не помещаются по высоте. Уменьшите шрифт или количество строк."
        )

    signature = design.signature
    if signature is not None and not signature.image.isNull():
        if signature.width_mm < 3.0 or signature.height_mm < 3.0:
            raise StampError("Подпись слишком мала.")
        half_w, half_h = signature_half_extents(signature)
        if (
            signature.x_mm - half_w < -0.5
            or signature.y_mm - half_h < -0.5
            or signature.x_mm + half_w > design.width_mm + 0.5
            or signature.y_mm + half_h > design.height_mm + 0.5
        ):
            raise StampError("Подпись выходит за пределы поля штампа.")


def render_stamp(design: StampDesign, dpi: float = 300.0) -> QImage:
    """Рисует штамп на прозрачном фоне с индивидуальным стилем каждой строки."""
    width, height, frame, inner, pen_width = _frame_geometry(design, dpi)
    image = QImage(width, height, QImage.Format_ARGB32_Premultiplied)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.TextAntialiasing, True)
    painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
    try:
        red, green, blue = parse_color(design.ink_color)
        color = QColor(red, green, blue)
        if pen_width > 0:
            pen = QPen(color)
            pen.setWidthF(max(0.1, pen_width))
            pen.setJoinStyle(Qt.MiterJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(frame)

        lines = _design_lines(design)
        if lines and inner.width() > 0 and inner.height() > 0:
            metrics = [_line_metrics(line, dpi) for line in lines]
            heights = [fm.height() for _line, _font, fm in metrics]
            gap = max(1.0, max(heights) * 0.25)
            total_height = sum(heights) + gap * (len(heights) - 1)
            y = inner.top() + max(0.0, (inner.height() - total_height) / 2.0)
            for line, font, fm in metrics:
                painter.setFont(font)
                painter.setPen(QPen(color))
                text_width = fm.horizontalAdvance(line.text)
                if line.alignment == "left":
                    x = inner.left()
                elif line.alignment == "right":
                    x = inner.right() - text_width
                else:
                    x = inner.center().x() - text_width / 2.0
                baseline = y + fm.ascent()
                painter.drawText(QPointF(x, baseline), line.text)
                if line.underline:
                    underline_pen = QPen(color)
                    underline_pen.setWidthF(max(1.0, fm.height() * 0.055))
                    painter.setPen(underline_pen)
                    underline_y = baseline + max(1.0, fm.height() * 0.07)
                    painter.drawLine(
                        QPointF(x, underline_y),
                        QPointF(x + text_width, underline_y),
                    )
                y += fm.height() + gap

        signature = design.signature
        if signature is not None and not signature.image.isNull():
            painter.save()
            painter.translate(_px(signature.x_mm, dpi), _px(signature.y_mm, dpi))
            painter.rotate(signature.rotation_deg)
            sig_w = max(1.0, _px(signature.width_mm, dpi))
            sig_h = max(1.0, _px(signature.height_mm, dpi))
            painter.drawImage(
                QRectF(-sig_w / 2.0, -sig_h / 2.0, sig_w, sig_h), signature.image
            )
            painter.restore()
    finally:
        painter.end()
    image.setDotsPerMeterX(int(round(dpi / 0.0254)))
    image.setDotsPerMeterY(int(round(dpi / 0.0254)))
    return image


class StampCanvas(QWidget):
    """Предпросмотр штампа и интерактивная подпись с ручками."""

    HANDLE_SIZE = 8.0
    signature_changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("StampCanvas")
        self.setFixedHeight(330)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMouseTracking(True)
        self.setCursor(Qt.ArrowCursor)
        self._image = QImage()
        self._design: StampDesign | None = None
        self._signature: SignatureImage | None = None
        self._display = QRectF()
        self._drag_mode: str | None = None
        self._drag_start = QPointF()
        self._drag_signature: SignatureImage | None = None

    def set_design(self, design: StampDesign) -> None:
        if design.signature is not None:
            self._signature = design.signature
        else:
            design.signature = self._signature
        self._design = design
        self._render()
        self.update()

    def set_signature(self, signature: SignatureImage | None) -> None:
        self._signature = signature
        if self._design is not None:
            self._design.signature = signature
        self._render()
        self.update()

    def signature(self) -> SignatureImage | None:
        return self._signature

    def _render(self) -> None:
        if self._design is None:
            self._image = QImage()
            return
        try:
            self._image = render_stamp(self._design, dpi=180.0)
        except StampError:
            fallback = StampDesign(
                width_mm=self._design.width_mm,
                height_mm=self._design.height_mm,
                ink_color=DEFAULT_INK,
                border_mm=self._design.border_mm,
                padding_mm=self._design.padding_mm,
                lines=self._design.lines,
                signature=self._signature,
            )
            self._image = render_stamp(fallback, dpi=180.0)

    def _display_geometry(self) -> tuple[QRectF, float, float]:
        if self._design is None or self._image.isNull():
            return QRectF(), 0.0, 0.0
        available = self.rect().adjusted(10, 10, -10, -10)
        scaled = self._image.size()
        scaled.scale(available.size(), Qt.KeepAspectRatio)
        target = QRectF(
            available.center().x() - scaled.width() / 2.0,
            available.center().y() - scaled.height() / 2.0,
            float(scaled.width()),
            float(scaled.height()),
        )
        scale_x = target.width() / self._design.width_mm
        scale_y = target.height() / self._design.height_mm
        return target, scale_x, scale_y

    def _signature_points(self) -> tuple[QPolygonF, QPointF, float, float, QRectF]:
        assert self._design is not None and self._signature is not None
        target, scale_x, scale_y = self._display_geometry()
        cx = target.left() + self._signature.x_mm * scale_x
        cy = target.top() + self._signature.y_mm * scale_y
        hw = self._signature.width_mm * scale_x / 2.0
        hh = self._signature.height_mm * scale_y / 2.0
        angle = math.radians(self._signature.rotation_deg)
        cos_a, sin_a = math.cos(angle), math.sin(angle)

        def rotate(lx: float, ly: float) -> QPointF:
            return QPointF(cx + lx * cos_a - ly * sin_a, cy + lx * sin_a + ly * cos_a)

        points = [
            rotate(-hw, -hh),
            rotate(hw, -hh),
            rotate(hw, hh),
            rotate(-hw, hh),
        ]
        top = QPointF((points[0].x() + points[1].x()) / 2, (points[0].y() + points[1].y()) / 2)
        handle_distance = 30.0
        rotate_handle = QPointF(
            top.x() + math.sin(angle) * handle_distance,
            top.y() - math.cos(angle) * handle_distance,
        )
        return QPolygonF(points), rotate_handle, scale_x, scale_y, target

    def _handle_points(self) -> dict[str, QPointF]:
        if self._design is None or self._signature is None:
            return {}
        points, rotate_handle, _sx, _sy, _target = self._signature_points()
        center = QPointF(
            (points[0].x() + points[1].x() + points[2].x() + points[3].x()) / 4.0,
            (points[0].y() + points[1].y() + points[2].y() + points[3].y()) / 4.0,
        )
        return {
            "nw": points[0],
            "ne": points[1],
            "se": points[2],
            "sw": points[3],
            "rotate": rotate_handle,
            "move": center,
        }

    def _hit_test(self, pos: QPointF) -> str | None:
        if self._design is None or self._signature is None:
            return None
        for name, point in self._handle_points().items():
            if math.hypot(pos.x() - point.x(), pos.y() - point.y()) <= 10.0:
                return name
        points, _rotate, _sx, _sy, _target = self._signature_points()
        if points.containsPoint(pos, Qt.OddEvenFill):
            return "move"
        return None

    def clamp_signature(self) -> None:
        self._clamp_signature_position()
        self._render()
        self.update()

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.LeftButton or self._signature is None:
            super().mousePressEvent(event)
            return
        mode = self._hit_test(event.position())
        if mode is None:
            super().mousePressEvent(event)
            return
        self._drag_mode = mode
        self._drag_start = event.position()
        self._drag_signature = SignatureImage(
            image=self._signature.image,
            x_mm=self._signature.x_mm,
            y_mm=self._signature.y_mm,
            width_mm=self._signature.width_mm,
            height_mm=self._signature.height_mm,
            rotation_deg=self._signature.rotation_deg,
        )
        if mode == "move":
            self.setCursor(Qt.SizeAllCursor)
        elif mode == "rotate":
            self.setCursor(Qt.CrossCursor)
        elif mode in ("nw", "se"):
            self.setCursor(Qt.SizeFDiagCursor)
        else:
            self.setCursor(Qt.SizeBDiagCursor)
        event.accept()

    def mouseMoveEvent(self, event) -> None:
        if (
            self._drag_mode is None
            or self._design is None
            or self._signature is None
            or self._drag_signature is None
        ):
            if self._signature is not None:
                mode = self._hit_test(event.position())
                if mode == "move":
                    self.setCursor(Qt.SizeAllCursor)
                elif mode == "rotate":
                    self.setCursor(Qt.CrossCursor)
                elif mode in ("nw", "se"):
                    self.setCursor(Qt.SizeFDiagCursor)
                elif mode in ("ne", "sw"):
                    self.setCursor(Qt.SizeBDiagCursor)
                else:
                    self.setCursor(Qt.ArrowCursor)
            super().mouseMoveEvent(event)
            return

        _target, scale_x, scale_y = self._display_geometry()
        if scale_x <= 0 or scale_y <= 0:
            return
        dx_mm = (event.position().x() - self._drag_start.x()) / scale_x
        dy_mm = (event.position().y() - self._drag_start.y()) / scale_y
        start = self._drag_signature

        if self._drag_mode == "move":
            self._signature.x_mm = start.x_mm + dx_mm
            self._signature.y_mm = start.y_mm + dy_mm
            self._clamp_signature_position()
        elif self._drag_mode == "rotate":
            center_x = _target.left() + start.x_mm * scale_x
            center_y = _target.top() + start.y_mm * scale_y
            angle = math.degrees(
                math.atan2(
                    event.position().y() - center_y,
                    event.position().x() - center_x,
                )
            ) + 90.0
            while angle > 180.0:
                angle -= 360.0
            while angle < -180.0:
                angle += 360.0
            self._signature.rotation_deg = angle
        else:
            center_x = _target.left() + start.x_mm * scale_x
            center_y = _target.top() + start.y_mm * scale_y
            angle = math.radians(start.rotation_deg)
            local_x = (event.position().x() - center_x) * math.cos(angle) + (
                event.position().y() - center_y
            ) * math.sin(angle)
            local_y = -(event.position().x() - center_x) * math.sin(angle) + (
                event.position().y() - center_y
            ) * math.cos(angle)
            half_w = max(0.1, start.width_mm * scale_x / 2.0)
            half_h = max(0.1, start.height_mm * scale_y / 2.0)
            factor = max(abs(local_x) / half_w, abs(local_y) / half_h)
            factor = max(0.08, min(8.0, factor))
            self._signature.width_mm = max(3.0, min(self._design.width_mm, start.width_mm * factor))
            ratio = start.width_mm / max(0.1, start.height_mm)
            self._signature.height_mm = max(3.0, self._signature.width_mm / ratio)
            if self._signature.height_mm > self._design.height_mm:
                self._signature.height_mm = self._design.height_mm
                self._signature.width_mm = self._signature.height_mm * ratio
            self._clamp_signature_position()

        self._render()
        self.update()
        self.signature_changed.emit()
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if self._drag_mode is not None:
            self._drag_mode = None
            self._drag_signature = None
            self.setCursor(Qt.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _clamp_signature_position(self) -> None:
        if self._design is None or self._signature is None:
            return
        half_w, half_h = signature_half_extents(self._signature)
        if half_w * 2 >= self._design.width_mm:
            self._signature.x_mm = self._design.width_mm / 2.0
        else:
            self._signature.x_mm = max(
                half_w, min(self._design.width_mm - half_w, self._signature.x_mm)
            )
        if half_h * 2 >= self._design.height_mm:
            self._signature.y_mm = self._design.height_mm / 2.0
        else:
            self._signature.y_mm = max(
                half_h, min(self._design.height_mm - half_h, self._signature.y_mm)
            )

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.fillRect(self.rect(), QColor("#FFFFFF"))

        cell = 10
        light = QColor("#EEF2F8")
        dark = QColor("#E2E8F2")
        for row, y in enumerate(range(0, self.height(), cell)):
            for col, x in enumerate(range(0, self.width(), cell)):
                painter.fillRect(
                    x, y, cell, cell, light if (row + col) % 2 == 0 else dark
                )

        if self._image.isNull() or self._design is None:
            painter.setPen(QColor("#7C8A9D"))
            painter.drawText(self.rect(), Qt.AlignCenter, "Предпросмотр штампа")
            painter.end()
            return

        target, _sx, _sy = self._display_geometry()
        self._display = target
        painter.drawImage(target, self._image)
        painter.setPen(QPen(QColor("#C8D3E1"), 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(target.adjusted(-1, -1, 1, 1))

        if self._signature is not None:
            points, rotate_handle, _sx, _sy, _target = self._signature_points()
            painter.setPen(QPen(QColor("#1F5EFF"), 1.5, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawPolygon(points)
            for name, point in self._handle_points().items():
                if name == "rotate":
                    paint_handle = QPointF(point)
                    top = QPointF(
                        (points[0].x() + points[1].x()) / 2,
                        (points[0].y() + points[1].y()) / 2,
                    )
                    painter.setPen(QPen(QColor("#1F5EFF"), 1.5))
                    painter.drawLine(top, paint_handle)
                    painter.setBrush(QColor("#FFFFFF"))
                    painter.drawEllipse(paint_handle, 5.0, 5.0)
                elif name == "move":
                    painter.setPen(QPen(QColor("#1F5EFF"), 1.3))
                    painter.setBrush(QColor("#FFFFFF"))
                    painter.drawEllipse(point, 4.0, 4.0)
                    painter.drawLine(
                        QPointF(point.x() - 6.5, point.y()),
                        QPointF(point.x() + 6.5, point.y()),
                    )
                    painter.drawLine(
                        QPointF(point.x(), point.y() - 6.5),
                        QPointF(point.x(), point.y() + 6.5),
                    )
                else:
                    painter.setPen(QPen(QColor("#1F5EFF"), 1.5))
                    painter.setBrush(QColor("#FFFFFF"))
                    painter.drawRect(
                        QRectF(
                            point.x() - self.HANDLE_SIZE / 2.0,
                            point.y() - self.HANDLE_SIZE / 2.0,
                            self.HANDLE_SIZE,
                            self.HANDLE_SIZE,
                        )
                    )

        painter.end()


class LineRow(QFrame):
    """Строка текста с независимыми шрифтом, выравниванием и подчёркиванием."""

    changed = Signal()
    removed = Signal()

    def __init__(self, line: TextLine, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("LineRow")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        top = QHBoxLayout()
        top.setSpacing(5)
        self.text_edit = QLineEdit(line.text)
        self.text_edit.setMaxLength(80)
        self.text_edit.setPlaceholderText("Текст строки")
        top.addWidget(self.text_edit, 1)
        self.remove_button = QPushButton("×")
        self.remove_button.setObjectName("Ghost")
        self.remove_button.setFixedSize(27, 27)
        self.remove_button.setToolTip("Удалить строку")
        top.addWidget(self.remove_button)
        layout.addLayout(top)

        bottom = QHBoxLayout()
        bottom.setSpacing(4)
        self.font_combo = QFontComboBox()
        self.font_combo.setCurrentFont(QFont(line.font_family))
        self.font_combo.setMinimumWidth(132)
        self.font_combo.setToolTip("Шрифт этой строки")
        bottom.addWidget(self.font_combo, 1)

        self.size_spin = QDoubleSpinBox()
        self.size_spin.setRange(4.0, 72.0)
        self.size_spin.setDecimals(1)
        self.size_spin.setSingleStep(0.5)
        self.size_spin.setSuffix(" пт")
        self.size_spin.setValue(line.font_size_pt)
        self.size_spin.setFixedWidth(76)
        bottom.addWidget(self.size_spin)

        self.align_combo = QComboBox()
        self.align_combo.addItem("Центр", "center")
        self.align_combo.addItem("Слева", "left")
        self.align_combo.addItem("Справа", "right")
        index = self.align_combo.findData(line.alignment)
        self.align_combo.setCurrentIndex(max(0, index))
        self.align_combo.setFixedWidth(92)
        self.align_combo.setToolTip("Выравнивание этой строки")
        bottom.addWidget(self.align_combo)

        self.bold_button = self._format_button("B", "Жирный", line.bold)
        self.italic_button = self._format_button("I", "Курсив", line.italic)
        self.underline_button = self._format_button("U", "Подчёркивание", line.underline)
        for button in (
            self.bold_button,
            self.italic_button,
            self.underline_button,
        ):
            bottom.addWidget(button)
        layout.addLayout(bottom)

        self.text_edit.textChanged.connect(self.changed)
        self.font_combo.currentFontChanged.connect(lambda *_: self.changed.emit())
        self.size_spin.valueChanged.connect(lambda *_: self.changed.emit())
        self.align_combo.currentIndexChanged.connect(lambda *_: self.changed.emit())
        self.bold_button.toggled.connect(lambda *_: self.changed.emit())
        self.italic_button.toggled.connect(lambda *_: self.changed.emit())
        self.underline_button.toggled.connect(lambda *_: self.changed.emit())
        self.remove_button.clicked.connect(self.removed)

    @staticmethod
    def _format_button(text: str, tooltip: str, checked: bool) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName("FormatToggle")
        button.setCheckable(True)
        button.setChecked(checked)
        button.setFixedSize(27, 27)
        button.setToolTip(tooltip)
        font = button.font()
        if text == "B":
            font.setBold(True)
        elif text == "I":
            font.setItalic(True)
        elif text == "U":
            font.setUnderline(True)
        button.setFont(font)
        return button

    def line(self) -> TextLine:
        return TextLine(
            text=self.text_edit.text(),
            font_family=self.font_combo.currentFont().family(),
            font_size_pt=self.size_spin.value(),
            bold=self.bold_button.isChecked(),
            italic=self.italic_button.isChecked(),
            underline=self.underline_button.isChecked(),
            alignment=str(self.align_combo.currentData() or "center"),
        )

    def set_remove_enabled(self, enabled: bool) -> None:
        self.remove_button.setEnabled(enabled)


class StampEditorPage(QScrollArea):
    """Страница редактора штампа на вкладке «Редактор»."""

    saved = Signal(str, float, float)

    def __init__(self, save_dir: Path, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("SettingsScroll")
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._save_dir = Path(save_dir)

        tab = QWidget()
        tab.setObjectName("SettingsPane")
        self.setWidget(tab)
        outer = QVBoxLayout(tab)
        outer.setContentsMargins(18, 16, 18, 16)
        outer.setSpacing(9)

        hint = QLabel(
            "Создайте собственный оттиск. Максимальное поле — 100 × 70 мм. "
            "Для каждой строки можно выбрать свой шрифт, выравнивание и "
            "подчёркивание. Готовый PNG сохраняется рядом с программой."
        )
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        outer.addWidget(hint)

        columns = QHBoxLayout()
        columns.setSpacing(14)
        left = QVBoxLayout()
        left.setSpacing(6)
        layout = QVBoxLayout()
        layout.setSpacing(9)
        columns.addLayout(left, 1)
        columns.addLayout(layout, 1)
        outer.addLayout(columns, 1)

        self.canvas = StampCanvas()
        left.addWidget(self.canvas, 1)

        size_row = QHBoxLayout()
        size_row.setSpacing(6)
        size_row.addWidget(self._field_label("Ширина"))
        self.width_spin = self._mm_spin(MAX_WIDTH_MM, MIN_WIDTH_MM, MAX_WIDTH_MM)
        size_row.addWidget(self.width_spin, 1)
        size_row.addWidget(self._field_label("Высота"))
        self.height_spin = self._mm_spin(MAX_HEIGHT_MM, MIN_HEIGHT_MM, MAX_HEIGHT_MM)
        size_row.addWidget(self.height_spin, 1)
        layout.addLayout(size_row)

        self.fit_content = QCheckBox("По содержимому")
        self.fit_content.setToolTip(
            "Подбирать ширину и высоту рамки по тексту, шрифту и отступам"
        )
        layout.addWidget(self.fit_content)

        self.canvas_hint = QLabel("Поле: 100 × 70 мм")
        self.canvas_hint.setObjectName("Hint")
        left.addWidget(self.canvas_hint)
        left.addStretch(1)

        layout.addWidget(self._subtitle("Оттиск"))
        color_row = QHBoxLayout()
        color_row.setSpacing(6)
        color_row.addWidget(self._field_label("Цвет"))
        self.color_edit = QLineEdit(DEFAULT_INK)
        self.color_edit.setMaxLength(40)
        self.color_edit.setPlaceholderText("#332A7A, rgb(40,30,120)")
        color_row.addWidget(self.color_edit, 1)
        self.color_swatch = QLabel()
        self.color_swatch.setFixedSize(25, 25)
        color_row.addWidget(self.color_swatch)
        self.color_button = QPushButton("…")
        self.color_button.setObjectName("Secondary")
        self.color_button.setFixedWidth(34)
        self.color_button.setToolTip("Выбрать цвет оттиска")
        color_row.addWidget(self.color_button)
        layout.addLayout(color_row)

        layout.addWidget(self._subtitle("Рамка"))
        frame_grid = QGridLayout()
        frame_grid.setHorizontalSpacing(8)
        frame_grid.setVerticalSpacing(4)
        frame_grid.addWidget(self._field_label("Толщина линий"), 0, 0)
        frame_grid.addWidget(self._field_label("Отступ от текста"), 0, 1)
        self.border_spin = self._mm_spin(1.0, 0.0, 10.0, step=0.1)
        self.padding_spin = self._mm_spin(4.0, 0.0, 30.0, step=0.5)
        frame_grid.addWidget(self.border_spin, 1, 0)
        frame_grid.addWidget(self.padding_spin, 1, 1)
        layout.addLayout(frame_grid)

        layout.addWidget(self._subtitle("Строки"))
        self.rows_layout = QVBoxLayout()
        self.rows_layout.setSpacing(5)
        layout.addLayout(self.rows_layout)
        self.add_line_button = QPushButton("+ Добавить строку")
        self.add_line_button.setObjectName("Secondary")
        self.add_line_button.clicked.connect(lambda: self._add_line(""))
        layout.addWidget(self.add_line_button)

        layout.addWidget(self._subtitle("Рукописная подпись"))
        signature_row = QHBoxLayout()
        signature_row.setSpacing(6)
        self.insert_signature_button = QPushButton("Вставить подпись")
        self.insert_signature_button.setObjectName("Secondary")
        self.insert_signature_button.clicked.connect(self._insert_signature)
        signature_row.addWidget(self.insert_signature_button)
        self.remove_signature_button = QPushButton("Удалить подпись")
        self.remove_signature_button.setObjectName("Ghost")
        self.remove_signature_button.setEnabled(False)
        self.remove_signature_button.clicked.connect(self._remove_signature)
        signature_row.addWidget(self.remove_signature_button)
        signature_row.addStretch(1)
        layout.addLayout(signature_row)
        signature_hint = QLabel(
            "Лучше PNG с прозрачным фоном. Перетаскивайте подпись мышью; "
            "углы — размер, верхняя круглая ручка — поворот."
        )
        signature_hint.setObjectName("Hint")
        signature_hint.setWordWrap(True)
        layout.addWidget(signature_hint)

        self.save_button = QPushButton("Сохранить шаблон")
        self.save_button.setObjectName("Primary")
        self.save_button.clicked.connect(self._save)
        layout.addWidget(self.save_button)
        self.save_hint = QLabel(f"Сохранение: {self._save_dir}")
        self.save_hint.setObjectName("Hint")
        self.save_hint.setWordWrap(True)
        layout.addWidget(self.save_hint)
        layout.addStretch(1)

        self._rows: list[LineRow] = []
        self._add_line("СОГЛАСОВАНО")
        self._connect()
        self._refresh_preview()

    @staticmethod
    def _field_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("FieldLabel")
        return label

    @staticmethod
    def _subtitle(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("SubTitle")
        return label

    @staticmethod
    def _mm_spin(
        value: float, minimum: float, maximum: float, step: float = 1.0
    ) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setDecimals(1)
        spin.setSingleStep(step)
        spin.setSuffix(" мм")
        spin.setValue(value)
        return spin

    def _connect(self) -> None:
        self.width_spin.valueChanged.connect(self._refresh_preview)
        self.height_spin.valueChanged.connect(self._refresh_preview)
        self.color_edit.textChanged.connect(self._color_changed)
        self.color_button.clicked.connect(self._choose_color)
        self.border_spin.valueChanged.connect(self._refresh_preview)
        self.padding_spin.valueChanged.connect(self._refresh_preview)
        self.fit_content.toggled.connect(self._fit_toggled)

    def _fit_toggled(self, checked: bool) -> None:
        self.width_spin.setEnabled(not checked)
        self.height_spin.setEnabled(not checked)
        self._refresh_preview()

    def _set_size_values(self, width: float, height: float) -> None:
        self.width_spin.blockSignals(True)
        self.height_spin.blockSignals(True)
        try:
            self.width_spin.setValue(width)
            self.height_spin.setValue(height)
        finally:
            self.width_spin.blockSignals(False)
            self.height_spin.blockSignals(False)

    def _add_line(self, text: str) -> None:
        if self._rows:
            base = self._rows[-1].line()
            line = TextLine(
                text=text,
                font_family=base.font_family,
                font_size_pt=base.font_size_pt,
                bold=base.bold,
                italic=base.italic,
                underline=base.underline,
                alignment=base.alignment,
            )
        else:
            line = TextLine(text=text)
        row = LineRow(line)
        self.rows_layout.addWidget(row)
        self._rows.append(row)
        row.changed.connect(self._refresh_preview)
        row.removed.connect(lambda r=row: self._remove_line(r))
        self._update_line_buttons()
        self._refresh_preview()

    def _remove_line(self, row: LineRow) -> None:
        if len(self._rows) <= 1:
            return
        if row in self._rows:
            self._rows.remove(row)
            self.rows_layout.removeWidget(row)
            row.deleteLater()
        self._update_line_buttons()
        self._refresh_preview()

    def _update_line_buttons(self) -> None:
        multiple = len(self._rows) > 1
        for row in self._rows:
            row.set_remove_enabled(multiple)
        self.add_line_button.setEnabled(len(self._rows) < 8)

    def _collect_design(self) -> StampDesign:
        return StampDesign(
            width_mm=self.width_spin.value(),
            height_mm=self.height_spin.value(),
            ink_color=self.color_edit.text(),
            border_mm=self.border_spin.value(),
            padding_mm=self.padding_spin.value(),
            lines=[row.line() for row in self._rows],
            signature=self.canvas.signature(),
        )

    def _color_changed(self) -> None:
        try:
            red, green, blue = parse_color(self.color_edit.text())
        except StampError as exc:
            self.color_swatch.setStyleSheet(
                "background: #FEE2E2; border: 1px solid #DC2626; border-radius: 4px;"
            )
            self.color_swatch.setToolTip(str(exc))
            self.color_edit.setToolTip(str(exc))
        else:
            self.color_swatch.setStyleSheet(
                f"background: rgb({red}, {green}, {blue}); "
                "border: 1px solid #94A3B8; border-radius: 4px;"
            )
            self.color_swatch.setToolTip(f"RGB({red}, {green}, {blue})")
            self.color_edit.setToolTip("")
        self._refresh_preview()

    def _choose_color(self) -> None:
        try:
            red, green, blue = parse_color(self.color_edit.text())
            initial = QColor(red, green, blue)
        except StampError:
            initial = QColor(DEFAULT_INK)
        color = QColorDialog.getColor(initial, self, "Цвет оттиска")
        if color.isValid():
            self.color_edit.setText(color.name().upper())

    def _refresh_preview(self) -> None:
        design = self._collect_design()
        if self.fit_content.isChecked():
            width, height = content_required_size(design)
            self._set_size_values(width, height)
            design.width_mm = width
            design.height_mm = height
        self.canvas_hint.setText(
            f"Поле: {design.width_mm:g} × {design.height_mm:g} мм"
        )
        self.canvas.set_design(design)
        self.canvas.clamp_signature()

    def _insert_signature(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Выбрать изображение подписи",
            str(self._save_dir),
            "Изображения (*.png *.jpg *.jpeg *.bmp *.webp);;Все файлы (*.*)",
        )
        if not path:
            return
        image = QImage(path)
        if image.isNull():
            QMessageBox.warning(
                self, "Не удалось открыть подпись", f"Файл:\n{path}"
            )
            return
        image = image.convertToFormat(QImage.Format_ARGB32_Premultiplied)
        design = self._collect_design()
        aspect = image.width() / max(1, image.height())
        width = min(40.0, design.width_mm * 0.55)
        height = width / max(0.01, aspect)
        max_height = design.height_mm * 0.55
        if height > max_height:
            height = max_height
            width = height * aspect
        signature = SignatureImage(
            image=image,
            x_mm=design.width_mm / 2.0,
            y_mm=design.height_mm * 0.68,
            width_mm=max(3.0, width),
            height_mm=max(3.0, height),
        )
        self.canvas.set_signature(signature)
        self.canvas.clamp_signature()
        self.canvas._render()
        self.canvas.update()
        self.remove_signature_button.setEnabled(True)

    def _remove_signature(self) -> None:
        self.canvas.set_signature(None)
        self.remove_signature_button.setEnabled(False)

    def _save(self) -> None:
        design = self._collect_design()
        try:
            validate_design(design)
        except StampError as exc:
            QMessageBox.warning(self, "Проверьте штамп", str(exc))
            return

        try:
            self._save_dir.mkdir(parents=True, exist_ok=True)
            stamp = render_stamp(design, dpi=300.0)
            path = self._unique_path(design)
            if not stamp.save(str(path), "PNG"):
                raise OSError("не удалось записать PNG")
        except (OSError, PermissionError) as exc:
            QMessageBox.critical(
                self,
                "Не удалось сохранить шаблон",
                f"Папка: {self._save_dir}\n\n{exc}",
            )
            return

        self.save_hint.setText(f"Сохранено: {path.name}")
        self.saved.emit(str(path), design.width_mm, design.height_mm)

    def _unique_path(self, design: StampDesign) -> Path:
        first = next((line.text.strip() for line in _design_lines(design)), "")
        safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "", first)
        safe = re.sub(r"\s+", "_", safe).strip(" ._")
        safe = re.sub(r"_+", "_", safe)[:40].strip(" ._")
        if not safe or safe.upper() in {
            "CON", "PRN", "AUX", "NUL", "COM1", "COM2", "COM3", "COM4",
            "COM5", "COM6", "COM7", "COM8", "COM9", "LPT1", "LPT2",
            "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
        }:
            safe = "Штамп"
        stamp = datetime.now().strftime("%d%m%Y_%H%M%S")
        path = self._save_dir / f"{safe}_{stamp}.png"
        counter = 2
        while path.exists():
            path = self._save_dir / f"{safe}_{stamp}_{counter}.png"
            counter += 1
        return path
