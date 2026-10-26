"""Дизайн-система приложения: палитра, стили и мелкая векторная графика темы."""

from __future__ import annotations

import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QApplication


@dataclass(frozen=True)
class ThemeColors:
    """Единая палитра приложения. Все модули берут цвета отсюда."""

    window: str = "#EEF1F6"        # фон главного окна
    dialog: str = "#F6F8FB"        # фон диалогов
    card: str = "#FFFFFF"          # фон карточек
    border: str = "#E4E9F1"        # рамки карточек и разделителей
    text: str = "#1F2937"          # основной текст
    secondary: str = "#475569"     # вторичный текст
    muted: str = "#64748B"         # приглушённый текст, подписи
    faint: str = "#94A3B8"         # самый светлый текст, плейсхолдеры
    accent: str = "#4F46E5"        # акцент (индиго)
    accent_hover: str = "#4338CA"
    accent_pressed: str = "#3730A3"
    accent_soft: str = "#EEF2FF"   # мягкий акцентный фон
    accent_border: str = "#C7D2FE"
    accent_text: str = "#4338CA"   # акцентный текст на светлом фоне
    ok: str = "#059669"
    ok_soft: str = "#ECFDF5"
    warn: str = "#B45309"
    warn_soft: str = "#FFFBEB"
    danger: str = "#DC2626"
    danger_soft: str = "#FEF2F2"
    info: str = "#64748B"
    # Шахматные фоны превью.
    check_light: str = "#F4F6FB"
    check_dark: str = "#E7ECF4"
    canvas_light: str = "#EEF2F8"
    canvas_dark: str = "#E2E8F2"


COLORS = ThemeColors()


def _bundled_icon_dir() -> Path | None:
    base = Path(
        getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1])
    )
    folder = base / "assets" / "theme"
    names = ("check.png", "radio.png", "arrow-down.png", "arrow-up.png")
    if all((folder / name).is_file() for name in names):
        return folder
    return None


def _icon_dir() -> Path:
    folder = Path(tempfile.gettempdir()) / "shtampilyator-theme"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _save_check(path: Path) -> None:
    """Белая галочка для выбранного чекбокса."""
    size = 18
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor("#FFFFFF"), 2.4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    painter.setPen(pen)
    painter.drawLine(QPointF(4.2, 9.4), QPointF(7.4, 12.6))
    painter.drawLine(QPointF(7.4, 12.6), QPointF(13.8, 5.2))
    painter.end()
    pixmap.save(str(path), "PNG")


def _save_radio(path: Path) -> None:
    """Белая точка для выбранной радиокнопки."""
    size = 18
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor("#FFFFFF"))
    painter.drawEllipse(QPointF(size / 2.0, size / 2.0), 4.4, 4.4)
    painter.end()
    pixmap.save(str(path), "PNG")


def _save_chevron(path: Path, size: tuple[int, int], color: str, up: bool) -> None:
    w, h = size
    pixmap = QPixmap(w, h)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    path_shape = QPainterPath()
    margin = 1.2
    if up:
        path_shape.moveTo(QPointF(margin, h - margin))
        path_shape.lineTo(QPointF(w / 2.0, margin))
        path_shape.lineTo(QPointF(w - margin, h - margin))
    else:
        path_shape.moveTo(QPointF(margin, margin))
        path_shape.lineTo(QPointF(w / 2.0, h - margin))
        path_shape.lineTo(QPointF(w - margin, margin))
    pen = QPen(QColor(color), 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    painter.setPen(pen)
    painter.drawPath(path_shape)
    painter.end()
    pixmap.save(str(path), "PNG")


def _ensure_icons() -> dict[str, str]:
    """Возвращает иконки темы, не требуя записи во временный каталог."""
    bundled = _bundled_icon_dir()
    if bundled is not None:
        icons = {
            "check": bundled / "check.png",
            "radio": bundled / "radio.png",
            "arrow_down": bundled / "arrow-down.png",
            "arrow_up": bundled / "arrow-up.png",
        }
        return {name: str(path).replace("\\", "/") for name, path in icons.items()}

    try:
        folder = _icon_dir()
        icons = {
            "check": folder / "check.png",
            "radio": folder / "radio.png",
            "arrow_down": folder / "arrow-down.png",
            "arrow_up": folder / "arrow-up.png",
        }
        if not icons["check"].exists():
            _save_check(icons["check"])
        if not icons["radio"].exists():
            _save_radio(icons["radio"])
        if not icons["arrow_down"].exists():
            _save_chevron(icons["arrow_down"], (12, 8), "#64748B", up=False)
        if not icons["arrow_up"].exists():
            _save_chevron(icons["arrow_up"], (12, 8), "#64748B", up=True)
        return {name: str(path).replace("\\", "/") for name, path in icons.items()}
    except OSError:
        # Темп может быть недоступен для записи — приложение всё равно
        # должно запускаться, просто без кастомных стрелок и галочек.
        return {}


def _build_style(icons: dict[str, str]) -> str:
    c = COLORS
    check = icons.get("check")
    radio = icons.get("radio")
    arrow_down = icons.get("arrow_down")
    arrow_up = icons.get("arrow_up")
    check_image = f'image: url("{check}");' if check else "image: none;"
    radio_image = f'image: url("{radio}");' if radio else "image: none;"
    down_image = f'image: url("{arrow_down}");' if arrow_down else "image: none;"
    up_image = f'image: url("{arrow_up}");' if arrow_up else "image: none;"
    return f"""
QWidget {{
    color: {c.text};
    font-family: "Segoe UI";
    font-size: 10pt;
    background: transparent;
}}
QMainWindow, QWidget#Root {{
    background: {c.window};
}}
QDialog, QMessageBox {{
    background: {c.dialog};
}}
QMessageBox QLabel {{
    color: {c.text};
    font-size: 10pt;
}}

/* ------------------------------------------------------------------ шапка */
QFrame#Header {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                stop:0 #0F152E, stop:0.5 #1C2142, stop:1 #312E81);
    border: none;
    border-bottom: 2px solid {c.accent};
}}
QLabel#AppTitle {{
    color: #FFFFFF;
    font-size: 20pt;
    font-weight: 600;
    letter-spacing: 0.4px;
}}
QLabel#AppSubtitle {{
    color: #A5B4FC;
    font-size: 9pt;
}}
QPushButton#ThanksButton {{
    background: rgba(255, 255, 255, 0.10);
    color: #EEF2FF;
    border: 1px solid rgba(255, 255, 255, 0.24);
    border-radius: 15px;
    padding: 7px 18px;
    font-size: 9.5pt;
    font-weight: 600;
}}
QPushButton#ThanksButton:hover {{
    background: rgba(255, 255, 255, 0.20);
    border-color: rgba(255, 255, 255, 0.42);
}}
QPushButton#ThanksButton:pressed {{
    background: rgba(255, 255, 255, 0.28);
}}

/* ---------------------------------------------------------------- карточки */
QFrame[card="true"] {{
    background: {c.card};
    border: 1px solid {c.border};
    border-radius: 16px;
}}
QLabel#CardTitle {{
    color: {c.text};
    font-size: 12.5pt;
    font-weight: 600;
}}
QLabel#SubTitle {{
    color: {c.text};
    font-size: 10pt;
    font-weight: 600;
    padding: 2px 0;
}}
QLabel#Badge {{
    background: {c.accent_soft};
    color: {c.accent_text};
    border-radius: 10px;
    padding: 3px 10px;
    font-size: 8.7pt;
    font-weight: 600;
}}
QLabel#Caption {{
    color: {c.muted};
    font-size: 9pt;
}}
QLabel#Muted {{
    color: {c.muted};
    font-size: 9pt;
}}
QLabel#Hint {{
    color: {c.faint};
    font-size: 8.7pt;
}}
QLabel#FieldLabel {{
    color: {c.secondary};
    font-size: 9pt;
    font-weight: 500;
}}
QLabel#EmptyHint {{
    color: {c.faint};
    font-size: 10pt;
}}
QLabel#ActionStatus {{
    color: {c.text};
    font-size: 10.5pt;
    font-weight: 600;
}}
QLabel#Percent {{
    color: {c.accent_text};
    font-size: 10pt;
    font-weight: 700;
}}
QLabel#DialogTitle {{
    color: {c.text};
    font-size: 15.5pt;
    font-weight: 600;
}}
QFrame#Divider {{
    color: {c.border};
    background: {c.border};
    max-height: 1px;
    border: none;
}}

/* ------------------------------------------------------------------- вкладки */
QTabWidget#SettingsTabs::pane {{
    background: {c.card};
    border: 1px solid {c.border};
    border-radius: 14px;
    top: -1px;
}}
QTabWidget#SettingsTabs QTabBar::tab {{
    background: transparent;
    color: {c.muted};
    border: none;
    padding: 7px 16px;
    margin-right: 4px;
    margin-bottom: 8px;
    margin-top: 2px;
    border-radius: 9px;
    font-size: 9pt;
    font-weight: 500;
}}
QTabWidget#SettingsTabs QTabBar::tab:hover {{
    background: #E9EDF5;
    color: {c.secondary};
}}
QTabWidget#SettingsTabs QTabBar::tab:selected {{
    background: {c.accent_soft};
    color: {c.accent_text};
    font-weight: 600;
}}

/* ------------------------------------------------------------------ кнопки */
QPushButton {{
    background: {c.card};
    color: {c.secondary};
    border: 1px solid #D8DFEA;
    border-radius: 10px;
    padding: 6px 14px;
    min-height: 30px;
    font-size: 9.5pt;
}}
QPushButton:hover {{
    background: #F4F6FB;
    border-color: #B9C4D6;
}}
QPushButton:pressed {{
    background: #E9EDF6;
}}
QPushButton:disabled {{
    color: #A8B3C4;
    background: #F3F6FA;
    border-color: {c.border};
}}
QPushButton#Primary {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 #5B55EA, stop:1 {c.accent});
    color: #FFFFFF;
    border: 1px solid {c.accent};
    border-radius: 11px;
    min-height: 38px;
    padding: 0 22px;
    font-weight: 600;
}}
QPushButton#Primary:hover {{
    background: {c.accent_hover};
    border-color: {c.accent_hover};
}}
QPushButton#Primary:pressed {{
    background: {c.accent_pressed};
    border-color: {c.accent_pressed};
}}
QPushButton#Primary:disabled {{
    background: #C7CEE4;
    border-color: #C7CEE4;
    color: #F4F6FD;
}}
QPushButton#Secondary {{
    background: {c.card};
    color: {c.secondary};
    border: 1px solid #D8DFEA;
    border-radius: 10px;
    min-height: 32px;
    padding: 0 14px;
}}
QPushButton#Secondary:hover {{
    background: #F4F6FB;
    border-color: #B9C4D6;
}}
QPushButton#Secondary:pressed {{
    background: #E9EDF6;
}}
QPushButton#Secondary:disabled {{
    color: #A8B3C4;
    background: #F3F6FA;
    border-color: {c.border};
}}
QPushButton#Ghost {{
    background: transparent;
    color: {c.accent_text};
    border: none;
    padding: 5px 8px;
    font-weight: 500;
}}
QPushButton#Ghost:hover {{
    background: {c.accent_soft};
    border-radius: 9px;
}}
QPushButton#Ghost:disabled {{
    color: {c.faint};
    background: transparent;
}}
QPushButton#Danger {{
    background: {c.danger_soft};
    color: {c.danger};
    border: 1px solid #F3C8C8;
    border-radius: 10px;
    min-height: 32px;
    padding: 0 14px;
    font-weight: 500;
}}
QPushButton#Danger:hover {{
    background: #FDE8E8;
    border-color: #E7A9A9;
}}
QPushButton#Danger:pressed {{
    background: #FBDCDC;
}}
QPushButton#Danger:disabled {{
    color: #D3A9A9;
    background: #FBF5F5;
    border-color: #F0DEDE;
}}

/* ------------------------------------------------------------- поля ввода */
QTextBrowser#UpdateNotes {{
    background: {c.card};
    border: 1px solid {c.border};
    border-radius: 10px;
    padding: 10px;
    color: {c.secondary};
    selection-background-color: {c.accent};
    selection-color: #FFFFFF;
}}
QLineEdit, QDoubleSpinBox, QComboBox, QFontComboBox {{
    background: {c.card};
    border: 1px solid #D8DFEA;
    border-radius: 9px;
    padding: 5px 10px;
    min-height: 29px;
    selection-background-color: {c.accent};
    selection-color: #FFFFFF;
}}
QLineEdit:hover, QDoubleSpinBox:hover, QComboBox:hover, QFontComboBox:hover {{
    border-color: #B9C4D6;
}}
QLineEdit:focus, QDoubleSpinBox:focus, QComboBox:focus, QFontComboBox:focus {{
    border: 1px solid {c.accent};
}}
QLineEdit:disabled, QDoubleSpinBox:disabled, QComboBox:disabled, QFontComboBox:disabled {{
    color: {c.faint};
    background: #F3F6FA;
    border-color: {c.border};
}}
QComboBox::drop-down, QFontComboBox::drop-down {{
    background: transparent;
    border: none;
    width: 30px;
}}
QComboBox::down-arrow, QFontComboBox::down-arrow {{
    {down_image}
    width: 12px;
    height: 8px;
}}
QComboBox::down-arrow:on, QFontComboBox::down-arrow:on {{
    top: 1px;
}}
QComboBox QAbstractItemView, QFontComboBox QAbstractItemView {{
    background: {c.card};
    border: 1px solid {c.border};
    border-radius: 9px;
    padding: 4px;
    outline: none;
    selection-background-color: {c.accent_soft};
    selection-color: #1E1B4B;
}}
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    background: transparent;
    border: none;
    width: 20px;
}}
QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {{
    background: {c.accent_soft};
}}
QDoubleSpinBox::up-button {{
    border-top-right-radius: 9px;
}}
QDoubleSpinBox::down-button {{
    border-bottom-right-radius: 9px;
}}
QDoubleSpinBox::up-arrow {{
    {up_image}
    width: 12px;
    height: 8px;
}}
QDoubleSpinBox::down-arrow {{
    {down_image}
    width: 12px;
    height: 8px;
}}
QDoubleSpinBox::up-arrow:disabled, QDoubleSpinBox::down-arrow:disabled {{
    image: none;
}}

/* ------------------------------------------------------ чекбоксы и радио */
QCheckBox, QRadioButton {{
    color: {c.secondary};
    spacing: 8px;
    font-size: 9.2pt;
    background: transparent;
}}
QCheckBox:disabled, QRadioButton:disabled {{
    color: {c.faint};
}}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 18px;
    height: 18px;
    background: {c.card};
    border: 1.5px solid #C3CCDC;
}}
QCheckBox::indicator {{
    border-radius: 5px;
}}
QRadioButton::indicator {{
    border-radius: 9px;
}}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
    border-color: {c.faint};
}}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    background: {c.accent};
    border-color: {c.accent};
}}
QCheckBox::indicator:checked {{
    {check_image}
}}
QRadioButton::indicator:checked {{
    {radio_image}
}}
QCheckBox::indicator:checked:hover, QRadioButton::indicator:checked:hover {{
    background: {c.accent_hover};
    border-color: {c.accent_hover};
}}
QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {{
    background: #F3F6FA;
    border-color: {c.border};
}}

/* -------------------------------------------------------------- таблицы */
QTableWidget {{
    background: {c.card};
    border: none;
    selection-background-color: {c.accent_soft};
    selection-color: {c.text};
}}
QTableWidget::item {{
    padding-left: 9px;
    border-bottom: 1px solid #F1F4F9;
}}
QTableWidget::item:selected {{
    background: {c.accent_soft};
    color: {c.text};
}}
QHeaderView::section {{
    background: {c.card};
    color: {c.muted};
    border: none;
    border-bottom: 1px solid {c.border};
    padding: 7px 9px;
    font-size: 8.8pt;
    font-weight: 600;
}}
QTableCornerButton::section {{
    background: {c.card};
    border: none;
}}
QTreeWidget {{
    background: {c.card};
    border: 1px solid {c.border};
    border-radius: 12px;
    selection-background-color: {c.accent_soft};
    selection-color: {c.text};
}}
QTreeWidget::item {{
    padding: 5px 4px;
    border-bottom: 1px solid #F2F5F9;
}}
QTreeWidget::item:selected {{
    background: {c.accent_soft};
    color: {c.text};
}}

/* ---------------------------------------------------------------- прочее */
QScrollArea, QWidget#SettingsPane {{
    background: transparent;
    border: none;
}}
QScrollArea#SettingsScroll {{
    background: transparent;
    border: none;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 2px 1px 2px 1px;
}}
QScrollBar::handle:vertical {{
    background: #CBD5E1;
    min-height: 32px;
    border-radius: 5px;
}}
QScrollBar::handle:vertical:hover {{
    background: {c.faint};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: transparent;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 1px 2px 1px 2px;
}}
QScrollBar::handle:horizontal {{
    background: #CBD5E1;
    min-width: 32px;
    border-radius: 5px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {c.faint};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    background: transparent;
}}
QProgressBar {{
    border: none;
    border-radius: 4px;
    background: #E6EAF2;
    text-align: center;
    color: transparent;
    min-height: 8px;
    max-height: 8px;
}}
QProgressBar::chunk {{
    border-radius: 4px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                stop:0 {c.accent}, stop:1 #818CF8);
}}
QToolTip {{
    background: #1E293B;
    color: #F1F5F9;
    border: none;
    border-radius: 8px;
    padding: 6px 9px;
    font-size: 9pt;
}}

/* ------------------------------------------------------- редактор штампа */
QWidget#StampCanvas {{
    background: {c.card};
    border: 1px solid {c.border};
    border-radius: 12px;
}}
QFrame#LineRow {{
    background: #F8FAFD;
    border: 1px solid {c.border};
    border-radius: 10px;
}}
QFrame#LineRow[empty="true"] {{
    background: #F3F6FB;
    border: 1px dashed #CBD5E1;
}}
QFrame#LineRow[active="true"] {{
    background: #FAFBFF;
    border: 1px solid {c.accent_border};
}}
QLabel#DragHandle {{
    color: {c.faint};
    font-size: 14pt;
    font-weight: 600;
    background: transparent;
}}
QPushButton#FormatToggle {{
    background: {c.card};
    color: {c.secondary};
    border: 1px solid #D8DFEA;
    border-radius: 7px;
    padding: 0;
    font-size: 9pt;
    font-weight: 600;
}}
QPushButton#FormatToggle:hover {{
    background: #F4F6FB;
    border-color: #B9C4D6;
}}
QPushButton#FormatToggle:checked {{
    background: {c.accent};
    color: #FFFFFF;
    border-color: {c.accent};
}}
QFrame#QrCard {{
    background: {c.card};
    border: 1px solid {c.border};
    border-radius: 14px;
}}
QLabel#QrCode {{
    background: {c.card};
}}
QLabel#ThanksText {{
    color: {c.secondary};
    font-size: 10pt;
}}
QLabel#ThanksCaption {{
    color: {c.muted};
    font-size: 8.7pt;
}}
"""


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    font = app.font()
    font.setFamily("Segoe UI")
    font.setPointSize(10)
    app.setFont(font)
    app.setStyleSheet(_build_style(_ensure_icons()))
