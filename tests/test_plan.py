# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

# pylint: disable=missing-class-docstring,missing-function-docstring

"""The imposition plan: page order as integers, checked without a PDF."""

import unittest

from impose import ImposeError
from impose.plan import BLANK, Placement, Plan, Surface, blanks_needed


def saddle_four() -> Plan:
    """A 4-page saddle-stitched booklet: front 4|1, back 2|3."""
    return Plan(
        columns=2,
        rows=1,
        pages=4,
        schema="saddle",
        surfaces=(
            Surface(0, "front", (Placement(3, 0, 0), Placement(0, 1, 0))),
            Surface(0, "back", (Placement(1, 0, 0), Placement(2, 1, 0))),
        ),
    )


class TestPlacement(unittest.TestCase):
    def test_cell_and_blank(self):
        self.assertEqual(Placement(0, 2, 3).cell, (2, 3))
        self.assertTrue(Placement(BLANK, 0, 0).is_blank)
        self.assertFalse(Placement(0, 0, 0).is_blank)

    def test_rejects_partial_turn(self):
        with self.assertRaises(ValueError):
            Placement(0, 0, 0, rotation=45)

    def test_accepts_quarter_turns(self):
        for turn in (0, 90, 180, 270, 360, -90):
            with self.subTest(turn=turn):
                self.assertEqual(Placement(0, 0, 0, rotation=turn).rotation, turn)

    def test_rejects_negative_cell(self):
        with self.assertRaises(ValueError):
            Placement(0, -1, 0)


class TestSurface(unittest.TestCase):
    def test_two_pages_in_one_cell_is_refused(self):
        with self.assertRaises(ImposeError) as caught:
            Surface(0, "front", (Placement(0, 0, 0), Placement(1, 0, 0)))
        self.assertIn("two pages in cell", str(caught.exception).lower())

    def test_lookup_by_cell(self):
        surface = saddle_four().surfaces[0]
        self.assertEqual(surface.at(0, 0).source, 3)
        self.assertIsNone(surface.at(5, 5))

    def test_sources_are_in_reading_order(self):
        surface = Surface(
            0,
            "front",
            (Placement(9, 1, 0), Placement(8, 0, 0), Placement(7, 0, 1)),
        )
        self.assertEqual(surface.sources, (8, 9, 7))

    def test_blanks_are_not_sources(self):
        surface = Surface(0, "front", (Placement(BLANK, 0, 0), Placement(5, 1, 0)))
        self.assertEqual(surface.sources, (5,))


class TestPlan(unittest.TestCase):
    def test_grid_and_counts(self):
        plan = saddle_four()
        self.assertEqual(plan.grid, (2, 1))
        self.assertEqual(plan.per_surface, 2)
        self.assertEqual(plan.sheets, 1)
        self.assertEqual(len(plan), 2)

    def test_iterates_surfaces(self):
        self.assertEqual([s.side for s in saddle_four()], ["front", "back"])

    def test_cell_outside_the_grid_is_refused(self):
        with self.assertRaises(ImposeError) as caught:
            Plan(
                columns=2,
                rows=1,
                pages=2,
                surfaces=(Surface(0, "front", (Placement(0, 5, 0),)),),
            )
        self.assertIn("outside", str(caught.exception))

    def test_rejects_empty_grid(self):
        with self.assertRaises(ValueError):
            Plan(columns=0, rows=1, pages=0, surfaces=())

    def test_describe_reads_as_a_sheet(self):
        text = saddle_four().describe()
        self.assertIn("sheet 1 front", text)
        # Page numbers are shown the way a person counts them.
        self.assertIn("4", text)
        self.assertIn("1", text)


class TestValidate(unittest.TestCase):
    def test_a_good_plan_passes(self):
        self.assertIsNone(saddle_four().validate())

    def test_a_page_imposed_twice_is_caught(self):
        plan = Plan(
            columns=2,
            rows=1,
            pages=2,
            schema="broken",
            surfaces=(Surface(0, "front", (Placement(0, 0, 0), Placement(0, 1, 0))),),
        )
        with self.assertRaises(ImposeError) as caught:
            plan.validate()
        self.assertIn("imposed 2 times", str(caught.exception))

    def test_a_page_never_imposed_is_caught(self):
        """The off-by-one that otherwise ships as a silent blank."""
        plan = Plan(
            columns=2,
            rows=1,
            pages=4,
            schema="broken",
            surfaces=(Surface(0, "front", (Placement(0, 0, 0), Placement(1, 1, 0))),),
        )
        with self.assertRaises(ImposeError) as caught:
            plan.validate()
        self.assertIn("never imposed", str(caught.exception))

    def test_a_page_outside_the_document_is_caught(self):
        plan = Plan(
            columns=2,
            rows=1,
            pages=2,
            schema="broken",
            surfaces=(Surface(0, "front", (Placement(0, 0, 0), Placement(99, 1, 0))),),
        )
        with self.assertRaises(ImposeError) as caught:
            plan.validate()
        self.assertIn("outside the document", str(caught.exception))

    def test_repetition_is_allowed_when_asked_for(self):
        """Step and repeat places one page many times, on purpose."""
        plan = Plan(
            columns=2,
            rows=1,
            pages=1,
            schema="step-and-repeat",
            surfaces=(Surface(0, "front", (Placement(0, 0, 0), Placement(0, 1, 0))),),
        )
        plan.validate(exhaustive=False)
        with self.assertRaises(ImposeError):
            plan.validate()

    def test_blanks_do_not_count_as_pages(self):
        plan = Plan(
            columns=2,
            rows=1,
            pages=1,
            schema="padded",
            surfaces=(
                Surface(0, "front", (Placement(0, 0, 0), Placement(BLANK, 1, 0))),
            ),
        )
        self.assertIsNone(plan.validate())


class TestBlanksNeeded(unittest.TestCase):
    def test_padding(self):
        self.assertEqual(blanks_needed(13, 4), 3)
        self.assertEqual(blanks_needed(16, 4), 0)
        self.assertEqual(blanks_needed(1, 8), 7)
        self.assertEqual(blanks_needed(0, 4), 0)

    def test_rejects_empty_form(self):
        with self.assertRaises(ValueError):
            blanks_needed(4, 0)
