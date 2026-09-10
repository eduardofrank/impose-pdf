# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

# pylint: disable=missing-class-docstring,missing-function-docstring

"""Gathered signatures.

The strongest check here is not one of these tests but the agreement between
two code paths: a signature folded once is the ordinary folded sheet, and must
come out identical to what perfect binding has always produced. Those two were
written months apart from different starting points, so if the folding model
were wrong they would disagree.
"""

import unittest

from impose import ImposeError
from impose.fold import FOOT_TO_FOOT, HEAD_TO_HEAD
from impose.plan import BLANK
from impose.schemas import perfect, signature


def sources(plan):
    """Every placed page in surface order, blanks dropped."""
    return [
        placement.source
        for surface in plan.surfaces
        for placement in surface.placements
        if placement.source is not BLANK
    ]


class TestAgreesWithPerfectBinding(unittest.TestCase):
    """A 2 x 1 signature is one fold, which is what perfect already does."""

    def test_identical_for_every_length(self):
        for pages in (4, 8, 12, 16, 32, 100):
            with self.subTest(pages=pages):
                folded = signature.impose(pages, columns=2, rows=1)
                gathered = perfect.impose(pages, section_pages=4)
                self.assertEqual(
                    [(s.sheet, s.side, s.sources) for s in folded.surfaces],
                    [(s.sheet, s.side, s.sources) for s in gathered.surfaces],
                )

    def test_identical_sheet_counts(self):
        for pages in (4, 9, 16, 33):
            with self.subTest(pages=pages):
                self.assertEqual(
                    signature.impose(pages, columns=2, rows=1).sheets,
                    perfect.impose(pages, section_pages=4).sheets,
                )


class TestFoldedTwice(unittest.TestCase):
    def test_one_sheet_carries_eight_pages(self):
        plan = signature.impose(8, columns=2, rows=2)
        self.assertEqual(plan.sheets, 1)
        self.assertEqual(len(plan.surfaces), 2)

    def test_sixteen_pages_take_two_sheets_not_four(self):
        """The whole point: folding again halves the sheets."""
        self.assertEqual(signature.impose(16, columns=2, rows=2).sheets, 2)
        self.assertEqual(signature.impose(16, columns=2, rows=1).sheets, 4)

    def test_half_the_pages_are_upside_down(self):
        plan = signature.impose(8, columns=2, rows=2)
        turned = [p for s in plan.surfaces for p in s.placements if p.rotation]
        self.assertEqual(len(turned), 4)
        self.assertTrue(all(p.rotation == 180 for p in turned))

    def test_the_turned_pages_are_all_in_one_row(self):
        """Head to head: one row upright, the other inverted, meeting at the
        fold that gets trimmed."""
        plan = signature.impose(8, columns=2, rows=2)
        by_row = {}
        for surface in plan.surfaces:
            for placement in surface.placements:
                by_row.setdefault(placement.row, set()).add(placement.rotation)
        self.assertEqual(by_row, {0: {180}, 1: {0}})

    def test_foot_to_foot_inverts_the_other_row(self):
        plan = signature.impose(8, columns=2, rows=2, style=FOOT_TO_FOOT)
        by_row = {}
        for surface in plan.surfaces:
            for placement in surface.placements:
                by_row.setdefault(placement.row, set()).add(placement.rotation)
        self.assertEqual(by_row, {0: {0}, 1: {180}})

    def test_sixteen_page_signature(self):
        plan = signature.impose(32, columns=4, rows=2)
        plan.validate()
        self.assertEqual(plan.sheets, 2)
        self.assertEqual(plan.grid, (4, 2))


class TestGathering(unittest.TestCase):
    def test_sections_are_gathered_in_order(self):
        """Signature one holds the first pages, signature two the next --
        gathered, not nested."""
        plan = signature.impose(24, columns=2, rows=2)
        for sheet in range(plan.sheets):
            on_sheet = {
                placement.source
                for surface in plan.surfaces
                if surface.sheet == sheet
                for placement in surface.placements
                if placement.source is not BLANK
            }
            self.assertEqual(on_sheet, set(range(sheet * 8, sheet * 8 + 8)))

    def test_every_page_imposed_exactly_once(self):
        for pages in (8, 16, 24, 100):
            for grid in ((2, 1), (2, 2), (4, 2), (2, 4)):
                with self.subTest(pages=pages, grid=grid):
                    plan = signature.impose(pages, columns=grid[0], rows=grid[1])
                    plan.validate()
                    self.assertEqual(sorted(sources(plan)), list(range(pages)))

    def test_a_short_document_is_padded_to_a_whole_signature(self):
        plan = signature.impose(5, columns=2, rows=2)
        plan.validate()
        self.assertEqual(plan.pages, 5)
        self.assertEqual(plan.sheets, 1)
        blanks = [p for s in plan.surfaces for p in s.placements if p.source is BLANK]
        self.assertEqual(len(blanks), 3)

    def test_padding_falls_at_the_end_of_the_book(self):
        plan = signature.impose(5, columns=2, rows=2)
        self.assertEqual(sorted(sources(plan)), [0, 1, 2, 3, 4])


class TestFoldLines(unittest.TestCase):
    def test_one_fold_is_the_spine_only(self):
        plan = signature.impose(8, columns=2, rows=1)
        self.assertEqual(plan.fold_columns, (1,))
        self.assertEqual(plan.fold_rows, ())

    def test_folding_again_adds_a_crease_across_the_sheet(self):
        plan = signature.impose(8, columns=2, rows=2)
        self.assertEqual(plan.fold_columns, (1,))
        self.assertEqual(plan.fold_rows, (1,))

    def test_a_sixteen_page_signature_has_two_creases_one_way(self):
        plan = signature.impose(16, columns=4, rows=2)
        self.assertEqual(plan.fold_columns, (2, 3))
        self.assertEqual(plan.fold_rows, (1,))


class TestRefusals(unittest.TestCase):
    def test_a_grid_that_cannot_be_folded_is_refused(self):
        with self.assertRaises(ImposeError) as caught:
            signature.impose(8, columns=3, rows=1)
        self.assertIn("power of two", str(caught.exception))

    def test_an_unknown_style_is_refused(self):
        with self.assertRaises(ImposeError):
            signature.impose(8, columns=2, rows=2, style="sideways")

    def test_the_style_names_are_the_ones_offered(self):
        for style in (HEAD_TO_HEAD, FOOT_TO_FOOT):
            with self.subTest(style=style):
                signature.impose(8, columns=2, rows=2, style=style).validate()
