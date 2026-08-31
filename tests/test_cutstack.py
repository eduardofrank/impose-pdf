# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

# pylint: disable=missing-class-docstring,missing-function-docstring

"""Cut and stack, checked by simulating the guillotine."""

import unittest

from impose.plan import BLANK, Plan
from impose.schemas import backing_cell, reading_order
from impose.schemas.cutstack import impose


def assemble(plan: Plan, *, duplex: bool, flip: str = "long-edge") -> list[int]:
    """Cut the sheets into stacks, set the stacks on each other, read the pages.

    This is the bindery operation in software: for each cell, take that cell
    from every sheet in turn -- front then back, since the piece is cut and has
    two sides -- then concatenate the stacks in cell order.
    """
    fronts = [s for s in plan.surfaces if s.side == "front"]
    backs = {s.sheet: s for s in plan.surfaces if s.side == "back"}
    order: list[int] = []
    for column, row in reading_order(plan.columns, plan.rows):
        for front in fronts:
            placement = front.at(column, row)
            if placement is not None and placement.source is not BLANK:
                order.append(placement.source)
            if not duplex:
                continue
            back = backs[front.sheet]
            # The reverse of this piece comes from the mirrored cell.
            mirrored = backing_cell(column, row, plan.columns, plan.rows, flip)
            placement = back.at(*mirrored)
            if placement is not None and placement.source is not BLANK:
                order.append(placement.source)
    return order


class TestAssembly(unittest.TestCase):
    def test_simplex_stacks_into_order(self):
        plan = impose(12, columns=2, rows=1, duplex=False)
        self.assertEqual(assemble(plan, duplex=False), list(range(12)))

    def test_duplex_stacks_into_order(self):
        plan = impose(16, columns=2, rows=1)
        self.assertEqual(assemble(plan, duplex=True), list(range(16)))

    def test_many_shapes_all_assemble(self):
        for pages in (8, 16, 24, 48):
            for grid in ((2, 1), (2, 2), (4, 2)):
                for duplex in (False, True):
                    with self.subTest(pages=pages, grid=grid, duplex=duplex):
                        plan = impose(
                            pages, columns=grid[0], rows=grid[1], duplex=duplex
                        )
                        self.assertEqual(
                            assemble(plan, duplex=duplex), list(range(pages))
                        )

    def test_short_edge_flip_also_assembles(self):
        plan = impose(16, columns=1, rows=2, flip="short-edge")
        self.assertEqual(
            assemble(plan, duplex=True, flip="short-edge"), list(range(16))
        )


class TestOrdering(unittest.TestCase):
    def test_each_cell_carries_a_consecutive_block(self):
        """Two stacks over a 4-page document: 1-2 in one, 3-4 in the other."""
        plan = impose(4, columns=2, rows=1, duplex=False)
        self.assertEqual(plan.surfaces[0].at(0, 0).source, 0)
        self.assertEqual(plan.surfaces[0].at(1, 0).source, 2)
        self.assertEqual(plan.surfaces[1].at(0, 0).source, 1)

    def test_back_is_mirrored_so_it_lands_on_the_right_piece(self):
        plan = impose(8, columns=2, rows=1)
        front, back = plan.surfaces[0], plan.surfaces[1]
        self.assertEqual(front.at(0, 0).source, 0)
        # Page 1 backs page 0, so it sits at the mirrored cell.
        self.assertEqual(back.at(1, 0).source, 1)

    def test_every_page_imposed_exactly_once(self):
        for pages in (8, 15, 16, 40):
            with self.subTest(pages=pages):
                impose(pages, columns=2, rows=2).validate()

    def test_short_document_is_padded(self):
        plan = impose(5, columns=2, rows=1)
        plan.validate()
        self.assertEqual(plan.pages, 5)
