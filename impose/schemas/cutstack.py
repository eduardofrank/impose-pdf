# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

"""Cut and stack: run a long document N-up without collating by hand.

Print the sheets, guillotine the pile into as many stacks as there are cells,
set the stacks on each other in cell order, and the pages come out in sequence.
It is how a digital press runs a job whose pages are much smaller than its
sheet without asking anyone to interleave thousands of pieces afterwards.

The ordering follows from that. Each cell is one stack, so each cell must carry
a *consecutive block* of the document: with four cells and a hundred sheets,
the first cell carries pages 1 to 100, the second 101 to 200, and so on. Cell
one on sheet one is page 1; cell one on sheet two is page 2.

Duplex is where the mirroring earns its place. The sheets are cut, so each
finished piece really does have a front and a back, and the piece at a given
cell takes its reverse from the *mirrored* cell of the back surface. Laying the
back out in reading order puts every page on the back of the wrong piece.
"""

from __future__ import annotations

import math

from ..plan import BLANK, Placement, Plan, Surface
from . import Flip, backing_cell, check_grid, reading_order


def impose(  # pylint: disable=too-many-locals
    pages: int,
    *,
    columns: int,
    rows: int,
    duplex: bool = True,
    flip: Flip = "long-edge",
) -> Plan:
    """Impose *pages* to be cut into ``columns`` x ``rows`` stacks.

    Two stacks, simplex: the first stack takes the first half of the document.

    >>> print(impose(4, columns=2, rows=1, duplex=False).describe())
    sheet 1 front
         1    3
    sheet 2 front
         2    4

    Cut down the middle and put the right stack under the left, and the pages
    read 1, 2, 3, 4.
    """
    check_grid(columns, rows)
    stacks = columns * rows
    per_side = 2 if duplex else 1
    per_sheet = stacks * per_side
    sheets = max(1, math.ceil(pages / per_sheet))
    per_stack = sheets * per_side

    cells = list(reading_order(columns, rows))
    surfaces: list[Surface] = []
    for sheet in range(sheets):
        front = []
        back = []
        for stack, (column, row) in enumerate(cells):
            base = stack * per_stack
            front.append(
                Placement(_source(base + sheet * per_side, pages), column, row)
            )
            if duplex:
                back.append(
                    Placement(
                        _source(base + sheet * per_side + 1, pages),
                        *backing_cell(column, row, columns, rows, flip),
                    )
                )
        surfaces.append(Surface(sheet, "front", tuple(front)))
        if duplex:
            surfaces.append(Surface(sheet, "back", tuple(back)))

    return Plan(
        columns=columns,
        rows=rows,
        surfaces=tuple(surfaces),
        pages=pages,
        schema="cut-and-stack",
    )


def _source(index: int, pages: int) -> int | None:
    """The page at *index*, or a blank where a stack runs short."""
    return index if index < pages else BLANK
