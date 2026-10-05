# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

# pylint: disable=missing-function-docstring
"""Different finished sizes share a sheet. A book still refuses that."""

import io
import unittest

from impose import ImposeError
from impose.gang import pack
from impose.geometry import Size
from impose.job import impose_document
from impose.units import MM

from .support import make_pdf


class TestPacking(unittest.TestCase):
    """Pages stay in file order, and a new row starts when the row is full."""

    def test_two_sizes_share_a_row(self):
        sheets = pack((Size(60, 40), Size(60, 40)), Size(130, 90), gutter=10)
        self.assertEqual(sheets, (((0, 0, 0), (1, 1, 0)),))

    def test_a_full_row_continues_below(self):
        sheets = pack(
            (Size(60, 40), Size(60, 40), Size(60, 30)),
            Size(130, 90),
            gutter=10,
        )
        self.assertEqual(sheets[0][2], (2, 0, 1))

    def test_what_does_not_fit_starts_a_sheet(self):
        sheets = pack(
            (Size(60, 40), Size(60, 40), Size(60, 40)),
            Size(130, 50),
            gutter=10,
        )
        self.assertEqual(len(sheets), 2)
        self.assertEqual(sheets[1][0][0], 2)

    def test_a_page_bigger_than_the_sheet_is_named(self):
        with self.assertRaises(ImposeError) as caught:
            pack((Size(200, 40),), Size(100, 100), gutter=0)
        self.assertIn("Page 1", str(caught.exception))


class TestImposedGang(unittest.TestCase):
    """The press file places each page at its own trim."""

    def test_mixed_pages_impose(self):
        card = make_pdf(pages=1, trim=Size(90 * MM, 50 * MM))
        flyer = make_pdf(pages=1, trim=Size(105 * MM, 148 * MM))
        card.pages.append(flyer.pages[0])
        result = impose_document(card, io.BytesIO(), schema="gang")
        self.assertEqual(result.plan.schema, "gang")
        self.assertEqual(result.sheets, 1)
        self.assertEqual(result.plan.surfaces[0].sources, (0, 1))

    def test_a_book_still_refuses_mixed_sizes(self):
        card = make_pdf(pages=1, trim=Size(90 * MM, 50 * MM))
        flyer = make_pdf(pages=1, trim=Size(105 * MM, 148 * MM))
        card.pages.append(flyer.pages[0])
        with self.assertRaises(ImposeError) as caught:
            impose_document(card, io.BytesIO(), schema="nup")
        self.assertIn("same size", str(caught.exception))


class TestAFormSizedSheet(unittest.TestCase):
    """--sheet fit measures a grid of one cell, which a mixed gang has not.

    Sizing the sheet from the first page quoted a form nobody asked for, and
    offered remedies -- a smaller gutter, shorter marks -- that cannot reach
    it, because shrinking the form shrinks the target with it.
    """

    @staticmethod
    def mixed():
        card = make_pdf(pages=1, trim=Size(90 * MM, 50 * MM))
        flyer = make_pdf(pages=1, trim=Size(105 * MM, 148 * MM))
        card.pages.append(flyer.pages[0])
        return card

    def test_a_mixed_gang_is_refused_by_its_sizes(self):
        with self.assertRaises(ImposeError) as caught:
            impose_document(self.mixed(), io.BytesIO(), schema="gang", sheet="fit")
        said = str(caught.exception)
        self.assertIn("2 finished sizes", said)
        self.assertIn("90 × 50 mm", said)
        self.assertIn("105 × 148 mm", said)

    def test_the_refusal_does_not_blame_the_marks_or_the_gutter(self):
        """The old message sent the operator after things that cannot help."""
        with self.assertRaises(ImposeError) as caught:
            impose_document(self.mixed(), io.BytesIO(), schema="gang", sheet="fit")
        self.assertNotIn("shorter marks", str(caught.exception))

    def test_a_gang_of_one_size_still_gets_a_form(self):
        """One size is one cell, so the form is measurable and it runs."""
        result = impose_document(
            make_pdf(pages=4, trim=Size(90 * MM, 50 * MM)),
            io.BytesIO(),
            schema="gang",
            sheet="fit",
        )
        self.assertEqual(result.press, "form")

    def test_a_real_sheet_still_gangs_mixed_sizes(self):
        result = impose_document(self.mixed(), io.BytesIO(), schema="gang")
        self.assertEqual(result.sheets, 1)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
