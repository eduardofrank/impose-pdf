# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

"""Turning a plan into rectangles on a sheet.

Layout answers three questions a plan does not. Where does each cell sit, once
gutters are allowed for. How much bleed may each page keep -- all of it on an
outer edge, none of it where two pages butt at a fold, and half the gutter in
between. And does the finished form fit the part of the sheet the press can
actually image.

Bleed is the part worth stating plainly. Two pages meeting at a spine share one
cut line: there is no gap for bleed to live in, and painting it there puts one
page's image over its neighbour. So bleed is shaved to nothing on a butting
edge, and the two trims are made to share a coordinate exactly, so the fold
mark and the guillotine agree.
"""

from __future__ import annotations

import dataclasses

from . import ImposeError
from .boxes import rotate_insets
from .geometry import Insets, Rect, Size, bounds
from .plan import BLANK, Placement, Surface
from .press import Press
from .units import format_mm, to_mm

#: Neighbouring pages are painted a hair into each other so that antialiasing
#: at the shared edge cannot show the sheet through as a pale hairline.
TRAP = 0.25


@dataclasses.dataclass(frozen=True, slots=True)
class Gutters:
    """Space left between cells, for the knife or the fold."""

    horizontal: float = 0.0
    vertical: float = 0.0

    @classmethod
    def uniform(cls, amount: float) -> Gutters:
        """The same gap in both directions."""
        return cls(amount, amount)


@dataclasses.dataclass(frozen=True, slots=True)
class PlacedPage:  # pylint: disable=too-many-instance-attributes
    """One source page, positioned on the sheet.

    *trim* is the finished page: where the knife goes. *paint* is the area the
    renderer fills, trim plus whatever bleed survived. *clip* is the region of
    the source page to take, in the source's own unrotated coordinates.
    """

    source: int | None
    trim: Rect
    paint: Rect
    clip: Rect
    rotation: int = 0
    butts: frozenset[str] = frozenset()
    column: int = 0
    row: int = 0

    @property
    def is_blank(self) -> bool:
        """Whether this cell is empty."""
        return self.source is BLANK


@dataclasses.dataclass(frozen=True, slots=True)
class SheetLayout:
    """One imposed surface, ready to draw."""

    sheet: Size
    imageable: Rect
    pages: tuple[PlacedPage, ...]
    trim_bounds: Rect
    bleed_bounds: Rect
    turned: bool = False

    @property
    def printed(self) -> tuple[PlacedPage, ...]:
        """Pages that actually carry content."""
        return tuple(page for page in self.pages if not page.is_blank)

    def fold_positions(self, fold_columns: tuple[int, ...]) -> tuple[float, ...]:
        """Where the named column boundaries fall on the sheet.

        A boundary is the right-hand trim edge of the column before it. If the
        form was turned to fit, those boundaries are now horizontal, and the
        marks for them are handled as such by the caller.
        """
        positions = []
        for boundary in fold_columns:
            for page in self.pages:
                if page.column == boundary - 1:
                    positions.append(page.trim.y1 if self.turned else page.trim.x1)
                    break
        return tuple(positions)


def _cell_size(trim: Size, rotation: int) -> Size:
    """The space a page occupies once turned."""
    return trim.rotated(rotation)


def _uniform_cell(placements: tuple[Placement, ...], trim: Size) -> Size:
    """The cell size shared by every placement, or an error.

    A form is a grid, so every cell is the same size. Quarter turns swap the
    page's proportions, so a surface may turn all its pages or none, but not
    some -- that would need a grid with two different cell sizes.
    """
    sizes = {_cell_size(trim, placement.rotation) for placement in placements}
    if len(sizes) > 1:
        raise ImposeError(
            "A surface cannot mix quarter-turned pages with upright ones: "
            "the cells would be different sizes."
        )
    return sizes.pop() if sizes else trim


def _butting_edges(
    placement: Placement, columns: int, rows: int, gutters: Gutters
) -> frozenset[str]:
    """Edges where this cell touches a neighbour with no gap between."""
    edges = set()
    if gutters.horizontal <= 1e-9:
        if placement.column > 0:
            edges.add("left")
        if placement.column < columns - 1:
            edges.add("right")
    if gutters.vertical <= 1e-9:
        if placement.row > 0:
            edges.add("top")
        if placement.row < rows - 1:
            edges.add("bottom")
    return frozenset(edges)


def _kept_bleed(available: Insets, butts: frozenset[str], gutters: Gutters) -> Insets:
    """How much bleed each edge may keep.

    An outer edge keeps all of it. A butting edge keeps none: there is no gap
    to put it in. An edge with a gutter keeps up to half the gutter, so two
    neighbours' bleeds meet in the middle rather than overlapping.
    """
    half_h = gutters.horizontal / 2
    half_v = gutters.vertical / 2
    return Insets(
        left=0.0 if "left" in butts else min(available.left, half_h or available.left),
        right=(
            0.0 if "right" in butts else min(available.right, half_h or available.right)
        ),
        bottom=(
            0.0
            if "bottom" in butts
            else min(available.bottom, half_v or available.bottom)
        ),
        top=0.0 if "top" in butts else min(available.top, half_v or available.top),
    )


def _source_clip(trim: Rect, kept: Insets, rotation: int) -> Rect:
    """The region of the source page to take, in its own coordinates.

    *kept* is expressed on the sheet, so it is turned back through the
    placement's rotation to reach source space.
    """
    inverse = rotate_insets(kept, -rotation)
    return trim.expanded(inverse)


def _turn_rect(rect: Rect, form: Size) -> Rect:
    """A rectangle in a form turned a quarter turn clockwise.

    Clockwise matches /Rotate, so the whole pipeline turns one way.
    """
    return Rect(rect.y0, form.width - rect.x1, rect.y1, form.width - rect.x0)


def lay_out(  # pylint: disable=too-many-arguments,too-many-locals
    surface: Surface,
    *,
    columns: int,
    rows: int,
    trim: Size,
    bleed: Insets = Insets(),
    gutters: Gutters = Gutters(),
    press: Press,
    sheet: Size | None = None,
    mark_allowance: float = 0.0,
    trim_origin: Rect,
) -> SheetLayout:
    """Place one surface on a sheet.

    *trim_origin* is the source page's TrimBox in its own coordinates, and it
    is required rather than defaulted. The clip is built by growing it toward
    the edges that kept bleed, so a TrimBox that does not sit at the origin --
    which is the normal case, since a supplier's export has bleed and slug
    around it -- would otherwise be placed offset by however far it sits in.
    """
    sheet = sheet or press.sheet
    imageable = press.imageable_area(sheet)
    cell = _uniform_cell(surface.placements, trim)
    source_trim = trim_origin

    step_x = cell.width + gutters.horizontal
    step_y = cell.height + gutters.vertical
    form = Size(
        columns * cell.width + (columns - 1) * gutters.horizontal,
        rows * cell.height + (rows - 1) * gutters.vertical,
    )

    placed: list[PlacedPage] = []
    for placement in surface.placements:
        # Rows count downward as a person reads; PDF y counts upward.
        x0 = placement.column * step_x
        y1 = form.height - placement.row * step_y
        cell_rect = Rect(x0, y1 - cell.height, x0 + cell.width, y1)
        butts = _butting_edges(placement, columns, rows, gutters)
        kept = _kept_bleed(bleed, butts, gutters)
        paint = cell_rect.expanded(kept)
        # Butting neighbours are painted a hair into each other so the shared
        # edge cannot show as a pale hairline.
        paint = paint.expanded(
            Insets(**{edge: TRAP for edge in butts}) if butts else Insets()
        )
        placed.append(
            PlacedPage(
                source=placement.source,
                trim=cell_rect,
                paint=paint,
                clip=_source_clip(source_trim, kept, placement.rotation),
                rotation=placement.rotation,
                butts=butts,
                column=placement.column,
                row=placement.row,
            )
        )

    return _position(placed, form, sheet, imageable, mark_allowance)


def _position(
    placed: list[PlacedPage],
    form: Size,
    sheet: Size,
    imageable: Rect,
    mark_allowance: float,
) -> SheetLayout:
    """Centre the form in the imageable area, turning it if that is what fits."""
    trim_bounds = bounds([page.trim for page in placed])
    paint_bounds = bounds([page.paint for page in placed])
    # Marks are measured from the trim, so a marked edge needs whichever is
    # larger: the bleed already there, or the reach of the mark.
    extent = paint_bounds.union(trim_bounds.expanded(Insets.uniform(mark_allowance)))

    turned = False
    if not _fits(extent.size, imageable.size):
        if not _fits(extent.size.swapped(), imageable.size):
            raise ImposeError(
                _why_it_does_not_fit(
                    extent, trim_bounds, paint_bounds, imageable, mark_allowance
                )
            )
        turned = True
        placed = [
            dataclasses.replace(
                page,
                trim=_turn_rect(page.trim, extent.size),
                paint=_turn_rect(page.paint, extent.size),
                rotation=(page.rotation + 90) % 360,
                butts=frozenset(_TURNED_EDGE[edge] for edge in page.butts),
            )
            for page in placed
        ]
        trim_bounds = bounds([page.trim for page in placed])
        paint_bounds = bounds([page.paint for page in placed])
        extent = paint_bounds.union(
            trim_bounds.expanded(Insets.uniform(mark_allowance))
        )
        form = form.swapped()

    target = extent.centered_in(imageable)
    dx, dy = target.x0 - extent.x0, target.y0 - extent.y0
    placed = [
        dataclasses.replace(
            page, trim=page.trim.translated(dx, dy), paint=page.paint.translated(dx, dy)
        )
        for page in placed
    ]
    placed = _snap_butting(placed)
    return SheetLayout(
        sheet=sheet,
        imageable=imageable,
        pages=tuple(placed),
        trim_bounds=bounds([page.trim for page in placed]),
        bleed_bounds=bounds([page.paint for page in placed]),
        turned=turned,
    )


def _why_it_does_not_fit(
    extent: Rect, trims: Rect, paint: Rect, imageable: Rect, allowance: float
) -> str:
    """Say what the form is made of, so the operator can see what to shed.

    A bare "it does not fit" leaves someone measuring by hand to work out
    whether it was the bleed, the marks, or the gutters that pushed it over.
    Each is a knob they can turn, so each is named with its cost.
    """
    over_w = extent.width - imageable.width
    over_h = extent.height - imageable.height
    turned_w = extent.height - imageable.width
    turned_h = extent.width - imageable.height
    by = min(
        max(over_w, over_h),
        max(turned_w, turned_h),
    )
    parts = [f"trims {format_mm(trims.size)}"]
    bleed = max(
        trims.x0 - paint.x0,
        paint.x1 - trims.x1,
        trims.y0 - paint.y0,
        paint.y1 - trims.y1,
    )
    if bleed > 1e-6:
        parts.append(f"{to_mm(bleed):g} mm bleed per edge")
    if allowance > 1e-6:
        parts.append(f"{to_mm(allowance):g} mm for marks per edge")
    return (
        f"The imposed form is {format_mm(extent.size)} "
        f"({', '.join(parts)}), and the imageable area is "
        f"{format_mm(imageable.size)}. It does not fit either way round, and "
        f"misses by {to_mm(by):.3g} mm. Fewer pages per sheet, a smaller "
        f"gutter, or shorter marks would each make room."
    )


# Turning the form clockwise carries each edge to the next one round.
_TURNED_EDGE = {"left": "top", "top": "right", "right": "bottom", "bottom": "left"}


def _fits(form: Size, area: Size, *, tolerance: float = 1e-6) -> bool:
    """Whether a form of this size fits an area, as laid out."""
    return (
        form.width <= area.width + tolerance and form.height <= area.height + tolerance
    )


def _snap_butting(placed: list[PlacedPage]) -> list[PlacedPage]:
    """Make butting trims share a coordinate exactly.

    Two pages either side of a fold are cut on one line. Float arithmetic can
    leave their trims a fraction apart, and a fraction is enough for a mark to
    be drawn twice or a hairline to show.
    """
    xs = sorted({page.trim.x0 for page in placed} | {page.trim.x1 for page in placed})
    ys = sorted({page.trim.y0 for page in placed} | {page.trim.y1 for page in placed})
    snap_x = _cluster(xs)
    snap_y = _cluster(ys)
    return [
        dataclasses.replace(
            page,
            trim=Rect(
                snap_x[page.trim.x0],
                snap_y[page.trim.y0],
                snap_x[page.trim.x1],
                snap_y[page.trim.y1],
            ),
        )
        for page in placed
    ]


def _cluster(values: list[float], *, tolerance: float = 1e-6) -> dict[float, float]:
    """Map near-identical coordinates onto one representative."""
    mapping: dict[float, float] = {}
    representative = None
    for value in values:
        if representative is None or value - representative > tolerance:
            representative = value
        mapping[value] = representative
    return mapping
