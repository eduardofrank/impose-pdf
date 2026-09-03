# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

# pylint: disable=missing-class-docstring,missing-function-docstring

"""Step and repeat: one item, many times."""

import unittest

from impose import ImposeError
from impose.schemas.steprepeat import impose, impressions


class TestFill(unittest.TestCase):
    def test_every_cell_carries_the_artwork(self):
        plan = impose(1, columns=4, rows=2)
        front = plan.surfaces[0]
        self.assertEqual(len(front.placements), 8)
        self.assertTrue(all(p.source == 0 for p in front.placements))

    def test_a_second_page_is_the_back(self):
        plan = impose(2, columns=2, rows=2)
        self.assertEqual(len(plan.surfaces), 2)
        self.assertTrue(all(p.source == 1 for p in plan.surfaces[1].placements))

    def test_single_page_is_simplex(self):
        plan = impose(1, columns=2, rows=2)
        self.assertEqual([s.side for s in plan.surfaces], ["front"])

    def test_one_sheet_per_item_whatever_the_run(self):
        """How many times to print it is a press setting, not an imposition."""
        self.assertEqual(impose(1, columns=4, rows=2).sheets, 1)
        self.assertEqual(impose(6, columns=4, rows=2).sheets, 3)

    def test_impressions_counts_pieces_a_sheet(self):
        self.assertEqual(impressions(impose(1, columns=4, rows=2)), 8)

    def test_default_is_one_sheet(self):
        self.assertEqual(impose(1, columns=3, rows=3).sheets, 1)


class TestValidation(unittest.TestCase):
    def test_repetition_is_allowed(self):
        """The whole point is placing one page many times."""
        self.assertIsNone(impose(1, columns=4, rows=2).validate(exhaustive=False))

    def test_exhaustive_validation_would_object(self):
        with self.assertRaises(ImposeError):
            impose(1, columns=4, rows=2).validate()

    def test_rejects_pages_that_do_not_divide_into_items(self):
        with self.assertRaises(ValueError) as caught:
            impose(3, columns=2, rows=2, sides=2)
        self.assertIn("do not divide", str(caught.exception))

    def test_rejects_an_empty_document(self):
        with self.assertRaises(ValueError):
            impose(0, columns=2, rows=2)

    def test_rejects_an_impossible_sidedness(self):
        with self.assertRaises(ValueError):
            impose(4, columns=2, rows=2, sides=3)

    def test_rejects_empty_grid(self):
        with self.assertRaises(ValueError):
            impose(1, columns=0, rows=1)


class TestDocumentOfItems(unittest.TestCase):
    """Several items, each filling its own sheets -- what a booklet needs."""

    def test_each_pair_gets_its_own_sheet(self):
        """Four signatures, two up: four sheets, each carrying one twice."""
        plan = impose(8, columns=1, rows=2)
        self.assertEqual(plan.sheets, 4)
        fronts = [s for s in plan.surfaces if s.side == "front"]
        self.assertEqual([s.placements[0].source for s in fronts], [0, 2, 4, 6])

    def test_a_sheet_carries_one_item_only(self):
        for surface in impose(8, columns=2, rows=2).surfaces:
            with self.subTest(sheet=surface.sheet, side=surface.side):
                self.assertEqual(len({p.source for p in surface.placements}), 1)

    def test_the_back_of_a_sheet_is_that_item_s_back(self):
        plan = impose(8, columns=1, rows=2)
        for front, back in zip(plan.surfaces[::2], plan.surfaces[1::2]):
            with self.subTest(sheet=front.sheet):
                self.assertEqual(
                    back.placements[0].source, front.placements[0].source + 1
                )

    def test_sidedness_is_read_from_the_page_count(self):
        self.assertEqual(len(impose(4, columns=2, rows=1).surfaces), 4)  # 2 pairs
        self.assertEqual(len(impose(3, columns=2, rows=1).surfaces), 3)  # 3 singles

    def test_single_sided_items_can_be_stated(self):
        """Four one-sided items, not two double-sided ones."""
        plan = impose(4, columns=2, rows=1, sides=1)
        self.assertTrue(all(s.side == "front" for s in plan.surfaces))
        self.assertEqual(plan.sheets, 4)

    def test_the_run_is_not_in_the_file(self):
        """Four signatures are four sheets, however many books are wanted."""
        self.assertEqual(impose(8, columns=1, rows=2).sheets, 4)

    def test_impressions_counts_pieces_a_sheet(self):
        self.assertEqual(impressions(impose(8, columns=1, rows=2)), 2)

    def test_it_still_validates_without_the_exhaustive_check(self):
        self.assertIsNone(impose(8, columns=1, rows=2).validate(exhaustive=False))
