# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

# pylint: disable=missing-class-docstring,missing-function-docstring

"""Press profiles: sheet, imageable area, and where the grippers are."""

import unittest

from impose import ImposeError
from impose.geometry import Insets, Size
from impose.press import (
    INDIGO_5000,
    INDIGO_7000,
    INDIGO_12000,
    Press,
    custom,
    get,
    insets,
    lookup,
    press_names,
    resolve,
)
from impose.units import MM, to_mm


class TestIndigo(unittest.TestCase):
    def test_sheet_and_imageable_are_the_stated_sizes(self):
        self.assertAlmostEqual(to_mm(INDIGO_5000.sheet.width), 320.0, places=6)
        self.assertAlmostEqual(to_mm(INDIGO_5000.sheet.height), 470.0, places=6)
        area = INDIGO_5000.imageable_area()
        self.assertAlmostEqual(to_mm(area.width), 310.0, places=6)
        self.assertAlmostEqual(to_mm(area.height), 450.0, places=6)

    def test_gripper_margin_is_not_centred(self):
        """The lead edge loses more than the tail; a centred model is wrong."""
        self.assertAlmostEqual(to_mm(INDIGO_5000.margins.bottom), 12.0, places=6)
        self.assertAlmostEqual(to_mm(INDIGO_5000.margins.top), 8.0, places=6)
        self.assertGreater(INDIGO_5000.margins.bottom, INDIGO_5000.margins.top)

    def test_side_margins_are_equal(self):
        self.assertAlmostEqual(to_mm(INDIGO_5000.margins.left), 5.0, places=6)
        self.assertAlmostEqual(to_mm(INDIGO_5000.margins.right), 5.0, places=6)

    def test_gripper_edge_is_the_short_edge(self):
        self.assertEqual(INDIGO_5000.gripper, "bottom")
        self.assertLess(INDIGO_5000.sheet.width, INDIGO_5000.sheet.height)

    def test_imageable_area_sits_where_the_margins_put_it(self):
        area = INDIGO_5000.imageable_area()
        self.assertAlmostEqual(to_mm(area.y0), 12.0, places=6)
        self.assertAlmostEqual(to_mm(area.x0), 5.0, places=6)

    def test_larger_models(self):
        self.assertAlmostEqual(to_mm(INDIGO_7000.sheet.width), 330.0, places=6)
        self.assertAlmostEqual(to_mm(INDIGO_12000.sheet.width), 750.0, places=6)
        self.assertTrue(INDIGO_12000.sheet.is_landscape)


class TestSmallerSheets(unittest.TestCase):
    def test_smaller_sheet_keeps_the_gripper_strip(self):
        """A short sheet loses the difference at the tail, not at the grippers."""
        area = INDIGO_5000.imageable_area(Size(320 * MM, 400 * MM))
        self.assertAlmostEqual(to_mm(area.y0), 12.0, places=6)
        self.assertAlmostEqual(to_mm(area.height), 400 - 12 - 8, places=6)

    def test_oversize_sheet_is_refused(self):
        with self.assertRaises(ImposeError) as caught:
            INDIGO_5000.imageable_area(Size(400 * MM, 600 * MM))
        self.assertIn("at most", str(caught.exception))

    def test_undersize_sheet_is_refused_when_a_minimum_is_set(self):
        press = Press(
            name="fussy",
            sheet=Size(1000, 1000),
            margins=Insets.uniform(10),
            min_sheet=Size(500, 500),
        )
        with self.assertRaises(ImposeError):
            press.imageable_area(Size(100, 100))


class TestRegistry(unittest.TestCase):
    def test_aliases(self):
        for alias in ("indigo", "Indigo-5000", "HP Indigo 5000", "indigo_5000"):
            with self.subTest(alias=alias):
                self.assertIs(lookup(alias), INDIGO_5000)

    def test_unknown_press_lists_the_alternatives(self):
        with self.assertRaises(ImposeError) as caught:
            get("linotype")
        self.assertIn("indigo-5000", str(caught.exception))

    def test_every_name_resolves(self):
        for name in press_names():
            with self.subTest(name=name):
                self.assertIsNotNone(lookup(name))

    def test_describe_reads_like_a_spec_sheet(self):
        text = INDIGO_5000.describe()
        self.assertIn("320 × 470 mm", text)
        self.assertIn("12 mm gripper at bottom", text)


class TestCustom(unittest.TestCase):
    def test_centred_imageable_area(self):
        press = custom(sheet="SRA3", imageable="A3")
        self.assertAlmostEqual(press.margins.left, press.margins.right, places=9)
        self.assertAlmostEqual(press.margins.bottom, press.margins.top, places=9)

    def test_explicit_margins(self):
        press = custom(sheet="SRA3", margins=Insets(bottom=10 * MM, top=5 * MM))
        self.assertAlmostEqual(to_mm(press.margins.bottom), 10.0, places=6)

    def test_uniform_margin_from_a_string(self):
        press = custom(sheet="SRA3", margins="5mm")
        self.assertAlmostEqual(to_mm(press.margins.top), 5.0, places=6)

    def test_imageable_larger_than_sheet_is_refused(self):
        with self.assertRaises(ImposeError):
            custom(sheet="A4", imageable="A3")

    def test_both_imageable_and_margins_is_a_mistake(self):
        with self.assertRaises(ValueError):
            custom(sheet="SRA3", imageable="A3", margins="5mm")

    def test_margins_leaving_nothing_is_refused(self):
        with self.assertRaises(ValueError):
            Press(name="silly", sheet=Size(100, 100), margins=Insets.uniform(60))


class TestInsets(unittest.TestCase):
    def test_one_length_is_every_edge(self):
        self.assertAlmostEqual(to_mm(insets("5mm").right), 5.0, places=6)

    def test_named_edges_leave_the_rest_at_nothing(self):
        border = insets({"bottom": "12mm", "top": "5mm"})
        self.assertAlmostEqual(to_mm(border.bottom), 12.0, places=6)
        self.assertEqual(border.left, 0.0)

    def test_an_insets_passes_through(self):
        border = Insets(bottom=3)
        self.assertIs(insets(border), border)

    def test_a_sheet_has_no_edge_called_side(self):
        with self.assertRaises(ImposeError) as caught:
            insets({"side": "5mm"})
        self.assertIn("bottom, top, left, right", str(caught.exception))


class TestResolve(unittest.TestCase):
    """A press as a command line or a job file names one."""

    def test_a_press_is_already_the_answer(self):
        self.assertIs(resolve(INDIGO_5000), INDIGO_5000)

    def test_a_name_is_a_profile(self):
        self.assertIs(resolve("indigo-5000"), INDIGO_5000)

    def test_a_size_is_a_press_whose_whole_sheet_images(self):
        press = resolve("320mmx450mm")
        self.assertAlmostEqual(to_mm(press.sheet.width), 320.0, places=6)
        self.assertEqual(press.margins, Insets())

    def test_an_unknown_name_names_the_alternatives(self):
        with self.assertRaises(ImposeError) as caught:
            resolve("linotype")
        self.assertIn("indigo-5000", str(caught.exception))

    def test_margins_override_a_profile_and_keep_its_sheet(self):
        press = resolve({"name": "indigo-5000", "margins": {"bottom": "15mm"}})
        self.assertEqual(press.sheet, INDIGO_5000.sheet)
        self.assertAlmostEqual(to_mm(press.gripper_margin), 15.0, places=6)

    def test_an_edge_not_named_keeps_the_profile_figure(self):
        """Saying nothing about the tail cannot widen the imageable area."""
        press = resolve({"name": "indigo-5000", "margins": {"bottom": "15mm"}})
        self.assertAlmostEqual(to_mm(press.margins.top), 8.0, places=6)
        self.assertAlmostEqual(to_mm(press.margins.left), 5.0, places=6)

    def test_an_edge_not_named_is_nothing_with_no_profile_to_keep(self):
        press = resolve({"sheet": "SRA3", "margins": {"bottom": "15mm"}})
        self.assertEqual(press.margins.top, 0.0)

    def test_a_uniform_margin_replaces_the_profile_border_whole(self):
        press = resolve({"name": "indigo-5000", "margins": "10mm"})
        self.assertAlmostEqual(to_mm(press.margins.top), 10.0, places=6)
        self.assertAlmostEqual(to_mm(press.gripper_margin), 10.0, places=6)

    def test_an_edge_the_profile_does_not_have_either(self):
        with self.assertRaises(ImposeError) as caught:
            resolve({"name": "indigo-5000", "margins": {"side": "5mm"}})
        self.assertIn("bottom, top, left, right", str(caught.exception))

    def test_a_sheet_alone_redefines_the_maximum_and_keeps_the_border(self):
        press = resolve({"name": "indigo-5000", "sheet": "SRA3"})
        self.assertAlmostEqual(to_mm(press.sheet.height), 450.0, places=6)
        self.assertEqual(press.margins, INDIGO_5000.margins)

    def test_a_sheet_makes_an_unknown_name_a_label(self):
        """A shop names its own machine; the name is not looked up."""
        press = resolve(
            {"name": "the-old-heidelberg", "sheet": "SRA3", "margins": "5mm"}
        )
        self.assertEqual(press.name, "the-old-heidelberg")

    def test_the_gripper_edge_can_be_moved(self):
        self.assertEqual(resolve({"sheet": "SRA3", "gripper": "left"}).gripper, "left")

    def test_an_edge_no_sheet_has_is_refused(self):
        with self.assertRaises(ImposeError) as caught:
            resolve({"sheet": "SRA3", "gripper": "north"})
        self.assertIn("bottom, top, left, right", str(caught.exception))

    def test_a_press_needs_a_sheet_or_a_profile(self):
        with self.assertRaises(ImposeError):
            resolve({"margins": "5mm"})

    def test_a_field_no_press_has_is_refused(self):
        with self.assertRaises(ImposeError) as caught:
            resolve({"sheet": "SRA3", "grippers": "left"})
        self.assertIn("grippers", str(caught.exception))

    def test_nothing_that_describes_a_press_is_refused(self):
        with self.assertRaises(ImposeError):
            resolve(320)

    def test_margins_wider_than_the_sheet_name_the_sheet(self):
        with self.assertRaises(ValueError) as caught:
            resolve({"sheet": "100mmx100mm", "margins": "60mm"})
        self.assertIn("100 × 100 mm", str(caught.exception))
