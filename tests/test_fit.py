# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

# pylint: disable=missing-class-docstring,missing-function-docstring

"""How many fit, which way round, and what the leftovers cost."""

import unittest

from impose.fit import (
    Arrangement,
    arrangements,
    best,
    compare,
    count_along,
    plan_run,
)
from impose.geometry import Size
from impose.press import INDIGO_5000
from impose.units import MM, to_mm

A6 = Size(105 * MM, 148 * MM)
CARD = Size(90 * MM, 55 * MM)
AREA = INDIGO_5000.imageable_area()
GUTTER = 4 * MM
ALLOWANCE = 5 * MM


class TestCountAlong(unittest.TestCase):
    def test_gaps_are_one_fewer_than_pieces(self):
        """Three pieces have two gaps, not three."""
        self.assertEqual(count_along(3 * 100 + 2 * 10, 100, 10), 3)
        self.assertEqual(count_along(3 * 100 + 2 * 10 - 1, 100, 10), 2)

    def test_no_gutter_is_plain_division(self):
        self.assertEqual(count_along(300, 100, 0), 3)
        self.assertEqual(count_along(299, 100, 0), 2)

    def test_nothing_fits(self):
        self.assertEqual(count_along(100, 150, 0), 0)
        self.assertEqual(count_along(100, 0, 0), 0)

    def test_exact_fit_is_not_lost_to_float_noise(self):
        self.assertEqual(count_along(148.0 * 2 + 4.0, 148.0, 4.0), 2)


class TestArrangements(unittest.TestCase):
    def test_a6_fits_eight_up_turned_on_an_indigo(self):
        """Upright it is four up; on their sides, eight."""
        found = arrangements(A6, AREA, gutter=GUTTER, allowance=ALLOWANCE)
        self.assertEqual(found[0].up, 8)
        self.assertTrue(found[0].turned)
        self.assertEqual((found[0].columns, found[0].rows), (2, 4))

    def test_the_upright_option_is_still_offered(self):
        found = arrangements(A6, AREA, gutter=GUTTER, allowance=ALLOWANCE)
        upright = [a for a in found if not a.turned]
        self.assertEqual(upright[0].up, 4)

    def test_densest_first(self):
        found = arrangements(CARD, AREA, gutter=GUTTER, allowance=ALLOWANCE)
        self.assertEqual(
            [a.up for a in found], sorted((a.up for a in found), reverse=True)
        )

    def test_upright_wins_a_tie(self):
        """Turning pages for no gain only makes the stack harder to read."""
        square = Size(50 * MM, 50 * MM)
        found = arrangements(square, AREA, gutter=GUTTER)
        self.assertFalse(found[0].turned)

    def test_allowance_is_taken_off_before_counting(self):
        """The 8-up A6 needs a 5 mm allowance; at 8 mm it no longer fits."""
        self.assertEqual(best(A6, AREA, gutter=GUTTER, allowance=5 * MM).up, 8)
        self.assertLess(best(A6, AREA, gutter=GUTTER, allowance=8 * MM).up, 8)

    def test_a_size_too_big_fits_nowhere(self):
        self.assertEqual(arrangements(Size(500 * MM, 500 * MM), AREA), [])
        self.assertIsNone(best(Size(500 * MM, 500 * MM), AREA))

    def test_form_measures_trims_and_gutters(self):
        found = best(A6, AREA, gutter=GUTTER, allowance=ALLOWANCE)
        self.assertAlmostEqual(to_mm(found.form.width), 2 * 148 + 4, places=3)
        self.assertAlmostEqual(to_mm(found.form.height), 4 * 105 + 3 * 4, places=3)

    def test_form_plus_allowance_fits_the_area(self):
        for trim in (A6, CARD, Size(210 * MM, 297 * MM)):
            with self.subTest(trim=trim):
                found = best(trim, AREA, gutter=GUTTER, allowance=ALLOWANCE)
                if found is None:
                    continue
                self.assertLessEqual(
                    found.form.width + 2 * ALLOWANCE, AREA.width + 1e-6
                )
                self.assertLessEqual(
                    found.form.height + 2 * ALLOWANCE, AREA.height + 1e-6
                )

    def test_describe(self):
        found = best(A6, AREA, gutter=GUTTER, allowance=ALLOWANCE)
        self.assertEqual(found.describe(), "8 up, 2 × 4 turned, form 300 × 432 mm")


class TestRun(unittest.TestCase):
    def test_sheets_and_leftovers(self):
        run = plan_run(Arrangement(3, 7, False, CARD, GUTTER), 500)
        self.assertEqual(run.sheets, 24)
        self.assertEqual(run.capacity, 504)
        self.assertEqual(run.on_last_sheet, 17)
        self.assertEqual(run.waste, 4)

    def test_an_exact_multiple_wastes_nothing(self):
        run = plan_run(Arrangement(2, 5, False, CARD, GUTTER), 500)
        self.assertEqual(run.sheets, 50)
        self.assertEqual(run.waste, 0)
        self.assertIsNone(run.advice())

    def test_advice_offers_the_free_units(self):
        run = plan_run(Arrangement(3, 7, False, CARD, GUTTER), 500)
        self.assertIn("504", run.advice())
        self.assertIn("no more", run.advice())

    def test_a_run_is_at_least_one(self):
        with self.assertRaises(ValueError):
            plan_run(Arrangement(2, 2, False, CARD, GUTTER), 0)


class TestCompare(unittest.TestCase):
    def test_the_densest_grid_is_not_always_the_least_wasteful(self):
        """21 up runs 24 sheets and wastes 4; 20 up runs 25 and wastes none."""
        runs = compare(CARD, AREA, 500, gutter=GUTTER, allowance=ALLOWANCE)
        self.assertGreater(runs[0].arrangement.up, runs[1].arrangement.up)
        self.assertGreater(runs[0].waste, runs[1].waste)

    def test_every_arrangement_is_costed(self):
        runs = compare(A6, AREA, 100, gutter=GUTTER, allowance=ALLOWANCE)
        self.assertEqual(
            len(runs), len(arrangements(A6, AREA, gutter=GUTTER, allowance=ALLOWANCE))
        )
        for run in runs:
            self.assertGreaterEqual(run.capacity, 100)
