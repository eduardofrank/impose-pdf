# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

"""Perfect binding: sections gathered on each other, spine milled and glued.

Paperbacks, thick catalogues, anything too thick to staple through the fold.
The book is made of sections -- folded groups of sheets -- and the sections are
*gathered*, set one on top of the next, rather than nested inside one another
as saddle stitch does. The spine is then milled off and the pages glued.

Within a section the ordering is the same nesting problem saddle stitch solves,
because a section is a small folded booklet. Between sections it is simple
succession: section one holds the first pages, section two the next.

Section size is the decision worth understanding. Four pages means every sheet
is its own section, folded once and gathered -- common on a digital press,
where sheets are cheap and folding equipment may be simple. Sixteen or thirty-
two pages means fewer, thicker sections, which is how a web press works and
gives a stronger spine.
"""

from __future__ import annotations

from ..plan import BLANK, Placement, Plan, Surface, blanks_needed
from . import LEFT, RIGHT

#: Pages carried by one folded sheet.
PAGES_PER_SHEET = 4


def impose(pages: int, *, section_pages: int = 4) -> Plan:
    """Impose *pages* as gathered sections of *section_pages* each.

    >>> print(impose(8, section_pages=4).describe())
    sheet 1 front
         4    1
    sheet 1 back
         2    3
    sheet 2 front
         8    5
    sheet 2 back
         6    7

    Each sheet is its own section here, so the sheets are simply stacked in
    order. With larger sections the pages nest within each one:

    >>> print(impose(8, section_pages=8).describe())
    sheet 1 front
         8    1
    sheet 1 back
         2    7
    sheet 2 front
         6    3
    sheet 2 back
         4    5
    """
    if section_pages % PAGES_PER_SHEET or section_pages < PAGES_PER_SHEET:
        raise ValueError(
            f"A section is made of folded sheets, so it holds a multiple of "
            f"{PAGES_PER_SHEET} pages; got {section_pages}."
        )
    total = pages + blanks_needed(pages, section_pages)
    sheets_per_section = section_pages // PAGES_PER_SHEET

    surfaces: list[Surface] = []
    sheet = 0
    for section in range(total // section_pages):
        base = section * section_pages
        for within in range(sheets_per_section):
            left = base + section_pages - 1 - 2 * within
            right = base + 2 * within
            surfaces.append(
                Surface(
                    sheet,
                    "front",
                    (
                        Placement(_source(left, pages), LEFT, 0),
                        Placement(_source(right, pages), RIGHT, 0),
                    ),
                )
            )
            surfaces.append(
                Surface(
                    sheet,
                    "back",
                    (
                        Placement(_source(right + 1, pages), LEFT, 0),
                        Placement(_source(left - 1, pages), RIGHT, 0),
                    ),
                )
            )
            sheet += 1

    return Plan(
        columns=2,
        rows=1,
        surfaces=tuple(surfaces),
        pages=pages,
        schema="perfect-bound",
    )


def _source(index: int, pages: int) -> int | None:
    """The page at *index*, or a blank where the document was padded."""
    return index if 0 <= index < pages else BLANK
