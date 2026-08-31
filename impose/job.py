# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

"""One call from a source document to an imposed file.

Everything the other modules do is composable by hand, and doing it by hand is
how the pieces were tested. This is the assembly: open the document, check it
is fit to impose, choose the ordering, lay each surface out, mark it, and
write the sheets.

The checks before any geometry are the part that matters. A document whose
pages are not all the same finished size cannot go on a uniform grid, and a
PDF/X file with no TrimBox has not told us the one measurement imposition
depends on. Both are refused by name here rather than discovered as a wrong
sheet on the press.
"""

from __future__ import annotations

import dataclasses
import pathlib
from collections.abc import Callable
from typing import IO, Any

import pikepdf

from . import ImposeError
from .boxes import PageBoxes, pdfx_version, read_boxes, require_trim
from .geometry import Size, approx
from .layout import Gutters, lay_out
from .marks import MarkStyle, Segment, trim_marks
from .plan import Plan
from .press import Press
from .press import get as get_press
from .schemas import cutstack, nup, perfect, saddle, steprepeat
from .units import format_mm, length, paper

#: Schemas by the name a person would type.
SCHEMAS: dict[str, Callable[..., Plan]] = {
    "saddle": saddle.impose,
    "perfect": perfect.impose,
    "nup": nup.impose,
    "cutstack": cutstack.impose,
    "steprepeat": steprepeat.impose,
}

#: Schemas whose grid is fixed by the binding rather than chosen.
_FIXED_GRID = frozenset({"saddle", "perfect"})

#: Marks are drawn unless a caller explicitly asks for none. A press sheet
#: with no indication of where to cut is not much use to a bindery.
DEFAULT_MARKS = MarkStyle()


@dataclasses.dataclass(frozen=True, slots=True)
class Result:
    """What a job produced, for reporting back to whoever asked."""

    plan: Plan
    sheets: int
    surfaces: int
    sheet_size: Size
    trim_size: Size
    press: str
    turned: bool

    def describe(self) -> str:
        """A summary an operator can check before sending the file."""
        turned = ", form turned to fit" if self.turned else ""
        return (
            f"{self.plan.schema}: {self.plan.pages} pages onto {self.sheets} "
            f"sheet(s) of {format_mm(self.sheet_size)} on {self.press}; "
            f"finished page {format_mm(self.trim_size)}{turned}"
        )


def source_boxes(pdf: pikepdf.Pdf) -> PageBoxes:
    """The page geometry shared by every page, or an error saying which differs.

    Imposition puts pages into a grid of one cell size, so the pages have to
    agree on their finished size. They must also agree on where the TrimBox
    sits inside the sheet, because that offset is what positions the artwork.
    """
    version = pdfx_version(pdf)
    first = read_boxes(pdf.pages[0])
    require_trim(first, page_number=1, pdfx=version)
    for number, page in enumerate(pdf.pages, start=1):
        boxes = read_boxes(page)
        require_trim(boxes, page_number=number, pdfx=version)
        if boxes.trim_size != first.trim_size:
            raise ImposeError(
                f"Page {number} has a finished size of "
                f"{format_mm(boxes.trim_size)}, but page 1 is "
                f"{format_mm(first.trim_size)}. Every page must be the same "
                f"size to go on one grid."
            )
        if not _same_rect(boxes.trim, first.trim):
            raise ImposeError(
                f"Page {number} has its TrimBox in a different place on the "
                f"sheet than page 1. Imposing pages whose boxes sit at "
                f"different offsets is not supported yet."
            )
    return first


def _same_rect(a, b) -> bool:
    """Whether two boxes are the same to within press-irrelevant noise."""
    return all(
        approx(getattr(a, edge), getattr(b, edge)) for edge in ("x0", "y0", "x1", "y1")
    )


def build_plan(schema: str, pages: int, **options: Any) -> Plan:
    """The ordering for *schema*, with its own options."""
    try:
        build = SCHEMAS[schema]
    except KeyError:
        raise ImposeError(
            f"Unknown schema {schema!r}. Known schemas: "
            f"{', '.join(sorted(SCHEMAS))}."
        ) from None
    if schema in _FIXED_GRID:
        for fixed in ("columns", "rows"):
            if options.pop(fixed, None) is not None:
                raise ImposeError(
                    f"The {schema} schema imposes a two-page spread; its grid "
                    f"is fixed by the binding and cannot be set."
                )
    else:
        options.setdefault("columns", 2)
        options.setdefault("rows", 1)
    return build(pages, **{k: v for k, v in options.items() if v is not None})


def impose_document(  # pylint: disable=too-many-arguments,too-many-locals
    source: pikepdf.Pdf | str | pathlib.Path,
    output: str | pathlib.Path | IO[bytes],
    *,
    schema: str = "saddle",
    press: Press | str = "indigo-5000",
    sheet: Size | str | tuple[float, float] | None = None,
    gutters: Gutters | float | str = 0.0,
    marks: MarkStyle | None = DEFAULT_MARKS,
    **options: Any,
) -> Result:
    """Impose *source* onto press sheets and write it to *output*.

    Pass ``marks=None`` for no marks at all; the default is registration crop
    marks. Remaining keyword arguments go to the schema: ``columns`` and
    ``rows`` for the grid schemas, ``section_pages`` for perfect binding,
    ``copies`` for step and repeat.
    """
    # Imported here rather than at module scope so that building and checking
    # a plan costs nothing but this module: the renderer pulls in pikepdf's
    # compiled extension, and the ordering logic has no use for it.
    from .render import Renderer  # pylint: disable=import-outside-toplevel

    opened = _open(source)
    try:
        machine = get_press(press) if isinstance(press, str) else press
        sheet_size = paper(sheet) if sheet is not None else machine.sheet
        machine.check_sheet(sheet_size)
        boxes = source_boxes(opened)

        plan = build_plan(schema, len(opened.pages), **options)
        plan.validate(exhaustive=schema != "steprepeat")

        style = marks
        gaps = _gutters(gutters)
        renderer = Renderer(style=style)
        turned = False
        for surface in plan:
            layout = lay_out(
                surface,
                columns=plan.columns,
                rows=plan.rows,
                trim=boxes.trim_size,
                trim_origin=boxes.trim,
                bleed=boxes.bleed_insets,
                gutters=gaps,
                press=machine,
                sheet=sheet_size,
                mark_allowance=style.reach if style else 0.0,
            )
            turned = turned or layout.turned
            renderer.add(
                layout,
                opened,
                marks=_marks(layout, plan, style),
                source_rotation=boxes.rotation,
            )
        renderer.save(output)

        return Result(
            plan=plan,
            sheets=plan.sheets,
            surfaces=len(plan),
            sheet_size=sheet_size,
            trim_size=boxes.trim_size,
            press=machine.name,
            turned=turned,
        )
    finally:
        if opened is not source:
            opened.close()


def _marks(layout, plan: Plan, style: MarkStyle | None) -> list[Segment] | None:
    """Cut marks for a laid-out surface, with the schema's folds dashed."""
    if style is None:
        return None
    return trim_marks(
        [page.trim for page in layout.pages],
        style=style,
        folds=layout.fold_positions(plan.fold_columns),
    )


def _gutters(value: Gutters | float | str) -> Gutters:
    """Accept a Gutters, a number, or a length such as ``"4mm"``."""
    if isinstance(value, Gutters):
        return value
    return Gutters.uniform(length(value))


def _open(source: pikepdf.Pdf | str | pathlib.Path) -> pikepdf.Pdf:
    """Open *source*, or pass an already-open document through."""
    if isinstance(source, pikepdf.Pdf):
        return source
    try:
        return pikepdf.open(source)
    except Exception as error:
        raise ImposeError(f"Cannot open {source}: {error}") from error


__all__ = ["Result", "SCHEMAS", "impose_document", "build_plan", "source_boxes"]
