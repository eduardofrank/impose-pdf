# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

"""What the bindery reads on a gathered book, besides the page numbers.

A perfect-bound book is sections gathered and then milled. Three things on
the sheet exist for that, and none of them is a cut mark.

The collation mark is a black bar on the spine of each section, stepped down
from the head. Gathered in order the bars make a diagonal; a missing or
swapped section breaks it. The bar sits in the grind gap when there is one,
so milling takes it away, and on the fold itself when the gap is closed.

The signature letter names the section: A, then B, and on past Z to AA. It
sits at the foot, outside the trim, where the final trim removes it.

The lap is not a mark. It is extra paper on the foot of the low folio, the
lip a folder grabs, and the trim takes that off too.
"""

from __future__ import annotations

import dataclasses

from .font import load
from .geometry import Rect
from .layout import SheetLayout
from .plan import Plan
from .units import MM

#: How far down from the head the first bar starts, and how far each next
#: section steps. A bar is the first of those and leaves a gap of the rest.
_INSET = 8 * MM
_STEP = 6 * MM
_BAR = 4 * MM

#: Letter size. It has to be readable on the flat sheet and still fit in the
#: margin the trim marks already reserve.
_LETTER = 8.0

#: Toward the foot, once the page sits at this rotation. The form turns with
#: the pages, so a quarter turn moves the foot from the bottom to one side.
_TOWARD_FOOT = {0: (0.0, -1.0), 90: (-1.0, 0.0), 180: (0.0, 1.0), 270: (1.0, 0.0)}


@dataclasses.dataclass(frozen=True, slots=True)
class BinderyMarks:
    """The collation bars and signature letters on one surface."""

    bars: tuple[Rect, ...]
    letters: tuple[tuple[float, float, str], ...]

    @property
    def text(self) -> str:
        """Every letter drawn, for the font subset."""
        return "".join(letter for _, _, letter in self.letters)


def letter(section: int) -> str:
    """The letter a binder reads for this section, counting from A.

    >>> letter(0)
    'A'
    >>> letter(25)
    'Z'
    >>> letter(26)
    'AA'
    """
    if section < 0:
        raise ValueError(f"A section cannot be negative, got {section}.")
    name = ""
    number = section
    while True:
        name = chr(ord("A") + number % 26) + name
        number = number // 26 - 1
        if number < 0:
            return name


def marks_for(layout: SheetLayout, plan: Plan) -> BinderyMarks:
    """Collation bars and letters for one laid-out surface.

    Only the outside of a section carries them: the surface that holds that
    section's lowest page. An inner sheet of a nested section is hidden once
    the section is folded, and a mark there would never be seen.
    """
    if plan.spine is None:
        return BinderyMarks((), ())
    section = _outside_section(layout, plan)
    if section is None:
        return BinderyMarks((), ())
    page = next(
        placed
        for placed in layout.pages
        if placed.source is not None and _section_source(plan, section) == placed.source
    )
    spine, vertical, gap = _spine_line(layout, plan)
    return _drawn(page, section, spine, vertical, gap)


def _drawn(  # pylint: disable=too-many-locals
    page, section: int, spine: float, vertical: bool, gap: float
) -> BinderyMarks:
    """One section's bar, stepped down from the head, and its letter at the foot."""
    rotation = page.rotation % 360
    span = _span(page.trim, rotation)
    slots = int((span - _INSET) / _STEP) if span > _INSET else 1
    start = _INSET + (section % max(slots, 1)) * _STEP
    thick = gap if gap > 0.4 else _BAR
    bars = (
        _bar(
            _at(page.trim, spine, rotation, start, vertical),
            _at(page.trim, spine, rotation, start + _BAR, vertical),
            spine,
            thick,
            vertical,
        ),
    )
    foot_x, foot_y = _at(page.trim, spine, rotation, span + _LETTER, vertical)
    text = letter(section)
    width = load().width(text, _LETTER)
    if vertical:
        origin = (spine - width / 2, foot_y, text)
    else:
        origin = (foot_x, spine - _LETTER / 2, text)
    return BinderyMarks(bars, (origin,))


def lip_cell(plan: Plan, surface) -> tuple[int, int] | None:
    """The low folio of this sheet, on the surface that actually carries it.

    Each folded sheet has one lip, on its own lowest page, which is the front
    the folder grabs. The other side of that sheet is not the lip.
    """
    on_sheet = [
        placement
        for candidate in plan.surfaces
        if candidate.sheet == surface.sheet
        for placement in candidate.placements
        if placement.source is not None
    ]
    if not on_sheet:
        return None
    lip = min(on_sheet, key=lambda placement: placement.source)
    if any(placement.source == lip.source for placement in surface.placements):
        return lip.cell
    return None


def _outside_section(layout: SheetLayout, plan: Plan) -> int | None:
    """The section whose lowest page is on this surface, if any."""
    here = {page.source for page in layout.pages if page.source is not None}
    sections = {
        placement.section
        for surface in plan.surfaces
        for placement in surface.placements
        if placement.source in here
    }
    for section in sections:
        if _section_source(plan, section) in here:
            return section
    return None


def _section_source(plan: Plan, section: int) -> int | None:
    """The lowest page number of one gathered section."""
    sources = [
        placement.source
        for surface in plan.surfaces
        for placement in surface.placements
        if placement.section == section and placement.source is not None
    ]
    return min(sources) if sources else None


def _spine_line(layout: SheetLayout, plan: Plan) -> tuple[float, bool, float]:
    """The binding fold, whether it runs up the sheet, and the gap across it."""
    verticals, horizontals = layout.fold_positions((plan.spine,), ())
    before = next(page for page in layout.pages if page.column == plan.spine - 1)
    after = next(page for page in layout.pages if page.column == plan.spine)
    if verticals:
        one, other = sorted((before.trim, after.trim), key=lambda rect: rect.x0)
        return verticals[0], True, other.x0 - one.x1
    one, other = sorted((before.trim, after.trim), key=lambda rect: rect.y0)
    return horizontals[0], False, other.y0 - one.y1


def _span(trim: Rect, rotation: int) -> float:
    """How far the head is from the foot, along the page."""
    _, dy = _TOWARD_FOOT[rotation]
    return trim.height if dy else trim.width


def _at(
    trim: Rect, spine: float, rotation: int, distance: float, vertical: bool
) -> tuple[float, float]:
    """A point on the spine, *distance* from the head toward the foot."""
    dx, dy = _TOWARD_FOOT[rotation]
    if vertical:
        head = trim.y1 if dy < 0 else trim.y0
        return (spine, head + dy * distance)
    head = trim.x1 if dx < 0 else trim.x0
    return (head + dx * distance, spine)


def _bar(
    start: tuple[float, float],
    end: tuple[float, float],
    spine: float,
    thick: float,
    vertical: bool,
) -> Rect:
    """A bar centred on the fold, running from *start* toward the foot."""
    half = thick / 2
    if vertical:
        y0, y1 = sorted((start[1], end[1]))
        return Rect(spine - half, y0, spine + half, y1)
    x0, x1 = sorted((start[0], end[0]))
    return Rect(x0, spine - half, x1, spine + half)
