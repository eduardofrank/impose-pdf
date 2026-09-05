# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

# pylint: disable=missing-class-docstring,missing-function-docstring

"""Placing a surface on a sheet: gutters, bleed, and fit."""

import unittest

from impose import ImposeError
from impose.geometry import Insets, Rect, Size
from impose.job import build_plan
from impose.layout import Gutters, lay_out
from impose.plan import Placement, Surface
from impose.press import INDIGO_5000, custom
from impose.units import MM, to_mm

A6 = Size(105 * MM, 148 * MM)
BLEED = Insets.uniform(3 * MM)


def spread(*, gutters=Gutters(), bleed=BLEED, press=INDIGO_5000, rotation=0, **kw):
    """A 2-up spread, the saddle-stitch case."""
    surface = Surface(
        0,
        "front",
        (Placement(3, 0, 0, rotation), Placement(0, 1, 0, rotation)),
    )
    return lay_out(
        surface,
        columns=2,
        rows=1,
        trim=A6,
        trim_origin=Rect.from_size(A6),
        bleed=bleed,
        gutters=gutters,
        press=press,
        **kw,
    )


class TestFoldAxis(unittest.TestCase):
    """Which way the fold runs, once the form has been turned."""

    @staticmethod
    def layout(trim, *, columns=2, rows=1):
        plan = build_plan("saddle", 4)
        surface = plan.surfaces[0]
        return lay_out(
            surface,
            columns=columns,
            rows=rows,
            trim=trim,
            trim_origin=Rect(0, 0, trim.width, trim.height),
            press=INDIGO_5000,
            sheet=INDIGO_5000.sheet,
        )

    def test_an_upright_form_folds_vertically(self):
        vertical, horizontal = self.layout(Size(105 * MM, 210 * MM)).fold_positions(
            (1,)
        )
        self.assertEqual(len(vertical), 1)
        self.assertEqual(horizontal, ())

    def test_a_turned_form_folds_horizontally(self):
        """The spine runs the other way once the form is turned. Reporting it
        as a vertical position matched no cut line, and the spine was marked
        as somewhere to put the knife."""
        layout = self.layout(Size(210 * MM, 105 * MM))
        self.assertTrue(layout.turned)
        vertical, horizontal = layout.fold_positions((1,))
        self.assertEqual(vertical, ())
        self.assertEqual(len(horizontal), 1)

    def test_no_fold_columns_means_no_folds(self):
        self.assertEqual(
            self.layout(Size(105 * MM, 210 * MM)).fold_positions(()), ((), ())
        )


class TestGrid(unittest.TestCase):
    def test_cells_are_side_by_side(self):
        left, right = spread().pages
        self.assertAlmostEqual(to_mm(left.trim.width), 105.0, places=6)
        self.assertAlmostEqual(left.trim.x1, right.trim.x0, places=9)

    def test_form_is_the_sum_of_its_cells(self):
        layout = spread()
        self.assertAlmostEqual(to_mm(layout.trim_bounds.width), 210.0, places=6)
        self.assertAlmostEqual(to_mm(layout.trim_bounds.height), 148.0, places=6)

    def test_gutters_push_cells_apart(self):
        layout = spread(gutters=Gutters(horizontal=10 * MM))
        left, right = layout.pages
        self.assertAlmostEqual(to_mm(right.trim.x0 - left.trim.x1), 10.0, places=6)
        self.assertAlmostEqual(to_mm(layout.trim_bounds.width), 220.0, places=6)

    def test_rows_count_downward_as_a_person_reads(self):
        """Row 0 is the top of the sheet, but PDF y grows upward."""
        surface = Surface(0, "front", (Placement(0, 0, 0), Placement(1, 0, 1)))
        layout = lay_out(
            surface,
            columns=1,
            rows=2,
            trim=A6,
            trim_origin=Rect.from_size(A6),
            press=INDIGO_5000,
        )
        top = next(p for p in layout.pages if p.source == 0)
        bottom = next(p for p in layout.pages if p.source == 1)
        self.assertGreater(top.trim.y0, bottom.trim.y0)


class TestBleed(unittest.TestCase):
    def test_outer_edges_keep_their_bleed(self):
        left, right = spread().pages
        self.assertAlmostEqual(to_mm(left.trim.x0 - left.paint.x0), 3.0, places=6)
        self.assertAlmostEqual(to_mm(right.paint.x1 - right.trim.x1), 3.0, places=6)

    def test_butting_edges_shave_bleed_to_nothing(self):
        """Two pages at a spine share one cut line; bleed has nowhere to go."""
        left, right = spread().pages
        self.assertEqual(left.butts, frozenset({"right"}))
        self.assertEqual(right.butts, frozenset({"left"}))
        # Only the trap, never the full 3 mm of bleed.
        self.assertLess(to_mm(left.paint.x1 - left.trim.x1), 0.5)
        self.assertLess(to_mm(right.trim.x0 - right.paint.x0), 0.5)

    def test_butting_trims_share_a_coordinate_exactly(self):
        left, right = spread().pages
        self.assertEqual(left.trim.x1, right.trim.x0)

    def test_gutter_splits_bleed_between_neighbours(self):
        """With a 4 mm gutter, each side keeps 2 mm, not the full 3."""
        left, right = spread(gutters=Gutters(horizontal=4 * MM)).pages
        self.assertAlmostEqual(to_mm(left.paint.x1 - left.trim.x1), 2.0, places=6)
        self.assertAlmostEqual(to_mm(right.trim.x0 - right.paint.x0), 2.0, places=6)

    def test_wide_gutter_keeps_the_whole_bleed(self):
        left, _ = spread(gutters=Gutters(horizontal=20 * MM)).pages
        self.assertAlmostEqual(to_mm(left.paint.x1 - left.trim.x1), 3.0, places=6)

    def test_no_bleed_means_paint_is_the_trim(self):
        left, _ = spread(bleed=Insets()).pages
        self.assertAlmostEqual(left.paint.x0, left.trim.x0, places=9)

    def test_clip_follows_the_kept_bleed(self):
        """The source region taken matches what will be painted."""
        left, _ = spread().pages
        self.assertAlmostEqual(to_mm(left.clip.width), 105.0 + 3.0, places=6)


class TestFit(unittest.TestCase):
    def test_form_is_centred_in_the_imageable_area(self):
        layout = spread()
        area = layout.imageable
        left_gap = layout.trim_bounds.x0 - area.x0
        right_gap = area.x1 - layout.trim_bounds.x1
        self.assertAlmostEqual(left_gap, right_gap, places=6)

    def test_centring_respects_the_gripper(self):
        """The form sits inside the imageable area, not the raw sheet."""
        layout = spread()
        self.assertGreaterEqual(
            layout.trim_bounds.y0, INDIGO_5000.imageable_area().y0 - 1e-6
        )
        self.assertAlmostEqual(to_mm(layout.trim_bounds.y0), 163.0, places=4)

    def test_a_form_that_only_fits_turned_is_turned(self):
        press = custom(sheet=Size(400 * MM, 200 * MM), margins="0mm")
        layout = lay_out(
            Surface(0, "front", (Placement(0, 0, 0),)),
            columns=1,
            rows=1,
            trim=Size(150 * MM, 350 * MM),
            trim_origin=Rect.from_size(Size(150 * MM, 350 * MM)),
            press=press,
        )
        self.assertTrue(layout.turned)
        self.assertAlmostEqual(to_mm(layout.trim_bounds.width), 350.0, places=4)

    def test_a_form_that_fits_is_not_turned(self):
        self.assertFalse(spread().turned)

    def test_a_form_that_fits_neither_way_is_refused(self):
        press = custom(sheet=Size(100 * MM, 100 * MM), margins="0mm")
        with self.assertRaises(ImposeError) as caught:
            lay_out(
                Surface(0, "front", (Placement(0, 0, 0),)),
                columns=1,
                rows=1,
                trim=A6,
                trim_origin=Rect.from_size(A6),
                press=press,
            )
        self.assertIn("does not fit", str(caught.exception))

    def test_marks_are_counted_when_checking_fit(self):
        """A form that fits bare may not fit once marks are allowed for."""
        press = custom(sheet=Size(212 * MM, 150 * MM), margins="0mm")
        lay_out(
            Surface(0, "front", (Placement(0, 0, 0), Placement(1, 1, 0))),
            columns=2,
            rows=1,
            trim=A6,
            trim_origin=Rect.from_size(A6),
            press=press,
            bleed=Insets(),
        )
        with self.assertRaises(ImposeError):
            lay_out(
                Surface(0, "front", (Placement(0, 0, 0), Placement(1, 1, 0))),
                columns=2,
                rows=1,
                trim=A6,
                trim_origin=Rect.from_size(A6),
                press=press,
                bleed=Insets(),
                mark_allowance=5 * MM,
            )


class TestRotation(unittest.TestCase):
    def test_quarter_turned_cells_swap_the_grid(self):
        layout = spread(rotation=90)
        self.assertAlmostEqual(to_mm(layout.pages[0].trim.width), 148.0, places=6)

    def test_mixing_turned_and_upright_is_refused(self):
        surface = Surface(0, "front", (Placement(0, 0, 0, 0), Placement(1, 1, 0, 90)))
        with self.assertRaises(ImposeError) as caught:
            lay_out(
                surface,
                columns=2,
                rows=1,
                trim=A6,
                trim_origin=Rect.from_size(A6),
                press=INDIGO_5000,
            )
        self.assertIn("different sizes", str(caught.exception))

    def test_half_turn_keeps_the_cell_size(self):
        layout = spread(rotation=180)
        self.assertAlmostEqual(to_mm(layout.pages[0].trim.width), 105.0, places=6)


class TestOuterBleed(unittest.TestCase):
    """An outer edge has no neighbour, so it keeps the whole bleed."""

    def test_a_gutter_does_not_cap_the_outside_of_the_form(self):
        layout = spread(bleed=Insets.uniform(5 * MM), gutters=Gutters(4 * MM, 4 * MM))
        left, right = layout.pages
        self.assertAlmostEqual(to_mm(left.trim.x0 - left.paint.x0), 5.0, places=6)
        self.assertAlmostEqual(to_mm(right.paint.x1 - right.trim.x1), 5.0, places=6)

    def test_the_inner_edges_still_share_the_gutter(self):
        layout = spread(bleed=Insets.uniform(5 * MM), gutters=Gutters(4 * MM, 4 * MM))
        left, right = layout.pages
        self.assertAlmostEqual(to_mm(left.paint.x1 - left.trim.x1), 2.0, places=6)
        self.assertAlmostEqual(to_mm(right.trim.x0 - right.paint.x0), 2.0, places=6)

    def test_top_and_bottom_are_outer_on_a_single_row(self):
        layout = spread(bleed=Insets.uniform(5 * MM), gutters=Gutters(4 * MM, 4 * MM))
        for page in layout.pages:
            self.assertAlmostEqual(to_mm(page.trim.y0 - page.paint.y0), 5.0, places=6)
