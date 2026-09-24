# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

"""Grind-off, the collation mark, the signature letter, and the folder lap."""

import io
import unittest

import pikepdf

from impose import ImposeError
from impose.bindery import letter, lip_cell, marks_for
from impose.geometry import Rect, Size
from impose.job import build_plan, impose_document
from impose.layout import lay_out
from impose.press import get as get_press
from impose.units import MM
from tests.support import make_pdf

_TRIM = Size(105 * MM, 148 * MM)


def _laid(pages=8, section_pages=4, grind=0.0, lap=0.0):
    plan = build_plan("perfect", pages, section_pages=section_pages)
    press = get_press("indigo-5000")
    layouts = [
        lay_out(
            surface,
            columns=plan.columns,
            rows=plan.rows,
            trim=_TRIM,
            trim_origin=Rect.from_size(_TRIM),
            press=press,
            grind=grind,
            spine=plan.spine,
            lap=lap,
            lip=lip_cell(plan, surface),
        )
        for surface in plan.surfaces
    ]
    return plan, layouts


class TestGrind(unittest.TestCase):
    """Milling shortens each leaf from the spine and does not change the bulk."""

    def test_the_trims_retreat_from_the_fold_by_the_grind(self):
        """Three millimetres off each leaf is a six-millimetre gap at the spine."""
        _, layouts = _laid(grind=3 * MM)
        left, right = sorted(layouts[0].pages, key=lambda page: page.trim.x0)
        self.assertAlmostEqual(right.trim.x0 - left.trim.x1, 6 * MM, places=3)

    def test_no_grind_leaves_the_pages_butted(self):
        """The default is still a fold with the two trims on one line."""
        _, layouts = _laid()
        left, right = sorted(layouts[0].pages, key=lambda page: page.trim.x0)
        self.assertAlmostEqual(right.trim.x0, left.trim.x1, places=3)

    def test_a_stapled_book_is_not_milled(self):
        """Saddle stitch keeps the fold, so there is nothing to grind off."""
        source = make_pdf(pages=8)
        with self.assertRaises(ImposeError) as caught:
            impose_document(source, io.BytesIO(), schema="saddle", grind=3 * MM)
        self.assertIn("mill", str(caught.exception))


class TestCollation(unittest.TestCase):
    """A bar stepped down the spine, and a letter for each section."""

    def test_each_section_steps_and_takes_the_next_letter(self):
        """Section two sits lower on the spine than section one, and is B."""
        plan, layouts = _laid()
        first = marks_for(layouts[0], plan)
        second = marks_for(layouts[2], plan)
        self.assertEqual(first.letters[0][2], "A")
        self.assertEqual(second.letters[0][2], "B")
        self.assertGreater(first.bars[0].y1, second.bars[0].y1)

    def test_an_inner_sheet_carries_no_mark(self):
        """Once the section is folded, only the outside is visible."""
        plan, layouts = _laid(pages=8, section_pages=8)
        self.assertTrue(marks_for(layouts[0], plan).bars)
        self.assertFalse(marks_for(layouts[2], plan).bars)

    def test_the_letter_is_on_the_press_sheet(self):
        """The letter is drawn, not only computed."""
        source = make_pdf(pages=8)
        output = io.BytesIO()
        impose_document(source, output, schema="perfect")
        output.seek(0)
        pdf = pikepdf.open(output)
        contents = pdf.pages[0].obj["/Contents"]
        streams = contents if isinstance(contents, pikepdf.Array) else [contents]
        text = b"".join(stream.read_bytes() for stream in streams)
        self.assertIn(b"(A)", text)

    def test_letters_run_past_z(self):
        """Twenty-seven sections need a second letter."""
        self.assertEqual(letter(26), "AA")


class TestLap(unittest.TestCase):
    """The lip a folder grabs, on the foot of the low folio only."""

    def test_the_low_folio_grows_at_the_foot(self):
        """Ten millimetres of lip, and only on the page the folder grabs."""
        _plan, layouts = _laid(lap=10 * MM)
        lip = next(page for page in layouts[0].pages if page.source == 0)
        self.assertAlmostEqual(lip.trim.y0 - lip.paint.y0, 10 * MM, places=3)
        other = next(page for page in layouts[0].pages if page.source != 0)
        self.assertAlmostEqual(other.paint.y0, other.trim.y0, places=3)
