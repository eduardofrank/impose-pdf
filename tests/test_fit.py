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
    largest_signature,
    plan_run,
    signature_arrangements,
)
from impose.geometry import Size
from impose.press import INDIGO_5000
from impose.units import MM, to_mm

A6 = Size(105 * MM, 148 * MM)
CARD = Size(90 * MM, 55 * MM)
AREA = INDIGO_5000.imageable_area()
GUTTER = 4 * MM
ALLOWANCE = 5 * MM


class TestSignatureGrids(unittest.TestCase):
    """Which signatures a sheet can be folded into."""

    AREA = INDIGO_5000.imageable_area()

    def options(self, w, h, allowance=5 * MM):
        return signature_arrangements(
            Size(w * MM, h * MM), self.AREA, allowance=allowance
        )

    def test_every_grid_is_a_power_of_two(self):
        """Each fold halves the sheet, so nothing in between is available."""
        for option in self.options(108, 140):
            with self.subTest(grid=(option.columns, option.rows)):
                for count in (option.columns, option.rows):
                    self.assertEqual(count & (count - 1), 0)

    def test_the_grid_always_has_a_spine(self):
        """One cell across folds at the head instead, which is a top-bound
        pad rather than a book."""
        for option in self.options(108, 140):
            self.assertGreaterEqual(option.columns, 2)

    def test_pages_are_never_turned_in_their_cells(self):
        """That would move the folds and make a different product."""
        self.assertTrue(all(not o.turned for o in self.options(108, 140)))

    def test_biggest_first(self):
        found = self.options(108, 140)
        self.assertEqual(
            [o.up for o in found], sorted((o.up for o in found), reverse=True)
        )

    def test_a_form_may_be_turned_as_a_whole_to_fit(self):
        """Four quarter-letter cells across is 432 mm and will not fit
        upright, but the finished form turned is 280 x 432 and does."""
        biggest = largest_signature(
            Size(108 * MM, 140 * MM), self.AREA, allowance=5 * MM
        )
        self.assertEqual((biggest.columns, biggest.rows), (4, 2))

    def test_a_bigger_page_folds_fewer_times(self):
        for size, expected in (
            ((108, 140), (4, 2)),
            ((139.7, 215.9), (2, 2)),
            ((215.9, 279.4), (2, 1)),
        ):
            with self.subTest(size=size):
                biggest = largest_signature(
                    Size(size[0] * MM, size[1] * MM), self.AREA, allowance=5 * MM
                )
                self.assertEqual((biggest.columns, biggest.rows), expected)

    def test_a_page_too_big_to_fold_at_all_has_no_answer(self):
        self.assertIsNone(
            largest_signature(Size(400 * MM, 400 * MM), self.AREA, allowance=5 * MM)
        )

    def test_the_limit_caps_the_signature(self):
        big = signature_arrangements(
            Size(50 * MM, 50 * MM), self.AREA, allowance=5 * MM, limit=8
        )
        self.assertTrue(all(o.up * 2 <= 8 for o in big))


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


BUSINESS_CARD = Size(90 * MM, 50 * MM)


class TestCompare(unittest.TestCase):
    """Ranked by what a job costs, not by how tightly it packs."""

    def test_a_tie_on_sheets_goes_to_the_tidier_grid(self):
        """100 cards: both grids run five sheets, but 24 up wastes twenty."""
        runs = compare(BUSINESS_CARD, AREA, 100, gutter=GUTTER, allowance=ALLOWANCE)
        self.assertEqual(runs[0].arrangement.up, 20)
        self.assertEqual(runs[0].sheets, 5)
        self.assertEqual(runs[0].waste, 0)
        self.assertEqual(runs[1].arrangement.up, 24)
        self.assertEqual(runs[1].waste, 20)

    def test_the_denser_grid_wins_once_it_saves_a_sheet(self):
        runs = compare(BUSINESS_CARD, AREA, 200, gutter=GUTTER, allowance=ALLOWANCE)
        self.assertEqual(runs[0].arrangement.up, 24)
        self.assertEqual(runs[0].sheets, 9)

    def test_the_crossover_sits_at_a_hundred(self):
        for quantity, expected in ((100, 20), (101, 24), (120, 24), (500, 24)):
            with self.subTest(quantity=quantity):
                runs = compare(
                    BUSINESS_CARD, AREA, quantity, gutter=GUTTER, allowance=ALLOWANCE
                )
                self.assertEqual(runs[0].arrangement.up, expected)

    def test_best_follows_the_same_rule_when_a_quantity_is_known(self):
        chosen = best(
            BUSINESS_CARD, AREA, quantity=100, gutter=GUTTER, allowance=ALLOWANCE
        )
        self.assertEqual(chosen.up, 20)

    def test_best_falls_back_to_density_without_a_quantity(self):
        chosen = best(BUSINESS_CARD, AREA, gutter=GUTTER, allowance=ALLOWANCE)
        self.assertEqual(chosen.up, 24)

    def test_the_card_grids_are_the_ones_the_shop_runs(self):
        """24 up is 3 x 8 here and 8 x 3 on a landscape sheet; same layout."""
        found = arrangements(BUSINESS_CARD, AREA, gutter=GUTTER, allowance=ALLOWANCE)
        self.assertEqual(
            {(a.up, a.columns, a.rows) for a in found}, {(24, 3, 8), (20, 5, 4)}
        )

    def test_every_arrangement_is_costed(self):
        runs = compare(A6, AREA, 100, gutter=GUTTER, allowance=ALLOWANCE)
        self.assertEqual(
            len(runs), len(arrangements(A6, AREA, gutter=GUTTER, allowance=ALLOWANCE))
        )
        for run in runs:
            self.assertGreaterEqual(run.capacity, 100)
