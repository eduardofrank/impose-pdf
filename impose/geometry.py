# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

"""Geometric value types, in PDF user space.

The origin is bottom-left and y grows upward, matching PDF and every box a
print-ready file carries. Nothing here knows about a PDF library; the renderer
converts to whatever convention its backend wants, once, at the boundary.

Every type is immutable. Imposition builds a lot of derived rectangles, and
sharing a mutable one by accident is the kind of bug that reaches a plate.
"""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Iterable, Iterator


@dataclasses.dataclass(frozen=True, slots=True)
class Size:
    """A width and a height, in points.

    >>> Size(10, 20).swapped()
    Size(width=20, height=10)
    """

    width: float
    height: float

    def __post_init__(self) -> None:
        if self.width < 0 or self.height < 0:
            raise ValueError(f"Size cannot be negative: {self.width}x{self.height}")

    def swapped(self) -> Size:
        """This size turned through a quarter turn."""
        return Size(self.height, self.width)

    def rotated(self, degrees: int) -> Size:
        """This size as it appears after rotating by *degrees*.

        >>> Size(10, 20).rotated(90)
        Size(width=20, height=10)
        >>> Size(10, 20).rotated(180)
        Size(width=10, height=20)
        """
        return self.swapped() if degrees % 180 else self

    @property
    def is_landscape(self) -> bool:
        """Whether the width exceeds the height."""
        return self.width > self.height

    def __iter__(self) -> Iterator[float]:
        yield self.width
        yield self.height


@dataclasses.dataclass(frozen=True, slots=True)
class Insets:
    """Distances inward from each edge, in points.

    Used for bleed, for gutters, and for the non-imageable border of a press
    sheet, where the four edges genuinely differ -- a gripper margin is not the
    same as a tail margin.
    """

    left: float = 0.0
    right: float = 0.0
    bottom: float = 0.0
    top: float = 0.0

    @classmethod
    def uniform(cls, amount: float) -> Insets:
        """The same distance on all four edges.

        >>> Insets.uniform(3)
        Insets(left=3, right=3, bottom=3, top=3)
        """
        return cls(amount, amount, amount, amount)

    def capped(self, limit: float) -> Insets:
        """These insets with no edge exceeding *limit*.

        >>> Insets(5, 1, 5, 1).capped(2)
        Insets(left=2, right=1, bottom=2, top=1)
        """
        return Insets(
            left=min(self.left, limit),
            right=min(self.right, limit),
            bottom=min(self.bottom, limit),
            top=min(self.top, limit),
        )

    @property
    def horizontal(self) -> float:
        """Total width consumed, left plus right."""
        return self.left + self.right

    @property
    def vertical(self) -> float:
        """Total height consumed, bottom plus top."""
        return self.bottom + self.top

    def __bool__(self) -> bool:
        return any((self.left, self.right, self.bottom, self.top))


@dataclasses.dataclass(frozen=True, slots=True)
class Rect:
    """An axis-aligned rectangle, bottom-left origin, y growing upward.

    >>> Rect(0, 0, 10, 20).size
    Size(width=10, height=20)
    >>> Rect(0, 0, 10, 20).translated(5, 5)
    Rect(x0=5, y0=5, x1=15, y1=25)
    """

    x0: float
    y0: float
    x1: float
    y1: float

    def __post_init__(self) -> None:
        if self.x1 < self.x0 or self.y1 < self.y0:
            raise ValueError(f"Rect is inside out: {self}")

    @classmethod
    def from_size(cls, size: Size, *, at: tuple[float, float] = (0.0, 0.0)) -> Rect:
        """A rectangle of *size* with its bottom-left corner *at*.

        >>> Rect.from_size(Size(10, 20))
        Rect(x0=0.0, y0=0.0, x1=10.0, y1=20.0)
        """
        x, y = at
        return cls(x, y, x + size.width, y + size.height)

    @property
    def width(self) -> float:
        """Horizontal extent."""
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        """Vertical extent."""
        return self.y1 - self.y0

    @property
    def size(self) -> Size:
        """Width and height, without the position."""
        return Size(self.width, self.height)

    @property
    def center(self) -> tuple[float, float]:
        """Midpoint, as ``(x, y)``."""
        return ((self.x0 + self.x1) / 2, (self.y0 + self.y1) / 2)

    def translated(self, dx: float, dy: float) -> Rect:
        """This rectangle moved by *dx*, *dy*."""
        return Rect(self.x0 + dx, self.y0 + dy, self.x1 + dx, self.y1 + dy)

    def expanded(self, insets: Insets) -> Rect:
        """This rectangle grown outward by *insets* -- bleed, typically."""
        return Rect(
            self.x0 - insets.left,
            self.y0 - insets.bottom,
            self.x1 + insets.right,
            self.y1 + insets.top,
        )

    def shrunk(self, insets: Insets) -> Rect:
        """This rectangle pulled inward by *insets* -- an imageable area.

        >>> Rect(0, 0, 100, 100).shrunk(Insets.uniform(10))
        Rect(x0=10, y0=10, x1=90, y1=90)
        """
        return Rect(
            self.x0 + insets.left,
            self.y0 + insets.bottom,
            self.x1 - insets.right,
            self.y1 - insets.top,
        )

    def union(self, other: Rect) -> Rect:
        """The smallest rectangle containing both."""
        return Rect(
            min(self.x0, other.x0),
            min(self.y0, other.y0),
            max(self.x1, other.x1),
            max(self.y1, other.y1),
        )

    def contains(self, other: Rect, *, tolerance: float = 1e-6) -> bool:
        """Whether *other* lies within this rectangle.

        The tolerance absorbs float noise from repeated centring; a form that
        misses by a nanometre fits.
        """
        return (
            other.x0 >= self.x0 - tolerance
            and other.y0 >= self.y0 - tolerance
            and other.x1 <= self.x1 + tolerance
            and other.y1 <= self.y1 + tolerance
        )

    def centered_in(self, other: Rect) -> Rect:
        """This rectangle's size, centred inside *other*."""
        cx, cy = other.center
        return Rect(
            cx - self.width / 2,
            cy - self.height / 2,
            cx + self.width / 2,
            cy + self.height / 2,
        )


def bounds(rects: Iterable[Rect]) -> Rect:
    """The smallest rectangle containing every rectangle given.

    >>> bounds([Rect(0, 0, 1, 1), Rect(5, 5, 6, 6)])
    Rect(x0=0, y0=0, x1=6, y1=6)
    """
    iterator = iter(rects)
    try:
        result = next(iterator)
    except StopIteration:
        raise ValueError("bounds() of no rectangles") from None
    for rect in iterator:
        result = result.union(rect)
    return result


def approx(value: float, other: float, *, tolerance: float = 1e-6) -> bool:
    """Whether two lengths are equal to within press-irrelevant noise."""
    return math.isclose(value, other, abs_tol=tolerance)
