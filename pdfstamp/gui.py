"""Оконный интерфейс приложения «Штампилятор»."""

from __future__ import annotations

import ctypes
import logging
import os
import sys
import threading
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import (
    QAbstractNativeEventFilter,
    QProcess,
    QRectF,
    QSettings,
    Qt,
    QThread,
    QTimer,
    QUrl,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QFont,
    QFontMetrics,
    QIcon,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QColorDialog,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QStyle,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .core import (
    CancelledError,
    PdfInfo,
    PdfResult,
    StampError,
    StampOptions,
    StampTemplate,
    build_output_path,
    inspect_pdf,
    load_template,
    parse_color,
    stamp_pdf,
)
from .stamp_editor import StampEditorPage, application_dir
from .theme import COLORS


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------


def resource_path(relative: str) -> Path:
    """Путь к ресурсу как в исходниках, так и в собранном PyInstaller EXE."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / relative


def app_settings() -> QSettings:
    """Настройки в INI-файле: реестр Windows в некоторых сборках Qt недоступен."""
    candidates: list[Path] = []
    appdata = os.environ.get("APPDATA")
    localappdata = os.environ.get("LOCALAPPDATA")
    if appdata:
        candidates.append(Path(appdata) / "Shtampilyator" / "settings.ini")
    if localappdata:
        candidates.append(Path(localappdata) / "Shtampilyator" / "settings.ini")
    candidates.append(Path.home() / ".shtampilyator" / "settings.ini")
    for path in candidates:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            return QSettings(str(path), QSettings.IniFormat)
        except OSError:
            continue
    return QSettings(str(Path.cwd() / "settings.ini"), QSettings.IniFormat)


def plural_ru(number: int, one: str, few: str, many: str) -> str:
    number = abs(number)
    if number % 10 == 1 and number % 100 != 11:
        return one
    if 2 <= number % 10 <= 4 and not 12 <= number % 100 <= 14:
        return few
    return many


def open_local_folder(
    folder: Path | None, select_file: Path | None = None
) -> bool:
    """Открывает папку в Проводнике, при возможности выделяя файл результата."""
    if folder is None:
        return False
    path = Path(folder).expanduser().resolve()
    selected = Path(select_file).expanduser().resolve() if select_file else None
    if not path.is_dir():
        QMessageBox.warning(
            None,
            "Папка не найдена",
            f"Не удалось открыть папку:\n{path}",
        )
        return False
    errors: list[str] = []
    if sys.platform == "win32":
        # 1. ShellExecute через os.startfile — обычно выводит Проводник вперёд.
        try:
            os.startfile(str(path))  # type: ignore[attr-defined]
            return True
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))
        # 2. Прямой ShellExecuteW.
        try:
            result = ctypes.windll.shell32.ShellExecuteW(
                None, "open", str(path), None, None, 1
            )
            if int(result) > 32:
                return True
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))
        # 3. Новое окно Проводника с выделением результата.
        try:
            args = ["/n,", str(path)]
            if selected is not None and selected.is_file():
                args = ["/select,", str(selected)]
            started, _pid = QProcess.startDetached("explorer.exe", args)
            if started:
                return True
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))

    try:
        if QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
            return True
    except Exception as exc:  # noqa: BLE001
        errors.append(str(exc))

    QMessageBox.warning(
        None,
        "Не удалось открыть папку",
        f"{path}\n\n" + ("\n".join(errors) if errors else "Проводник недоступен"),
    )
    return False


# ---------------------------------------------------------------------------
# Перехват WM_CLOSE для стабильного завершения упакованного Qt-приложения
# ---------------------------------------------------------------------------


class _CloseEventFilter(QAbstractNativeEventFilter):
    def __init__(self, window: "MainWindow") -> None:
        super().__init__()
        self._window = window

    def nativeEventFilter(self, event_type, message):  # noqa: N802
        try:
            if not getattr(sys, "frozen", False):
                return False, 0
            if bytes(event_type) not in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
                return False, 0
            msg = wintypes.MSG.from_address(int(message))
            if msg.message != 0x0010:  # WM_CLOSE
                return False, 0
            if int(msg.hWnd) != int(self._window.winId()):
                return False, 0
            if self._window._worker is not None:
                return False, 0
            self._window._save_settings()
            try:
                self._window._settings.sync()
            except Exception:  # noqa: BLE001
                pass
            logging.shutdown()
            os._exit(0)
        except Exception:  # noqa: BLE001
            return False, 0
        return False, 0


# ---------------------------------------------------------------------------
# Данные фоновой обработки
# ---------------------------------------------------------------------------


@dataclass
class FileOutcome:
    source: Path
    page_count: int
    ok: bool
    canceled: bool
    output: Path | None
    message: str
    result: PdfResult | None = None


class StampWorker(QThread):
    """Фоновая обработка PDF, чтобы интерфейс не замирал."""

    progress = Signal(int, int, str)
    file_started = Signal(str)
    file_finished = Signal(object)
    finished_all = Signal(object, bool)

    def __init__(
        self,
        sources: list[tuple[Path, int]],
        template: StampTemplate,
        options: StampOptions,
        output_folder: Path | None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._sources = sources
        self._template = template
        self._options = options
        self._output_folder = output_folder
        self._cancel = threading.Event()

    def stop(self) -> None:
        self._cancel.set()

    def run(self) -> None:  # noqa: D401 - метод Qt
        total = sum(max(0, pages) for _, pages in self._sources)
        done_base = 0
        outcomes: list[FileOutcome] = []
        canceled = False

        for source, page_count in self._sources:
            if self._cancel.is_set():
                canceled = True
                break

            self.file_started.emit(str(source))
            try:
                output = build_output_path(source, self._output_folder)
                file_total = max(1, page_count)

                def on_page(current: int, _total: int, base: int = done_base) -> None:
                    self.progress.emit(
                        min(total, base + current),
                        max(total, 1),
                        f"{source.name} · страница {current} из {file_total}",
                    )

                result = stamp_pdf(
                    source,
                    output,
                    self._template,
                    self._options,
                    progress=on_page,
                    cancel=self._cancel.is_set,
                )
                outcome = FileOutcome(
                    source=source,
                    page_count=result.page_count,
                    ok=True,
                    canceled=False,
                    output=result.output,
                    message="Обработан",
                    result=result,
                )
                outcomes.append(outcome)
                self.file_finished.emit(outcome)
                done_base += result.page_count
            except CancelledError:
                canceled = True
                outcome = FileOutcome(
                    source=source,
                    page_count=page_count,
                    ok=False,
                    canceled=True,
                    output=None,
                    message="Обработка отменена",
                )
                outcomes.append(outcome)
                self.file_finished.emit(outcome)
                break
            except StampError as exc:
                outcome = FileOutcome(
                    source=source,
                    page_count=page_count,
                    ok=False,
                    canceled=False,
                    output=None,
                    message=str(exc),
                )
                outcomes.append(outcome)
                self.file_finished.emit(outcome)
                done_base += page_count
            except Exception as exc:  # noqa: BLE001
                outcome = FileOutcome(
                    source=source,
                    page_count=page_count,
                    ok=False,
                    canceled=False,
                    output=None,
                    message=f"Непредвиденная ошибка: {exc}",
                )
                outcomes.append(outcome)
                self.file_finished.emit(outcome)
                done_base += page_count

            if self._cancel.is_set():
                canceled = True
                break

        self.finished_all.emit(outcomes, canceled)


# ---------------------------------------------------------------------------
# Виджеты
# ---------------------------------------------------------------------------


class StampPreview(QWidget):
    """Превью шаблона на шахматном фоне (видна прозрачность)."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._pixmap: QPixmap | None = None
        self._caption = ""
        self._caption_color = QColor(0, 0, 0)
        self.setMinimumHeight(158)
        self.setMaximumHeight(185)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_caption(self, text: str, color: QColor | None = None) -> None:
        self._caption = (text or "").strip()
        self._caption_color = QColor(color) if color is not None else QColor(0, 0, 0)
        self.update()

    def set_image(self, image: QImage | QPixmap | bytes | None) -> None:
        if image is None:
            self._pixmap = None
        elif isinstance(image, bytes):
            pix = QPixmap()
            pix.loadFromData(image, "PNG")
            self._pixmap = pix
        else:
            self._pixmap = QPixmap(image)
        self.update()

    def clear(self) -> None:
        self._pixmap = None
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - метод Qt
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        bounds = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(bounds, 12, 12)
        painter.setClipPath(path)

        # Шахматка.
        painter.fillRect(bounds, QColor(COLORS.card))
        cell = 11
        light = QColor(COLORS.check_light)
        dark = QColor(COLORS.check_dark)
        y = 0
        row = 0
        while y < self.height():
            x = 0
            col = 0
            while x < self.width():
                if (row + col) % 2 == 0:
                    painter.fillRect(x, y, cell, cell, light)
                else:
                    painter.fillRect(x, y, cell, cell, dark)
                x += cell
                col += 1
            y += cell
            row += 1

        painter.setClipping(False)
        border_pen = QPen(QColor(COLORS.border), 1)
        painter.setPen(border_pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(bounds, 12, 12)

        if self._pixmap is None or self._pixmap.isNull():
            painter.setPen(QColor(COLORS.muted))
            font = QFont("Segoe UI", 10)
            font.setWeight(QFont.Medium)
            painter.setFont(font)
            painter.drawText(
                self.rect().adjusted(22, 18, -22, -24),
                Qt.AlignCenter | Qt.TextWordWrap,
                "Шаблон не выбран\n\nPNG с прозрачным фоном\nили JPG / BMP",
            )
            return

        caption_height = 30.0 if self._caption else 0.0
        target = QRectF(self.rect()).adjusted(
            16, 14, -16, -14 - caption_height
        )
        scaled = self._pixmap.scaled(
            target.size().toSize(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        x = target.x() + (target.width() - scaled.width()) / 2
        y = target.y() + (target.height() - scaled.height()) / 2
        # Лёгкая тень под изображением.
        shadow = QRectF(x + 1.5, y + 2.5, scaled.width(), scaled.height())
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(20, 35, 60, 30))
        painter.drawRoundedRect(shadow.adjusted(2, 2, -2, -2), 4, 4)
        painter.drawPixmap(int(x), int(y), scaled)

        if self._caption:
            caption_rect = QRectF(
                target.left(),
                target.bottom() + 3,
                target.width(),
                max(16.0, caption_height - 3),
            )
            font = QFont("Arial", 9)
            painter.setFont(font)
            painter.setPen(self._caption_color)
            caption = QFontMetrics(font).elidedText(
                self._caption, Qt.ElideRight, int(caption_rect.width())
            )
            painter.drawText(caption_rect, Qt.AlignCenter, caption)


class PdfTable(QTableWidget):
    """Таблица выбранных файлов с подсказкой при пустом списке."""

    files_dropped = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setColumnCount(3)
        self.setHorizontalHeaderLabels(["Документ", "Страниц", "Статус"])
        header = self.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Fixed)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        header.resizeSection(1, 76)
        header.resizeSection(2, 134)
        header.setHighlightSections(False)
        self.verticalHeader().hide()
        self.verticalHeader().setDefaultSectionSize(43)
        self.setShowGrid(False)
        self.setWordWrap(False)
        self.setTextElideMode(Qt.ElideMiddle)
        self.setSelectionBehavior(QTableWidget.SelectRows)
        self.setSelectionMode(QTableWidget.ExtendedSelection)
        self.setEditTriggers(QTableWidget.NoEditTriggers)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAlternatingRowColors(False)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setDropIndicatorShown(False)

        self.empty_label = QLabel(self.viewport())
        self.empty_label.setObjectName("EmptyHint")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.empty_label.setText(
            "Перетащите PDF-файлы сюда\n\n"
            "или нажмите «Добавить PDF»"
        )
        self.empty_label.show()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.empty_label.setGeometry(self.viewport().rect())

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self.empty_label.setGeometry(self.viewport().rect())

    def update_empty_state(self) -> None:
        self.empty_label.setVisible(self.rowCount() == 0)

    def _make_item(self, text: str, tooltip: str = "") -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        if tooltip:
            item.setToolTip(tooltip)
        return item

    def find_row(self, path: Path) -> int:
        normalized = str(path.resolve()).casefold()
        for row in range(self.rowCount()):
            item = self.item(row, 0)
            if item and str(item.data(Qt.UserRole)).casefold() == normalized:
                return row
        return -1

    def add_file(self, info: PdfInfo) -> bool:
        if self.find_row(info.path) >= 0:
            return False
        row = self.rowCount()
        self.insertRow(row)
        name_item = self._make_item(info.path.name, str(info.path))
        name_item.setData(Qt.UserRole, str(info.path.resolve()))
        name_item.setData(Qt.UserRole + 1, info.page_count)
        pages_item = self._make_item(str(info.page_count))
        pages_item.setTextAlignment(Qt.AlignCenter)
        status_item = self._make_item("Ожидает", "Файл добавлен в очередь")
        status_item.setTextAlignment(Qt.AlignCenter)
        status_item.setForeground(QColor(COLORS.muted))
        self.setItem(row, 0, name_item)
        self.setItem(row, 1, pages_item)
        self.setItem(row, 2, status_item)
        self.update_empty_state()
        return True

    def set_status(self, path: Path, text: str, color: str, tooltip: str = "") -> None:
        row = self.find_row(path)
        if row < 0:
            return
        item = self.item(row, 2)
        if item is None:
            item = QTableWidgetItem()
            self.setItem(row, 2, item)
        item.setText(text)
        item.setForeground(QColor(color))
        if tooltip:
            item.setToolTip(tooltip)

    def remove_selected(self) -> int:
        rows = sorted({index.row() for index in self.selectedIndexes()}, reverse=True)
        for row in rows:
            self.removeRow(row)
        self.update_empty_state()
        return len(rows)

    def clear_files(self) -> None:
        self.setRowCount(0)
        self.update_empty_state()

    def sources(self) -> list[tuple[Path, int]]:
        result: list[tuple[Path, int]] = []
        for row in range(self.rowCount()):
            item = self.item(row, 0)
            pages_item = self.item(row, 1)
            if not item:
                continue
            path = Path(str(item.data(Qt.UserRole)))
            pages = int(pages_item.text()) if pages_item else 0
            result.append((path, pages))
        return result

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:  # noqa: N802
        paths: list[Path] = []
        for url in event.mimeData().urls():
            if url.isLocalFile():
                paths.append(Path(url.toLocalFile()))
        if paths:
            event.acceptProposedAction()
            self.files_dropped.emit(paths)
            return
        super().dropEvent(event)


def _status_icon(ok: bool, canceled: bool = False) -> QIcon:
    pixmap = QPixmap(18, 18)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    if ok:
        pen = QPen(QColor(COLORS.ok), 2.4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(pen)
        painter.drawLine(4, 9, 7, 12)
        painter.drawLine(7, 12, 14, 4)
    elif canceled:
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(COLORS.info))
        painter.drawEllipse(2, 2, 14, 14)
        painter.setPen(QPen(QColor("#FFFFFF"), 2.0, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(9, 6, 9, 11)
        painter.drawPoint(9, 13)
    else:
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(COLORS.danger))
        painter.drawEllipse(2, 2, 14, 14)
        painter.setPen(QPen(QColor("#FFFFFF"), 2.0, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(6, 6, 12, 12)
        painter.drawLine(12, 6, 6, 12)
    painter.end()
    return QIcon(pixmap)


class ResultsDialog(QDialog):
    """Итоги обработки с построчными пояснениями."""

    def __init__(
        self,
        outcomes: list[FileOutcome],
        canceled: bool,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Результаты обработки")
        self.setMinimumSize(760, 540)
        self.resize(820, 580)
        self._outcomes = outcomes
        self._report_text = self._build_report_text()

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 20)
        root.setSpacing(14)

        header = QHBoxLayout()
        header.setSpacing(12)
        icon_label = QLabel()
        icon_label.setFixedSize(38, 38)
        has_errors = canceled or any(not item.ok for item in outcomes)
        if has_errors:
            pix = self.style().standardIcon(QStyle.SP_MessageBoxWarning).pixmap(34, 34)
        else:
            pix = self.style().standardIcon(QStyle.SP_DialogApplyButton).pixmap(34, 34)
        title_text = "Результаты обработки"
        icon_label.setPixmap(pix)
        icon_label.setAlignment(Qt.AlignCenter)
        header.addWidget(icon_label)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title = QLabel(title_text)
        title.setObjectName("DialogTitle")
        subtitle = QLabel(self._summary_text(canceled))
        subtitle.setObjectName("Muted")
        subtitle.setWordWrap(True)
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box, 1)
        root.addLayout(header)

        tree = QTreeWidget()
        tree.setObjectName("ResultsTree")
        tree.setColumnCount(3)
        tree.setHeaderLabels(["Файл / страница", "Статус", "Примечание"])
        tree.header().setSectionResizeMode(0, QHeaderView.Interactive)
        tree.header().setSectionResizeMode(1, QHeaderView.Fixed)
        tree.header().setSectionResizeMode(2, QHeaderView.Stretch)
        tree.setColumnWidth(0, 260)
        tree.setColumnWidth(1, 105)
        tree.setRootIsDecorated(True)
        tree.setUniformRowHeights(False)
        tree.setWordWrap(True)
        tree.setAlternatingRowColors(False)
        tree.setIndentation(18)
        tree.setTextElideMode(Qt.ElideNone)

        for outcome in outcomes:
            top = QTreeWidgetItem([outcome.source.name, "", ""])
            top.setToolTip(0, str(outcome.source))
            if outcome.ok and outcome.output:
                top.setText(1, "Готово")
                top.setIcon(1, _status_icon(True))
                top.setForeground(1, QColor(COLORS.ok))
                skipped = len(outcome.result.skipped_pages) if outcome.result else 0
                top.setText(2, f"Страниц: {outcome.page_count}" + (
                    f", без штампа: {skipped}" if skipped else ""
                ))
                top.setToolTip(2, str(outcome.output))
                if outcome.result:
                    for page in outcome.result.placements:
                        child = QTreeWidgetItem(
                            [f"Страница {page.page_number}", "", page.note]
                        )
                        if page.skipped:
                            child.setForeground(2, QColor(COLORS.danger))
                        elif page.fallback:
                            child.setForeground(2, QColor(COLORS.warn))
                        elif page.scaled:
                            child.setForeground(2, QColor(COLORS.warn))
                        else:
                            child.setForeground(2, QColor(COLORS.secondary))
                        top.addChild(child)
                    if outcome.result.fallback_pages or outcome.result.skipped_pages:
                        tree.addTopLevelItem(top)
                        tree.expandItem(top)
                    else:
                        tree.addTopLevelItem(top)
            elif outcome.canceled:
                top.setText(1, "Ошибка")
                top.setIcon(1, _status_icon(False))
                top.setForeground(1, QColor(COLORS.danger))
                top.setText(2, "Обработка отменена")
                tree.addTopLevelItem(top)
                tree.expandItem(top)
            else:
                top.setText(1, "Ошибка")
                top.setIcon(1, _status_icon(False))
                top.setForeground(1, QColor(COLORS.danger))
                top.setText(2, outcome.message)
                top.setToolTip(2, outcome.message)
                tree.addTopLevelItem(top)
                tree.expandItem(top)

        root.addWidget(tree, 1)

        path_hint = QLabel(self._folder_hint())
        path_hint.setObjectName("Hint")
        path_hint.setWordWrap(True)
        path_hint.setTextInteractionFlags(Qt.TextSelectableByMouse)
        root.addWidget(path_hint)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        copy_button = QPushButton("Копировать отчёт")
        copy_button.setObjectName("Secondary")
        copy_button.clicked.connect(self._copy_report)
        buttons.addWidget(copy_button)

        open_button = QPushButton("Открыть папку")
        open_button.setObjectName("Secondary")
        open_button.setEnabled(bool(self._folder()))
        open_button.clicked.connect(self._open_folder)
        buttons.addWidget(open_button)
        buttons.addStretch(1)

        close_button = QPushButton("Закрыть")
        close_button.setObjectName("Primary")
        close_button.clicked.connect(self.accept)
        buttons.addWidget(close_button)
        root.addLayout(buttons)
        close_button.setFocus()

    def _folder(self) -> Path | None:
        for outcome in self._outcomes:
            if outcome.ok and outcome.output:
                return outcome.output.parent
        return None

    def _output_file(self) -> Path | None:
        for outcome in self._outcomes:
            if outcome.ok and outcome.output:
                return outcome.output
        return None

    def _folder_hint(self) -> str:
        folder = self._folder()
        if folder is None:
            return "Успешно обработанных файлов нет."
        return f"Результаты сохранены в: {folder}"

    def _summary_text(self, canceled: bool) -> str:
        ok = [item for item in self._outcomes if item.ok]
        pages = sum(item.page_count for item in ok)
        errors = sum(1 for item in self._outcomes if not item.ok and not item.canceled)
        fallback = sum(
            len(item.result.fallback_pages)
            for item in ok
            if item.result is not None
        )
        skipped = sum(
            len(item.result.skipped_pages)
            for item in ok
            if item.result is not None
        )
        parts: list[str] = []
        if ok:
            parts.append(
                f"{len(ok)} {plural_ru(len(ok), 'файл', 'файла', 'файлов')} · "
                f"{pages} {plural_ru(pages, 'страница', 'страницы', 'страниц')}"
            )
        if errors:
            parts.append(
                f"{errors} {plural_ru(errors, 'ошибка', 'ошибки', 'ошибок')}"
            )
        if fallback:
            parts.append(
                f"перекрытие на {fallback} "
                f"{plural_ru(fallback, 'странице', 'страницах', 'страницах')}"
            )
        if skipped:
            parts.append(
                f"без штампа {skipped} "
                f"{plural_ru(skipped, 'страница', 'страницы', 'страниц')}"
            )
        if canceled and not parts:
            return "Действие остановлено пользователем."
        return " · ".join(parts) if parts else "Нет результатов."

    def _build_report_text(self) -> str:
        lines: list[str] = ["ШТАМПИЛЯТОР · ОТЧЁТ О ПРОСТАНОВКЕ ШТАМПА", ""]
        for outcome in self._outcomes:
            lines.append(f"Файл: {outcome.source}")
            if outcome.ok:
                lines.append(f"  Статус: обработан, страниц: {outcome.page_count}")
                if outcome.result:
                    lines.append(
                        f"  Со штампом: {outcome.result.stamped_pages} из {outcome.page_count}"
                    )
                lines.append(f"  Результат: {outcome.output}")
                if outcome.result:
                    for page in outcome.result.placements:
                        lines.append(f"  Стр. {page.page_number}: {page.note}")
            elif outcome.canceled:
                lines.append("  Статус: отменено")
            else:
                lines.append(f"  Статус: ошибка — {outcome.message}")
            lines.append("")
        return "\n".join(lines)

    def _copy_report(self) -> None:
        QApplication.clipboard().setText(self._report_text)

    def _open_folder(self) -> None:
        open_local_folder(self._folder(), self._output_file())


class ThanksDialog(QDialog):
    """Окно с реквизитами для добровольной поддержки разработчика."""

    WALLET = "4100119660336630"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Поблагодарить")
        self.setMinimumWidth(560)
        self.resize(600, 590)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 20)
        root.setSpacing(14)

        title = QLabel("Поблагодарить")
        title.setObjectName("DialogTitle")
        root.addWidget(title)

        text = QLabel(
            "Если приложение показалось Вам полезным, и помогло в вашей "
            "работе - вы можете поблагодарить разработчика переводом по "
            "QR-ссылке либо на кошелек Юmoney "
            f"<b>{self.WALLET}</b>. Либо просто поделитесь этим приложением."
        )
        text.setObjectName("ThanksText")
        text.setWordWrap(True)
        text.setTextFormat(Qt.RichText)
        text.setTextInteractionFlags(Qt.TextSelectableByMouse)
        root.addWidget(text)

        qr_card = QFrame()
        qr_card.setObjectName("QrCard")
        qr_layout = QVBoxLayout(qr_card)
        qr_layout.setContentsMargins(16, 14, 16, 14)
        qr_layout.setSpacing(8)
        qr_layout.setAlignment(Qt.AlignCenter)

        qr_label = QLabel()
        qr_label.setObjectName("QrCode")
        qr_label.setFixedSize(200, 200)
        qr_label.setAlignment(Qt.AlignCenter)
        qr_path = resource_path("assets/QR.jpg")
        if qr_path.exists():
            pixmap = QPixmap(str(qr_path))
            if not pixmap.isNull():
                dpr = max(1.0, self.devicePixelRatioF())
                target = int(round(200 * dpr))
                scaled = pixmap.scaled(
                    target, target, Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
                scaled.setDevicePixelRatio(dpr)
                qr_label.setPixmap(scaled)
        if qr_label.pixmap() is None or qr_label.pixmap().isNull():
            qr_label.setText("QR-код\nне найден")
        qr_layout.addWidget(qr_label, 0, Qt.AlignCenter)
        caption = QLabel("QR-код для перевода")
        caption.setObjectName("ThanksCaption")
        caption.setAlignment(Qt.AlignCenter)
        qr_layout.addWidget(caption)
        root.addWidget(qr_card, 0, Qt.AlignCenter)

        root.addStretch(1)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.copy_button = QPushButton("Скопировать номер кошелька")
        self.copy_button.setObjectName("Secondary")
        self.copy_button.clicked.connect(self._copy_wallet)
        buttons.addWidget(self.copy_button)
        buttons.addStretch(1)
        close_button = QPushButton("Закрыть")
        close_button.setObjectName("Primary")
        close_button.clicked.connect(self.accept)
        buttons.addWidget(close_button)
        root.addLayout(buttons)
        close_button.setFocus()

    def _copy_wallet(self) -> None:
        QApplication.clipboard().setText(self.WALLET)
        self.copy_button.setText("Номер скопирован")
        QTimer.singleShot(1600, lambda: self.copy_button.setText("Скопировать номер кошелька"))


# ---------------------------------------------------------------------------
# Главное окно
# ---------------------------------------------------------------------------


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Штампилятор")
        self.setMinimumSize(960, 620)
        screen = QApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            self.resize(
                max(960, min(1200, available.width() - 40)),
                max(620, min(810, available.height() - 80)),
            )
        else:
            self.resize(1200, 810)
        icon_path = resource_path("assets/app.ico")
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        self._settings = app_settings()
        self._close_filter = _CloseEventFilter(self)
        QApplication.instance().installNativeEventFilter(self._close_filter)
        self._template: StampTemplate | None = None
        self._template_path: Path | None = None
        self._template_is_example = False
        self._worker: StampWorker | None = None
        self._busy = False
        self._close_after_worker = False
        self._last_outcomes: list[FileOutcome] = []
        self._updating_sizes = False
        self._last_pdf_dir = str(Path.home())
        self._last_template_dir = str(Path.home())
        self._last_output_dir = str(Path.home() / "Documents")
        self._restoring = True
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(500)
        self._save_timer.timeout.connect(self._save_settings)

        self._build_ui()
        self._connect_signals()
        self._restore_settings()
        self._update_output_controls()
        self._update_file_actions()
        self._update_ready_state()

    # ------------------------------------------------------------------ UI
    def _on_tab_changed(self, index: int) -> None:
        editor = index == self.tabs.indexOf(self.editor_page)
        self.documents_card.setVisible(not editor)
        if editor:
            # В редакторе убираем левую карточку и отдаём всю ширину
            # странице штампа.
            self.tabs.setMinimumWidth(0)
            self.tabs.setMaximumWidth(16777215)
            self.tabs.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            self.columns_layout.setStretch(0, 0)
            self.columns_layout.setStretch(1, 1)
        else:
            self.tabs.setMinimumWidth(420)
            self.tabs.setMaximumWidth(420)
            self.tabs.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
            self.columns_layout.setStretch(0, 1)
            self.columns_layout.setStretch(1, 0)

    def _show_thanks(self) -> None:
        ThanksDialog(self).exec()

    def _on_editor_saved(
        self, path: str, width_mm: float, height_mm: float
    ) -> None:
        stamp_path = Path(path)
        if not stamp_path.is_file():
            return
        self._template_is_example = False
        self._load_template(stamp_path, silent=True)
        if self._template is None:
            return
        self._updating_sizes = True
        try:
            self.width_spin.setValue(
                max(self.width_spin.minimum(), min(self.width_spin.maximum(), width_mm))
            )
            self.height_spin.setValue(
                max(
                    self.height_spin.minimum(),
                    min(self.height_spin.maximum(), height_mm),
                )
            )
        finally:
            self._updating_sizes = False
        self._last_template_dir = str(stamp_path.parent)
        self.summary_label.setText(f"Создан шаблон: {stamp_path.name}")
        self.tabs.setCurrentIndex(0)
        self._update_ready_state()
        self._queue_save()

    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("Root")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header())

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(24, 20, 24, 20)
        body_layout.setSpacing(16)
        root.addWidget(body, 1)

        columns = QHBoxLayout()
        columns.setSpacing(16)
        self.columns_layout = columns
        self.documents_card = self._build_documents_card()
        self.settings_panel = self._build_settings_panel()
        columns.addWidget(self.documents_card, 1)
        columns.addWidget(self.settings_panel, 0)
        body_layout.addLayout(columns, 1)
        body_layout.addWidget(self._build_action_card())
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self._on_tab_changed(self.tabs.currentIndex())

    def _build_header(self) -> QWidget:
        header = QFrame()
        header.setObjectName("Header")
        header.setFixedHeight(102)
        layout = QHBoxLayout(header)
        layout.setContentsMargins(26, 16, 28, 16)
        layout.setSpacing(14)

        logo = QLabel()
        logo.setFixedSize(52, 52)
        logo_path = resource_path("assets/logo.png")
        if logo_path.exists():
            logo.setPixmap(
                QPixmap(str(logo_path)).scaled(
                    52, 52, Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
            )
        layout.addWidget(logo)

        titles = QVBoxLayout()
        titles.setSpacing(2)
        app_title = QLabel("Штампилятор")
        app_title.setObjectName("AppTitle")
        subtitle = QLabel("Автоматическое размещение штампа в свободной области PDF")
        subtitle.setObjectName("AppSubtitle")
        titles.addWidget(app_title)
        titles.addWidget(subtitle)
        layout.addLayout(titles)
        layout.addStretch(1)

        self.thanks_button = QPushButton("Поблагодарить")
        self.thanks_button.setObjectName("ThanksButton")
        self.thanks_button.setCursor(Qt.PointingHandCursor)
        self.thanks_button.setToolTip("Поддержать разработчика")
        layout.addWidget(self.thanks_button)
        return header

    def _card(self) -> tuple[QFrame, QVBoxLayout]:
        frame = QFrame()
        frame.setProperty("card", True)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)
        return frame, layout

    def _card_header(self, title: str, badge: QLabel | None = None) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)
        label = QLabel(title)
        label.setObjectName("CardTitle")
        row.addWidget(label)
        if badge is not None:
            row.addWidget(badge)
        row.addStretch(1)
        return row

    def _build_documents_card(self) -> QWidget:
        frame, layout = self._card()
        self.count_badge = QLabel("0 файлов")
        self.count_badge.setObjectName("Badge")
        layout.addLayout(self._card_header("Документы PDF", self.count_badge))

        hint = QLabel(
            "Исходные файлы не изменяются — рядом создаётся копия "
            "с суффиксом «_со_штампом»."
        )
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.table = PdfTable()
        layout.addWidget(self.table, 1)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.add_button = QPushButton("Добавить PDF")
        self.add_button.setObjectName("Secondary")
        self.add_button.setToolTip("Добавить один или несколько PDF (Ctrl+O)")
        self.remove_button = QPushButton("Удалить")
        self.remove_button.setObjectName("Secondary")
        self.remove_button.setToolTip("Удалить выбранные файлы из списка (Delete)")
        self.clear_button = QPushButton("Очистить")
        self.clear_button.setObjectName("Ghost")
        self.clear_button.setToolTip("Очистить список файлов")
        buttons.addWidget(self.add_button)
        buttons.addWidget(self.remove_button)
        buttons.addWidget(self.clear_button)
        buttons.addStretch(1)
        self.pages_badge = QLabel("0 страниц")
        self.pages_badge.setObjectName("Caption")
        buttons.addWidget(self.pages_badge)
        layout.addLayout(buttons)
        return frame

    def _field_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("FieldLabel")
        return label

    def _build_settings_panel(self) -> QWidget:
        tabs = QTabWidget()
        tabs.setObjectName("SettingsTabs")
        tabs.setMinimumWidth(420)
        tabs.setMaximumWidth(420)
        tabs.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        tabs.setUsesScrollButtons(False)
        self.tabs = tabs

        self.editor_page = StampEditorPage(application_dir())
        self.editor_page.saved.connect(self._on_editor_saved)

        tabs.addTab(self._build_template_tab(), "Шаблон")
        tabs.addTab(self.editor_page, "Редактор")
        tabs.addTab(self._build_params_tab(), "Размер")
        tabs.addTab(self._build_output_tab(), "Сохранение")
        return tabs

    def _build_template_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setObjectName("SettingsScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        tab = QWidget()
        tab.setObjectName("SettingsPane")
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)
        scroll.setWidget(tab)

        hint = QLabel(
            "Изображение накладывается на каждую страницу как единый объект. "
            "Лучше использовать PNG с прозрачным фоном."
        )
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.preview = StampPreview()
        layout.addWidget(self.preview)

        template_buttons = QHBoxLayout()
        template_buttons.setSpacing(8)
        self.template_button = QPushButton("Выбрать изображение")
        self.template_button.setObjectName("Secondary")
        self.example_button = QPushButton("Пример")
        self.example_button.setObjectName("Ghost")
        self.example_button.setToolTip("Загрузить демонстрационный шаблон из папки assets")
        template_buttons.addWidget(self.template_button, 1)
        template_buttons.addWidget(self.example_button)
        layout.addLayout(template_buttons)

        self.template_info = QLabel("PNG / JPG / BMP · лучше PNG с прозрачностью")
        self.template_info.setObjectName("Hint")
        self.template_info.setWordWrap(True)
        layout.addWidget(self.template_info)

        self.white_checkbox = QCheckBox("Сделать белый фон шаблона прозрачным")
        self.white_checkbox.setToolTip(
            "Полезно для JPG/PNG со сплошным белым фоном. Белые детали внутри "
            "штампа тоже станут прозрачными."
        )
        layout.addWidget(self.white_checkbox)

        note = QLabel(
            "Прозрачность показывается шахматным фоном. Белый фон убирается "
            "только у пикселей светлее 244 по каждому каналу."
        )
        note.setObjectName("Hint")
        note.setWordWrap(True)
        layout.addWidget(note)

        self.add_text = QCheckBox("Добавить текстовую строку")
        self.add_text.setToolTip("Строка до 30 символов под штампом, по центру")
        layout.addWidget(self.add_text)

        self.text_panel = QWidget()
        text_layout = QVBoxLayout(self.text_panel)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(5)

        text_row = QHBoxLayout()
        text_row.setSpacing(8)
        text_row.addWidget(self._field_label("Текст"))
        self.text_edit = QLineEdit()
        self.text_edit.setMaxLength(30)
        self.text_edit.setPlaceholderText("До 30 символов")
        text_row.addWidget(self.text_edit, 1)
        text_layout.addLayout(text_row)

        text_grid = QGridLayout()
        text_grid.setHorizontalSpacing(10)
        text_grid.setVerticalSpacing(4)
        text_grid.addWidget(self._field_label("Отступ от штампа"), 0, 0)
        text_grid.addWidget(self._field_label("Высота шрифта"), 0, 1)
        self.text_gap_spin = self._mm_spin(
            2.0, "Расстояние от нижнего края штампа до текста"
        )
        self.text_gap_spin.setRange(0.0, 50.0)
        self.text_font_spin = QDoubleSpinBox()
        self.text_font_spin.setRange(4.0, 72.0)
        self.text_font_spin.setDecimals(1)
        self.text_font_spin.setSingleStep(0.5)
        self.text_font_spin.setSuffix(" пт")
        self.text_font_spin.setValue(9.0)
        self.text_font_spin.setToolTip("Высота шрифта Arial в пунктах")
        text_grid.addWidget(self.text_gap_spin, 1, 0)
        text_grid.addWidget(self.text_font_spin, 1, 1)
        text_layout.addLayout(text_grid)

        color_row = QHBoxLayout()
        color_row.setSpacing(6)
        color_row.addWidget(self._field_label("Цвет текста"))
        self.text_color_edit = QLineEdit("#000000")
        self.text_color_edit.setMaxLength(40)
        self.text_color_edit.setPlaceholderText("#000000, red, rgb(0,0,0)")
        color_row.addWidget(self.text_color_edit, 1)
        self.text_color_swatch = QLabel()
        self.text_color_swatch.setFixedSize(25, 25)
        self.text_color_swatch.setToolTip("Предпросмотр цвета текста")
        color_row.addWidget(self.text_color_swatch)
        self.text_color_button = QPushButton("…")
        self.text_color_button.setObjectName("Secondary")
        self.text_color_button.setFixedWidth(46)
        self.text_color_button.setToolTip("Выбрать цвет")
        color_row.addWidget(self.text_color_button)
        text_layout.addLayout(color_row)
        self._update_color_preview()

        layout.addWidget(self.text_panel)
        self.text_panel.setVisible(False)

        layout.addStretch(1)
        return scroll

    def _mm_spin(self, value: float, tooltip: str = "") -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(0.0, 100.0)
        spin.setDecimals(1)
        spin.setSingleStep(1.0)
        spin.setSuffix(" мм")
        spin.setValue(value)
        if tooltip:
            spin.setToolTip(tooltip)
        return spin

    def _build_params_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setObjectName("SettingsScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        tab = QWidget()
        tab.setObjectName("SettingsPane")
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(18, 14, 18, 16)
        layout.setSpacing(8)
        scroll.setWidget(tab)

        size_title = QLabel("Размер штампа")
        size_title.setObjectName("SubTitle")
        layout.addWidget(size_title)

        size_grid = QGridLayout()
        size_grid.setHorizontalSpacing(10)
        size_grid.setVerticalSpacing(4)
        size_grid.addWidget(self._field_label("Ширина"), 0, 0)
        size_grid.addWidget(self._field_label("Высота"), 0, 1)

        self.width_spin = QDoubleSpinBox()
        self.width_spin.setRange(5.0, 500.0)
        self.width_spin.setDecimals(1)
        self.width_spin.setSingleStep(5.0)
        self.width_spin.setSuffix(" мм")
        self.width_spin.setValue(60.0)
        self.width_spin.setKeyboardTracking(False)
        self.height_spin = QDoubleSpinBox()
        self.height_spin.setRange(5.0, 500.0)
        self.height_spin.setDecimals(1)
        self.height_spin.setSingleStep(5.0)
        self.height_spin.setSuffix(" мм")
        self.height_spin.setValue(38.0)
        self.height_spin.setKeyboardTracking(False)
        size_grid.addWidget(self.width_spin, 1, 0)
        size_grid.addWidget(self.height_spin, 1, 1)
        layout.addLayout(size_grid)

        self.preserve_aspect = QCheckBox("Сохранять пропорции шаблона")
        self.preserve_aspect.setChecked(True)
        layout.addWidget(self.preserve_aspect)

        layout.addWidget(self._divider())
        placement_title = QLabel("Расположение")
        placement_title.setObjectName("SubTitle")
        layout.addWidget(placement_title)

        self.allow_overlap = QCheckBox("Разрешить частичное перекрытие содержимого")
        self.allow_overlap.setToolTip(
            "Если включено, при отсутствии полностью свободного места выбирается "
            "точка с минимальным наложением на содержимое."
        )
        layout.addWidget(self.allow_overlap)
        self.ignore_title_block = QCheckBox("Игнорировать область основной надписи")
        self.ignore_title_block.setToolTip(
            "Не размещать штамп в зоне основной надписи ГОСТ 2.104: справа "
            "снизу на чертежах или в нижней полосе текстовых документов."
        )
        layout.addWidget(self.ignore_title_block)

        margin_grid = QGridLayout()
        margin_grid.setHorizontalSpacing(10)
        margin_grid.setVerticalSpacing(4)
        margin_grid.addWidget(self._field_label("Слева"), 0, 0)
        margin_grid.addWidget(self._field_label("Справа"), 0, 1)
        margin_grid.addWidget(self._field_label("Сверху"), 2, 0)
        margin_grid.addWidget(self._field_label("Снизу"), 2, 1)

        self.margin_left_spin = self._mm_spin(8.0, "Отступ от левого края листа")
        self.margin_right_spin = self._mm_spin(8.0, "Отступ от правого края листа")
        self.margin_top_spin = self._mm_spin(8.0, "Отступ от верхнего края листа")
        self.margin_bottom_spin = self._mm_spin(8.0, "Отступ от нижнего края листа")
        margin_grid.addWidget(self.margin_left_spin, 1, 0)
        margin_grid.addWidget(self.margin_right_spin, 1, 1)
        margin_grid.addWidget(self.margin_top_spin, 3, 0)
        margin_grid.addWidget(self.margin_bottom_spin, 3, 1)
        layout.addLayout(margin_grid)

        self.clearance_spin = self._mm_spin(
            3.0, "Дополнительный отступ от текста, линий и изображений"
        )
        clearance_row = QHBoxLayout()
        clearance_row.setSpacing(8)
        clearance_row.addWidget(self._field_label("Зазор до содержимого"))
        clearance_row.addWidget(self.clearance_spin, 1)
        layout.addLayout(clearance_row)

        info = QLabel(
            "Поиск начинается с правого нижнего угла и учитывает реально "
            "нарисованные пиксели, а не габариты векторных объектов. Без "
            "разрешения перекрытия страницы, где штамп не помещается полностью "
            "в свободную область, остаются без штампа."
        )
        info.setObjectName("Hint")
        info.setWordWrap(True)
        layout.addWidget(info)

        layout.addStretch(1)
        return scroll

    def _build_output_tab(self) -> QWidget:
        tab = QWidget()
        tab.setObjectName("SettingsPane")
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(9)

        hint = QLabel(
            "Готовые файлы получают суффикс «_со_штампом». Существующие "
            "файлы не перезаписываются: при совпадении имени добавляется номер."
        )
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.output_near = QRadioButton("Рядом с исходным PDF")
        self.output_near.setChecked(True)
        self.output_folder_radio = QRadioButton("В отдельную папку")
        layout.addWidget(self.output_near)
        layout.addWidget(self.output_folder_radio)

        folder_row = QHBoxLayout()
        folder_row.setSpacing(6)
        self.output_edit = QLineEdit()
        self.output_edit.setPlaceholderText("Путь к папке")
        self.output_browse = QPushButton("…")
        self.output_browse.setObjectName("Secondary")
        self.output_browse.setFixedWidth(38)
        folder_row.addWidget(self.output_edit, 1)
        folder_row.addWidget(self.output_browse)
        layout.addLayout(folder_row)

        layout.addWidget(self._divider())
        note_title = QLabel("Что происходит с исходником")
        note_title.setObjectName("SubTitle")
        layout.addWidget(note_title)
        note = QLabel(
            "Открывается копия PDF, на каждой странице размещается штамп, "
            "результат сохраняется в новый файл. Исходный документ, его "
            "закладки и метаданные не изменяются."
        )
        note.setObjectName("Hint")
        note.setWordWrap(True)
        layout.addWidget(note)

        security = QLabel(
            "PDF с паролем не обрабатываются. Электронная подпись после "
            "изменения документа становится недействительной."
        )
        security.setObjectName("Hint")
        security.setWordWrap(True)
        layout.addWidget(security)
        layout.addStretch(1)
        return tab

    def _divider(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setObjectName("Divider")
        return line

    def _build_action_card(self) -> QWidget:
        card = QFrame()
        card.setProperty("card", True)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(8)

        top = QHBoxLayout()
        top.setSpacing(8)
        self.status_label = QLabel("Готов к работе")
        self.status_label.setObjectName("ActionStatus")
        self.status_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.percent_label = QLabel("0%")
        self.percent_label.setObjectName("Percent")
        top.addWidget(self.status_label, 1)
        top.addWidget(self.percent_label)
        layout.addLayout(top)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(8)
        layout.addWidget(self.progress)

        bottom = QHBoxLayout()
        bottom.setSpacing(8)
        self.summary_label = QLabel("Добавьте PDF и выберите шаблон штампа")
        self.summary_label.setObjectName("Muted")
        self.summary_label.setWordWrap(False)
        bottom.addWidget(self.summary_label, 1)

        self.open_folder_button = QPushButton("Открыть папку")
        self.open_folder_button.setObjectName("Ghost")
        self.open_folder_button.setVisible(False)
        self.cancel_button = QPushButton("Отменить")
        self.cancel_button.setObjectName("Danger")
        self.cancel_button.setVisible(False)
        self.process_button = QPushButton("Поставить штамп")
        self.process_button.setObjectName("Primary")
        self.process_button.setMinimumWidth(176)
        bottom.addWidget(self.open_folder_button)
        bottom.addWidget(self.cancel_button)
        bottom.addWidget(self.process_button)
        layout.addLayout(bottom)
        return card

    def _connect_signals(self) -> None:
        self.add_button.clicked.connect(self._choose_pdfs)
        self.remove_button.clicked.connect(self._remove_selected)
        self.clear_button.clicked.connect(self._clear_files)
        self.table.files_dropped.connect(self._add_paths)
        self.table.itemSelectionChanged.connect(self._update_file_actions)
        self.template_button.clicked.connect(self._choose_template)
        self.example_button.clicked.connect(self._load_example_template)
        self.width_spin.valueChanged.connect(self._width_changed)
        self.height_spin.valueChanged.connect(self._height_changed)
        self.preserve_aspect.toggled.connect(self._aspect_toggled)
        self.white_checkbox.toggled.connect(self._white_background_toggled)
        self.add_text.toggled.connect(self._text_toggled)
        self.output_near.toggled.connect(self._update_output_controls)
        self.output_folder_radio.toggled.connect(self._update_output_controls)
        self.output_browse.clicked.connect(self._choose_output_folder)
        self.process_button.clicked.connect(self._start_processing)
        self.cancel_button.clicked.connect(self._cancel_processing)
        self.open_folder_button.clicked.connect(self._open_last_folder)
        self.thanks_button.clicked.connect(self._show_thanks)
        self.table.itemChanged.connect(lambda _item: self._update_counters())

        # Автосохранение последних настроек.
        for spin in (
            self.width_spin,
            self.height_spin,
            self.margin_left_spin,
            self.margin_right_spin,
            self.margin_top_spin,
            self.margin_bottom_spin,
            self.clearance_spin,
            self.text_gap_spin,
            self.text_font_spin,
        ):
            spin.valueChanged.connect(lambda *_: self._queue_save())
        for check in (
            self.preserve_aspect,
            self.white_checkbox,
            self.allow_overlap,
            self.ignore_title_block,
            self.add_text,
        ):
            check.toggled.connect(lambda *_: self._queue_save())
        self.text_edit.textChanged.connect(lambda *_: self._queue_save())
        self.text_edit.textChanged.connect(lambda *_: self._update_preview_caption())
        self.text_gap_spin.valueChanged.connect(lambda *_: self._update_preview_caption())
        self.text_font_spin.valueChanged.connect(lambda *_: self._update_preview_caption())
        self.text_color_edit.textChanged.connect(self._update_color_preview)
        self.text_color_edit.textChanged.connect(lambda *_: self._update_preview_caption())
        self.text_color_edit.textChanged.connect(lambda *_: self._queue_save())
        self.text_color_button.clicked.connect(self._choose_text_color)
        self.output_edit.textChanged.connect(lambda *_: self._queue_save())
        self.output_near.toggled.connect(lambda *_: self._queue_save())
        self.output_folder_radio.toggled.connect(lambda *_: self._queue_save())

        # Горячие клавиши.
        self._add_shortcut("Ctrl+O", self._choose_pdfs)
        self._add_shortcut("Ctrl+T", self._choose_template)
        self._add_shortcut("Ctrl+Return", self._start_processing)
        self._add_shortcut(
            "Delete",
            self._remove_selected,
            parent=self.table,
            context=Qt.WidgetWithChildrenShortcut,
        )

    def _add_shortcut(
        self, keys: str, slot, parent=None, context=Qt.WindowShortcut
    ) -> None:
        from PySide6.QtGui import QKeySequence, QShortcut

        shortcut = QShortcut(QKeySequence(keys), parent or self)
        shortcut.setContext(context)
        shortcut.activated.connect(slot)

    # ------------------------------------------------------------- settings
    def _restore_settings(self) -> None:
        self._restoring = True
        geometry = self._settings.value("geometry")
        if geometry:
            try:
                self.restoreGeometry(geometry)
            except Exception:  # noqa: BLE001
                pass
        self._last_pdf_dir = self._settings.value(
            "last_pdf_dir", self._last_pdf_dir, type=str
        )
        self._last_template_dir = self._settings.value(
            "last_template_dir", self._last_template_dir, type=str
        )
        self._last_output_dir = self._settings.value(
            "last_output_dir", self._last_output_dir, type=str
        )

        self.white_checkbox.setChecked(
            self._settings.value("white_background", False, type=bool)
        )
        self.preserve_aspect.setChecked(
            self._settings.value("preserve_aspect", True, type=bool)
        )
        legacy_margin = self._settings.value("margin_mm", 8.0, type=float)
        self.margin_left_spin.setValue(
            self._settings.value("margin_left_mm", legacy_margin, type=float)
        )
        self.margin_right_spin.setValue(
            self._settings.value("margin_right_mm", legacy_margin, type=float)
        )
        self.margin_top_spin.setValue(
            self._settings.value("margin_top_mm", legacy_margin, type=float)
        )
        self.margin_bottom_spin.setValue(
            self._settings.value("margin_bottom_mm", legacy_margin, type=float)
        )
        self.clearance_spin.setValue(
            self._settings.value("clearance_mm", 3.0, type=float)
        )
        self.allow_overlap.setChecked(
            self._settings.value("allow_overlap", False, type=bool)
        )
        self.ignore_title_block.setChecked(
            self._settings.value("ignore_title_block", False, type=bool)
        )
        self.width_spin.setValue(self._settings.value("width_mm", 60.0, type=float))
        self.height_spin.setValue(
            self._settings.value("height_mm", 38.0, type=float)
        )
        self.text_edit.setText(
            self._settings.value("text_line", "", type=str)
        )
        self.text_gap_spin.setValue(
            self._settings.value("text_gap_mm", 2.0, type=float)
        )
        self.text_font_spin.setValue(
            self._settings.value("text_font_size_pt", 9.0, type=float)
        )
        self.text_color_edit.setText(
            self._settings.value("text_color", "#000000", type=str)
        )
        self.add_text.setChecked(
            self._settings.value("add_text", False, type=bool)
        )
        self._text_toggled(self.add_text.isChecked())

        if self._settings.value("output_mode", "near", type=str) == "folder":
            self.output_folder_radio.setChecked(True)
        else:
            self.output_near.setChecked(True)
        saved_folder = self._settings.value("output_folder", "", type=str)
        if saved_folder:
            self.output_edit.setText(saved_folder)
        elif self._last_output_dir:
            self.output_edit.setText(str(Path(self._last_output_dir) / "Штампованные PDF"))

        template_path = self._settings.value("template_path", "", type=str)
        if template_path and Path(template_path).is_file():
            self._load_template(Path(template_path), silent=True)
        self._update_counters()
        self._restoring = False

    def _queue_save(self) -> None:
        if self._restoring:
            return
        self._save_timer.start()

    def _save_settings(self) -> None:
        if self._restoring:
            return
        self._settings.setValue("geometry", self.saveGeometry())
        self._settings.setValue("last_pdf_dir", self._last_pdf_dir)
        self._settings.setValue("last_template_dir", self._last_template_dir)
        self._settings.setValue("last_output_dir", self._last_output_dir)
        self._settings.setValue("width_mm", self.width_spin.value())
        self._settings.setValue("height_mm", self.height_spin.value())
        self._settings.setValue("preserve_aspect", self.preserve_aspect.isChecked())
        self._settings.setValue("margin_left_mm", self.margin_left_spin.value())
        self._settings.setValue("margin_right_mm", self.margin_right_spin.value())
        self._settings.setValue("margin_top_mm", self.margin_top_spin.value())
        self._settings.setValue("margin_bottom_mm", self.margin_bottom_spin.value())
        self._settings.setValue("clearance_mm", self.clearance_spin.value())
        self._settings.setValue("allow_overlap", self.allow_overlap.isChecked())
        self._settings.setValue(
            "ignore_title_block", self.ignore_title_block.isChecked()
        )
        self._settings.setValue("add_text", self.add_text.isChecked())
        self._settings.setValue("text_line", self.text_edit.text())
        self._settings.setValue("text_gap_mm", self.text_gap_spin.value())
        self._settings.setValue(
            "text_font_size_pt", self.text_font_spin.value()
        )
        self._settings.setValue("text_color", self.text_color_edit.text())
        self._settings.setValue("white_background", self.white_checkbox.isChecked())
        self._settings.setValue(
            "output_mode", "folder" if self.output_folder_radio.isChecked() else "near"
        )
        self._settings.setValue("output_folder", self.output_edit.text().strip())
        template_path = str(self._template_path) if self._template_path else ""
        # Во frozen-сборке пример распаковывается во временный _MEIPASS и
        # исчезает после закрытия приложения; такой путь не сохраняем.
        if self._template_is_example and getattr(sys, "frozen", False):
            template_path = ""
        self._settings.setValue("template_path", template_path)
        self._settings.sync()

    # --------------------------------------------------------------- files
    def _choose_pdfs(self) -> None:
        if self._busy:
            return
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Выберите PDF-файлы",
            self._last_pdf_dir,
            "PDF-файлы (*.pdf);;Все файлы (*.*)",
        )
        if paths:
            self._last_pdf_dir = str(Path(paths[0]).parent)
            self._add_paths([Path(path) for path in paths])

    def _add_paths(self, paths: list[Path]) -> None:
        if self._busy:
            return
        pdfs: list[Path] = []
        images: list[Path] = []
        for path in paths:
            suffix = path.suffix.lower()
            if suffix == ".pdf":
                pdfs.append(path)
            elif suffix in {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff"}:
                images.append(path)
        if not pdfs:
            if len(images) == 1:
                self._load_template(images[0])
                return
            if images:
                QMessageBox.information(
                    self,
                    "Нет PDF-файлов",
                    "Перетащено изображений: "
                    f"{len(images)}. Загрузить изображение как шаблон можно "
                    "только по одному — используйте кнопку «Выбрать изображение».",
                )
                return
            QMessageBox.information(
                self,
                "Нет PDF-файлов",
                "Перетащенные файлы не являются PDF и не были добавлены.",
            )
            return

        errors: list[str] = []
        added = 0
        duplicates = 0
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            for path in pdfs:
                try:
                    info = inspect_pdf(path)
                    if info.page_count <= 0:
                        errors.append(f"{path.name}: в документе нет страниц.")
                        continue
                    if self.table.add_file(info):
                        added += 1
                    else:
                        duplicates += 1
                except StampError as exc:
                    errors.append(str(exc))
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{path.name}: {exc}")
        finally:
            QApplication.restoreOverrideCursor()

        if added:
            self._last_pdf_dir = str(pdfs[0].parent)
            self.table.clearSelection()
            self.table.setCurrentCell(-1, -1)
        self._update_counters()
        self._update_file_actions()
        self._update_ready_state()
        ignored = len(paths) - len(pdfs)
        if added or ignored:
            summary = f"Добавлено файлов: {added}" if added else "PDF не добавлены"
            if duplicates:
                summary += f" · пропущено дубликатов: {duplicates}"
            if ignored:
                summary += (
                    f" · не PDF и пропущено: {ignored} "
                    f"({plural_ru(ignored, 'файл', 'файла', 'файлов')})"
                )
            self.summary_label.setText(summary)
        if errors:
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Warning)
            box.setWindowTitle("Не удалось добавить файлы")
            box.setText("Некоторые файлы не были добавлены:")
            box.setDetailedText("\n\n".join(errors))
            box.exec()

    def _remove_selected(self) -> None:
        if self._busy:
            return
        removed = self.table.remove_selected()
        if removed:
            self._update_counters()
            self._update_file_actions()
            self._update_ready_state()

    def _clear_files(self) -> None:
        if self._busy or self.table.rowCount() == 0:
            return
        if self._ask_yes_no(
            "Очистить список",
            "Удалить все PDF из списка? Сами файлы останутся на диске.",
        ):
            self.table.clear_files()
            self._update_counters()
            self._update_file_actions()
            self._update_ready_state()

    def _update_counters(self) -> None:
        count = self.table.rowCount()
        pages = sum(page_count for _, page_count in self.table.sources())
        self.count_badge.setText(
            f"{count} {plural_ru(count, 'файл', 'файла', 'файлов')}"
        )
        self.pages_badge.setText(
            f"{pages} {plural_ru(pages, 'страница', 'страницы', 'страниц')}"
        )

    def _update_file_actions(self) -> None:
        has_files = self.table.rowCount() > 0
        has_selection = bool(self.table.selectedIndexes())
        self.remove_button.setEnabled(has_files and has_selection and not self._busy)
        self.clear_button.setEnabled(has_files and not self._busy)
        self.add_button.setEnabled(not self._busy)
        self.table.setEnabled(not self._busy)
        self._update_ready_state()

    # -------------------------------------------------------------- template
    def _choose_template(self) -> None:
        if self._busy:
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Выберите изображение штампа",
            self._last_template_dir,
            "Изображения (*.png *.jpg *.jpeg *.bmp *.webp *.tif *.tiff);;Все файлы (*.*)",
        )
        if path:
            self._last_template_dir = str(Path(path).parent)
            self._load_template(Path(path))

    def _load_example_template(self) -> None:
        if self._busy:
            return
        path = resource_path("assets/example_stamp.png")
        if not path.exists():
            QMessageBox.warning(
                self, "Шаблон не найден", f"Не найден файл примера:\n{path}"
            )
            return
        self._load_template(path, example=True)

    def _load_template(self, path: Path, silent: bool = False, example: bool = False) -> None:
        error: str | None = None
        template: StampTemplate | None = None
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            template = load_template(path, self.white_checkbox.isChecked())
        except StampError as exc:
            error = str(exc)
        except Exception as exc:  # noqa: BLE001
            error = str(exc)
        finally:
            # Снимаем ровно один уровень курсора: снаружи может оставаться
            # курсор ожидания от перетаскивания файлов.
            if QApplication.overrideCursor() is not None:
                QApplication.restoreOverrideCursor()

        if template is None:
            if not silent:
                QMessageBox.warning(self, "Не удалось загрузить шаблон", error or "")
            return

        if not silent:
            self._template_is_example = example
        self._template = template
        self._template_path = path
        pix = QPixmap()
        pix.loadFromData(template.png_bytes, "PNG")
        self.preview.set_image(pix)
        self._update_preview_caption()
        suffix = " · пример" if example else ""
        self.template_info.setText(
            f"{path.name} · {template.width_px}×{template.height_px} px"
            f" · {template.aspect:.2f}:1{suffix}"
        )
        if self.preserve_aspect.isChecked():
            self._sync_height_from_width()
        self._update_ready_state()
        if not silent:
            self.summary_label.setText(f"Шаблон загружен: {path.name}")
        self._queue_save()

    def _white_background_toggled(self, _checked: bool) -> None:
        if self._busy or self._template_path is None:
            return
        self._load_template(self._template_path, silent=True)

    def _width_changed(self, value: float) -> None:
        if self._updating_sizes or not self.preserve_aspect.isChecked():
            return
        if self._template is None:
            return
        self._updating_sizes = True
        try:
            height = value / max(0.01, self._template.aspect)
            self.height_spin.setValue(max(self.height_spin.minimum(), min(self.height_spin.maximum(), height)))
        finally:
            self._updating_sizes = False

    def _height_changed(self, value: float) -> None:
        if self._updating_sizes or not self.preserve_aspect.isChecked():
            return
        if self._template is None:
            return
        self._updating_sizes = True
        try:
            width = value * self._template.aspect
            self.width_spin.setValue(max(self.width_spin.minimum(), min(self.width_spin.maximum(), width)))
        finally:
            self._updating_sizes = False

    def _sync_height_from_width(self) -> None:
        if self._template is None:
            return
        self._updating_sizes = True
        try:
            height = self.width_spin.value() / max(0.01, self._template.aspect)
            self.height_spin.setValue(
                max(self.height_spin.minimum(), min(self.height_spin.maximum(), height))
            )
        finally:
            self._updating_sizes = False

    def _aspect_toggled(self, checked: bool) -> None:
        if checked and self._template is not None:
            self._sync_height_from_width()

    def _text_toggled(self, checked: bool) -> None:
        self.text_panel.setVisible(checked)
        self._update_preview_caption()
        self._queue_save()

    def _update_preview_caption(self) -> None:
        if not hasattr(self, "preview"):
            return
        if self.add_text.isChecked():
            text = self.text_edit.text().strip()
            try:
                red, green, blue = parse_color(self.text_color_edit.text())
                color = QColor(red, green, blue)
            except StampError:
                color = QColor(0, 0, 0)
            self.preview.set_caption(text, color)
        else:
            self.preview.set_caption("", QColor(0, 0, 0))

    def _update_color_preview(self) -> None:
        try:
            red, green, blue = parse_color(self.text_color_edit.text())
        except StampError as exc:
            self.text_color_swatch.setStyleSheet(
                f"background: {COLORS.danger_soft}; "
                f"border: 1px solid {COLORS.danger}; border-radius: 5px;"
            )
            self.text_color_swatch.setToolTip(str(exc))
            self.text_color_edit.setToolTip(str(exc))
            return
        self.text_color_swatch.setStyleSheet(
            f"background: rgb({red}, {green}, {blue}); "
            f"border: 1px solid {COLORS.faint}; border-radius: 5px;"
        )
        self.text_color_swatch.setToolTip(f"RGB({red}, {green}, {blue})")
        self.text_color_edit.setToolTip("")

    def _choose_text_color(self) -> None:
        try:
            red, green, blue = parse_color(self.text_color_edit.text())
            initial = QColor(red, green, blue)
        except StampError:
            initial = QColor(0, 0, 0)
        color = QColorDialog.getColor(initial, self, "Цвет текста")
        if color.isValid():
            self.text_color_edit.setText(color.name().upper())

    # --------------------------------------------------------------- output
    def _update_output_controls(self) -> None:
        folder_mode = self.output_folder_radio.isChecked()
        enabled = folder_mode and not self._busy
        self.output_edit.setEnabled(enabled)
        self.output_browse.setEnabled(enabled)

    def _choose_output_folder(self) -> None:
        start = self.output_edit.text().strip() or self._last_output_dir
        folder = QFileDialog.getExistingDirectory(
            self, "Выберите папку для результатов", start
        )
        if folder:
            self.output_edit.setText(folder)
            self._last_output_dir = folder
            self.output_folder_radio.setChecked(True)

    # -------------------------------------------------------------- process
    def _update_ready_state(self) -> None:
        ready = (
            not self._busy
            and self.table.rowCount() > 0
            and self._template is not None
        )
        self.process_button.setEnabled(ready)
        if self._busy:
            return
        if self._template is None and self.table.rowCount() == 0:
            self.summary_label.setText("Добавьте PDF и выберите шаблон штампа")
        elif self._template is None:
            self.summary_label.setText("Выберите шаблон штампа")
        elif self.table.rowCount() == 0:
            self.summary_label.setText("Добавьте PDF-файлы для обработки")
        elif not ready:
            self.summary_label.setText("Проверьте параметры обработки")
        else:
            count = self.table.rowCount()
            pages = sum(p for _, p in self.table.sources())
            self.summary_label.setText(
                f"Готов к работе · {count} {plural_ru(count, 'файл', 'файла', 'файлов')} · "
                f"{pages} {plural_ru(pages, 'страница', 'страницы', 'страниц')}"
            )
        self.process_button.setToolTip(
            "Обработать все PDF и добавить штамп"
            if ready
            else "Добавьте PDF и выберите шаблон штампа"
        )

    def _start_processing(self) -> None:
        if self._busy or self._worker is not None:
            return
        if self.table.rowCount() == 0:
            QMessageBox.information(
                self, "Нет файлов", "Добавьте хотя бы один PDF-файл."
            )
            return
        if self._template is None:
            QMessageBox.information(
                self, "Нет шаблона", "Выберите изображение штампа."
            )
            return
        if self.width_spin.value() <= 0 or self.height_spin.value() <= 0:
            QMessageBox.warning(
                self, "Неверный размер", "Размер штампа должен быть больше нуля."
            )
            return

        output_folder: Path | None = None
        if self.output_folder_radio.isChecked():
            raw = self.output_edit.text().strip()
            if not raw:
                QMessageBox.warning(
                    self,
                    "Не выбрана папка",
                    "Выберите папку для сохранения результатов.",
                )
                self.output_browse.setFocus()
                return
            output_folder = Path(raw).expanduser().resolve()
            try:
                output_folder.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                QMessageBox.warning(
                    self,
                    "Папка недоступна",
                    f"Не удалось создать папку:\n{output_folder}\n\n{exc}",
                )
                return
            self._last_output_dir = str(output_folder)

        # Перезагружаем шаблон с актуальной настройкой прозрачности.
        try:
            template = load_template(
                self._template_path, self.white_checkbox.isChecked()
            )
        except StampError as exc:
            QMessageBox.warning(self, "Ошибка шаблона", str(exc))
            return

        options = StampOptions(
            width_mm=self.width_spin.value(),
            height_mm=self.height_spin.value(),
            margin_left_mm=self.margin_left_spin.value(),
            margin_right_mm=self.margin_right_spin.value(),
            margin_top_mm=self.margin_top_spin.value(),
            margin_bottom_mm=self.margin_bottom_spin.value(),
            clearance_mm=self.clearance_spin.value(),
            allow_overlap=self.allow_overlap.isChecked(),
            ignore_title_block=self.ignore_title_block.isChecked(),
            add_text=self.add_text.isChecked(),
            text=self.text_edit.text(),
            text_gap_mm=self.text_gap_spin.value(),
            text_font_size_pt=self.text_font_spin.value(),
            text_color=self.text_color_edit.text(),
            remove_white_background=self.white_checkbox.isChecked(),
        )
        try:
            options.validate()
        except StampError as exc:
            QMessageBox.warning(self, "Неверные параметры", str(exc))
            return

        sources = self.table.sources()
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item:
                self.table.set_status(
                    Path(str(item.data(Qt.UserRole))),
                    "В очереди",
                    COLORS.muted,
                    "Ожидает обработки",
                )

        self._save_settings()
        self._set_busy(True)
        self.progress.setValue(0)
        self.percent_label.setText("0%")
        self.status_label.setText("Подготовка к обработке…")
        self.open_folder_button.setVisible(False)
        self._last_outcomes = []

        worker = StampWorker(sources, template, options, output_folder, self)
        self._worker = worker
        worker.progress.connect(self._on_progress)
        worker.file_started.connect(self._on_file_started)
        worker.file_finished.connect(self._on_file_finished)
        worker.finished_all.connect(self._on_finished)
        worker.finished.connect(self._on_worker_stopped)
        worker.start()

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        for widget in (
            self.add_button,
            self.remove_button,
            self.clear_button,
            self.table,
            self.template_button,
            self.example_button,
            self.width_spin,
            self.height_spin,
            self.preserve_aspect,
            self.margin_left_spin,
            self.margin_right_spin,
            self.margin_top_spin,
            self.margin_bottom_spin,
            self.clearance_spin,
            self.allow_overlap,
            self.ignore_title_block,
            self.editor_page,
            self.add_text,
            self.text_panel,
            self.text_edit,
            self.text_gap_spin,
            self.text_font_spin,
            self.text_color_edit,
            self.text_color_button,
            self.white_checkbox,
            self.output_near,
            self.output_folder_radio,
        ):
            widget.setEnabled(not busy)
        self._update_output_controls()
        self.process_button.setEnabled(not busy)
        self.cancel_button.setVisible(busy)
        self.cancel_button.setEnabled(busy)
        self._update_file_actions()

    def _cancel_processing(self) -> None:
        if self._worker is None:
            return
        self.cancel_button.setEnabled(False)
        self.status_label.setText("Останавливаем обработку…")
        self._worker.stop()

    def _on_progress(self, done: int, total: int, message: str) -> None:
        total = max(1, total)
        percent = max(0, min(100, int(round(done * 100.0 / total))))
        self.progress.setValue(percent)
        self.percent_label.setText(f"{percent}%")
        self.status_label.setText(message)

    def _on_file_started(self, source: str) -> None:
        self.table.set_status(
            Path(source), "Обработка…", COLORS.warn, "Идёт анализ страниц и вставка штампа"
        )

    def _on_file_finished(self, outcome: FileOutcome) -> None:
        if outcome.ok:
            tooltip = f"Результат: {outcome.output}"
            if outcome.result and outcome.result.warnings:
                tooltip += "\n" + "\n".join(outcome.result.warnings)
            self.table.set_status(
                outcome.source, "Готово", COLORS.ok, tooltip
            )
        elif outcome.canceled:
            self.table.set_status(
                outcome.source, "Отменено", COLORS.info, outcome.message
            )
        else:
            self.table.set_status(
                outcome.source, "Ошибка", COLORS.danger, outcome.message
            )

    def _on_finished(self, outcomes: list[FileOutcome], canceled: bool) -> None:
        self._last_outcomes = outcomes
        self._set_busy(False)
        self.cancel_button.setVisible(False)
        self.progress.setValue(100 if not canceled else self.progress.value())
        if canceled:
            self.percent_label.setText(f"{self.progress.value()}%")
            self.status_label.setText("Обработка отменена")
        else:
            self.percent_label.setText("100%")
            ok = [item for item in outcomes if item.ok]
            pages = sum(item.page_count for item in ok)
            self.status_label.setText(
                f"Готово: {len(ok)} {plural_ru(len(ok), 'файл', 'файла', 'файлов')} · "
                f"{pages} {plural_ru(pages, 'страница', 'страницы', 'страниц')}"
            )

        successful = [item for item in outcomes if item.ok and item.output]
        self.open_folder_button.setVisible(bool(successful))
        self._update_ready_state()

        if canceled:
            done_pages = sum(item.page_count for item in successful)
            self.summary_label.setText(
                f"Обработка отменена · успешно обработано страниц: {done_pages}"
            )
            processed = {str(item.source.resolve()).casefold() for item in outcomes}
            for row in range(self.table.rowCount()):
                table_item = self.table.item(row, 0)
                if not table_item:
                    continue
                path = Path(str(table_item.data(Qt.UserRole)))
                if str(path.resolve()).casefold() not in processed:
                    self.table.set_status(
                        path, "Отменено", COLORS.info, "Файл не обрабатывался"
                    )
        elif len(successful) == len(outcomes):
            skipped_total = sum(
                len(item.result.skipped_pages)
                for item in successful
                if item.result is not None
            )
            if skipped_total:
                self.summary_label.setText(
                    f"Готово, но {skipped_total} "
                    f"{plural_ru(skipped_total, 'страница', 'страницы', 'страниц')} "
                    "без штампа — включите частичное перекрытие."
                )
            else:
                self.summary_label.setText(
                    "Штамп добавлен. Исходные PDF не изменены."
                )
        else:
            self.summary_label.setText(
                "Обработка завершена с ошибками — подробности в отчёте."
            )

        if self._close_after_worker:
            return
        dialog = ResultsDialog(outcomes, canceled, self)
        dialog.exec()

    def _on_worker_stopped(self) -> None:
        worker = self._worker
        self._worker = None
        if worker is not None:
            worker.deleteLater()
        if self._close_after_worker:
            self._close_after_worker = False
            QTimer.singleShot(0, self.close)

    def _open_last_folder(self) -> None:
        for outcome in self._last_outcomes:
            if outcome.ok and outcome.output:
                open_local_folder(outcome.output.parent, outcome.output)
                return
        if self._last_output_dir:
            open_local_folder(Path(self._last_output_dir))

    # ---------------------------------------------------------------- window
    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dropEvent(self, event) -> None:  # noqa: N802
        if self._busy:
            return
        paths = [
            Path(url.toLocalFile())
            for url in event.mimeData().urls()
            if url.isLocalFile()
        ]
        if paths:
            event.acceptProposedAction()
            self._add_paths(paths)
            return
        super().dropEvent(event)

    def _ask_yes_no(self, title: str, text: str) -> bool:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Question)
        box.setWindowTitle(title)
        box.setText(text)
        yes_button = box.addButton("Да", QMessageBox.AcceptRole)
        no_button = box.addButton("Нет", QMessageBox.RejectRole)
        box.setDefaultButton(no_button)
        box.exec()
        return box.clickedButton() is yes_button

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._worker is not None:
            if not self._ask_yes_no(
                "Обработка продолжается",
                "Остановить обработку и закрыть приложение?",
            ):
                event.ignore()
                return
            self._close_after_worker = True
            self._worker.stop()
            self.cancel_button.setEnabled(False)
            self.status_label.setText("Останавливаем обработку…")
            event.ignore()
            return
        self._save_settings()
        try:
            self._settings.sync()
        except Exception:  # noqa: BLE001
            pass

        # На Windows упакованное PySide6-приложение иногда падает при нативном
        # разрушении сложного дерева виджетов уже после закрытия окна. К этому
        # моменту настройки сохранены, обработка остановлена, файлы закрыты.
        if getattr(sys, "frozen", False) and os.environ.get("SHTAMPILYATOR_SOFT_EXIT") != "1":
            logging.shutdown()
            os._exit(0)

        event.accept()
