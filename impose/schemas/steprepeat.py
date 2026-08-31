# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

"""Step and repeat: one item, many times, filling the sheet.

Business cards, labels, tickets, swatches. There is no document order to
preserve -- there is one piece of artwork, and the job is to get as many
impressions of it onto each sheet as will fit, then cut them apart.

This is the one schema that deliberately places the same page more than once,
so its plans are validated without the exhaustive check the binding schemas
use. A two-page source is read as a front and a back rather than as a sequence.
"""

from __future__ import annotations

import math

from ..plan import Placement, Plan, Surface
from . import Flip, backing_cell, check_grid, reading_order


def impose(
    pages: int = 1,
    *,
    columns: int,
    rows: int,
    copies: int | None = None,
    flip: Flip = "long-edge",
) -> Plan:
    """Fill a ``columns`` x ``rows`` grid with repetitions of the artwork.

    *pages* is 1 for a single-sided item, or 2 for one with a back. *copies* is
    how many finished pieces are wanted; the default is one sheet's worth.

    >>> print(impose(2, columns=2, rows=2, copies=4).describe())
    sheet 1 front
         1    1
         1    1
    sheet 1 back
         2    2
         2    2
    """
    check_grid(columns, rows)
    if pages not in (1, 2):
        raise ValueError(
            "Step and repeat takes one page, or two for a front and a back; "
            f"got {pages}."
        )
    per_sheet = columns * rows
    sheets = max(1, math.ceil((copies or per_sheet) / per_sheet))
    cells = list(reading_order(columns, rows))

    surfaces: list[Surface] = []
    for sheet in range(sheets):
        surfaces.append(
            Surface(
                sheet,
                "front",
                tuple(Placement(0, column, row) for column, row in cells),
            )
        )
        if pages == 2:
            surfaces.append(
                Surface(
                    sheet,
                    "back",
                    tuple(
                        Placement(1, *backing_cell(column, row, columns, rows, flip))
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
    """How many finished pieces *plan* yields."""
    fronts = [surface for surface in plan.surfaces if surface.side == "front"]
    return sum(len(surface.placements) for surface in fronts)
