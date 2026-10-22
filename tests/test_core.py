"""Модульные тесты ядра: анализ страниц, размещение и сохранение."""

from __future__ import annotations

import hashlib
import io
import unittest
import uuid
from pathlib import Path

import fitz
from PIL import Image, ImageDraw

from pdfstamp.core import (
    CancelledError,
    StampError,
    StampOptions,
    PT_TO_MM,
    build_output_path,
    inspect_pdf,
    load_template,
    parse_color,
    stamp_pdf,
)
from tools.make_samples import (
    blank_document,
    dense_document,
    multi_page,
    photo_document,
    rotated_document,
    text_document,
)

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / ".tmp" / "tests"
SAMPLES = WORK / "samples"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _make_orientation_stamp(path: Path) -> None:
    image = Image.new("RGBA", (300, 150), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((2, 2, 297, 147), fill=(220, 30, 40, 255), outline=(0, 0, 0, 255), width=3)
    draw.rectangle((0, 0, 299, 28), fill=(0, 180, 70, 255))
    draw.rectangle((0, 122, 299, 149), fill=(0, 80, 220, 255))
    image.save(path)


def _pixel(pix: fitz.Pixmap, x: int, y: int) -> tuple[int, int, int]:
    # samples содержит RGB (n=3), координаты ограничиваем пикселями.
    x = max(0, min(pix.width - 1, x))
    y = max(0, min(pix.height - 1, y))
    index = (y * pix.width + x) * pix.n
    return tuple(pix.samples[index : index + 3])  # type: ignore[return-value]


class CoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        WORK.mkdir(parents=True, exist_ok=True)
        SAMPLES.mkdir(parents=True, exist_ok=True)
        text_document(SAMPLES / "text_document.pdf")
        dense_document(SAMPLES / "dense_document.pdf")
        blank_document(SAMPLES / "blank_document.pdf")
        rotated_document(SAMPLES / "rotated_document.pdf")
        photo_document(SAMPLES / "photo_document.pdf")
        multi_page(SAMPLES / "multi_page.pdf")
        _make_orientation_stamp(WORK / "orientation_stamp.png")
        cls.stamp = load_template(ROOT / "assets" / "example_stamp.png")
        cls.orientation_stamp = load_template(WORK / "orientation_stamp.png")

    def setUp(self) -> None:
        self.case_dir = WORK / f"case_{uuid.uuid4().hex[:8]}"
        self.case_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        # Результаты небольшие; очищаем, чтобы не засорять рабочую папку.
        for path in self.case_dir.glob("*"):
            try:
                path.unlink()
            except OSError:
                pass
        try:
            self.case_dir.rmdir()
        except OSError:
            pass

    def _run(
        self,
        source: Path,
        options: StampOptions | None = None,
        template=None,
    ):
        output = build_output_path(source, self.case_dir)
        result = stamp_pdf(
            source,
            output,
            template or self.stamp,
            options
            or StampOptions(
                width_mm=60,
                height_mm=38,
                margin_left_mm=8,
                margin_right_mm=8,
                margin_top_mm=8,
                margin_bottom_mm=8,
                clearance_mm=3,
            ),
        )
        self.assertTrue(output.is_file())
        return result, output

    # ------------------------------------------------------------------
    def test_template_loading_and_white_background(self) -> None:
        self.assertGreater(self.stamp.width_px, 10)
        self.assertGreater(self.stamp.aspect, 0)
        self.assertTrue(self.stamp.png_bytes.startswith(b"\x89PNG"))

        jpg_path = self.case_dir / "white_stamp.jpg"
        image = Image.new("RGB", (420, 220), "white")
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((20, 20, 400, 200), radius=16, outline=(0, 0, 0), width=8)
        draw.rectangle((100, 90, 320, 140), fill=(180, 30, 40))
        image.save(jpg_path, quality=95)

        opaque = load_template(jpg_path, remove_white_background=False)
        transparent = load_template(jpg_path, remove_white_background=True)
        with Image.open(io.BytesIO(opaque.png_bytes)) as img:
            self.assertEqual(img.getchannel("A").getextrema(), (255, 255))
        with Image.open(io.BytesIO(transparent.png_bytes)) as img:
            corner = img.getpixel((2, 2))
            self.assertEqual(corner[3], 0)
            center = img.getpixel((img.width // 2, img.height // 2))
            self.assertEqual(center[3], 255)

    def test_blank_page_uses_bottom_right(self) -> None:
        source = SAMPLES / "blank_document.pdf"
        before = _sha256(source)
        result, output = self._run(source)
        page = result.placements[0]
        page_rect = fitz.open(source)[0].rect
        margin_pt = 8 * 72 / 25.4
        self.assertEqual(page.overlap_ratio, 0)
        self.assertFalse(page.fallback)
        self.assertLessEqual(abs((page_rect.width - margin_pt) - page.rect.x1), 2.0)
        self.assertLessEqual(abs((page_rect.height - margin_pt) - page.rect.y1), 2.0)
        self.assertEqual(before, _sha256(source))
        self.assertNotEqual(before, _sha256(output))

    def test_separate_margins(self) -> None:
        source = SAMPLES / "blank_document.pdf"
        options = StampOptions(
            width_mm=40,
            height_mm=20,
            margin_left_mm=70,
            margin_right_mm=10,
            margin_top_mm=20,
            margin_bottom_mm=30,
            clearance_mm=0,
        )
        result, _ = self._run(source, options)
        page = result.placements[0]
        page_rect = fitz.open(source)[0].rect
        mm = 72 / 25.4
        self.assertGreaterEqual(page.rect.x0, 70 * mm - 1.5)
        self.assertLessEqual(page.rect.x1, page_rect.width - 10 * mm + 1.5)
        self.assertGreaterEqual(page.rect.y0, 20 * mm - 1.5)
        self.assertLessEqual(page.rect.y1, page_rect.height - 30 * mm + 1.5)
        self.assertEqual(page.overlap_ratio, 0)

    def test_text_page_preserved_and_free_place_found(self) -> None:
        source = SAMPLES / "text_document.pdf"
        source_doc = fitz.open(source)
        original_text = source_doc[0].get_text().strip()
        result, output = self._run(source)
        self.assertEqual(result.page_count, 1)

        out_doc = fitz.open(output)
        self.assertEqual(out_doc[0].get_text().strip(), original_text)
        self.assertGreater(len(out_doc[0].get_image_info()), 0)

        placement = result.placements[0]
        self.assertEqual(placement.overlap_ratio, 0)
        self.assertFalse(placement.fallback)
        self.assertGreater(placement.rect.x1, out_doc[0].rect.width * 0.85)
        # Штамп не должен упираться в самый нижний край: там подпись/колонтитул,
        # но обязан быть в нижней половине листа.
        self.assertGreater(placement.rect.y1, out_doc[0].rect.height * 0.65)

    def test_dense_page_reports_overlap(self) -> None:
        # Страница целиком залита серым: свободного места гарантированно нет.
        source = self.case_dir / "solid_page.pdf"
        doc = fitz.open()
        page = doc.new_page(width=595, height=842)
        page.draw_rect(
            page.rect, color=(0.4, 0.4, 0.4), fill=(0.55, 0.55, 0.55), width=0
        )
        page.insert_text((50, 80), "Solid page")
        doc.save(source)
        doc.close()

        options = StampOptions(
            width_mm=60,
            height_mm=38,
            margin_left_mm=8,
            margin_right_mm=8,
            margin_top_mm=8,
            margin_bottom_mm=8,
            clearance_mm=3,
            allow_overlap=False,
        )
        result, output = self._run(source, options)
        page_result = result.placements[0]
        self.assertEqual(result.skipped_pages, [1])
        self.assertTrue(page_result.skipped)
        self.assertIn("без штампа", " ".join(result.warnings).lower())
        self.assertEqual(len(fitz.open(output)[0].get_image_info()), 0)

        # С разрешённым перекрытием выбирается положение с минимальным наложением.
        options_overlap = StampOptions(
            width_mm=60,
            height_mm=38,
            margin_left_mm=8,
            margin_right_mm=8,
            margin_top_mm=8,
            margin_bottom_mm=8,
            clearance_mm=3,
            allow_overlap=True,
        )
        result_overlap, output_overlap = self._run(source, options_overlap)
        page_overlap = result_overlap.placements[0]
        self.assertFalse(page_overlap.skipped)
        self.assertGreater(page_overlap.overlap_ratio, 0.5)
        self.assertEqual(result_overlap.fallback_pages, [1])
        self.assertGreater(len(fitz.open(output_overlap)[0].get_image_info()), 0)

    def test_page_frame_does_not_block_free_space(self) -> None:
        # Рамка листа имеет bbox на всю страницу, но занимает только периметр.
        source = self.case_dir / "framed.pdf"
        doc = fitz.open()
        page = doc.new_page(width=595, height=842)
        page.draw_rect(page.rect, color=(0, 0, 0), fill=None, width=2)
        page.insert_text((50, 80), "Framed page")
        doc.save(source)
        doc.close()

        result, _ = self._run(source)
        placement = result.placements[0]
        self.assertFalse(placement.skipped)
        self.assertEqual(placement.overlap_ratio, 0)
        self.assertEqual(result.skipped_pages, [])

    def test_title_block_is_avoided(self) -> None:
        mm = 72 / 25.4
        source = self.case_dir / "a3_title_block.pdf"
        doc = fitz.open()
        page = doc.new_page(width=420 * mm, height=297 * mm)
        page_w, page_h = page.rect.width, page.rect.height
        title_block = fitz.Rect(page_w - 190 * mm, page_h - 60 * mm, page_w, page_h)
        page.draw_rect(title_block, color=(0, 0, 0), fill=None, width=2)
        page.insert_text((30, 30), "Drawing")
        doc.save(source)
        doc.close()

        base = dict(
            width_mm=30,
            height_mm=15,
            margin_left_mm=8,
            margin_right_mm=8,
            margin_top_mm=8,
            margin_bottom_mm=8,
            clearance_mm=2,
            allow_overlap=False,
        )
        without, _ = self._run(source, StampOptions(**base, ignore_title_block=False))
        with_ignore, _ = self._run(source, StampOptions(**base, ignore_title_block=True))
        rect_without = without.placements[0].rect
        rect_with = with_ignore.placements[0].rect
        intersection_without = fitz.Rect(rect_without) & title_block
        intersection_with = fitz.Rect(rect_with) & title_block
        self.assertGreater(intersection_without.width * intersection_without.height, 0)
        self.assertEqual(intersection_with.width * intersection_with.height, 0)
        self.assertFalse(with_ignore.placements[0].skipped)

    def test_text_title_block_bottom_is_avoided(self) -> None:
        mm = 72 / 25.4
        source = self.case_dir / "a4_text_title_block.pdf"
        doc = fitz.open()
        page = doc.new_page(width=210 * mm, height=297 * mm)
        page_height = page.rect.height
        page.draw_rect(
            fitz.Rect(0, page_height - 45 * mm, page.rect.width, page_height),
            color=(0, 0, 0),
            fill=None,
            width=2,
        )
        page.insert_text((30, 40), "Text document")
        doc.save(source)
        doc.close()

        result, _ = self._run(
            source,
            StampOptions(
                width_mm=30,
                height_mm=15,
                margin_left_mm=8,
                margin_right_mm=8,
                margin_top_mm=8,
                margin_bottom_mm=8,
                clearance_mm=2,
                allow_overlap=False,
                ignore_title_block=True,
            ),
        )
        placement = result.placements[0]
        self.assertFalse(placement.skipped)
        self.assertLessEqual(placement.rect.y1, page_height - 45 * mm + 1.0)

    def test_caption_below_stamp_in_arial(self) -> None:
        source = SAMPLES / "blank_document.pdf"
        options = StampOptions(
            width_mm=40,
            height_mm=20,
            margin_left_mm=8,
            margin_right_mm=8,
            margin_top_mm=8,
            margin_bottom_mm=8,
            clearance_mm=2,
            add_text=True,
            text="Производство работ",
            text_gap_mm=2,
            text_font_size_pt=9,
            text_color="#FF0000",
        )
        result, output = self._run(source, options)
        placement = result.placements[0]
        self.assertFalse(placement.skipped)

        page = fitz.open(output)[0]
        caption_spans = [
            span
            for block in page.get_text("dict").get("blocks", [])
            for line in block.get("lines", [])
            for span in line.get("spans", [])
            if "Производство" in span.get("text", "")
        ]
        self.assertEqual(len(caption_spans), 1)
        span = caption_spans[0]
        self.assertIn("Arial", span.get("font", ""))
        self.assertAlmostEqual(span["size"], 9.0, places=1)
        self.assertEqual(span.get("color"), 0xFF0000)
        center = (span["bbox"][0] + span["bbox"][2]) / 2
        self.assertAlmostEqual(center, (placement.rect.x0 + placement.rect.x1) / 2, delta=1.5)
        self.assertGreaterEqual(span["bbox"][1], placement.rect.y1 + 2 * 72 / 25.4 - 1.0)

    def test_color_formats(self) -> None:
        self.assertEqual(parse_color("#000000"), (0, 0, 0))
        self.assertEqual(parse_color("#f00"), (255, 0, 0))
        self.assertEqual(parse_color("red"), (255, 0, 0))
        self.assertEqual(parse_color("rgb(0, 128, 0)"), (0, 128, 0))
        self.assertEqual(parse_color("rgba(0, 0, 255, 0.5)"), (0, 0, 255))
        self.assertEqual(parse_color("0, 0, 255"), (0, 0, 255))
        self.assertEqual(parse_color("255 0 0"), (255, 0, 0))
        self.assertEqual(parse_color("0xFF0000"), (255, 0, 0))
        self.assertEqual(parse_color("hsl(120, 100%, 25%)"), (0, 128, 0))
        self.assertEqual(parse_color("чёрный"), (0, 0, 0))
        with self.assertRaises(StampError):
            parse_color("не цвет")

    def test_caption_length_limit(self) -> None:
        options = StampOptions(
            add_text=True,
            text="x" * 31,
            text_gap_mm=2,
            text_font_size_pt=9,
        )
        with self.assertRaises(StampError):
            options.validate()

    def test_rotated_page_stamp_is_upright(self) -> None:
        result, output = self._run(
            SAMPLES / "rotated_document.pdf", template=self.orientation_stamp
        )
        doc = fitz.open(output)
        page = doc[0]
        placement = result.placements[0]
        self.assertEqual(page.rotation, 90)
        self.assertGreater(page.rect.width, page.rect.height)
        self.assertGreater(placement.rect.x1, page.rect.width * 0.7)
        self.assertGreater(placement.rect.y1, page.rect.height * 0.7)

        pix = page.get_pixmap(matrix=fitz.Matrix(1, 1), alpha=False)
        center_x = int((placement.rect.x0 + placement.rect.x1) / 2)
        top_color = _pixel(
            pix, center_x, int(placement.rect.y0 + placement.rect.height * 0.12)
        )
        bottom_color = _pixel(
            pix, center_x, int(placement.rect.y1 - placement.rect.height * 0.12)
        )
        self.assertGreater(top_color[1], 120, top_color)
        self.assertLess(top_color[0], 90, top_color)
        self.assertGreater(bottom_color[2], 130, bottom_color)
        self.assertLess(bottom_color[1], 130, bottom_color)

    def test_cropbox_and_rotation(self) -> None:
        source = self.case_dir / "crop_rotated.pdf"
        doc = fitz.open(SAMPLES / "text_document.pdf")
        page = doc[0]
        page.set_cropbox(fitz.Rect(50, 50, 545, 792))
        page.set_rotation(90)
        doc.save(source)
        doc.close()

        result, output = self._run(source, template=self.orientation_stamp)
        out_doc = fitz.open(output)
        page = out_doc[0]
        self.assertEqual(page.rotation, 90)
        placement = result.placements[0]
        pix = page.get_pixmap(matrix=fitz.Matrix(1, 1), alpha=False)
        center = _pixel(
            pix,
            int((placement.rect.x0 + placement.rect.x1) / 2),
            int((placement.rect.y0 + placement.rect.y1) / 2),
        )
        # В центре штампа красная заливка.
        self.assertGreater(center[0], 150, center)
        self.assertLess(center[1], 100, center)
        self.assertLess(center[2], 100, center)

    def test_multi_page_and_unique_output(self) -> None:
        source = SAMPLES / "multi_page.pdf"
        first, output1 = self._run(source)
        self.assertEqual(first.page_count, 4)
        self.assertEqual(len(first.placements), 4)

        output2 = build_output_path(source, self.case_dir)
        self.assertNotEqual(output1, output2)
        self._run(source)
        self.assertTrue(output2.is_file())

    def test_scaled_down_on_small_page(self) -> None:
        # A6: 105 × 148 мм. Штамп 200 × 140 мм не помещается.
        source = self.case_dir / "a6.pdf"
        doc = fitz.open()
        page = doc.new_page(width=105 * 72 / 25.4, height=148 * 72 / 25.4)
        page.insert_text((20, 30), "A6 test")
        doc.save(source)
        doc.close()

        result, _ = self._run(
            source,
            StampOptions(
                width_mm=200,
                height_mm=140,
                margin_left_mm=8,
                margin_right_mm=8,
                margin_top_mm=8,
                margin_bottom_mm=8,
                clearance_mm=2,
            ),
        )
        page = result.placements[0]
        self.assertTrue(page.scaled)
        self.assertLess(page.width_mm, 200)
        self.assertLessEqual(page.width_mm, 105 - 2 * 8 + 0.5)
        self.assertLessEqual(page.height_mm, 148 - 2 * 8 + 0.5)
        self.assertEqual(page.overlap_ratio, 0)

    def test_cancel_before_processing(self) -> None:
        source = SAMPLES / "blank_document.pdf"
        output = build_output_path(source, self.case_dir)
        with self.assertRaises(CancelledError):
            stamp_pdf(
                source,
                output,
                self.stamp,
                StampOptions(),
                cancel=lambda: True,
            )
        self.assertFalse(output.exists())

    def test_inspect_and_non_pdf(self) -> None:
        info = inspect_pdf(SAMPLES / "multi_page.pdf")
        self.assertEqual(info.page_count, 4)
        self.assertFalse(info.needs_password)

        bad = self.case_dir / "not_a_pdf.pdf"
        bad.write_text("this is not a PDF", encoding="utf-8")
        with self.assertRaises(StampError):
            inspect_pdf(bad)

    def test_password_protected_pdf(self) -> None:
        source = self.case_dir / "protected.pdf"
        doc = fitz.open(SAMPLES / "blank_document.pdf")
        doc.save(
            source,
            encryption=fitz.PDF_ENCRYPT_AES_256,
            owner_pw="owner-secret",
            user_pw="user-secret",
        )
        doc.close()
        with self.assertRaises(StampError) as context:
            inspect_pdf(source)
        self.assertIn("парол", str(context.exception).lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
