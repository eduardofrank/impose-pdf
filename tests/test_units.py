# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

"""Lengths are PDF points, and sheets are the size the standard says.

Expectations are literals from ISO 216 / ISO 217 and from the PDF
specification, never restatements of what the code computes.
"""

# The test name is the documentation here; docstrings appear only where
# they add something a name cannot carry.
# pylint: disable=missing-class-docstring,missing-function-docstring

import decimal
import unittest

from impose.geometry import Size
from impose.units import INCH, MM, length, paper, paper_names, to_mm

# 1 inch = 72 PDF points, so 1 mm = 72/25.4. Spelled out rather than imported
# so this file is an independent check on the module.
POINTS_PER_MM = 72 / 25.4


class TestLength(unittest.TestCase):
    def test_inch_is_seventy_two_points(self):
        self.assertEqual(length("1in"), 72.0)
        self.assertEqual(INCH, 72.0)

    def test_point_is_the_pdf_point(self):
        """Not the TeX point of 1/72.27 inch."""
        self.assertEqual(length("1pt"), 1.0)
        self.assertEqual(length("72pt"), length("1in"))
        self.assertEqual(length("1bp"), 1.0)

    def test_millimetre(self):
        self.assertAlmostEqual(length("1mm"), POINTS_PER_MM, places=12)
        self.assertAlmostEqual(MM, POINTS_PER_MM, places=12)
        self.assertAlmostEqual(length("25.4mm"), 72.0, places=9)

    def test_centimetre_and_pica(self):
        self.assertAlmostEqual(length("1cm"), 10 * POINTS_PER_MM, places=12)
        self.assertEqual(length("1pc"), 12.0)

    def test_bare_number_is_points(self):
        self.assertEqual(length("12"), 12.0)
        self.assertEqual(length("0.75"), 0.75)

    def test_numbers_pass_through(self):
        self.assertEqual(length(12), 12.0)
        self.assertEqual(length(12.5), 12.5)
        self.assertEqual(length(decimal.Decimal("12.5")), 12.5)

    def test_negative(self):
        self.assertEqual(length("-3pt"), -3.0)

    def test_rejects_unknown_unit(self):
        with self.assertRaises(ValueError) as caught:
            length("3furlong")
        self.assertIn("furlong", str(caught.exception))

    def test_rejects_nonsense(self):
        for bad in ("", "mm", "three mm", "3 mm 4"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                length(bad)


class TestPaper(unittest.TestCase):
    def test_a4_is_210_by_297_mm(self):
        size = paper("A4")
        self.assertAlmostEqual(to_mm(size.width), 210.0, places=9)
        self.assertAlmostEqual(to_mm(size.height), 297.0, places=9)
        self.assertAlmostEqual(size.width, 595.2755905, places=6)
        self.assertAlmostEqual(size.height, 841.8897637, places=6)

    def test_sra3_is_the_press_sheet(self):
        """SRA3 is 320x450 mm -- A3 plus bleed and marks."""
        size = paper("SRA3")
        self.assertAlmostEqual(to_mm(size.width), 320.0, places=9)
        self.assertAlmostEqual(to_mm(size.height), 450.0, places=9)

    def test_letter_is_exact(self):
        self.assertEqual(paper("letter"), Size(612.0, 792.0))

    def test_names_are_case_and_space_insensitive(self):
        self.assertEqual(paper("a4"), paper("A4"))
        self.assertEqual(paper("ANSI-A"), paper("ansi a"))

    def test_explicit_sizes(self):
        self.assertEqual(paper("100x200"), Size(100.0, 200.0))
        self.assertEqual(paper("210mm x 297mm"), paper("A4"))
        # 29.7cm and 297mm are the same length by different arithmetic, so
        # they can differ in the last bit. Equal to a picometre is equal.
        by_cm, by_name = paper("21cm×29.7cm"), paper("A4")
        self.assertAlmostEqual(by_cm.width, by_name.width, places=9)
        self.assertAlmostEqual(by_cm.height, by_name.height, places=9)

    def test_a_series_halves(self):
        """Each A size is the previous one folded, to within ISO rounding."""
        for larger, smaller in (("A3", "A4"), ("A4", "A5"), ("A5", "A6")):
            with self.subTest(pair=(larger, smaller)):
                big, small = paper(larger), paper(smaller)
                self.assertAlmostEqual(
                    to_mm(big.height) / 2, to_mm(small.width), delta=0.5
                )

    def test_tuple_and_size_pass_through(self):
        self.assertEqual(paper((10, 20)), Size(10.0, 20.0))
        self.assertEqual(paper(Size(10, 20)), Size(10, 20))

    def test_rejects_nonsense(self):
        for bad in ("A99", "not a size", "10x20x30"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                paper(bad)

    def test_every_advertised_name_parses(self):
        for name in paper_names():
            with self.subTest(name=name):
                size = paper(name)
                self.assertGreater(size.width, 0)
                self.assertGreater(size.height, 0)
