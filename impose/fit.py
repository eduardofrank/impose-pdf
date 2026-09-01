# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

"""How many fit, which way round, and what the leftovers cost.

The schemas answer "what order do the pages go in". This answers the question
that comes first in a shop: given a finished size and a press, how many fit on
a sheet, and how much of the sheet is thrown away.

Two things decide it. Pages may sit upright or on their sides, and the denser
of the two is usually -- not always -- the one to run. And the count along a
span is not a simple division once there is a gutter: *n* pieces have *n-1*
gaps between them, never *n*, so the gap is added once to the span before
dividing rather than once per piece.

The waste arithmetic is here because it belongs to imposition, not to pricing.
A job of 500 cards at 21 up runs 24 sheets and leaves 4 slots empty. Those 4
are already paid for, so the useful thing to tell someone is that 504 cards
cost the same as 500.

Density is not the same as cheapness, and choosing on density alone is a
mistake. A 90 x 50 mm card goes 24 up on an Indigo turned, or 20 up upright.
For 100 cards both run five sheets -- but 24 up throws away twenty cards to do
it, and 20 up fills the sheet exactly. Past that the denser grid starts saving
sheets and becomes the right answer. So where a quantity is known, the
arrangements are ranked by sheets first and waste second, and density only
breaks a remaining tie.
"""

from __future__ import annotations

import dataclasses
import math

from .geometry import Rect, Size
from .units import format_mm

#: A gap wide enough for a guillotine to take without cutting into a neighbour.
DEFAULT_GUTTER = 4.0 * 72 / 25.4


@dataclasses.dataclass(frozen=True, slots=True)
class Arrangement:
    """One way of putting a finished size onto a sheet."""

    columns: int
    rows: int
    turned: bool
    cell: Size
    gutter: float = 0.0

    @property
    def up(self) -> int:
        """How many pieces one surface carries."""
        return self.columns * self.rows

    @property
    def form(self) -> Size:
        """The trims and their gutters, without marks or bleed."""
        return Size(
            self.columns * self.cell.width + (self.columns - 1) * self.gutter,
            self.rows * self.cell.height + (self.rows - 1) * self.gutter,
        )

    def describe(self) -> str:
        """A line for an operator choosing a layout.

        >>> from .units import MM
        >>> a = Arrangement(2, 4, True, Size(148 * MM, 105 * MM), 4 * MM)
        >>> a.describe()
        '8 up, 2 × 4 turned, form 300 × 432 mm'
        """
        way = "turned" if self.turned else "upright"
        return (
            f"{self.up} up, {self.columns} × {self.rows} {way}, "
            f"form {format_mm(self.form)}"
        )


@dataclasses.dataclass(frozen=True, slots=True)
class Run:
    """What an arrangement means for a job of a given size."""

    arrangement: Arrangement
    quantity: int
    sheets: int
    on_last_sheet: int

    @property
    def capacity(self) -> int:
        """Pieces the press run could carry."""
        return self.sheets * self.arrangement.up

    @property
    def waste(self) -> int:
        """Slots printed and thrown away."""
        return self.capacity - self.quantity

    def advice(self) -> str | None:
        """What to say about the leftovers, if anything.

        The sheets are already being run, so the empty slots cost nothing more
        in clicks. They do cost ink: every surplus piece is imaged and then
        thrown away. So the useful thing to say is that filling them is free,
        and that discarding them is not quite.
        """
        if self.waste <= 0:
            return None
        return (
            f"{self.waste} surplus piece(s) are imaged on the last sheet and "
            f"discarded, which is ink spent on nothing. The sheets are already "
            f"being run, so raising the order to {self.capacity} costs no more "
            f"press time."
        )

    def describe(self) -> str:
        """A summary of the run."""
        return (
            f"{self.quantity} on {self.sheets} sheet(s) at "
            f"{self.arrangement.up} up; {self.on_last_sheet} on the last, "
            f"{self.waste} wasted"
        )


def count_along(span: float, unit: float, gutter: float = 0.0) -> int:
    """How many *unit* lengths fit in *span* with *gutter* between them.

    There are one fewer gaps than pieces, so the gap is added to the span once
    before dividing rather than charged against every piece.

    >>> count_along(300, 148, 4)
    2
    >>> count_along(440, 105, 4)
    4
    >>> count_along(100, 150, 0)
    0
    """
    if unit <= 0 or span < unit:
        return 0
    if gutter <= 0:
        return int(math.floor((span + 1e-9) / unit))
    return max(0, int(math.floor((span + gutter + 1e-9) / (unit + gutter))))


def arrangements(
    trim: Size,
    area: Size | Rect,
    *,
    gutter: float = DEFAULT_GUTTER,
    allowance: float = 0.0,
) -> list[Arrangement]:
    """Every way *trim* fits *area*, densest first.

    *allowance* is the room to keep clear on each edge for marks and bleed; it
    is taken off the area before anything is counted.
    """
    usable = area.size if isinstance(area, Rect) else area
    width = usable.width - 2 * allowance
    height = usable.height - 2 * allowance

    found: list[Arrangement] = []
    for turned in (False, True):
        cell = trim.swapped() if turned else trim
        columns = count_along(width, cell.width, gutter)
        rows = count_along(height, cell.height, gutter)
        if columns and rows:
            found.append(Arrangement(columns, rows, turned, cell, gutter))
    # Densest first; on a tie the upright one, since turning pages for no gain
    # only makes the sheet harder to read on the stacker.
    found.sort(key=lambda a: (-a.up, a.turned))
    return found


def rank(runs: list[Run]) -> list[Run]:
    """Costed arrangements, cheapest first.

    Fewest sheets wins, because a sheet is the thing being paid for. A tie goes
    to whichever throws away less, and only then to the denser grid.
    """
    return sorted(runs, key=lambda r: (r.sheets, r.waste, -r.arrangement.up))


def best(
    trim: Size,
    area: Size | Rect,
    *,
    quantity: int | None = None,
    gutter: float = DEFAULT_GUTTER,
    allowance: float = 0.0,
) -> Arrangement | None:
    """The arrangement to run, or ``None`` if the size will not fit at all.

    With a *quantity*, that means the one costing fewest sheets, then least
    waste. Without one there is nothing to weigh against density, so the
    densest is returned.
    """
    found = arrangements(trim, area, gutter=gutter, allowance=allowance)
    if not found:
        return None
    if quantity is None or quantity < 1:
        return found[0]
    return rank([plan_run(a, quantity) for a in found])[0].arrangement


def plan_run(arrangement: Arrangement, quantity: int) -> Run:
    """What *quantity* pieces cost in sheets at this arrangement.

    >>> from .units import MM
    >>> a = Arrangement(3, 7, False, Size(90 * MM, 55 * MM), 4 * MM)
    >>> plan_run(a, 500).describe()
    '500 on 24 sheet(s) at 21 up; 17 on the last, 4 wasted'
    """
    if quantity < 1:
        raise ValueError(f"A run is at least one piece; got {quantity}.")
    up = arrangement.up
    sheets = math.ceil(quantity / up)
    on_last = quantity - (sheets - 1) * up
    return Run(arrangement, quantity, sheets, on_last)


def compare(
    trim: Size,
    area: Size | Rect,
    quantity: int,
    *,
    gutter: float = DEFAULT_GUTTER,
    allowance: float = 0.0,
) -> list[Run]:
    """Every arrangement costed for a job, cheapest first.

    The densest is not always the cheapest for a given order: a sparser grid
    can divide the quantity more evenly and waste less on the same number of
    sheets.

    >>> from .units import MM
    >>> from .press import INDIGO_5000
    >>> card = Size(90 * MM, 50 * MM)
    >>> area = INDIGO_5000.imageable_area()
    >>> for run in compare(card, area, 100, gutter=4 * MM):
    ...     print(run.describe())
    100 on 5 sheet(s) at 20 up; 20 on the last, 0 wasted
    100 on 5 sheet(s) at 24 up; 4 on the last, 20 wasted
    """
    return rank(
        [
            plan_run(arrangement, quantity)
            for arrangement in arrangements(
                trim, area, gutter=gutter, allowance=allowance
            )
        ]
    )
