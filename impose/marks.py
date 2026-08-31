# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

"""Press marks: where the knife goes, and where the folder goes.

Marks sit at the ends of each cut line, out beyond the form. That is how a
guillotine is actually used: the operator lines the blade up on a pair of marks
at opposite edges of the sheet and cuts the whole way across, so a mark in the
middle of the form would be cut through and a mark inside the trim would be
delivered to the customer.

The colour matters as much as the position. A mark exists to be seen on every
plate at once, so it is laid down in all separations -- a Separation /All
colorant at full strength, overprinting -- and not in black. Black marks appear
on the black plate alone, which gives a four-colour job no colour-to-colour
reference and gives the cutter nothing on a job with no black in it.

Registration is the default, but not the only right answer. On a digital press
there are no plates to register, the marks are only guiding the knife and the
folder, and 400% coverage in the trim area risks setting off onto the next
sheet. K-only is the better choice there, so the colour is selectable.
"""

from __future__ import annotations

import dataclasses
from typing import Literal

from .geometry import Rect, approx
from .units import MM

#: How a mark is coloured.
#:
#: ``registration`` is a Separation /All colorant at 100%, overprinting, which
#: appears on every plate. ``black`` is K only, for mono work and for digital
#: presses where heavy coverage in the trim zone is a liability.
MarkColour = Literal["registration", "black"]


@dataclasses.dataclass(frozen=True, slots=True)
class Segment:
    """A straight mark, drawn as a stroked line."""

    x0: float
    y0: float
    x1: float
    y1: float
    width: float
    dashed: bool = False

    @property
    def is_vertical(self) -> bool:
        """Whether the segment runs up the sheet."""
        return approx(self.x0, self.x1)


@dataclasses.dataclass(frozen=True, slots=True)
class MarkStyle:
    """How marks are drawn.

    The default offset clears a 3 mm bleed, so a mark never lands on artwork
    that is about to be trimmed off and mistaken for part of the image.
    """

    offset: float = 3 * MM
    length: float = 5 * MM
    width: float = 0.25
    colour: MarkColour = "registration"

    @property
    def reach(self) -> float:
        """How far beyond the trim a mark extends, offset and length together."""
        return self.offset + self.length


def cut_lines(trims: list[Rect]) -> tuple[list[float], list[float]]:
    """The distinct cut lines through a form.

    Every left and right trim edge is a vertical cut; every bottom and top edge
    is a horizontal one. Neighbouring pages share an edge, so the coordinates
    are folded together and each line is marked once rather than twice.

    >>> cut_lines([Rect(0, 0, 10, 10), Rect(10, 0, 20, 10)])
    ([0.0, 10.0, 20.0], [0.0, 10.0])
    """
    verticals = _distinct(edge for trim in trims for edge in (trim.x0, trim.x1))
    horizontals = _distinct(edge for trim in trims for edge in (trim.y0, trim.y1))
    return verticals, horizontals


def _distinct(values) -> list[float]:
    """Sorted coordinates, with near-identical ones treated as one line."""
    result: list[float] = []
    for value in sorted(float(v) for v in values):
        if not result or not approx(result[-1], value):
            result.append(value)
    return result


def trim_marks(
    trims: list[Rect],
    *,
    style: MarkStyle | None = None,
    folds: tuple[float, ...] = (),
) -> list[Segment]:
    """Marks at both ends of every cut line through the form.

    *folds* names vertical cut lines that are folds rather than cuts -- a
    saddle-stitched spine, say. Those are drawn dashed, so the folder is not
    invited to cut the book in half.
    """
    style = style or MarkStyle()
    if not trims:
        return []
    form = trims[0]
    for trim in trims[1:]:
        form = form.union(trim)
    verticals, horizontals = cut_lines(trims)

    marks: list[Segment] = []
    for x in verticals:
        dashed = any(approx(x, fold) for fold in folds)
        marks.append(
            Segment(
                x, form.y0 - style.offset, x, form.y0 - style.reach, style.width, dashed
            )
        )
        marks.append(
            Segment(
                x, form.y1 + style.offset, x, form.y1 + style.reach, style.width, dashed
            )
        )
    for y in horizontals:
        marks.append(
            Segment(form.x0 - style.offset, y, form.x0 - style.reach, y, style.width)
        )
        marks.append(
            Segment(form.x1 + style.offset, y, form.x1 + style.reach, y, style.width)
        )
    return marks


def allowance(style: MarkStyle | None) -> float:
    """How much room beyond the trim a form needs for its marks."""
    return 0.0 if style is None else style.reach
