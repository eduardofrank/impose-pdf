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
from .fit import DEFAULT_GUTTER, best
from .geometry import Insets, Size, approx
from .layout import Gutters, lay_out
from .marks import MarkStyle, Segment, furniture, trim_marks
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

#: Schemas where turning the pages would change the product. A saddle-stitched
#: booklet folds down the middle of its spread: turn the pages a quarter and
#: the fold runs the other way, which is a top-bound book, not the one that was
#: asked for. The flat schemas are cut apart, so orientation is free.
_BINDING_EDGE_MATTERS = frozenset({"saddle", "perfect"})

#: The most bleed to place, capping whatever the artwork arrived with. Two
#: millimetres is enough for any guillotine to cut into and leaves the rest of
#: a small sheet to the job.
DEFAULT_BLEED = "2mm"

#: Ask for a sheet exactly the size of the imposed form -- no press margins, no
#: centring, nothing spare. The result is not a press sheet but a *form*: one
#: folded signature, trimmed to its own outer edge, ready to be fed to a second
#: imposition that puts several of them on real paper.
FIT_SHEET = "fit"

#: What the output page is. `imageable` makes it the part of the sheet the
#: press can actually print, so a form that fits the page is a form that runs --
#: an operator can judge the job by opening it. `sheet` makes it the physical
#: sheet, with the unimageable border shown as margin.
PAGE_CHOICES = ("imageable", "sheet")


def default_gutter(schema: str) -> float:
    """The gap to leave between pages, when the caller has not said.

    Cut work wants room for the knife: 4 mm between pieces is what a guillotine
    needs to come down without shaving a neighbour. A folded spread wants the
    opposite -- its two pages meet across the fold and any gap there is a gap
    in the middle of the reader's page -- so the binding schemas default to
    none and butt at the spine.
    """
    return 0.0 if schema in _BINDING_EDGE_MATTERS else DEFAULT_GUTTER


#: Marks are drawn unless a caller explicitly asks for none. A press sheet
#: with no indication of where to cut is not much use to a bindery.
DEFAULT_MARKS = MarkStyle()


@dataclasses.dataclass(frozen=True, slots=True)
class Result:  # pylint: disable=too-many-instance-attributes
    """What a job produced, for reporting back to whoever asked."""

    plan: Plan
    sheets: int
    surfaces: int
    sheet_size: Size
    trim_size: Size
    press: str
    turned: bool
    pdfx: str | None = None
    warnings: tuple[str, ...] = ()

    @property
    def up(self) -> int:
        """Finished pages on one surface."""
        return self.plan.columns * self.plan.rows

    def describe(self) -> str:
        """A summary an operator can check before sending the file.

        The grid is in it because that is the number a shop checks first: how
        many to a sheet. Whether it was given or worked out, it is the one
        thing worth reading off the summary before the file goes to press.
        """
        turned = ", form turned to fit" if self.turned else ""
        claim = f", {self.pdfx}" if self.pdfx else ""
        return (
            f"{self.plan.schema}: {self.plan.pages} pages onto {self.sheets} "
            f"sheet(s) at {self.up} up ({self.plan.columns} × "
            f"{self.plan.rows}), page {format_mm(self.sheet_size)} on "
            f"{self.press}; finished page {format_mm(self.trim_size)}"
            f"{turned}{claim}"
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


@dataclasses.dataclass(frozen=True, slots=True)
class Measurement:
    """What a document says about its own size, for the fit arithmetic.

    Enough to answer "how many of these go on a sheet" without imposing
    anything: the finished size, how many pages there are to divide, and how
    much bleed the artwork actually brought.
    """

    trim_size: Size
    pages: int
    bleed_insets: Insets
    pdfx: str | None = None


def measure(source: pikepdf.Pdf | str | pathlib.Path) -> Measurement:
    """Read the finished size and page count off a document.

    The same checks imposing makes: a document whose pages disagree on their
    finished size has no single size to fit, and says so here rather than on
    the press.
    """
    pdf = _open(source)
    try:
        boxes = source_boxes(pdf)
        return Measurement(
            boxes.trim_size, len(pdf.pages), boxes.bleed_insets, pdfx_version(pdf)
        )
    finally:
        if pdf is not source:
            pdf.close()


def repeating_unit(trim: Size, schema: str) -> Size:
    """The block that has to fit for one more of the job to fit.

    Most schemas repeat a finished page: fit the page and you have fitted the
    unit. The bound ones repeat a spread. A saddle-stitched sheet carries two
    pages butted at the spine and folds down the middle, so what has to go on
    the sheet twice for two booklets to share it is the pair, not the page.

    >>> from .units import MM, format_mm
    >>> half_letter = Size(139.7 * MM, 215.9 * MM)
    >>> format_mm(repeating_unit(half_letter, "nup"))
    '139.7 × 215.9 mm'
    >>> format_mm(repeating_unit(half_letter, "saddle"))
    '279.4 × 215.9 mm'
    """
    if schema in _FIXED_GRID:
        return Size(trim.width * 2, trim.height)
    return trim


def choose_grid(  # pylint: disable=too-many-arguments
    trim: Size,
    press: Press,
    sheet: Size,
    *,
    gutters: Gutters,
    allowance: float,
    quantity: int | None = None,
) -> tuple[int, int, bool]:
    """The grid to run, and whether it needs the pages turned.

    This is the question a shop asks before anything else: given this finished
    size and this press, how many to a sheet.

    With a *quantity* the answer is what costs fewest sheets, then wastes least
    -- the densest grid is not always that, since a sparser one can divide the
    document more evenly. Without one, density is all there is to go on, which
    is the right answer for a schema that fills every sheet with the same thing
    however many are wanted.
    """
    gutter = max(gutters.horizontal, gutters.vertical)
    arrangement = best(
        trim,
        press.imageable_area(sheet),
        quantity=quantity,
        gutter=gutter,
        allowance=allowance,
    )
    if arrangement is None:
        raise ImposeError(
            f"A finished size of {format_mm(trim)} does not fit the imageable "
            f"area of {press.name} "
            f"({format_mm(press.imageable_area(sheet).size)}) even one up."
        )
    return arrangement.columns, arrangement.rows, arrangement.turned


def impose_document(  # pylint: disable=too-many-arguments,too-many-locals
    source: pikepdf.Pdf | str | pathlib.Path,
    output: str | pathlib.Path | IO[bytes],
    *,
    schema: str = "saddle",
    press: Press | str = "indigo-5000",
    sheet: Size | str | tuple[float, float] | None = None,
    gutters: Gutters | float | str | None = None,
    marks: MarkStyle | None = DEFAULT_MARKS,
    orientation: str = "auto",
    max_nested_sheets: int = saddle.MAX_NESTED_SHEETS,
    paper_caliper: float | str = 0.0,
    bleed: float | str = DEFAULT_BLEED,
    registration: bool = False,
    colour_bar: bool = False,
    page: str = "imageable",
    **options: Any,
) -> Result:
    """Impose *source* onto press sheets and write it to *output*.

    Pass ``marks=None`` for no marks at all; the default is registration crop
    marks.

    *page* decides what the output page is. ``"imageable"``, the default, makes
    it the area the press can print, so anything that fits the page will run
    and the press positions the smaller sheet itself. ``"sheet"`` makes it the
    physical sheet, with the gripper margin shown.

    *gutters* defaults to what the schema wants: 4 mm between pieces that will
    be cut apart, and none between the two halves of a folded spread.

    *bleed* is the most bleed to place, and it caps whatever the artwork
    brought rather than requesting it: a file supplied with 5 mm is shaved to
    2 mm, one supplied with 1 mm keeps its 1 mm, and one with none stays with
    none. Bleed that is not there cannot be invented.

    *paper_caliper* is the thickness of one sheet of the stock being run, and
    turns on creep compensation: nested sheets push out at the fore edge, and
    each sheet's image is slid toward the spine by as much as its own fold has
    been displaced. Measure it rather than guess -- a micrometer on a stack of
    twenty, divided by twenty, is how a shop gets this number.

    *registration* adds a bullseye on each side of the form, and *colour_bar*
    a row of ink patches along the tail. Both are placed only where the margin
    has room, so a form that nearly fills the sheet simply gets fewer or none.

    *orientation* decides how the pages sit in their cells. ``"auto"`` tries
    them upright and, if the form will not fit, tries them turned a quarter --
    six A6 pages will not fit an Indigo upright but fit comfortably on their
    sides. ``"upright"`` and ``"turned"`` pin it. Turning is never tried
    automatically for a binding schema, because it would move the fold and
    give a top-bound book instead of a side-bound one.

    Remaining keyword arguments go to the schema: ``columns`` and ``rows`` for
    the grid schemas, ``section_pages`` for perfect binding, ``sides`` for
    step and repeat.
    """
    # Imported here rather than at module scope so that building and checking
    # a plan costs nothing but this module: the renderer pulls in pikepdf's
    # compiled extension, and the ordering logic has no use for it.
    from .render import Renderer  # pylint: disable=import-outside-toplevel

    opened = _open(source)
    try:
        fit_to_form = isinstance(sheet, str) and sheet.strip().lower() == FIT_SHEET
        machine = get_press(press) if isinstance(press, str) else press
        if not fit_to_form:
            sheet_size = paper(sheet) if sheet is not None else machine.sheet
            machine.check_sheet(sheet_size)
        if page not in PAGE_CHOICES:
            raise ImposeError(
                f"Unknown page {page!r}; use {' or '.join(PAGE_CHOICES)}."
            )
        boxes = source_boxes(opened)

        gaps = _gutters(default_gutter(schema) if gutters is None else gutters)
        bleed_insets = boxes.bleed_insets.capped(length(bleed))
        allowance = max(
            marks.reach if marks else 0.0,
            bleed_insets.left,
            bleed_insets.right,
            bleed_insets.bottom,
            bleed_insets.top,
        )
        chose_turned = False
        if schema not in _FIXED_GRID and not (
            options.get("columns") or options.get("rows")
        ):
            columns, rows, chose_turned = choose_grid(
                boxes.trim_size,
                machine,
                sheet_size,
                gutters=gaps,
                allowance=allowance,
                # Step and repeat makes one sheet per item whatever the grid,
                # so nothing is being divided and denser is simply better. The
                # schemas that spread a document across the cells are weighed
                # against the page count instead.
                quantity=None if schema == "steprepeat" else len(opened.pages),
            )
            options["columns"], options["rows"] = columns, rows

        plan = build_plan(schema, len(opened.pages), **options)
        plan.validate(exhaustive=schema != "steprepeat")
        if fit_to_form:
            machine = _form_press(
                boxes.trim_size, plan, gutters=gaps, allowance=allowance
            )
            sheet_size = machine.sheet
        elif page == "imageable":
            # The page becomes the printable area itself. Nothing about the
            # layout changes -- the form still sits where it sat -- but the
            # margin the press cannot reach is no longer part of the file, so
            # a form that fits the page is a form that runs.
            sheet_size = machine.imageable_area(sheet_size).size
            machine = Press(
                name=machine.name,
                sheet=sheet_size,
                margins=Insets(),
                description=f"{machine.name} imageable area",
            )
        if chose_turned and orientation == "auto":
            orientation = "turned"

        style = marks
        plan, layouts = _fit(
            plan,
            schema=schema,
            orientation=orientation,
            boxes=boxes,
            bleed=bleed_insets,
            gutters=gaps,
            press=machine,
            sheet=sheet_size,
            allowance=allowance,
            creep=_creep_table(
                schema, length(paper_caliper), options.get("section_pages", 4)
            ),
        )
        renderer = Renderer(style=style)
        turned = any(layout.turned for layout in layouts)
        for layout in layouts:
            targets, patches = (
                furniture(
                    layout.trim_bounds,
                    layout.imageable,
                    style=style,
                    bar=colour_bar,
                    targets=registration,
                )
                if style and (registration or colour_bar)
                else ([], [])
            )
            renderer.add(
                layout,
                opened,
                marks=_marks(layout, plan, style),
                targets=targets,
                bar=patches,
                source_rotation=boxes.rotation,
            )
        identity = renderer.carry_over(opened)
        renderer.save(output)
        warnings = _warnings(plan, schema, max_nested_sheets)

        return Result(
            plan=plan,
            sheets=plan.sheets,
            surfaces=len(plan),
            sheet_size=sheet_size,
            trim_size=boxes.trim_size,
            press=machine.name,
            turned=turned,
            pdfx=identity.version,
            warnings=warnings,
        )
    finally:
        if opened is not source:
            opened.close()


def _candidates(plan: Plan, schema: str, orientation: str) -> list[Plan]:
    """The page orientations worth trying, in order of preference."""
    if orientation == "upright":
        return [plan]
    if orientation == "turned":
        return [plan.turned()]
    if orientation != "auto":
        raise ImposeError(
            f"Unknown orientation {orientation!r}; use auto, upright, or turned."
        )
    if schema in _BINDING_EDGE_MATTERS:
        return [plan]
    return [plan, plan.turned()]


def _fit(  # pylint: disable=too-many-arguments
    plan: Plan,
    *,
    schema: str,
    orientation: str,
    boxes: PageBoxes,
    bleed: Insets,
    gutters: Gutters,
    press: Press,
    sheet: Size,
    allowance: float,
    creep: Callable[[int], float] = lambda _sheet: 0.0,
) -> tuple[Plan, list]:
    """Lay every surface out, turning the pages if that is what fits."""
    failure: ImposeError | None = None
    for candidate in _candidates(plan, schema, orientation):
        try:
            layouts = [
                lay_out(
                    surface,
                    columns=candidate.columns,
                    rows=candidate.rows,
                    trim=boxes.trim_size,
                    trim_origin=boxes.trim,
                    bleed=bleed,
                    gutters=gutters,
                    press=press,
                    sheet=sheet,
                    mark_allowance=allowance,
                    creep=creep(surface.sheet),
                    fold_columns=candidate.fold_columns,
                )
                for surface in candidate
            ]
        except ImposeError as error:
            failure = error
            continue
        return candidate, layouts
    raise failure  # every orientation was tried and none fitted


def _form_press(trim: Size, plan: Plan, *, gutters: Gutters, allowance: float) -> Press:
    """A press whose sheet is exactly the form, with no margin anywhere.

    Used for the first pass of a two-stage job: impose the signature onto its
    own outer edge, then feed that to a second imposition that puts two or four
    of them on real paper. The output is a form, not something to run.
    """
    width = (
        plan.columns * trim.width
        + (plan.columns - 1) * gutters.horizontal
        + 2 * allowance
    )
    height = (
        plan.rows * trim.height + (plan.rows - 1) * gutters.vertical + 2 * allowance
    )
    return Press(
        name="form",
        sheet=Size(width, height),
        margins=Insets(),
        description="The imposed form itself, for a second pass.",
    )


def _creep_table(
    schema: str, caliper: float, section_pages: int
) -> Callable[[int], float]:
    """How far sheet *n*'s image slides toward the spine.

    A sheet's fold is displaced by the thickness of everything wrapping it, so
    the shift is its depth in the nest times the caliper. Depth restarts with
    each section of a perfect-bound book, since sections are gathered rather
    than nested, and the outermost sheet of any nest does not creep at all.
    """
    if caliper <= 0 or schema not in ("saddle", "perfect"):
        return lambda sheet: 0.0
    if schema == "saddle":
        return lambda sheet: sheet * caliper
    per_section = max(1, section_pages // saddle.PAGES_PER_SHEET)
    return lambda sheet: (sheet % per_section) * caliper


def _warnings(plan: Plan, schema: str, max_nested_sheets: int) -> tuple[str, ...]:
    """Things worth saying about a job that is otherwise imposable."""
    found = []
    if schema == "saddle":
        warning = saddle.nesting_warning(plan.sheets, max_nested_sheets)
        if warning:
            found.append(warning)
    return tuple(found)


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


__all__ = [
    "Result",
    "SCHEMAS",
    "Measurement",
    "impose_document",
    "build_plan",
    "measure",
    "repeating_unit",
    "source_boxes",
]
