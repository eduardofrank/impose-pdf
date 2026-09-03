# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

"""Step and repeat: one item, many times, filling the sheet.

Business cards, labels, tickets, swatches -- and folded signatures, which is
the same problem wearing different clothes. There is no document order to
preserve. There is a piece of artwork, and the job is to get as many
impressions of it onto each sheet as will fit, then cut them apart.

An item may be one page or two. Two makes it double-sided, and the second page
goes on the back of the sheet, mirrored, so it lands behind the first once the
press turns it. A document of several items is several separate step-and-repeat
runs, one after another: each item gets its own sheets, filled with itself.

That last part is what a saddle-stitched booklet needs. Impose it onto its own
form first, and the result is a document of two-page items -- each folded sheet,
front and back. Step and repeat that two up and every press sheet carries one
signature twice; cut it down the middle and there are two identical folded
sheets, one for each copy of the booklet. No collation to get right, because
the halves are interchangeable.

This is the one schema that places a page more than once on purpose, so its
plans are validated without the exhaustive check the binding schemas use.
"""

from __future__ import annotations

from ..plan import Placement, Plan, Surface
from . import Flip, backing_cell, check_grid, reading_order


def impose(  # pylint: disable=too-many-arguments
    pages: int = 1,
    *,
    columns: int,
    rows: int,
    sides: int | None = None,
    flip: Flip = "long-edge",
) -> Plan:
    """Fill a ``columns`` x ``rows`` grid with repetitions of each item.

    *sides* is 1 for single-sided items and 2 for items with a back. Left out,
    it is taken from the page count: an even document is read as front-and-back
    pairs, an odd one as separate single-sided items. Say it outright when a
    document of an even number of single-sided items would otherwise be
    misread.

    There is no run length here. A schema says what one sheet carries; how
    many times to print it is a press setting, and baking it into the file
    would mean a 400-page PDF where 8 pages say the same thing. `impose fit`
    answers how many sheets a quantity needs.

    >>> print(impose(2, columns=2, rows=2).describe())
    sheet 1 front
         1    1
         1    1
    sheet 1 back
         2    2
         2    2

    Several items follow one another, each filling its own sheets:

    >>> print(impose(4, columns=2, rows=1).describe())
    sheet 1 front
         1    1
    sheet 1 back
         2    2
    sheet 2 front
         3    3
    sheet 2 back
         4    4
    """
    check_grid(columns, rows)
    if pages < 1:
        raise ValueError(f"There is nothing to repeat; got {pages} pages.")
    if sides is None:
        sides = 2 if pages % 2 == 0 else 1
    if sides not in (1, 2):
        raise ValueError(f"An item has one side or two; got {sides}.")
    if pages % sides:
        raise ValueError(f"{pages} pages do not divide into {sides}-sided items.")

    items = pages // sides
    cells = list(reading_order(columns, rows))

    surfaces: list[Surface] = []
    for item in range(items):
        front = item * sides
        surfaces.append(
            Surface(
                item,
                "front",
                tuple(Placement(front, column, row) for column, row in cells),
            )
        )
        if sides == 2:
            surfaces.append(
                Surface(
                    item,
                    "back",
                    tuple(
                        Placement(
                            front + 1,
                            *backing_cell(column, row, columns, rows, flip),
                        )
                        for column, row in cells
                    ),
                )
            )

    return Plan(
        columns=columns,
        rows=rows,
        surfaces=tuple(surfaces),
        pages=pages,
        schema="step-and-repeat",
    )


def impressions(plan: Plan) -> int:
    """How many finished pieces of each item *plan* yields."""
    fronts = [s for s in plan.surfaces if s.side == "front"]
    if not fronts:
        return 0
    items = len({s.placements[0].source for s in fronts})
    return sum(len(s.placements) for s in fronts) // max(1, items)
