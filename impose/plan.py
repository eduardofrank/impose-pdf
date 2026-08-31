# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

"""What goes where: imposition as integers, before any geometry.

A schema's real content is an ordering. Saddle stitch pairs the first page with
the last; cut and stack runs each stack down a column so the piles can be set
on each other after cutting. None of that involves a millimetre, and none of it
should have to produce a PDF to be checked.

So a schema returns a :class:`Plan`: for each side of each sheet, which source
page sits in which cell, and how it is turned. :mod:`impose.layout` turns a
plan into rectangles, and :mod:`impose.render` draws them. A schema that gets
the ordering wrong fails a test that reads like a bindery instruction.
"""

from __future__ import annotations

import dataclasses
from collections import Counter
from collections.abc import Iterator
from typing import Literal

from . import ImposeError

Side = Literal["front", "back"]

#: A cell holding no page: the odd corner of a form that does not divide.
BLANK = None


@dataclasses.dataclass(frozen=True, slots=True)
class Placement:
    """One source page in one cell of one surface.

    ``column`` counts from the left and ``row`` from the top, as a person reads
    a laid-out sheet. Layout converts to PDF's upward y once, in one place.
    """

    source: int | None
    column: int
    row: int
    rotation: int = 0

    def __post_init__(self) -> None:
        if self.rotation % 90:
            raise ValueError(f"Rotation must be a quarter turn, got {self.rotation}.")
        if self.column < 0 or self.row < 0:
            raise ValueError(f"Cell must be non-negative, got {self.cell}.")

    @property
    def cell(self) -> tuple[int, int]:
        """``(column, row)``."""
        return (self.column, self.row)

    @property
    def is_blank(self) -> bool:
        """Whether this cell is deliberately empty."""
        return self.source is BLANK


@dataclasses.dataclass(frozen=True, slots=True)
class Surface:
    """One side of one press sheet -- one page of the output document."""

    sheet: int
    side: Side
    placements: tuple[Placement, ...]

    def __post_init__(self) -> None:
        seen = Counter(placement.cell for placement in self.placements)
        clashes = [cell for cell, count in seen.items() if count > 1]
        if clashes:
            raise ImposeError(
                f"Sheet {self.sheet} {self.side}: two pages in cell {clashes[0]}."
            )

    def at(self, column: int, row: int) -> Placement | None:
        """The placement in a cell, or ``None`` if the cell is unused."""
        for placement in self.placements:
            if placement.cell == (column, row):
                return placement
        return None

    @property
    def sources(self) -> tuple[int, ...]:
        """Source pages on this surface, in cell order, blanks omitted."""
        return tuple(
            placement.source
            for placement in sorted(self.placements, key=lambda p: (p.row, p.column))
            if placement.source is not BLANK
        )


@dataclasses.dataclass(frozen=True, slots=True)
class Plan:
    """A complete imposition, as page numbers on a grid.

    ``pages`` is how many source pages the plan consumes, counting the blanks
    added to fill the last form. A schema pads to a whole number of forms, and
    the count is part of the plan so the renderer knows what it was promised.
    """

    columns: int
    rows: int
    surfaces: tuple[Surface, ...]
    pages: int
    schema: str = ""

    def __post_init__(self) -> None:
        if self.columns < 1 or self.rows < 1:
            raise ValueError(f"Grid must be at least 1x1, got {self.grid}.")
        for surface in self.surfaces:
            for placement in surface.placements:
                if placement.column >= self.columns or placement.row >= self.rows:
                    raise ImposeError(
                        f"Sheet {surface.sheet} {surface.side}: cell "
                        f"{placement.cell} is outside the {self.columns}x"
                        f"{self.rows} grid."
                    )

    @property
    def grid(self) -> tuple[int, int]:
        """``(columns, rows)``."""
        return (self.columns, self.rows)

    @property
    def per_surface(self) -> int:
        """Cells on one side of one sheet."""
        return self.columns * self.rows

    @property
    def sheets(self) -> int:
        """Physical sheets, each carrying up to two surfaces."""
        return len({surface.sheet for surface in self.surfaces})

    def __iter__(self) -> Iterator[Surface]:
        return iter(self.surfaces)

    def __len__(self) -> int:
        return len(self.surfaces)

    def placed_sources(self) -> tuple[int, ...]:
        """Every source page the plan places, in surface order."""
        return tuple(
            placement.source
            for surface in self.surfaces
            for placement in surface.placements
            if placement.source is not BLANK
        )

    def validate(self, *, exhaustive: bool = True) -> None:
        """Check the plan is a plan.

        With *exhaustive*, every source page from 0 to :attr:`pages` must be
        placed exactly once -- true of any binding schema, and the check that
        catches an off-by-one before it reaches a plate. Step and repeat sets
        it False, since it places the same page many times on purpose.
        """
        placed = self.placed_sources()
        out_of_range = [n for n in placed if not 0 <= n < self.pages]
        if out_of_range:
            raise ImposeError(
                f"{self.schema or 'plan'}: page {out_of_range[0]} is outside "
                f"the document (0..{self.pages - 1})."
            )
        if not exhaustive:
            return
        counts = Counter(placed)
        duplicated = sorted(n for n, count in counts.items() if count > 1)
        if duplicated:
            raise ImposeError(
                f"{self.schema or 'plan'}: page {duplicated[0]} is imposed "
                f"{counts[duplicated[0]]} times."
            )
        missing = sorted(set(range(self.pages)) - set(counts))
        if missing:
            raise ImposeError(
                f"{self.schema or 'plan'}: page {missing[0]} is never imposed."
            )

    def describe(self) -> str:
        """The plan as a grid of page numbers, for reading and for bug reports.

        Page numbers are shown 1-based, as a person counts them; ``.`` is a
        blank cell.
        """
        lines: list[str] = []
        for surface in self.surfaces:
            lines.append(f"sheet {surface.sheet + 1} {surface.side}")
            for row in range(self.rows):
                cells = []
                for column in range(self.columns):
                    placement = surface.at(column, row)
                    if placement is None or placement.is_blank:
                        cells.append("   .")
                    else:
                        turn = "" if not placement.rotation else "*"
                        cells.append(f"{placement.source + 1:>4}{turn}")
                lines.append("  " + " ".join(cells))
        return "\n".join(lines)


def blanks_needed(pages: int, per_form: int) -> int:
    """Blank pages to add so *pages* fills a whole number of forms.

    >>> blanks_needed(13, 4)
    3
    >>> blanks_needed(16, 4)
    0
    """
    if per_form < 1:
        raise ValueError("A form holds at least one page.")
    remainder = pages % per_form
    return 0 if remainder == 0 else per_form - remainder
