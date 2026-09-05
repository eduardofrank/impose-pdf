# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

# pylint: disable=missing-class-docstring,missing-function-docstring

"""Registration targets and colour bars: what goes in the margin."""

import io
import unittest

import pikepdf

from impose.geometry import Rect
from impose.job import impose_document
from impose.marks import (
    STANDARD_PATCHES,
    circle_path,
    colour_bar,
    furniture,
    registration_targets,
    trim_marks,
)
from impose.press import INDIGO_5000
from impose.units import MM

from .support import make_pdf

AREA = INDIGO_5000.imageable_area()
FORM = Rect(AREA.x0 + 30 * MM, AREA.y0 + 40 * MM, AREA.x1 - 30 * MM, AREA.y1 - 40 * MM)


def content(data: bytes) -> str:
    pdf = pikepdf.open(io.BytesIO(data))
    obj = pdf.pages[0].obj["/Contents"]
    text = (
        b"".join(s.read_bytes() for s in obj)
        if isinstance(obj, pikepdf.Array)
        else obj.read_bytes()
    ).decode("ascii")
    pdf.close()
    return text


class TestFoldMarks(unittest.TestCase):
    """A fold is not a cut, and saying so is the whole point of the mark."""

    SPREAD = [Rect(0, 0, 100, 200), Rect(100, 0, 200, 200)]

    def dashed(self, marks):
        return [m for m in marks if m.dashed]

    def test_a_vertical_fold_is_dashed_at_both_ends(self):
        marks = trim_marks(self.SPREAD, fold_x=(100.0,))
        self.assertEqual(len(self.dashed(marks)), 2)
        self.assertTrue(all(m.x0 == m.x1 == 100.0 for m in self.dashed(marks)))

    def test_a_horizontal_fold_is_dashed_at_both_ends(self):
        """A form turned to fit has its spine running the other way. Matching
        folds against vertical lines only left it drawn as a cut line, which
        tells the bindery to guillotine the book down the spine."""
        marks = trim_marks(
            [Rect(0, 0, 200, 100), Rect(0, 100, 200, 200)], fold_y=(100.0,)
        )
        self.assertEqual(len(self.dashed(marks)), 2)
        self.assertTrue(all(m.y0 == m.y1 == 100.0 for m in self.dashed(marks)))

    def test_cut_lines_are_not_dashed(self):
        marks = trim_marks(self.SPREAD, fold_x=(100.0,))
        outer = [m for m in marks if m.x0 in (0.0, 200.0) and m.x0 == m.x1]
        self.assertTrue(outer)
        self.assertFalse(any(m.dashed for m in outer))

    def test_a_fold_that_is_not_a_cut_line_is_still_marked(self):
        """A spread that folds down its own middle has a fold there and no
        cell boundary. Two-stage jobs are entirely made of these."""
        single = [Rect(0, 0, 200, 200)]
        without = trim_marks(single)
        withfold = trim_marks(single, fold_x=(100.0,))
        self.assertEqual(len(withfold) - len(without), 2)
        self.assertEqual(len(self.dashed(withfold)), 2)

    def test_folds_on_both_axes_at_once(self):
        marks = trim_marks([Rect(0, 0, 200, 200)], fold_x=(100.0,), fold_y=(100.0,))
        self.assertEqual(len(self.dashed(marks)), 4)


class TestTargets(unittest.TestCase):
    def test_one_on_each_side_of_the_form(self):
        self.assertEqual(len(registration_targets(FORM, AREA)), 4)

    def test_they_sit_outside_the_form(self):
        for target in registration_targets(FORM, AREA):
            inside = FORM.x0 < target.x < FORM.x1 and FORM.y0 < target.y < FORM.y1
            self.assertFalse(inside)

    def test_they_stay_inside_the_imageable_area(self):
        for target in registration_targets(FORM, AREA):
            self.assertGreaterEqual(target.x - target.reach, AREA.x0 - 1e-6)
            self.assertLessEqual(target.x + target.reach, AREA.x1 + 1e-6)

    def test_a_form_filling_the_sheet_gets_none(self):
        """No margin, nowhere to put them, so none are drawn."""
        self.assertEqual(registration_targets(AREA, AREA), [])

    def test_circle_is_four_arcs(self):
        arcs = circle_path(0, 0, 10)
        self.assertEqual(len(arcs), 4)
        self.assertTrue(all(len(arc) == 6 for arc in arcs))


class TestColourBar(unittest.TestCase):
    def test_every_patch_is_drawn(self):
        self.assertEqual(len(colour_bar(FORM, AREA)), len(STANDARD_PATCHES))

    def test_it_sits_at_the_tail_of_the_sheet(self):
        patches = colour_bar(FORM, AREA)
        self.assertAlmostEqual(patches[0].rect.y0, AREA.y0, places=6)

    def test_the_inks_are_the_process_set(self):
        labels = [patch.label for patch in colour_bar(FORM, AREA)]
        for ink in ("C", "M", "Y", "K"):
            self.assertIn(ink, labels)
        self.assertIn("CMY", labels)

    def test_solids_are_full_strength(self):
        patches = {p.label: p.cmyk for p in colour_bar(FORM, AREA)}
        self.assertEqual(patches["C"], (1, 0, 0, 0))
        self.assertEqual(patches["K"], (0, 0, 0, 1))
        self.assertEqual(patches["C50"], (0.5, 0, 0, 0))

    def test_no_room_means_no_bar(self):
        self.assertEqual(colour_bar(AREA, AREA), [])

    def test_patches_too_narrow_to_read_are_not_drawn(self):
        """An unreadable bar is worse than none: it looks like a check."""
        narrow = Rect(AREA.x0, AREA.y0 + 40 * MM, AREA.x0 + 40 * MM, AREA.y1 - 40 * MM)
        self.assertEqual(colour_bar(narrow, AREA), [])


class TestFurniture(unittest.TestCase):
    def test_targets_and_bar_do_not_overlap(self):
        targets, patches = furniture(FORM, AREA)
        ceiling = max(patch.rect.y1 for patch in patches)
        for target in targets:
            self.assertGreater(target.y - target.reach, ceiling)

    def test_either_can_be_left_out(self):
        self.assertEqual(furniture(FORM, AREA, bar=False)[1], [])
        self.assertEqual(furniture(FORM, AREA, targets=False)[0], [])

    def test_a_target_that_would_land_on_the_bar_is_dropped(self):
        tight = Rect(
            AREA.x0 + 5 * MM, AREA.y0 + 12 * MM, AREA.x1 - 5 * MM, AREA.y1 - 5 * MM
        )
        targets, patches = furniture(tight, AREA)
        if patches:
            ceiling = max(patch.rect.y1 for patch in patches)
            for target in targets:
                self.assertGreater(target.y - target.reach, ceiling)


class TestThroughTheJob(unittest.TestCase):
    def test_off_by_default(self):
        buffer = io.BytesIO()
        impose_document(make_pdf(8), buffer, schema="saddle")
        text = content(buffer.getvalue())
        self.assertNotIn(" c\n", text)
        self.assertNotIn(" re f", text)

    def test_registration_draws_rings(self):
        buffer = io.BytesIO()
        impose_document(make_pdf(8), buffer, schema="saddle", registration=True)
        # Four targets, two rings each, four arcs a ring.
        self.assertEqual(content(buffer.getvalue()).count(" c\n"), 32)

    def test_colour_bar_draws_patches(self):
        buffer = io.BytesIO()
        impose_document(make_pdf(8), buffer, schema="saddle", colour_bar=True)
        self.assertEqual(
            content(buffer.getvalue()).count(" re f"), len(STANDARD_PATCHES)
        )

    def test_patches_are_laid_down_in_process_inks(self):
        buffer = io.BytesIO()
        impose_document(make_pdf(8), buffer, schema="saddle", colour_bar=True)
        self.assertIn("1 0 0 0 k", content(buffer.getvalue()))

    def test_no_marks_means_no_furniture(self):
        buffer = io.BytesIO()
        impose_document(
            make_pdf(8), buffer, schema="saddle", marks=None, registration=True
        )
        self.assertNotIn(" c\n", content(buffer.getvalue()))
