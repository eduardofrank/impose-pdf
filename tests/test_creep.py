# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

# pylint: disable=missing-class-docstring,missing-function-docstring

"""Creep: nested sheets push out, and the image slides to meet the trim."""

import io
import unittest

from impose.boxes import read_boxes
from impose.geometry import Size
from impose.job import impose_document
from impose.layout import _creep_shift, lay_out
from impose.plan import Placement, Surface
from impose.press import INDIGO_5000
from impose.schemas import cutstack, nup, perfect, saddle, signature, steprepeat
from impose.units import MM, to_mm

from .support import make_pdf

CALIPER = 0.1 * MM


def spread(shift=0.0, rotation=0, depth=1):
    """One saddle spread, with the fold between the two columns.

    *shift* is how far the images should move, which the layout now reaches by
    multiplying the caliper by the leaf's own depth in the nest.
    """
    source = make_pdf(4)
    boxes = read_boxes(source.pages[0])
    return lay_out(
        Surface(
            0,
            "front",
            (
                Placement(3, 0, 0, rotation, depth),
                Placement(0, 1, 0, rotation, depth),
            ),
        ),
        columns=2,
        rows=1,
        trim=boxes.trim_size,
        trim_origin=boxes.trim,
        bleed=boxes.bleed_insets,
        press=INDIGO_5000,
        caliper=shift / depth if depth else 0.0,
        fold_columns=(1,),
    )


class TestDirection(unittest.TestCase):
    def test_the_cells_do_not_move(self):
        """The fold is where the fold is; only the image slides."""
        plain, crept = spread(), spread(1 * MM)
        for a, b in zip(plain.pages, crept.pages):
            self.assertEqual(a.trim, b.trim)

    def test_both_images_move_toward_the_spine(self):
        """Left page's spine is on its right, and the reverse."""
        plain, crept = spread(), spread(1 * MM)
        left_before, right_before = plain.pages
        left_after, right_after = crept.pages
        # Window left  -> image right -> toward the spine for the left page.
        self.assertAlmostEqual(
            to_mm(left_before.clip.x0 - left_after.clip.x0), 1.0, places=6
        )
        # Window right -> image left  -> toward the spine for the right page.
        self.assertAlmostEqual(
            to_mm(right_after.clip.x0 - right_before.clip.x0), 1.0, places=6
        )

    def test_the_window_keeps_its_size(self):
        plain, crept = spread(), spread(1 * MM)
        for a, b in zip(plain.pages, crept.pages):
            self.assertAlmostEqual(a.clip.width, b.clip.width, places=9)

    def test_no_caliper_means_no_shift(self):
        plain, zero = spread(), spread(0.0)
        for a, b in zip(plain.pages, zero.pages):
            self.assertEqual(a.clip, b.clip)

    def test_a_quarter_turn_moves_the_window_on_the_other_axis(self):
        """The shift is along the sheet; the window lives in the page."""
        plain, crept = spread(rotation=90), spread(1 * MM, rotation=90)
        left_before, left_after = plain.pages[0], crept.pages[0]
        self.assertAlmostEqual(left_before.clip.x0, left_after.clip.x0, places=9)
        self.assertAlmostEqual(
            to_mm(left_before.clip.y0 - left_after.clip.y0), 1.0, places=6
        )

    def test_a_cell_with_no_fold_beside_it_does_not_creep(self):
        source = make_pdf(4)
        boxes = read_boxes(source.pages[0])
        flat = lay_out(
            Surface(0, "front", (Placement(0, 0, 0, 0, 1), Placement(1, 1, 0, 0, 1))),
            columns=2,
            rows=1,
            trim=boxes.trim_size,
            trim_origin=boxes.trim,
            press=INDIGO_5000,
            caliper=1 * MM,
            fold_columns=(),
        )
        plain = lay_out(
            Surface(0, "front", (Placement(0, 0, 0, 0, 1), Placement(1, 1, 0, 0, 1))),
            columns=2,
            rows=1,
            trim=boxes.trim_size,
            trim_origin=boxes.trim,
            press=INDIGO_5000,
        )
        for a, b in zip(flat.pages, plain.pages):
            self.assertEqual(a.clip, b.clip)


class TestDepth(unittest.TestCase):
    """How deep a page sits in the nest, which is the schema's to say.

    Depth used to be worked out per sheet from the schema name. A folded
    signature carries leaves at several depths on one piece of paper, so it
    belongs to the placement instead, and the caliper says what a depth costs.
    """

    @staticmethod
    def depths(plan):
        return [
            sorted({p.depth for p in surface.placements}) for surface in plan.surfaces
        ]

    def test_the_outermost_sheet_does_not_creep(self):
        """Nothing wraps it, so its fold is not displaced."""
        plan = saddle.impose(16)
        self.assertEqual(sorted({p.depth for p in plan.surfaces[0].placements}), [0])

    def test_depth_grows_with_the_nest(self):
        self.assertEqual(
            self.depths(saddle.impose(16)), [[0], [0], [1], [1], [2], [2], [3], [3]]
        )

    def test_depth_restarts_with_each_gathered_section(self):
        """Sections are stacked, not nested, so each starts again at zero."""
        self.assertEqual(
            self.depths(perfect.impose(32, section_pages=8)),
            [[0], [0], [1], [1]] * 4,  # 32 pages is four 8-page sections
        )

    def test_a_signature_carries_two_depths_on_one_sheet(self):
        """Cut the bolts and it is a nest: the outer pair of leaves does not
        creep and the inner pair does, on the same piece of paper."""
        plan = signature.impose(8, columns=2, rows=2)
        self.assertEqual(self.depths(plan), [[0, 1], [0, 1]])

    def test_a_bigger_signature_nests_deeper(self):
        plan = signature.impose(16, columns=4, rows=2)
        self.assertEqual(self.depths(plan), [[0, 1, 2, 3], [0, 1, 2, 3]])

    def test_flat_schemas_never_creep(self):
        for schema, plan in (
            ("nup", nup.impose(16, columns=2, rows=2)),
            ("cutstack", cutstack.impose(16, columns=2, rows=2)),
            ("steprepeat", steprepeat.impose(2, columns=2, rows=2)),
        ):
            with self.subTest(schema=schema):
                self.assertEqual(
                    {p.depth for s in plan.surfaces for p in s.placements}, {0}
                )

    def test_no_caliper_is_no_creep(self):
        plain, zero = spread(), spread(0.0)
        for a, b in zip(plain.pages, zero.pages):
            self.assertEqual(a.clip, b.clip)

    def test_depth_cannot_be_negative(self):
        with self.assertRaises(ValueError):
            Placement(0, 0, 0, 0, -1)


class TestSheetSpaceDirection(unittest.TestCase):
    """Which way the image goes, measured before rotation muddies it.

    _creep_shift answers in sheet space and layout expresses that in the
    source page's own axes, so an upside-down cell's clip window moves the
    opposite way while its image still travels toward the spine. Checking the
    clip alone reads as a bug; checking the sheet-space vector does not.
    """

    FOLD = (1,)

    def shift(self, column, depth, caliper=CALIPER):
        return _creep_shift(Placement(0, column, 0, 0, depth), self.FOLD, caliper)

    def test_a_page_left_of_the_fold_moves_right(self):
        x, y = self.shift(column=0, depth=1)
        self.assertAlmostEqual(x, CALIPER)
        self.assertEqual(y, 0.0)

    def test_a_page_right_of_the_fold_moves_left(self):
        x, _ = self.shift(column=1, depth=1)
        self.assertAlmostEqual(x, -CALIPER)

    def test_the_outer_leaf_does_not_move(self):
        self.assertEqual(self.shift(column=0, depth=0), (0.0, 0.0))

    def test_distance_is_depth_times_thickness(self):
        for depth in range(5):
            with self.subTest(depth=depth):
                x, _ = self.shift(column=0, depth=depth)
                self.assertAlmostEqual(x, depth * CALIPER)

    def test_no_thickness_is_no_shift(self):
        self.assertEqual(self.shift(column=0, depth=3, caliper=0.0), (0.0, 0.0))

    def test_a_cell_with_no_fold_beside_it_does_not_move(self):
        placement = Placement(0, 0, 0, 0, 3)
        self.assertEqual(_creep_shift(placement, (), CALIPER), (0.0, 0.0))


class TestSignatureCreep(unittest.TestCase):
    """A folded signature nests within itself, so one sheet creeps unevenly."""

    @staticmethod
    def clips(caliper):
        source = make_pdf(16, trim=Size(105 * MM, 148 * MM))
        boxes = read_boxes(source.pages[0])
        plan = signature.impose(16, columns=2, rows=2)
        layout = lay_out(
            plan.surfaces[0],
            columns=2,
            rows=2,
            trim=boxes.trim_size,
            trim_origin=boxes.trim,
            press=INDIGO_5000,
            caliper=caliper,
            fold_columns=plan.fold_columns,
        )
        depth = {(p.column, p.row): p.depth for p in plan.surfaces[0].placements}
        return {
            (p.column, p.row): (depth[(p.column, p.row)], p.clip.x0)
            for p in layout.pages
        }

    def test_the_outer_pair_stays_and_the_inner_pair_moves(self):
        plain, crept = self.clips(0.0), self.clips(CALIPER)
        for cell, (depth, position) in crept.items():
            with self.subTest(cell=cell, depth=depth):
                moved = abs(position - plain[cell][1])
                self.assertAlmostEqual(moved, depth * CALIPER, places=9)

    def test_both_depths_are_present_on_one_sheet(self):
        self.assertEqual({d for d, _ in self.clips(CALIPER).values()}, {0, 1})

    def test_the_two_halves_of_a_row_move_opposite_ways(self):
        """Each toward its own spine, which is on opposite sides."""
        plain, crept = self.clips(0.0), self.clips(CALIPER)
        left = crept[(0, 0)][1] - plain[(0, 0)][1]
        right = crept[(1, 0)][1] - plain[(1, 0)][1]
        self.assertAlmostEqual(left, -right)
        self.assertNotAlmostEqual(left, 0.0)


class TestEndToEnd(unittest.TestCase):
    def test_a_crept_job_differs_from_an_uncrept_one(self):
        plain, crept = io.BytesIO(), io.BytesIO()
        impose_document(make_pdf(32), plain, schema="saddle")
        impose_document(make_pdf(32), crept, schema="saddle", paper_caliper="0.1mm")
        self.assertNotEqual(plain.getvalue(), crept.getvalue())

    def test_caliper_accepts_a_length(self):
        result = impose_document(
            make_pdf(16), io.BytesIO(), schema="saddle", paper_caliper="0.12mm"
        )
        self.assertEqual(result.sheets, 4)

    def test_perfect_binding_creeps_within_its_sections(self):
        result = impose_document(
            make_pdf(32),
            io.BytesIO(),
            schema="perfect",
            section_pages=16,
            paper_caliper="0.1mm",
        )
        self.assertEqual(result.sheets, 8)
