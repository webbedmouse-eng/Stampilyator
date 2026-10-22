"""Единая светлая тема приложения."""

from __future__ import annotations

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

STYLE = """
QWidget {
    color: #1D2C43;
    font-family: "Segoe UI";
    font-size: 10pt;
}
QMainWindow, QWidget#Root {
    background: #F2F5FA;
}
QDialog {
    background: #F7F9FC;
}
QFrame#Header {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                stop:0 #0B1B30, stop:0.55 #122A49, stop:1 #1B3D68);
    border: none;
}
QLabel#AppTitle {
    color: #FFFFFF;
    font-size: 21pt;
    font-weight: 600;
}
QLabel#AppSubtitle {
    color: #AAC0DC;
    font-size: 9.5pt;
}
QFrame#Pill {
    background: rgba(255, 255, 255, 0.08);
    border: 1px solid rgba(255, 255, 255, 0.16);
    border-radius: 15px;
}
QLabel#PillText {
    color: #DCE7F5;
    font-size: 9pt;
}
QPushButton#ThanksButton {
    background: rgba(255, 255, 255, 0.10);
    color: #EEF5FF;
    border: 1px solid rgba(255, 255, 255, 0.26);
    border-radius: 14px;
    padding: 7px 18px;
    font-size: 9.5pt;
    font-weight: 600;
}
QPushButton#ThanksButton:hover {
    background: rgba(255, 255, 255, 0.18);
    border-color: rgba(255, 255, 255, 0.40);
}
QPushButton#ThanksButton:pressed {
    background: rgba(255, 255, 255, 0.26);
}
QFrame#LineRow {
    background: #F8FAFD;
    border: 1px solid #E1E8F2;
    border-radius: 8px;
}
QPushButton#FormatToggle {
    background: #FFFFFF;
    color: #33475F;
    border: 1px solid #D6E0EC;
    border-radius: 5px;
    padding: 0;
    font-size: 9pt;
    font-weight: 600;
}
QPushButton#FormatToggle:hover {
    background: #EEF3FA;
}
QPushButton#FormatToggle:checked {
    background: #1F5EFF;
    color: #FFFFFF;
    border-color: #1F5EFF;
}
QFrame#QrCard {
    background: #FFFFFF;
    border: 1px solid #DFE6F0;
    border-radius: 12px;
}
QLabel#QrCode {
    background: #FFFFFF;
}
QLabel#ThanksText {
    color: #31445F;
    font-size: 10pt;
    line-height: 1.5;
}
QLabel#ThanksCaption {
    color: #7C8A9D;
    font-size: 8.7pt;
}
QFrame[card="true"] {
    background: #FFFFFF;
    border: 1px solid #DFE6F0;
    border-radius: 14px;
}
QTabWidget#SettingsTabs::pane {
    background: #FFFFFF;
    border: 1px solid #DFE6F0;
    border-radius: 14px;
    top: -1px;
}
QTabWidget#SettingsTabs QTabBar::tab {
    background: #E9EEF6;
    color: #5B6C84;
    border: none;
    padding: 8px 16px;
    margin-right: 4px;
    margin-bottom: 6px;
    border-radius: 8px;
    font-size: 9pt;
    font-weight: 500;
}
QTabWidget#SettingsTabs QTabBar::tab:hover {
    background: #DFE7F2;
    color: #33475F;
}
QTabWidget#SettingsTabs QTabBar::tab:selected {
    background: #1F5EFF;
    color: #FFFFFF;
    font-weight: 600;
}
QLabel#CardTitle {
    color: #12233D;
    font-size: 13pt;
    font-weight: 600;
}
QLabel#SubTitle {
    color: #1D2C43;
    font-size: 10pt;
    font-weight: 600;
    padding: 2px 0;
}
QLabel#Badge {
    background: #EAF1FF;
    color: #2457C5;
    border-radius: 9px;
    padding: 2px 8px;
    font-size: 8.7pt;
    font-weight: 600;
}
QLabel#Caption {
    color: #7B889B;
    font-size: 9pt;
}
QLabel#Muted {
    color: #6C7A90;
    font-size: 9pt;
}
QLabel#Hint {
    color: #7C8A9D;
    font-size: 8.7pt;
}
QLabel#FieldLabel {
    color: #5A6A81;
    font-size: 9pt;
    font-weight: 500;
}
QLabel#EmptyHint {
    color: #91A0B5;
    font-size: 10pt;
    background: transparent;
}
QLabel#ActionStatus {
    color: #172A45;
    font-size: 10.5pt;
    font-weight: 600;
}
QLabel#Percent {
    color: #2457C5;
    font-size: 10pt;
    font-weight: 600;
}
QLabel#DialogTitle {
    color: #14243D;
    font-size: 16pt;
    font-weight: 600;
}
QPushButton {
    font-size: 9.5pt;
    border-radius: 9px;
}
QPushButton#Primary {
    background: #1F5EFF;
    color: #FFFFFF;
    border: 1px solid #1F5EFF;
    min-height: 38px;
    padding: 0 20px;
    font-weight: 600;
}
QPushButton#Primary:hover {
    background: #174FDB;
    border-color: #174FDB;
}
QPushButton#Primary:pressed {
    background: #1143BE;
    border-color: #1143BE;
}
QPushButton#Primary:disabled {
    background: #B8C7E4;
    border-color: #B8C7E4;
    color: #F4F7FD;
}
QPushButton#Secondary {
    background: #FFFFFF;
    color: #263C5A;
    border: 1px solid #D6DFEC;
    min-height: 32px;
    padding: 0 12px;
}
QPushButton#Secondary:hover {
    background: #F5F8FD;
    border-color: #B9C8DE;
}
QPushButton#Secondary:pressed {
    background: #EDF3FC;
}
QPushButton#Secondary:disabled {
    color: #9AA8BA;
    background: #F6F8FB;
    border-color: #E4EAF3;
}
QPushButton#Ghost {
    background: transparent;
    color: #2857B8;
    border: none;
    padding: 5px 7px;
    font-weight: 500;
}
QPushButton#Ghost:hover {
    background: #EDF3FC;
    border-radius: 8px;
}
QPushButton#Ghost:disabled {
    color: #9AA8BA;
}
QPushButton#Danger {
    background: #FFF7F6;
    color: #B42318;
    border: 1px solid #F0C9C4;
    min-height: 32px;
    padding: 0 14px;
}
QPushButton#Danger:hover {
    background: #FEEFEC;
    border-color: #E7A9A2;
}
QPushButton#Danger:disabled {
    color: #C7A8A3;
    background: #FAF6F5;
}
QLineEdit, QDoubleSpinBox {
    background: #FBFCFE;
    border: 1px solid #D7E0EC;
    border-radius: 8px;
    padding: 5px 8px;
    min-height: 29px;
    selection-background-color: #2A64F6;
    selection-color: #FFFFFF;
}
QLineEdit:hover, QDoubleSpinBox:hover {
    border-color: #BBC9DD;
}
QLineEdit:focus, QDoubleSpinBox:focus {
    border: 1px solid #2A64F6;
    background: #FFFFFF;
}
QLineEdit:disabled, QDoubleSpinBox:disabled {
    color: #98A5B8;
    background: #F4F6FA;
    border-color: #E4EAF3;
}
QCheckBox, QRadioButton {
    color: #31445F;
    spacing: 7px;
    font-size: 9.2pt;
}
QCheckBox:disabled, QRadioButton:disabled {
    color: #9AA8BA;
}
QTableWidget {
    background: #FFFFFF;
    border: none;
    selection-background-color: #EAF1FF;
    selection-color: #12233D;
}
QTableWidget::item {
    padding-left: 9px;
    border-bottom: 1px solid #F0F3F8;
}
QTableWidget::item:selected {
    background: #EAF1FF;
    color: #12233D;
}
QHeaderView::section {
    background: #F8FAFD;
    color: #6E7C91;
    border: none;
    border-bottom: 1px solid #E5EBF4;
    padding: 7px 9px;
    font-size: 8.8pt;
    font-weight: 600;
}
QTableCornerButton::section {
    background: #F8FAFD;
    border: none;
}
QScrollArea, QWidget#SettingsPane {
    background: transparent;
    border: none;
}
QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 2px 1px 2px 1px;
}
QScrollBar::handle:vertical {
    background: #C9D4E4;
    min-height: 32px;
    border-radius: 4px;
}
QScrollBar::handle:vertical:hover {
    background: #AEBED5;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: transparent;
}
QFrame#Divider {
    color: #E9EEF5;
    background: #E9EEF5;
    max-height: 1px;
    border: none;
}
QProgressBar {
    border: none;
    border-radius: 4px;
    background: #E8EEF7;
    text-align: center;
    color: transparent;
}
QProgressBar::chunk {
    border-radius: 4px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                stop:0 #2A64F6, stop:1 #4B83FF);
}
QTreeWidget {
    background: #FCFDFF;
    border: 1px solid #E4EAF3;
    border-radius: 9px;
    alternate-background-color: #F8FAFD;
    selection-background-color: #EAF1FF;
    selection-color: #12233D;
}
QTreeWidget::item {
    padding: 5px 4px;
    border-bottom: 1px solid #F2F5F9;
}
QTreeWidget::item:selected {
    background: #EAF1FF;
    color: #12233D;
}
QToolTip {
    background: #13233A;
    color: #F4F7FC;
    border: none;
    padding: 5px 7px;
}
"""


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    font = QFont("Segoe UI", 10)
    font.setHintingPreference(QFont.PreferDefaultHinting)
    app.setFont(font)
    app.setStyleSheet(STYLE)
