# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

# pylint: disable=missing-class-docstring,missing-function-docstring

"""Folding a sheet, checked by reading the folded booklet.

The ordering is derived rather than tabulated, so these check the derivation
against the two things that can be known independently: the four-page case,
which the bound schemas already impose and have always imposed correctly, and
the structural properties any signature must have whatever its size.
"""

import unittest

from impose import ImposeError
from impose.fold import (
    FOOT_TO_FOOT,
    HEAD_TO_HEAD,
    Face,
    Fold,
    leaves,
    pages_per_sheet,
    signature_folds,
)
from impose.schemas import backing_cell


def folded(columns, rows, style=HEAD_TO_HEAD, flip="long-edge"):
    return leaves(columns, rows, signature_folds(columns, rows, style=style), flip=flip)


def grid(faces, side, rows, columns):
    """The page numbers on one surface, row by row, as printed."""
    at = {(f.side, f.column, f.row): n for n, f in enumerate(faces, 1)}
    return [[at[(side, c, r)] for c in range(columns)] for r in range(rows)]


class TestAgainstTheFoldedSheetWeAlreadyImpose(unittest.TestCase):
    """A four-page signature is one fold, and both bound schemas already do it.

    If the folding model disagreed here it would not be a generalisation of
    what the tool does -- it would be a second, contradicting answer.
    """

    def test_four_pages_match_the_bound_schemas(self):
        faces = folded(2, 1)
        self.assertEqual(grid(faces, "front", 1, 2), [[4, 1]])
        self.assertEqual(grid(faces, "back", 1, 2), [[2, 3]])

    def test_a_single_fold_turns_nothing(self):
        self.assertEqual({f.rotation for f in folded(2, 1)}, {0})


class TestEightPageSignature(unittest.TestCase):
    def test_the_classic_layout(self):
        faces = folded(2, 2)
        self.assertEqual(grid(faces, "front", 2, 2), [[5, 4], [8, 1]])
        self.assertEqual(grid(faces, "back", 2, 2), [[3, 6], [2, 7]])

    def test_one_row_is_turned_and_the_other_is_not(self):
        """The head-to-head layout, which is what the second fold forces."""
        faces = folded(2, 2)
        turned = {(f.row, f.rotation) for f in faces}
        self.assertEqual(turned, {(0, 180), (1, 0)})

    def test_foot_to_foot_turns_the_other_row(self):
        faces = folded(2, 2, FOOT_TO_FOOT)
        self.assertEqual({(f.row, f.rotation) for f in faces}, {(0, 0), (1, 180)})

    def test_foot_to_foot_is_the_same_sheet_the_other_way_up(self):
        head = grid(folded(2, 2, HEAD_TO_HEAD), "front", 2, 2)
        foot = grid(folded(2, 2, FOOT_TO_FOOT), "front", 2, 2)
        self.assertEqual(foot, head[::-1])


class TestAnySignature(unittest.TestCase):
    """Properties that hold whatever the sheet is folded into."""

    SHAPES = ((2, 1), (2, 2), (2, 4), (4, 2), (4, 4), (1, 2), (1, 4))

    def test_every_face_is_used_exactly_once(self):
        for columns, rows in self.SHAPES:
            for style in (HEAD_TO_HEAD, FOOT_TO_FOOT):
                with self.subTest(shape=(columns, rows), style=style):
                    faces = folded(columns, rows, style)
                    self.assertEqual(len(faces), pages_per_sheet(columns, rows))
                    self.assertEqual(len(set(faces)), len(faces))

    def test_the_two_faces_of_a_leaf_are_consecutive_pages(self):
        """Front and back of one piece of paper have to be pages n and n+1,
        or the reader turns a leaf and lands somewhere else in the book."""
        for columns, rows in self.SHAPES:
            with self.subTest(shape=(columns, rows)):
                faces = folded(columns, rows)
                for index in range(0, len(faces), 2):
                    first, second = faces[index], faces[index + 1]
                    self.assertNotEqual(first.side, second.side)
                    physical = (
                        (first.column, first.row)
                        if first.side == "front"
                        else backing_cell(first.column, first.row, columns, rows)
                    )
                    other = (
                        (second.column, second.row)
                        if second.side == "front"
                        else backing_cell(second.column, second.row, columns, rows)
                    )
                    self.assertEqual(physical, other)

    def test_both_faces_of_a_leaf_share_a_rotation(self):
        """The rotation belongs to the piece of paper, not to the face."""
        for columns, rows in self.SHAPES:
            with self.subTest(shape=(columns, rows)):
                faces = folded(columns, rows)
                for index in range(0, len(faces), 2):
                    self.assertEqual(faces[index].rotation, faces[index + 1].rotation)

    def test_rotation_is_only_ever_a_half_turn(self):
        for columns, rows in self.SHAPES:
            with self.subTest(shape=(columns, rows)):
                self.assertLessEqual(
                    {f.rotation for f in folded(columns, rows)}, {0, 180}
                )

    def test_a_sheet_with_no_rows_to_fold_turns_nothing(self):
        """Only a fold across the sheet puts pages head to head."""
        for columns in (2, 4):
            with self.subTest(columns=columns):
                self.assertEqual({f.rotation for f in folded(columns, 1)}, {0})


class TestRefusals(unittest.TestCase):
    def test_a_grid_that_is_not_a_power_of_two_is_refused(self):
        for columns, rows in ((3, 1), (2, 3), (6, 2)):
            with self.subTest(shape=(columns, rows)):
                with self.assertRaises(ImposeError) as caught:
                    signature_folds(columns, rows)
                self.assertIn("power of two", str(caught.exception))

    def test_an_unknown_style_is_refused_by_name(self):
        with self.assertRaises(ImposeError) as caught:
            signature_folds(2, 2, style="sideways")
        self.assertIn("sideways", str(caught.exception))

    def test_folds_that_do_not_reach_one_leaf_are_refused(self):
        with self.assertRaises(ImposeError) as caught:
            leaves(2, 2, (Fold("vertical", 1),))
        self.assertIn("separate pieces", str(caught.exception))

    def test_a_fold_off_the_sheet_is_refused(self):
        with self.assertRaises(ImposeError):
            leaves(2, 1, (Fold("vertical", 2),))

    def test_a_fold_needs_a_real_axis(self):
        with self.assertRaises(ValueError):
            Fold("diagonal", 1)

    def test_a_fold_moves_one_half_or_the_other(self):
        with self.assertRaises(ValueError):
            Fold("vertical", 1, "sideways")


class TestFaceIdentity(unittest.TestCase):
    def test_a_face_is_comparable(self):
        self.assertEqual(Face("front", 1, 0, 180), Face("front", 1, 0, 180))
        self.assertNotEqual(Face("front", 1, 0), Face("back", 1, 0))
