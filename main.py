"""Точка входа приложения «Штампилятор»."""

from __future__ import annotations

import ctypes
import logging
import os
import sys
import tempfile
import traceback
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from pdfstamp import __app_name__, __version__
from pdfstamp.gui import MainWindow, resource_path
from pdfstamp.theme import apply_theme


def _setup_logging() -> Path | None:
    """Пытается открыть журнал в доступном каталоге, не блокируя запуск."""
    candidates: list[Path] = []
    for env_name in ("LOCALAPPDATA", "APPDATA"):
        root = os.environ.get(env_name)
        if root:
            candidates.append(Path(root) / "Shtampilyator" / "app.log")
    try:
        candidates.append(Path(tempfile.gettempdir()) / "Shtampilyator" / "app.log")
    except Exception:  # noqa: BLE001
        pass
    candidates.append(Path.home() / "AppData" / "Local" / "Shtampilyator" / "app.log")
    candidates.append(Path.cwd() / "app.log")

    seen: set[str] = set()
    for log_path in candidates:
        key = str(log_path).casefold()
        if key in seen:
            continue
        seen.add(key)
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            # Проверяем не только каталог, но и саму возможность записи файла:
            # существующий app.log мог остаться read-only после другой версии.
            with log_path.open("a", encoding="utf-8"):
                pass
            logging.basicConfig(
                filename=str(log_path),
                level=logging.INFO,
                format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                encoding="utf-8",
                force=True,
            )
            return log_path
        except (OSError, PermissionError, ValueError):
            continue

    # Приложение должно запускаться даже на полностью read-only профиле.
    logging.getLogger().addHandler(logging.NullHandler())
    return None


def _install_exception_hook(log_path: Path | None) -> None:
    def handler(exc_type, exc_value, exc_tb):
        text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        logging.critical("Необработанная ошибка:\n%s", text)
        if QApplication.instance() is not None:
            box = QMessageBox()
            box.setIcon(QMessageBox.Critical)
            box.setWindowTitle("Непредвиденная ошибка")
            hint = (
                f"Подробности записаны в журнал:\n{log_path}"
                if log_path is not None
                else "Файл журнала недоступен."
            )
            box.setText(
                "Приложению не удалось выполнить операцию.\n" + hint
            )
            box.setDetailedText(text)
            box.exec()
        try:
            sys.__excepthook__(exc_type, exc_value, exc_tb)
        except Exception:  # noqa: BLE001
            pass

    sys.excepthook = handler


def main() -> int:
    if sys.platform == "win32":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                f"Volgodonsk.Shtampilyator.{__version__}"
            )
        except Exception:  # noqa: BLE001
            pass

    log_path = _setup_logging()
    _install_exception_hook(log_path)
    logging.info("Запуск приложения версии %s", __version__)

    app = QApplication(sys.argv)
    app.setApplicationName(__app_name__)
    app.setApplicationDisplayName(__app_name__)
    app.setOrganizationName("Volgodonsk")
    app.setApplicationVersion(__version__)
    icon_path = resource_path("assets/app.ico")
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    apply_theme(app)

    window = MainWindow()
    window.show()
    QTimer.singleShot(0, window.raise_)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
