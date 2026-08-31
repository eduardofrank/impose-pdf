# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

# pylint: disable=missing-class-docstring,missing-function-docstring

"""Reading the boxes a print-ready file carries."""

import dataclasses
import unittest

import pikepdf

from impose import ImposeError
from impose.boxes import (
    PageBoxes,
    has_output_intent,
    pdfx_version,
    read_boxes,
    require_trim,
    rotate_insets,
)
from impose.geometry import Insets, Rect, Size
from impose.units import MM, to_mm

from .support import declare_pdfx, make_pdf


class TestReadBoxes(unittest.TestCase):
    def test_reads_what_the_file_declares(self):
        pdf = make_pdf(1)
        boxes = read_boxes(pdf.pages[0])
        self.assertAlmostEqual(to_mm(boxes.trim.width), 105.0, places=6)
        self.assertAlmostEqual(to_mm(boxes.trim.height), 148.0, places=6)
        # MediaBox is trim plus 3 mm bleed plus 6 mm slug, each side.
        self.assertAlmostEqual(to_mm(boxes.media.width), 123.0, places=6)
        self.assertTrue(boxes.has_explicit_trim)
        self.assertTrue(boxes.has_explicit_bleed)

    def test_bleed_insets(self):
        pdf = make_pdf(1, bleed=3 * MM)
        boxes = read_boxes(pdf.pages[0])
        for edge in ("left", "right", "bottom", "top"):
            with self.subTest(edge=edge):
                self.assertAlmostEqual(
                    to_mm(getattr(boxes.bleed_insets, edge)), 3.0, places=6
                )
        self.assertTrue(boxes.has_bleed)

    def test_defaults_when_boxes_are_absent(self):
        """Missing TrimBox and BleedBox both fall back to CropBox."""
        pdf = make_pdf(1, with_trimbox=False, with_bleedbox=False)
        boxes = read_boxes(pdf.pages[0])
        self.assertEqual(boxes.trim, boxes.crop)
        self.assertEqual(boxes.bleed, boxes.crop)
        self.assertFalse(boxes.has_explicit_trim)
        self.assertFalse(boxes.has_explicit_bleed)
        self.assertFalse(boxes.has_bleed)

    def test_no_bleedbox_means_no_bleed(self):
        """A file without BleedBox gets zero bleed, not an invented default."""
        pdf = make_pdf(1, with_bleedbox=False)
        boxes = read_boxes(pdf.pages[0])
        self.assertEqual(boxes.bleed_insets, Insets(0.0, 0.0, 0.0, 0.0))

    def test_cropbox_defaults_to_mediabox(self):
        pdf = pikepdf.Pdf.new()
        pdf.add_blank_page(page_size=(612, 792))
        boxes = read_boxes(pdf.pages[0])
        self.assertEqual(boxes.crop, Rect(0, 0, 612, 792))
        self.assertEqual(boxes.media, boxes.crop)

    def test_boxes_are_clipped_to_mediabox(self):
        """A TrimBox reaching past the sheet is clipped, per the specification."""
        pdf = pikepdf.Pdf.new()
        page = pdf.add_blank_page(page_size=(100, 100))
        page.obj["/TrimBox"] = pikepdf.Array([-50, -50, 150, 150])
        self.assertEqual(read_boxes(pdf.pages[0]).trim, Rect(0, 0, 100, 100))

    def test_box_outside_mediabox_is_an_error(self):
        pdf = pikepdf.Pdf.new()
        page = pdf.add_blank_page(page_size=(100, 100))
        page.obj["/TrimBox"] = pikepdf.Array([200, 200, 300, 300])
        with self.assertRaises(ImposeError):
            read_boxes(pdf.pages[0])

    def test_reversed_coordinates_are_normalized(self):
        """A box written x1,y1,x0,y0 is still that rectangle."""
        pdf = pikepdf.Pdf.new()
        page = pdf.add_blank_page(page_size=(100, 200))
        page.obj["/TrimBox"] = pikepdf.Array([80, 150, 20, 50])
        self.assertEqual(read_boxes(pdf.pages[0]).trim, Rect(20, 50, 80, 150))

    def test_nonzero_origin_mediabox(self):
        """Origins need not be zero, and nothing may assume they are."""
        pdf = pikepdf.Pdf.new()
        page = pdf.add_blank_page(page_size=(100, 100))
        page.obj["/MediaBox"] = pikepdf.Array([10, 20, 110, 120])
        page.obj["/TrimBox"] = pikepdf.Array([30, 40, 90, 100])
        boxes = read_boxes(pdf.pages[0])
        self.assertEqual(boxes.media, Rect(10, 20, 110, 120))
        self.assertEqual(boxes.trim, Rect(30, 40, 90, 100))
        self.assertEqual(boxes.trim_size, Size(60, 60))


class TestRotation(unittest.TestCase):
    def test_rotation_is_read(self):
        pdf = make_pdf(1, rotation=90)
        self.assertEqual(read_boxes(pdf.pages[0]).rotation, 90)

    def test_trim_size_is_what_a_reader_sees(self):
        upright_pdf, turned_pdf = make_pdf(1), make_pdf(1, rotation=90)
        upright = read_boxes(upright_pdf.pages[0]).trim_size
        turned = read_boxes(turned_pdf.pages[0]).trim_size
        self.assertEqual(turned, upright.swapped())

    def test_invalid_rotation_is_ignored(self):
        pdf = pikepdf.Pdf.new()
        page = pdf.add_blank_page(page_size=(100, 100))
        page.obj["/Rotate"] = 45
        self.assertEqual(read_boxes(pdf.pages[0]).rotation, 0)

    def test_rotation_normalizes(self):
        pdf = pikepdf.Pdf.new()
        page = pdf.add_blank_page(page_size=(100, 100))
        page.obj["/Rotate"] = -90
        self.assertEqual(read_boxes(pdf.pages[0]).rotation, 270)

    def test_quarter_turn_carries_left_edge_to_the_top(self):
        """/Rotate 90 displays the page turned clockwise."""
        self.assertEqual(rotate_insets(Insets(left=3), 90), Insets(top=3))
        self.assertEqual(rotate_insets(Insets(top=3), 90), Insets(right=3))

    def test_rotation_round_trips(self):
        insets = Insets(left=1, right=2, bottom=3, top=4)
        result = insets
        for _ in range(4):
            result = rotate_insets(result, 90)
        self.assertEqual(result, insets)

    def test_displayed_bleed_follows_rotation(self):
        pdf = make_pdf(1)
        boxes = dataclasses_replace_rotation(read_boxes(pdf.pages[0]), 90)
        self.assertAlmostEqual(
            boxes.displayed_bleed_insets.top, boxes.bleed_insets.left, places=9
        )


def dataclasses_replace_rotation(boxes: PageBoxes, rotation: int) -> PageBoxes:
    """A copy of *boxes* turned, without rebuilding the fixture."""
    return dataclasses.replace(boxes, rotation=rotation)


class TestPdfX(unittest.TestCase):
    def test_plain_file_claims_nothing(self):
        self.assertIsNone(pdfx_version(make_pdf(1)))
        self.assertFalse(has_output_intent(make_pdf(1)))

    def test_declared_version_is_found(self):
        pdf = declare_pdfx(make_pdf(1), "PDF/X-4")
        self.assertIn("PDF/X-4", pdfx_version(pdf) or "")

    def test_pdfx_without_trimbox_is_refused(self):
        """The finished size is exactly what we would have to guess."""
        pdf = make_pdf(1, with_trimbox=False)
        boxes = read_boxes(pdf.pages[0])
        with self.assertRaises(ImposeError) as caught:
            require_trim(boxes, page_number=1, pdfx="PDF/X-4")
        self.assertIn("TrimBox", str(caught.exception))

    def test_trimbox_present_is_accepted(self):
        pdf = make_pdf(1)
        boxes = read_boxes(pdf.pages[0])
        self.assertIsNone(require_trim(boxes, page_number=1, pdfx="PDF/X-4"))

    def test_no_pdfx_claim_means_no_requirement(self):
        pdf = make_pdf(1, with_trimbox=False)
        boxes = read_boxes(pdf.pages[0])
        self.assertIsNone(require_trim(boxes, page_number=1, pdfx=None))
