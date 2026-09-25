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


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
