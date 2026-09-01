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

#: Bezier handle length for a circular arc of unit radius. Four arcs of this
#: make a circle indistinguishable from one at any sane resolution.
_KAPPA = 0.5522847498307936

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


@dataclasses.dataclass(frozen=True, slots=True)
class Patch:
    """A filled rectangle of a named ink mixture, for a colour bar."""

    rect: Rect
    cmyk: tuple[float, float, float, float]
    label: str = ""


@dataclasses.dataclass(frozen=True, slots=True)
class Target:
    """A registration bullseye: concentric ring with a crosshair through it.

    Drawn in registration colour, so it appears on every plate. Where the
    plates are out, the rings and the cross stop agreeing, which is what makes
    it readable at a glance rather than by measurement.
    """

    x: float
    y: float
    radius: float
    width: float

    @property
    def reach(self) -> float:
        """Half the space the target needs, crosshair included."""
        return self.radius * 1.6


#: The patch sequence of a working colour bar: each process ink solid and in
#: quarter steps, then the two-colour overprints that show trapping, then a
#: three-colour grey and a registration solid.
#:
#: This is a serviceable bar for checking density and dot gain on press. It is
#: not a standardised wedge -- Fogra, Ugra and GATF strips are specified
#: objects with their own patch geometry, and if a job needs one of those it
#: needs the real thing, not an approximation of it.
STANDARD_PATCHES: tuple[tuple[str, tuple[float, float, float, float]], ...] = (
    ("C", (1, 0, 0, 0)),
    ("C75", (0.75, 0, 0, 0)),
    ("C50", (0.5, 0, 0, 0)),
    ("C25", (0.25, 0, 0, 0)),
    ("M", (0, 1, 0, 0)),
    ("M75", (0, 0.75, 0, 0)),
    ("M50", (0, 0.5, 0, 0)),
    ("M25", (0, 0.25, 0, 0)),
    ("Y", (0, 0, 1, 0)),
    ("Y75", (0, 0, 0.75, 0)),
    ("Y50", (0, 0, 0.5, 0)),
    ("Y25", (0, 0, 0.25, 0)),
    ("K", (0, 0, 0, 1)),
    ("K75", (0, 0, 0, 0.75)),
    ("K50", (0, 0, 0, 0.5)),
    ("K25", (0, 0, 0, 0.25)),
    ("CM", (1, 1, 0, 0)),
    ("CY", (1, 0, 1, 0)),
    ("MY", (0, 1, 1, 0)),
    ("CMY", (1, 1, 1, 0)),
)


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


def registration_targets(
    form: Rect,
    area: Rect,
    *,
    style: MarkStyle | None = None,
    radius: float = 2.5 * MM,
) -> list[Target]:
    """Bullseyes centred on each side of the form, out in the margin.

    One per edge is enough to read a plate that has moved or turned. A target
    is placed only where the margin actually has room for it, so a form that
    nearly fills the sheet simply gets fewer.
    """
    style = style or MarkStyle()
    gap = style.reach + radius * 1.6
    centre_x = (form.x0 + form.x1) / 2
    centre_y = (form.y0 + form.y1) / 2
    candidates = (
        (centre_x, form.y0 - gap),
        (centre_x, form.y1 + gap),
        (form.x0 - gap, centre_y),
        (form.x1 + gap, centre_y),
    )
    return [
        Target(x, y, radius, style.width)
        for x, y in candidates
        if _has_room(x, y, radius * 1.6, area)
    ]


def _has_room(x: float, y: float, reach: float, area: Rect) -> bool:
    """Whether a mark of this reach fits inside the imageable area."""
    return (
        area.x0 <= x - reach
        and x + reach <= area.x1
        and area.y0 <= y - reach
        and y + reach <= area.y1
    )


def colour_bar(  # pylint: disable=too-many-arguments
    form: Rect,
    area: Rect,
    *,
    style: MarkStyle | None = None,
    patches: tuple[tuple[str, tuple[float, float, float, float]], ...] = (
        STANDARD_PATCHES
    ),
    height: float = 5 * MM,
    minimum_patch: float = 3 * MM,
) -> list[Patch]:
    """A row of ink patches along the tail of the sheet, if there is room.

    The bar is laid below the form and sized to the space available. Where the
    patches would come out narrower than a spectrophotometer aperture can read,
    none are drawn: an unreadable bar is worse than no bar, because it looks
    like a check that was made.
    """
    style = style or MarkStyle()
    # Flush to the tail of the imageable area. A colour bar lives in the waste
    # at the sheet edge, not tucked against the form, and putting it there
    # keeps it clear of anything else in the margin.
    bottom = area.y0
    top = bottom + height
    if not patches or top > form.y0 - style.reach:
        return []
    width = min(form.width, area.width) / len(patches)
    if width < minimum_patch:
        return []
    left = max(area.x0, (form.x0 + form.x1) / 2 - width * len(patches) / 2)
    return [
        Patch(
            Rect(left + index * width, bottom, left + (index + 1) * width, top),
            cmyk,
            label,
        )
        for index, (label, cmyk) in enumerate(patches)
    ]


def circle_path(x: float, y: float, radius: float) -> list[tuple[float, ...]]:
    """Four Bezier arcs approximating a circle, as PDF operands.

    Returned as ``(x1, y1, x2, y2, x3, y3)`` control points for ``c``, after a
    ``m`` to the starting point.
    """
    k = _KAPPA * radius
    return [
        (x + radius, y + k, x + k, y + radius, x, y + radius),
        (x - k, y + radius, x - radius, y + k, x - radius, y),
        (x - radius, y - k, x - k, y - radius, x, y - radius),
        (x + k, y - radius, x + radius, y - k, x + radius, y),
    ]


def furniture(
    form: Rect,
    area: Rect,
    *,
    style: MarkStyle | None = None,
    bar: bool = True,
    targets: bool = True,
) -> tuple[list[Target], list[Patch]]:
    """Everything that goes in the margin, placed so nothing lands on anything.

    The bar takes the tail of the sheet and the targets sit just outside the
    form, so the only way they can meet is on a sheet with almost no margin --
    and there the target that would collide is dropped rather than printed over
    the patches.
    """
    style = style or MarkStyle()
    patches = colour_bar(form, area, style=style) if bar else []
    found = registration_targets(form, area, style=style) if targets else []
    if not patches:
        return found, patches
    ceiling = max(patch.rect.y1 for patch in patches)
    return [t for t in found if t.y - t.reach > ceiling], patches


def allowance(style: MarkStyle | None) -> float:
    """How much room beyond the trim a form needs for its marks."""
    return 0.0 if style is None else style.reach
