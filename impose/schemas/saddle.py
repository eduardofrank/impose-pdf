# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

"""Saddle stitch: sheets nested inside one another, folded, stapled on the fold.

Magazines, programmes, thin catalogues. Every sheet carries four pages, and
because the sheets sit inside each other the outermost one carries the first
page and the last, the next one in carries the second and the second-to-last,
and so on inward. That pairing is the schema: page 1 is always beside page n.

It follows that the page count must be a multiple of four -- a folded sheet
cannot contribute any other number -- so a document is padded with blanks
before it is imposed. It also follows that a saddle-stitched book cannot be
very thick: the inner sheets stick out further than the outer ones, which is
what creep compensates for and what eventually makes perfect binding the
better answer.
"""

from __future__ import annotations

from ..plan import BLANK, Placement, Plan, Surface, blanks_needed
from . import LEFT, RIGHT

#: Pages carried by one folded sheet: two on the front, two on the back.
PAGES_PER_SHEET = 4


def impose(pages: int) -> Plan:
    """Impose *pages* as a saddle-stitched booklet.

    >>> print(impose(8).describe())
    sheet 1 front
         8    1
    sheet 1 back
         2    7
    sheet 2 front
         6    3
    sheet 2 back
         4    5

    The outermost sheet carries the first page and the last, which is the
    whole of saddle stitch.
    """
    total = pages + blanks_needed(pages, PAGES_PER_SHEET)
    surfaces = []
    for sheet in range(total // PAGES_PER_SHEET):
        surfaces.extend(_sheet(sheet, first=0, last=total - 1, pages=pages))
    return Plan(
        columns=2,
        rows=1,
        surfaces=tuple(surfaces),
        pages=pages,
        fold_columns=(1,),
        schema="saddle-stitch",
    )


def _sheet(sheet: int, *, first: int, last: int, pages: int) -> list[Surface]:
    """The two surfaces of one nested sheet.

    *sheet* counts inward from the outside, so sheet 0 wraps everything.
    """
    outer_left = last - 2 * sheet
    outer_right = first + 2 * sheet
    return [
        Surface(
            sheet,
            "front",
            (
                Placement(_source(outer_left, pages), LEFT, 0),
                Placement(_source(outer_right, pages), RIGHT, 0),
            ),
        ),
        Surface(
            sheet,
            "back",
            (
                Placement(_source(outer_right + 1, pages), LEFT, 0),
                Placement(_source(outer_left - 1, pages), RIGHT, 0),
            ),
        ),
    ]


def _source(index: int, pages: int) -> int | None:
    """The page at *index*, or a blank where the document was padded."""
    return index if 0 <= index < pages else BLANK
