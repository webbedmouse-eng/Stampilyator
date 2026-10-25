"""Пересъёмка docs/screenshot.png, docs/editor.png и docs/thanks.png в актуальной теме."""

import os
import sys
from pathlib import Path

# Изолируем настройки, чтобы окно открылось с заводскими значениями.
FAKE_APPDATA = Path(__file__).resolve().parents[1] / ".tmp" / "fake-appdata"
FAKE_APPDATA.mkdir(parents=True, exist_ok=True)
os.environ["APPDATA"] = str(FAKE_APPDATA)
os.environ["LOCALAPPDATA"] = str(FAKE_APPDATA)

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pdfstamp.gui import MainWindow, PdfInfo, ThanksDialog
from pdfstamp.theme import apply_theme

DOCS = ROOT / "docs"


def main() -> int:
    app = QApplication(sys.argv)
    apply_theme(app)
    window = MainWindow()
    info = PdfInfo(ROOT / "samples" / "договор_подряда.pdf", 12, False, False)
    window.table.add_file(info)
    window._load_example_template()
    window._update_counters()
    window._update_ready_state()
    window.show()

    def capture_main() -> None:
        window.grab().save(str(DOCS / "screenshot.png"), "PNG")
        window.tabs.setCurrentIndex(1)
        QTimer.singleShot(350, capture_editor)

    def capture_editor() -> None:
        window.grab().save(str(DOCS / "editor.png"), "PNG")
        window.tabs.setCurrentIndex(0)
        dialog = ThanksDialog(window)
        dialog.show()
        QTimer.singleShot(350, lambda: capture_thanks(dialog))

    def capture_thanks(dialog) -> None:
        dialog.grab().save(str(DOCS / "thanks.png"), "PNG")
        dialog.close()
        app.quit()

    QTimer.singleShot(400, capture_main)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
