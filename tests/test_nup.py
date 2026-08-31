# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

# pylint: disable=missing-class-docstring,missing-function-docstring

"""N-up: consecutive pages in reading order."""

import unittest

from impose.plan import BLANK
from impose.schemas.nup import impose


class TestOrder(unittest.TestCase):
    def test_pages_run_in_reading_order(self):
        plan = impose(8, columns=2, rows=1)
        self.assertEqual(plan.surfaces[0].sources, (0, 1))
        self.assertEqual(plan.surfaces[1].sources, (2, 3))

    def test_the_back_is_not_mirrored(self):
        """The duplex unit turns the sheet; doing it here would double it."""
        back = impose(8, columns=2, rows=1).surfaces[1]
        self.assertEqual(back.at(0, 0).source, 2)
        self.assertEqual(back.at(1, 0).source, 3)

    def test_grid_fills_across_then_down(self):
        plan = impose(4, columns=2, rows=2, duplex=False)
        front = plan.surfaces[0]
        self.assertEqual(front.at(0, 0).source, 0)
        self.assertEqual(front.at(1, 0).source, 1)
        self.assertEqual(front.at(0, 1).source, 2)
        self.assertEqual(front.at(1, 1).source, 3)

    def test_whole_document_in_order(self):
        plan = impose(24, columns=2, rows=2)
        self.assertEqual(plan.placed_sources(), tuple(range(24)))

    def test_every_page_imposed_exactly_once(self):
        for pages in (1, 7, 8, 9, 33):
            for grid in ((2, 1), (2, 2), (3, 2)):
                with self.subTest(pages=pages, grid=grid):
                    plan = impose(pages, columns=grid[0], rows=grid[1])
                    plan.validate()


class TestPadding(unittest.TestCase):
    def test_short_document_is_padded_with_blanks(self):
        plan = impose(3, columns=2, rows=1, duplex=False)
        self.assertEqual(plan.surfaces[-1].at(1, 0).source, BLANK)

    def test_duplex_pads_to_a_whole_sheet(self):
        """A duplex sheet has two surfaces, so padding rounds to four here."""
        plan = impose(5, columns=2, rows=1)
        self.assertEqual(len(plan.surfaces), 4)
        self.assertEqual(plan.sheets, 2)

    def test_simplex_produces_fronts_only(self):
        plan = impose(4, columns=2, rows=1, duplex=False)
        self.assertTrue(all(s.side == "front" for s in plan.surfaces))


class TestArguments(unittest.TestCase):
    def test_rejects_empty_grid(self):
        with self.assertRaises(ValueError):
            impose(4, columns=0, rows=1)
