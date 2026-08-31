# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

"""Geometry in PDF coordinates: origin bottom-left, y growing upward."""

# The test name is the documentation here; docstrings appear only where
# they add something a name cannot carry.
# pylint: disable=missing-class-docstring,missing-function-docstring

import unittest

from impose.geometry import Insets, Rect, Size, approx, bounds


class TestSize(unittest.TestCase):
    def test_swap_and_rotate(self):
        self.assertEqual(Size(10, 20).swapped(), Size(20, 10))
        self.assertEqual(Size(10, 20).rotated(0), Size(10, 20))
        self.assertEqual(Size(10, 20).rotated(90), Size(20, 10))
        self.assertEqual(Size(10, 20).rotated(180), Size(10, 20))
        self.assertEqual(Size(10, 20).rotated(270), Size(20, 10))

    def test_orientation(self):
        self.assertTrue(Size(20, 10).is_landscape)
        self.assertFalse(Size(10, 20).is_landscape)
        self.assertFalse(Size(10, 10).is_landscape)

    def test_unpacks(self):
        width, height = Size(10, 20)
        self.assertEqual((width, height), (10, 20))

    def test_rejects_negative(self):
        with self.assertRaises(ValueError):
            Size(-1, 10)

    def test_immutable(self):
        with self.assertRaises(Exception):
            Size(1, 2).width = 5


class TestInsets(unittest.TestCase):
    def test_uniform(self):
        self.assertEqual(Insets.uniform(3), Insets(3, 3, 3, 3))

    def test_totals(self):
        insets = Insets(left=1, right=2, bottom=3, top=4)
        self.assertEqual(insets.horizontal, 3)
        self.assertEqual(insets.vertical, 7)

    def test_truthiness(self):
        self.assertFalse(Insets())
        self.assertTrue(Insets(left=1))


class TestRect(unittest.TestCase):
    def test_size_and_centre(self):
        rect = Rect(10, 20, 30, 60)
        self.assertEqual(rect.size, Size(20, 40))
        self.assertEqual(rect.center, (20, 40))

    def test_from_size(self):
        self.assertEqual(Rect.from_size(Size(10, 20)), Rect(0, 0, 10, 20))
        self.assertEqual(Rect.from_size(Size(10, 20), at=(5, 5)), Rect(5, 5, 15, 25))

    def test_translate(self):
        self.assertEqual(Rect(0, 0, 10, 20).translated(5, -5), Rect(5, -5, 15, 15))

    def test_expand_is_outward(self):
        """Bleed grows the rectangle on every edge."""
        grown = Rect(10, 10, 20, 20).expanded(Insets.uniform(3))
        self.assertEqual(grown, Rect(7, 7, 23, 23))

    def test_shrink_is_inward(self):
        """An imageable area pulls in from the sheet edges."""
        inner = Rect(0, 0, 100, 100).shrunk(Insets(left=5, right=5, bottom=10, top=10))
        self.assertEqual(inner, Rect(5, 10, 95, 90))

    def test_expand_and_shrink_are_inverse(self):
        insets = Insets(left=1, right=2, bottom=3, top=4)
        rect = Rect(10, 10, 50, 50)
        self.assertEqual(rect.expanded(insets).shrunk(insets), rect)

    def test_asymmetric_insets_respect_pdf_axes(self):
        """`bottom` moves y0 and `top` moves y1, since y grows upward."""
        rect = Rect(0, 0, 10, 10).expanded(Insets(bottom=1, top=2))
        self.assertEqual(rect.y0, -1)
        self.assertEqual(rect.y1, 12)

    def test_union_and_bounds(self):
        self.assertEqual(Rect(0, 0, 1, 1).union(Rect(5, 5, 6, 6)), Rect(0, 0, 6, 6))
        self.assertEqual(
            bounds([Rect(0, 0, 1, 1), Rect(5, 5, 6, 6), Rect(-1, 2, 0, 3)]),
            Rect(-1, 0, 6, 6),
        )

    def test_bounds_of_nothing_is_an_error(self):
        with self.assertRaises(ValueError):
            bounds([])

    def test_contains(self):
        sheet = Rect(0, 0, 100, 100)
        self.assertTrue(sheet.contains(Rect(10, 10, 90, 90)))
        self.assertTrue(sheet.contains(sheet))
        self.assertFalse(sheet.contains(Rect(-1, 10, 90, 90)))

    def test_contains_tolerates_float_noise(self):
        """A form missing by a nanometre fits; one missing by a millimetre does not."""
        sheet = Rect(0, 0, 100, 100)
        self.assertTrue(sheet.contains(Rect(0, 0, 100 + 1e-9, 100)))
        self.assertFalse(sheet.contains(Rect(0, 0, 100 + 2.8, 100)))

    def test_centered_in(self):
        centred = Rect(0, 0, 10, 10).centered_in(Rect(0, 0, 100, 50))
        self.assertEqual(centred, Rect(45, 20, 55, 30))
        self.assertEqual(centred.size, Size(10, 10))

    def test_rejects_inside_out(self):
        with self.assertRaises(ValueError):
            Rect(10, 0, 0, 10)

    def test_immutable(self):
        with self.assertRaises(Exception):
            Rect(0, 0, 1, 1).x0 = 5


class TestApprox(unittest.TestCase):
    def test_tolerance(self):
        self.assertTrue(approx(1.0, 1.0 + 1e-9))
        self.assertFalse(approx(1.0, 1.01))
