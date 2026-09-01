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
)
from impose.press import INDIGO_5000
from impose.units import MM, to_mm

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
