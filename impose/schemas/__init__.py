# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

"""Imposition schemas: the orderings.

Each schema turns a page count and a grid into a :class:`~impose.plan.Plan`.
None of them touches a millimetre. What distinguishes them is how the finished
work is assembled -- nested and stapled, gathered and glued, cut into piles and
stacked -- and that assembly is entirely a question of which page number goes
in which cell.
"""

from __future__ import annotations

from typing import Literal

#: How the press turns the sheet to print its reverse.
#:
#: Long edge is the common default: the sheet turns about its long axis, so
#: the columns reverse. Short edge turns it about the short axis instead, and
#: the rows reverse. Getting this wrong backs every page up against the wrong
#: neighbour, and the error is invisible until the job is cut.
Flip = Literal["long-edge", "short-edge"]


def backing_cell(
    column: int, row: int, columns: int, rows: int, flip: Flip = "long-edge"
) -> tuple[int, int]:
    """Where a front cell lands on the reverse once the sheet is turned.

    >>> backing_cell(0, 0, 2, 1)
    (1, 0)
    >>> backing_cell(0, 0, 1, 2, "short-edge")
    (0, 1)
    """
    if flip == "long-edge":
        return (columns - 1 - column, row)
    if flip == "short-edge":
        return (column, rows - 1 - row)
    raise ValueError(f"Unknown flip {flip!r}; use 'long-edge' or 'short-edge'.")


def reading_order(columns: int, rows: int):
    """Cells left to right, top to bottom, as a person reads a laid-out sheet.

    >>> list(reading_order(2, 2))
    [(0, 0), (1, 0), (0, 1), (1, 1)]
    """
    for row in range(rows):
        for column in range(columns):
            yield (column, row)


def check_grid(columns: int, rows: int) -> None:
    """Refuse a grid that cannot hold anything."""
    if columns < 1 or rows < 1:
        raise ValueError(f"Grid must be at least 1x1, got {columns}x{rows}.")
