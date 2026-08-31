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

    def test_copies_drive_the_sheet_count(self):
        self.assertEqual(impose(1, columns=4, rows=2, copies=8).sheets, 1)
        self.assertEqual(impose(1, columns=4, rows=2, copies=9).sheets, 2)
        self.assertEqual(impose(1, columns=4, rows=2, copies=80).sheets, 10)

    def test_impressions_counts_finished_pieces(self):
        self.assertEqual(impressions(impose(1, columns=4, rows=2, copies=9)), 16)

    def test_default_is_one_sheet(self):
        self.assertEqual(impose(1, columns=3, rows=3).sheets, 1)


class TestValidation(unittest.TestCase):
    def test_repetition_is_allowed(self):
        """The whole point is placing one page many times."""
        self.assertIsNone(impose(1, columns=4, rows=2).validate(exhaustive=False))

    def test_exhaustive_validation_would_object(self):
        with self.assertRaises(ImposeError):
            impose(1, columns=4, rows=2).validate()

    def test_rejects_more_than_a_front_and_a_back(self):
        with self.assertRaises(ValueError) as caught:
            impose(3, columns=2, rows=2)
        self.assertIn("front and a back", str(caught.exception))

    def test_rejects_empty_grid(self):
        with self.assertRaises(ValueError):
            impose(1, columns=0, rows=1)
