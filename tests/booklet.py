# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

"""Reading a folded booklet, in software.

The only convincing test of a binding schema is to assemble the thing and read
it. Nesting a set of sheets and turning the pages is a short enough operation
to write down exactly, so these helpers do that, and the schema tests assert
that the pages come out 1, 2, 3.
"""

from __future__ import annotations

from impose.plan import BLANK, Surface
from impose.schemas import LEFT, RIGHT


def read_nested(surfaces: list[Surface]) -> list[int]:
    """Turn the pages of a nested, folded set of sheets.

    Sheets are given outermost first. Reading a saddle-stitched booklet visits
    the right-hand page of each front and the left-hand page of each back, in
    order inward; then, having reached the middle, comes back out visiting the
    right of each back and the left of each front.
    """
    fronts = {s.sheet: s for s in surfaces if s.side == "front"}
    backs = {s.sheet: s for s in surfaces if s.side == "back"}
    sheets = sorted(fronts)

    pages: list[int | None] = []
    for sheet in sheets:  # inward
        pages.append(fronts[sheet].at(RIGHT, 0).source)
        pages.append(backs[sheet].at(LEFT, 0).source)
    for sheet in reversed(sheets):  # and back out
        pages.append(backs[sheet].at(RIGHT, 0).source)
        pages.append(fronts[sheet].at(LEFT, 0).source)
    return [page for page in pages if page is not BLANK]


def read_gathered(surfaces: list[Surface], *, sheets_per_section: int) -> list[int]:
    """Read sections that are stacked on each other rather than nested."""
    sheets = sorted({s.sheet for s in surfaces})
    pages: list[int] = []
    for start in range(0, len(sheets), sheets_per_section):
        group = set(sheets[start : start + sheets_per_section])
        pages.extend(read_nested([s for s in surfaces if s.sheet in group]))
    return pages
