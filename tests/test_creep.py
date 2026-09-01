# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

# pylint: disable=missing-class-docstring,missing-function-docstring

"""Creep: nested sheets push out, and the image slides to meet the trim."""

import io
import unittest

from impose.boxes import read_boxes
from impose.job import _creep_table, impose_document
from impose.layout import lay_out
from impose.plan import Placement, Surface
from impose.press import INDIGO_5000
from impose.units import MM, to_mm

from .support import make_pdf

CALIPER = 0.1 * MM


def spread(creep=0.0, rotation=0):
    """One saddle spread, with the fold between the two columns."""
    source = make_pdf(4)
    boxes = read_boxes(source.pages[0])
    return lay_out(
        Surface(
            0, "front", (Placement(3, 0, 0, rotation), Placement(0, 1, 0, rotation))
        ),
        columns=2,
        rows=1,
        trim=boxes.trim_size,
        trim_origin=boxes.trim,
        bleed=boxes.bleed_insets,
        press=INDIGO_5000,
        creep=creep,
        fold_columns=(1,),
    )


class TestDirection(unittest.TestCase):
    def test_the_cells_do_not_move(self):
        """The fold is where the fold is; only the image slides."""
        plain, crept = spread(), spread(1 * MM)
        for a, b in zip(plain.pages, crept.pages):
            self.assertEqual(a.trim, b.trim)

    def test_both_images_move_toward_the_spine(self):
        """Left page's spine is on its right, and the reverse."""
        plain, crept = spread(), spread(1 * MM)
        left_before, right_before = plain.pages
        left_after, right_after = crept.pages
        # Window left  -> image right -> toward the spine for the left page.
        self.assertAlmostEqual(
            to_mm(left_before.clip.x0 - left_after.clip.x0), 1.0, places=6
        )
        # Window right -> image left  -> toward the spine for the right page.
        self.assertAlmostEqual(
            to_mm(right_after.clip.x0 - right_before.clip.x0), 1.0, places=6
        )

    def test_the_window_keeps_its_size(self):
        plain, crept = spread(), spread(1 * MM)
        for a, b in zip(plain.pages, crept.pages):
            self.assertAlmostEqual(a.clip.width, b.clip.width, places=9)

    def test_no_caliper_means_no_shift(self):
        plain, zero = spread(), spread(0.0)
        for a, b in zip(plain.pages, zero.pages):
            self.assertEqual(a.clip, b.clip)

    def test_a_quarter_turn_moves_the_window_on_the_other_axis(self):
        """The shift is along the sheet; the window lives in the page."""
        plain, crept = spread(rotation=90), spread(1 * MM, rotation=90)
        left_before, left_after = plain.pages[0], crept.pages[0]
        self.assertAlmostEqual(left_before.clip.x0, left_after.clip.x0, places=9)
        self.assertAlmostEqual(
            to_mm(left_before.clip.y0 - left_after.clip.y0), 1.0, places=6
        )

    def test_a_cell_with_no_fold_beside_it_does_not_creep(self):
        source = make_pdf(4)
        boxes = read_boxes(source.pages[0])
        flat = lay_out(
            Surface(0, "front", (Placement(0, 0, 0), Placement(1, 1, 0))),
            columns=2,
            rows=1,
            trim=boxes.trim_size,
            trim_origin=boxes.trim,
            press=INDIGO_5000,
            creep=1 * MM,
            fold_columns=(),
        )
        plain = lay_out(
            Surface(0, "front", (Placement(0, 0, 0), Placement(1, 1, 0))),
            columns=2,
            rows=1,
            trim=boxes.trim_size,
            trim_origin=boxes.trim,
            press=INDIGO_5000,
        )
        for a, b in zip(flat.pages, plain.pages):
            self.assertEqual(a.clip, b.clip)


class TestDepth(unittest.TestCase):
    def test_the_outermost_sheet_does_not_creep(self):
        """Nothing wraps it, so its fold is not displaced."""
        self.assertEqual(_creep_table("saddle", CALIPER, 4)(0), 0.0)

    def test_shift_grows_with_depth_in_the_nest(self):
        table = _creep_table("saddle", CALIPER, 4)
        self.assertAlmostEqual(to_mm(table(1)), 0.1, places=6)
        self.assertAlmostEqual(to_mm(table(14)), 1.4, places=6)

    def test_depth_restarts_with_each_gathered_section(self):
        """Sections are stacked, not nested, so each starts again at zero."""
        table = _creep_table("perfect", CALIPER, 16)
        self.assertEqual(
            [round(to_mm(table(n)), 3) for n in range(8)],
            [0.0, 0.1, 0.2, 0.3, 0.0, 0.1, 0.2, 0.3],
        )

    def test_flat_schemas_never_creep(self):
        for schema in ("nup", "cutstack", "steprepeat"):
            with self.subTest(schema=schema):
                self.assertEqual(_creep_table(schema, CALIPER, 4)(5), 0.0)

    def test_no_caliper_is_no_creep(self):
        self.assertEqual(_creep_table("saddle", 0.0, 4)(5), 0.0)


class TestEndToEnd(unittest.TestCase):
    def test_a_crept_job_differs_from_an_uncrept_one(self):
        plain, crept = io.BytesIO(), io.BytesIO()
        impose_document(make_pdf(32), plain, schema="saddle")
        impose_document(make_pdf(32), crept, schema="saddle", paper_caliper="0.1mm")
        self.assertNotEqual(plain.getvalue(), crept.getvalue())

    def test_caliper_accepts_a_length(self):
        result = impose_document(
            make_pdf(16), io.BytesIO(), schema="saddle", paper_caliper="0.12mm"
        )
        self.assertEqual(result.sheets, 4)

    def test_perfect_binding_creeps_within_its_sections(self):
        result = impose_document(
            make_pdf(32),
            io.BytesIO(),
            schema="perfect",
            section_pages=16,
            paper_caliper="0.1mm",
        )
        self.assertEqual(result.sheets, 8)
