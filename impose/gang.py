# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

"""Different finished sizes on one sheet.

A book is one size. A gang is how a short-run press earns the sheet: a card,
a flyer and a label, each its own trim, cut apart after printing. The pages
stay in the order the file gives them, left to right and then a new row, and
a new sheet when the row no longer fits. Nothing is turned to make room. A
page that does not fit the sheet on its own is named and refused.
"""

from __future__ import annotations

import pikepdf

from . import ImposeError
from .boxes import pdfx_version, read_boxes, require_trim
from .geometry import Size
from .plan import Placement, Plan, Surface
from .units import format_mm, length


def sizes(pages):
    """Finished size of each page, or none when this is not a gang."""
    if not pages:
        return None
    return tuple(page.trim_size for page in pages)


def origins(pages):
    """Each page's TrimBox, in that page's own coordinates."""
    if not pages:
        return None
    return tuple(page.trim for page in pages)


def allowance(marks, bleeds) -> float:
    """Room kept outside the trims: the marks, or the deepest bleed."""
    reach = marks.reach if marks else 0.0
    edges = [
        getattr(bleed, edge)
        for bleed in bleeds
        for edge in ("left", "right", "bottom", "top")
    ]
    return max(reach, *edges)


def read_pages(pdf: pikepdf.Pdf, bleed_cap):
    """Every page's boxes and its bleed, capped. Sizes are not required to agree."""
    cap = length(bleed_cap)
    version = pdfx_version(pdf)
    found = []
    for number, page in enumerate(pdf.pages, start=1):
        boxes = read_boxes(page)
        require_trim(boxes, page_number=number, pdfx=version)
        if boxes.rotation:
            raise ImposeError(
                f"Page {number} of a gang carries /Rotate {boxes.rotation}. "
                "Build each item upright; a gang does not turn a page."
            )
        found.append(boxes)
    if not found:
        raise ImposeError("A gang needs at least one page.")
    pages = tuple(found)
    bleeds = tuple(page.bleed_insets.capped(cap) for page in pages)
    return pages, bleeds


def impose(pages: int, **_options) -> Plan:
    """Refuse a gang built from a page count.

    The pages decide the packing, because they are not one size. The job
    reads each trim and packs that, which a count cannot do.
    """
    raise ImposeError(
        "A gang is packed from the pages' own sizes, not from a page count "
        f"({pages})."
    )


def pack(
    pages: tuple[Size, ...], area: Size, gutter: float
) -> tuple[tuple[tuple[int, int, int], ...], ...]:
    """Shelf-pack each page into the imageable area.

    Each sheet is a tuple of ``(source, column, row)``, in file order. Rows
    run down the sheet. A gutter separates neighbours; the first of a row has
    none before it.
    """
    if not pages:
        raise ImposeError("A gang needs at least one page.")
    sheets: list[list[tuple[int, int, int]]] = []
    placed: list[tuple[int, int, int]] = []
    column = row = 0
    x = y = row_height = 0.0
    for index, size in enumerate(pages):
        _must_fit(index, size, area)
        gap = gutter if column else 0.0
        if column and x + gap + size.width > area.width + 1e-6:
            y += row_height + gutter
            column = 0
            row += 1
            x = 0.0
            row_height = 0.0
            gap = 0.0
        if y and y + size.height > area.height + 1e-6:
            sheets.append(placed)
            placed = []
            column = row = 0
            x = y = row_height = 0.0
            gap = 0.0
        placed.append((index, column, row))
        x += gap + size.width
        column += 1
        row_height = max(row_height, size.height)
    sheets.append(placed)
    return tuple(tuple(sheet) for sheet in sheets)


def arranged(pages, width: float, height: float, gutter: float) -> Plan:
    """Pack *pages* into an area of this size, leaving *gutter* between them."""
    return plan_for(
        tuple(page.trim_size for page in pages), Size(width, height), gutter
    )


def plan_for(pages: tuple[Size, ...], area: Size, gutter: float) -> Plan:
    """The gang as a plan: one single-sided sheet per packed surface."""
    sheets = pack(pages, area, gutter)
    surfaces = []
    columns = rows = 1
    for number, sheet in enumerate(sheets):
        surfaces.append(
            Surface(
                number,
                "front",
                tuple(Placement(source, column, row) for source, column, row in sheet),
            )
        )
        columns = max(columns, *(column + 1 for _, column, _ in sheet))
        rows = max(rows, *(row + 1 for _, _, row in sheet))
    return Plan(
        columns=columns,
        rows=rows,
        surfaces=tuple(surfaces),
        pages=len(pages),
        schema="gang",
    )


def _must_fit(index: int, size: Size, area: Size) -> None:
    """Refuse a page that cannot sit on the sheet even alone."""
    if size.width <= area.width + 1e-6 and size.height <= area.height + 1e-6:
        return
    raise ImposeError(
        f"Page {index + 1} is {format_mm(size)}, and the area a gang can "
        f"use is {format_mm(area)}. It does not fit, and a gang does not "
        f"turn a page to make it."
    )
