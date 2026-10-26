"""Проверка обновлений на GitHub и диалог предложения обновления."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
)

from . import __version__

API_URL = "https://api.github.com/repos/webbedmouse-eng/Stampilyator/releases/latest"
RELEASES_URL = "https://github.com/webbedmouse-eng/Stampilyator/releases/latest"


@dataclass(frozen=True)
class UpdateInfo:
    version: str
    tag: str
    name: str
    url: str
    notes: str


def parse_version(value: str) -> tuple[int, int, int] | None:
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", value or "")
    if not match:
        return None
    return tuple(int(part) for part in match.groups())


def is_newer(latest: str, current: str = __version__) -> bool:
    latest_parts = parse_version(latest)
    current_parts = parse_version(current)
    return bool(latest_parts and current_parts and latest_parts > current_parts)


class UpdateChecker(QObject):
    """Асинхронно получает последний стабильный релиз GitHub."""

    finished = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._manager = QNetworkAccessManager(self)
        self._reply: QNetworkReply | None = None
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        request = QNetworkRequest(QUrl(API_URL))
        request.setRawHeader(
            b"User-Agent", f"Shtampilyator/{__version__}".encode("ascii")
        )
        request.setRawHeader(b"Accept", b"application/vnd.github+json")
        self._reply = self._manager.get(request)
        self._reply.finished.connect(self._on_finished)

    def _on_finished(self) -> None:
        reply = self._reply
        info: UpdateInfo | None = None
        try:
            if reply is not None and reply.error() == QNetworkReply.NetworkError.NoError:
                payload = json.loads(bytes(reply.readAll()).decode("utf-8"))
                tag = str(payload.get("tag_name", "")).strip()
                if tag:
                    info = UpdateInfo(
                        version=tag.lstrip("vV"),
                        tag=tag,
                        name=str(payload.get("name") or tag),
                        url=str(payload.get("html_url") or RELEASES_URL),
                        notes=str(payload.get("body") or ""),
                    )
        except (ValueError, OSError, UnicodeDecodeError):
            info = None
        finally:
            if reply is not None:
                reply.deleteLater()
            self._reply = None
        self.finished.emit(info)


class UpdateDialog(QDialog):
    """Предложение обновления с возможностью отключить автопроверку."""

    def __init__(self, info: UpdateInfo, parent=None) -> None:
        super().__init__(parent)
        self.info = info
        self.setWindowTitle("Доступно обновление")
        self.setMinimumSize(560, 440)
        self.resize(620, 500)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 20)
        root.setSpacing(12)

        title = QLabel(f"Доступна версия {info.version}")
        title.setObjectName("DialogTitle")
        root.addWidget(title)

        subtitle = QLabel(
            f"Установлена версия {__version__}. Обновление можно скачать "
            "на странице релиза."
        )
        subtitle.setObjectName("Muted")
        subtitle.setWordWrap(True)
        root.addWidget(subtitle)

        notes = QTextBrowser()
        notes.setObjectName("UpdateNotes")
        notes.setOpenExternalLinks(True)
        notes.setPlainText(info.notes.strip() or "Описание изменений не указано.")
        root.addWidget(notes, 1)

        self.disable_check = QCheckBox("Не проверять обновления автоматически")
        root.addWidget(self.disable_check)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.open_button = QPushButton("Открыть страницу обновления")
        self.open_button.setObjectName("Primary")
        self.open_button.clicked.connect(self._open_release)
        buttons.addWidget(self.open_button)
        buttons.addStretch(1)
        later = QPushButton("Позже")
        later.setObjectName("Secondary")
        later.clicked.connect(self.reject)
        buttons.addWidget(later)
        root.addLayout(buttons)

    @property
    def disable_requested(self) -> bool:
        return self.disable_check.isChecked()

    def _open_release(self) -> None:
        QDesktopServices.openUrl(QUrl(self.info.url or RELEASES_URL))
        self.accept()
