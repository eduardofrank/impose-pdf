# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

# pylint: disable=missing-class-docstring,missing-function-docstring

"""Saddle stitch, checked by folding the booklet and reading it."""

import unittest

from impose.plan import BLANK
from impose.schemas import LEFT, RIGHT
from impose.schemas.saddle import MAX_NESTED_SHEETS, impose, nesting_warning

from .booklet import read_nested


class TestReading(unittest.TestCase):
    def test_a_booklet_reads_in_order(self):
        plan = impose(8)
        self.assertEqual(read_nested(list(plan.surfaces)), list(range(8)))

    def test_many_lengths_all_read_in_order(self):
        for pages in (4, 8, 12, 16, 32, 64, 200):
            with self.subTest(pages=pages):
                plan = impose(pages)
                self.assertEqual(read_nested(list(plan.surfaces)), list(range(pages)))

    def test_odd_lengths_read_in_order_then_stop(self):
        """Padding sits at the end of the book, where a blank leaf belongs."""
        for pages in (1, 5, 6, 7, 13):
            with self.subTest(pages=pages):
                plan = impose(pages)
                self.assertEqual(read_nested(list(plan.surfaces)), list(range(pages)))


class TestPairing(unittest.TestCase):
    def test_the_outer_sheet_carries_the_first_and_last_page(self):
        front = impose(16).surfaces[0]
        self.assertEqual(front.at(RIGHT, 0).source, 0)
        self.assertEqual(front.at(LEFT, 0).source, 15)

    def test_the_inner_sheet_carries_the_middle(self):
        plan = impose(16)
        front = [s for s in plan.surfaces if s.side == "front"][-1]
        self.assertEqual(front.at(RIGHT, 0).source, 6)
        self.assertEqual(front.at(LEFT, 0).source, 9)

    def test_page_one_is_always_beside_the_last(self):
        for pages in (4, 12, 40):
            with self.subTest(pages=pages):
                front = impose(pages).surfaces[0]
                self.assertEqual(front.at(RIGHT, 0).source, 0)
                self.assertEqual(front.at(LEFT, 0).source, pages - 1)


class TestPadding(unittest.TestCase):
    def test_page_count_rounds_up_to_a_folded_sheet(self):
        self.assertEqual(impose(1).sheets, 1)
        self.assertEqual(impose(5).sheets, 2)
        self.assertEqual(impose(8).sheets, 2)
        self.assertEqual(impose(9).sheets, 3)

    def test_padding_appears_as_blanks(self):
        plan = impose(5)
        sources = [
            p.source for s in plan.surfaces for p in s.placements if p.source is BLANK
        ]
        self.assertEqual(len(sources), 3)

    def test_every_page_imposed_exactly_once(self):
        for pages in (1, 4, 7, 8, 33, 100):
            with self.subTest(pages=pages):
                impose(pages).validate()

    def test_grid_is_a_spread(self):
        self.assertEqual(impose(8).grid, (2, 1))


class TestNestingLimit(unittest.TestCase):
    """How many sheets will actually staple through the fold."""

    def test_thin_stock_takes_fifteen_sheets(self):
        self.assertEqual(MAX_NESTED_SHEETS, 15)
        self.assertIsNone(nesting_warning(15))
        self.assertIsNone(nesting_warning(1))

    def test_past_the_limit_it_says_so_and_says_what_to_do(self):
        warning = nesting_warning(16)
        self.assertIn("16 nested sheets", warning)
        self.assertIn("15", warning)
        self.assertIn("perfect bound", warning)

    def test_sixty_pages_is_the_last_that_staples(self):
        """Fifteen sheets at four pages each."""
        self.assertIsNone(nesting_warning(impose(60).sheets))
        self.assertIsNotNone(nesting_warning(impose(64).sheets))

    def test_the_limit_belongs_to_the_stock_and_the_stapler(self):
        """Heavier paper bulks up faster, so the figure is a parameter."""
        self.assertIsNone(nesting_warning(8, 8))
        self.assertIsNotNone(nesting_warning(9, 8))

    def test_the_page_count_in_the_message_matches_the_limit(self):
        self.assertIn("32 pages", nesting_warning(9, 8))
