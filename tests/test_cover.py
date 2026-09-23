# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

# pylint: disable=missing-class-docstring,missing-function-docstring

"""The perfect-bound cover flat.

The spine is leaves times caliper, the blanks that finish a section count,
and the scores land inside the flat rather than on its outer edge.
"""

import io
import unittest

import pikepdf

from impose import ImposeError
from impose.boxes import read_boxes
from impose.cover import build_flat, flat, impose_cover
from impose.geometry import Size
from impose.units import MM

from .support import make_pdf


class TestSpine(unittest.TestCase):
    def test_eighty_pages_at_a_tenth_of_a_millimetre(self):
        """Forty leaves, no pad, no glue: the spine is the paper alone."""
        cover = flat(Size(148 * MM, 210 * MM), 80, 0.1 * MM)
        self.assertAlmostEqual(cover.spine, 4 * MM, places=6)
        self.assertAlmostEqual(cover.flat.width, 300 * MM, places=6)
        self.assertAlmostEqual(cover.flat.height, 210 * MM, places=6)
        self.assertEqual(cover.scores, (148 * MM, 152 * MM))

    def test_blanks_that_finish_a_section_are_in_the_block(self):
        cover = flat(Size(100, 200), 81, 1)
        self.assertEqual(cover.imposed_pages, 84)
        self.assertAlmostEqual(cover.spine, 42)

    def test_hinges_sit_each_side_of_the_spine_and_glue_widens_only_the_panel(self):
        cover = flat(Size(100, 200), 4, 10, hinge=5, glue=1)
        self.assertAlmostEqual(cover.spine, 21)
        self.assertEqual(cover.scores, (100, 105, 126, 131))
        self.assertAlmostEqual(cover.flat.width, 231)

    def test_a_missing_gauge_is_refused(self):
        with self.assertRaises(ImposeError) as caught:
            flat(Size(100, 200), 8, 0)
        self.assertIn("micrometer", str(caught.exception))

    def test_the_sentence_names_the_pad_and_the_hinges(self):
        text = flat(Size(148 * MM, 210 * MM), 81, 0.1 * MM, hinge=5 * MM).describe()
        self.assertIn("spine 4.2 mm", text)
        self.assertIn("81 pages plus 3 blanks", text)
        self.assertIn("hinges 5 mm", text)
        self.assertIn("flat 310.2 × 210 mm", text)


class TestFlat(unittest.TestCase):
    def test_a_template_records_the_scores_inside_the_trim(self):
        cover = flat(Size(100, 200), 8, 10)
        document = build_flat(cover, bleed=0)
        boxes = read_boxes(document.pages[0])
        self.assertEqual(boxes.folds[0], cover.scores)
        self.assertIn(b"BACK", document.pages[0].obj["/Contents"].read_bytes())
        self.assertIn(b"FRONT", document.pages[0].obj["/Contents"].read_bytes())

    def test_artwork_of_the_wrong_size_is_named(self):
        cover = flat(Size(100, 200), 8, 10)
        artwork = make_pdf(1, trim=Size(90, 200), bleed=0, slug=0)
        with self.assertRaises(ImposeError) as caught:
            build_flat(cover, artwork, bleed=0)
        self.assertIn("artwork", str(caught.exception))
        self.assertIn("spine", str(caught.exception))

    def test_two_pages_are_the_outside_and_the_inside(self):
        cover = flat(Size(100, 200), 8, 10)
        width = cover.flat.width
        artwork = make_pdf(2, trim=Size(width, 200), bleed=0, slug=0)
        document = build_flat(cover, artwork, bleed=0)
        self.assertEqual(len(document.pages), 2)
        for page in document.pages:
            self.assertEqual(read_boxes(page).folds[0], cover.scores)


class TestImposedCover(unittest.TestCase):
    def test_the_scores_are_fold_marks_on_the_press_sheet(self):
        source = make_pdf(8)
        output = io.BytesIO()
        cover, result, _ = impose_cover(
            source, output, paper_caliper=1 * MM, plan_only=False
        )
        self.assertAlmostEqual(cover.spine, 4 * MM, places=5)
        self.assertEqual(result.plan.schema, "cover")
        self.assertFalse(result.pages_turned)
        output.seek(0)
        with pikepdf.open(output) as imposed:
            folds = read_boxes(imposed.pages[0]).folds
            self.assertEqual(len(folds[0]), 2)
            self.assertEqual(folds[1], ())

    def test_a_flat_that_only_fits_sideways_turns_as_a_whole(self):
        """Turning the flat keeps the spine square to the faces."""
        source = make_pdf(200, trim=Size(210 * MM, 297 * MM))
        output = io.BytesIO()
        _, result, _ = impose_cover(
            source, output, paper_caliper=0.1 * MM, plan_only=True
        )
        self.assertTrue(result.turned)
        self.assertFalse(result.pages_turned)
