"""Скриншоты вкладок «Размер» и «Сохранение» для проверки чекбоксов/радио."""

import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pdfstamp.gui import MainWindow, PdfInfo
from pdfstamp.theme import apply_theme

OUT = ROOT / ".tmp" / "shots"
OUT.mkdir(parents=True, exist_ok=True)


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

    def capture() -> None:
        window.tabs.setCurrentIndex(2)
        QTimer.singleShot(300, capture_size)

    def capture_size() -> None:
        window.grab().save(str(OUT / "04-tab-size.png"), "PNG")
        window.tabs.setCurrentIndex(3)
        QTimer.singleShot(300, capture_output)

    def capture_output() -> None:
        window.grab().save(str(OUT / "05-tab-output.png"), "PNG")
        app.quit()

    QTimer.singleShot(400, capture)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
