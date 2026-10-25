"""Скриншоты главного окна и диалогов для визуальной проверки темы."""

import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pdfstamp.gui import FileOutcome, MainWindow, PdfInfo, ResultsDialog
from pdfstamp.theme import apply_theme

OUT = ROOT / ".tmp" / "shots"
OUT.mkdir(parents=True, exist_ok=True)


def shot(widget, name: str) -> None:
    widget.grab().save(str(OUT / f"{name}.png"), "PNG")


def main() -> int:
    app = QApplication(sys.argv)
    apply_theme(app)
    window = MainWindow()

    # Наполняем интерфейс демо-данными.
    info = PdfInfo(ROOT / "samples" / "договор_подряда.pdf", 12, False, False)
    window.table.add_file(info)
    info2 = PdfInfo(ROOT / "samples" / "чертеж_А3.pdf", 4, False, False)
    window.table.add_file(info2)
    window._load_example_template()
    window._update_counters()
    window._update_ready_state()

    window.show()

    def capture() -> None:
        shot(window, "01-main")

        window.tabs.setCurrentIndex(1)
        QTimer.singleShot(400, capture_editor)

    def capture_editor() -> None:
        shot(window, "02-editor")
        window.tabs.setCurrentIndex(0)

        outcomes = [
            FileOutcome(info.path, 12, True, False, info.path.with_name("договор_подряда_со_штампом.pdf"), "Обработан"),
            FileOutcome(info2.path, 4, False, True, None, "Обработка отменена"),
            FileOutcome(ROOT / "samples" / "повреждён.pdf", 0, False, False, None, "Файл не является PDF"),
        ]
        dialog = ResultsDialog(outcomes, True, window)
        dialog.show()
        QTimer.singleShot(400, lambda: capture_dialog(dialog))

    def capture_dialog(dialog) -> None:
        shot(dialog, "03-results")
        dialog.close()
        app.quit()

    QTimer.singleShot(400, capture)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
