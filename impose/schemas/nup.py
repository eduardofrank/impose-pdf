# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

"""N-up: consecutive pages, in reading order, on a grid.

The plainest schema there is, and what a print driver means by "2 pages per
sheet". Pages run 1, 2, 3 across and down; the next surface carries on where
the last left off. It is for proofs, handouts, and reading a document with
fewer sheets -- work that is read as a stack, not cut apart.

Both sides are laid out in reading order. The duplex unit turns the sheet, so
the back of sheet one carries pages 3 and 4 the same way round as the front
carried 1 and 2. Mirroring the back here would be doing the press's job twice.

That also means n-up says nothing about which page ends up physically behind
which. If the sheets are to be cut into pieces, that relationship is the whole
problem, and :mod:`impose.schemas.cutstack` is the schema that solves it.
"""

from __future__ import annotations

from ..plan import BLANK, Placement, Plan, Surface, blanks_needed
from . import check_grid, reading_order


def impose(pages: int, *, columns: int, rows: int, duplex: bool = True) -> Plan:
    """Lay *pages* out consecutively on a ``columns`` x ``rows`` grid.

    >>> print(impose(8, columns=2, rows=1).describe())
    sheet 1 front
         1    2
    sheet 1 back
         3    4
    sheet 2 front
         5    6
    sheet 2 back
         7    8

    A document that does not fill its last surface is padded with blanks:

    >>> print(impose(3, columns=2, rows=1, duplex=False).describe())
    sheet 1 front
         1    2
    sheet 2 front
         3    .
    """
    check_grid(columns, rows)
    per_surface = columns * rows
    per_sheet = per_surface * 2 if duplex else per_surface
    total = pages + blanks_needed(pages, per_sheet)
    cells = list(reading_order(columns, rows))

    surfaces: list[Surface] = []
    page = 0
    sheet = 0
    while page < total:
        for side in ("front", "back") if duplex else ("front",):
            surfaces.append(
                Surface(
                    sheet,
                    side,
                    tuple(
                        Placement(_source(page + index, pages), column, row)
                        for index, (column, row) in enumerate(cells)
                    ),
                )
            )
            page += per_surface
        sheet += 1

    return Plan(
        columns=columns,
        rows=rows,
        surfaces=tuple(surfaces),
        pages=pages,
        schema="n-up",
    )


def _source(index: int, pages: int) -> int | None:
    """The page at *index*, or a blank once the document runs out."""
    return index if index < pages else BLANK
