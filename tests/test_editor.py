"""Тесты редактора собственного штампа."""

from __future__ import annotations

import sys
import unittest

from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication

from pdfstamp.core import StampError
from pdfstamp.stamp_editor import (
    SignatureImage,
    StampDesign,
    TextLine,
    content_required_size,
    render_stamp,
    validate_design,
)


class StampEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def test_renders_transparent_png_canvas(self) -> None:
        design = StampDesign(lines=["СОГЛАСОВАНО"], ink_color="#332A7A")
        validate_design(design)
        image = render_stamp(design, dpi=300)
        self.assertEqual((image.width(), image.height()), (1181, 827))
        self.assertTrue(image.hasAlphaChannel())
        # По краю проходит рамка, внутри фон прозрачный.
        self.assertEqual(image.pixelColor(0, 0).alpha(), 255)
        self.assertEqual(image.pixelColor(image.width() // 2, 100).alpha(), 0)

    def test_rejects_too_long_line(self) -> None:
        design = StampDesign(lines=["О" * 80])
        with self.assertRaises(StampError):
            validate_design(design)

    def test_rejects_empty_lines(self) -> None:
        design = StampDesign(lines=["", "   "])
        with self.assertRaises(StampError):
            validate_design(design)

    def test_renders_signature_with_transform(self) -> None:
        signature_image = QImage(200, 80, QImage.Format_ARGB32_Premultiplied)
        signature_image.fill(QColor(0, 0, 0, 0))
        painter = QPainter(signature_image)
        painter.setPen(QColor("#111111"))
        painter.drawLine(5, 60, 190, 20)
        painter.end()
        design = StampDesign(
            lines=[TextLine(text="СОГЛАСОВАНО")],
            signature=SignatureImage(
                image=signature_image,
                x_mm=50,
                y_mm=45,
                width_mm=30,
                height_mm=12,
                rotation_deg=15,
            ),
        )
        validate_design(design)
        image = render_stamp(design, dpi=300)
        self.assertEqual((image.width(), image.height()), (1181, 827))
        self.assertTrue(image.hasAlphaChannel())

    def test_signature_outside_field_is_rejected(self) -> None:
        signature_image = QImage(20, 20, QImage.Format_ARGB32_Premultiplied)
        signature_image.fill(QColor("#000000"))
        design = StampDesign(
            lines=[TextLine(text="СОГЛАСОВАНО")],
            signature=SignatureImage(
                image=signature_image,
                x_mm=5,
                y_mm=5,
                width_mm=30,
                height_mm=12,
            ),
        )
        with self.assertRaises(StampError):
            validate_design(design)

    def test_content_size_follows_text_and_padding(self) -> None:
        small = StampDesign(lines=[TextLine(text="A")], padding_mm=2.0)
        large = StampDesign(
            lines=[TextLine(text="ОЧЕНЬ ДЛИННАЯ СТРОКА ДЛЯ ШТАМПА")],
            padding_mm=2.0,
        )
        small_w, small_h = content_required_size(small)
        large_w, large_h = content_required_size(large)
        self.assertGreaterEqual(small_w, 10.0)
        self.assertGreater(large_w, small_w)
        self.assertGreaterEqual(large_h, 10.0)

    def test_dimensions_are_limited(self) -> None:
        design = StampDesign(width_mm=110)
        with self.assertRaises(StampError):
            validate_design(design)
        design = StampDesign(height_mm=80)
        with self.assertRaises(StampError):
            validate_design(design)


if __name__ == "__main__":
    unittest.main()
