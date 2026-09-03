# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

"""The `impose` command.

Deliberately thin. Everything it does is available from :mod:`impose.job`, and
nothing decided here should be unavailable to a caller using the library. Its
work is turning words into the arguments that module already takes, and turning
failures back into a sentence rather than a traceback.

Each schema is a subcommand, so the options that only make sense for one of
them -- section size for perfect binding, sidedness for step and repeat --
appear
only where they apply.
"""

from __future__ import annotations

import argparse
import dataclasses
import pathlib
import sys
from collections.abc import Sequence

from . import ImposeError, __version__
from .fit import DEFAULT_GUTTER, arrangements, compare
from .geometry import Size
from .job import (
    DEFAULT_BLEED,
    SCHEMAS,
    build_plan,
    impose_document,
    measure,
    repeating_unit,
    source_boxes,
)
from .marks import MarkStyle
from .press import get as get_press
from .press import press_names
from .schemas.saddle import MAX_NESTED_SHEETS as SADDLE_NESTING_LIMIT
from .units import format_mm, length, paper

#: Schemas whose grid the operator chooses.
_GRID_SCHEMAS = ("nup", "cutstack", "steprepeat")

#: Schemas that repeat a two-page spread rather than a single page.
_SPREAD_SCHEMAS = ("saddle", "perfect")


def _grid(text: str) -> tuple[int, int]:
    """Parse ``COLUMNSxROWS``.

    >>> _grid("4x2")
    (4, 2)
    """
    try:
        columns, rows = (int(part) for part in text.lower().split("x"))
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"Expected COLUMNSxROWS, such as 4x2; got {text!r}."
        ) from None
    if columns < 1 or rows < 1:
        raise argparse.ArgumentTypeError(f"A grid must be at least 1x1; got {text!r}.")
    return (columns, rows)


def _length(text: str) -> float:
    """Parse a length, reporting the units we accept if it will not parse."""
    try:
        return length(text)
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from None


def _default_output(source: pathlib.Path) -> pathlib.Path:
    """`book.pdf` becomes `book-imposed.pdf`, beside the original."""
    return source.with_name(f"{source.stem}-imposed{source.suffix or '.pdf'}")


def _add_mark_options(parser: argparse.ArgumentParser) -> None:
    """Options describing the marks, shared by imposing and by `fit`.

    `fit` needs them because the room the marks reserve is exactly the room the
    artwork does not get, and answering how many fit without knowing that is
    answering a different question.
    """
    parser.add_argument(
        "--marks",
        choices=("registration", "black", "none"),
        default="registration",
        help="Colour for cut and fold marks. registration prints on every "
        "plate; black is K only, for digital presses. Default: %(default)s.",
    )
    parser.add_argument(
        "--mark-offset",
        type=_length,
        metavar="LENGTH",
        help="Gap between the trim and the start of a mark. Default: 2mm.",
    )
    parser.add_argument(
        "--mark-length",
        type=_length,
        metavar="LENGTH",
        help="How long each mark is. Default: 3mm.",
    )
    parser.add_argument(
        "--mark-width",
        type=_length,
        metavar="LENGTH",
        help="Stroke width of marks. Default: 0.25pt.",
    )


def _mark_reach(args: argparse.Namespace) -> float:
    """How far the marks described by *args* reach past the trim."""
    if args.marks == "none":
        return 0.0
    default = MarkStyle()
    return MarkStyle(
        offset=args.mark_offset if args.mark_offset is not None else default.offset,
        length=args.mark_length if args.mark_length is not None else default.length,
    ).reach


def _common(parser: argparse.ArgumentParser) -> None:
    """Options every schema takes."""
    parser.add_argument("input", type=pathlib.Path, help="PDF to impose.")
    parser.add_argument(
        "-o",
        "--output",
        type=pathlib.Path,
        help="Where to write. Default: the input with -imposed appended.",
    )
    parser.add_argument(
        "--press",
        default="indigo-5000",
        metavar="NAME",
        help=f"Press profile. One of: {', '.join(press_names())}. "
        f"Default: %(default)s.",
    )
    parser.add_argument(
        "--sheet",
        metavar="SIZE",
        help="Sheet to run, if smaller than the press maximum. A name such "
        "as SRA3, WIDTHxHEIGHT such as 320mmx450mm, or `fit` for a sheet "
        "exactly the size of the form -- the first pass of a two-stage job, "
        "whose output is imposed again rather than run.",
    )
    parser.add_argument(
        "--gutters",
        "--gutter",
        dest="gutters",
        type=_length,
        default=None,
        metavar="LENGTH",
        help="Space between pages, for the knife. Defaults to 4mm where the "
        "sheet will be cut apart, and to none between the two halves of a "
        "folded spread, which must meet at the fold.",
    )
    parser.add_argument(
        "--page",
        choices=("imageable", "sheet"),
        default="imageable",
        help="What the output page is. imageable is the area the press can "
        "print, so a form that fits the page is a form that runs; sheet is "
        "the physical sheet with its unprintable border. Default: %(default)s.",
    )
    parser.add_argument(
        "--bleed",
        type=_length,
        default=_length(DEFAULT_BLEED),
        metavar="LENGTH",
        help="The most bleed to place. This caps what the artwork brought "
        "rather than asking for it: 5 mm is shaved to this, 1 mm stays 1 mm, "
        "and none stays none. Default: 2mm.",
    )
    _add_mark_options(parser)
    parser.add_argument(
        "--registration",
        action="store_true",
        help="Add a registration bullseye on each side of the form, in "
        "registration colour. Placed only where the margin has room.",
    )
    parser.add_argument(
        "--colour-bar",
        "--color-bar",
        dest="colour_bar",
        action="store_true",
        help="Add a row of process-ink patches along the tail of the sheet, "
        "for reading density on press.",
    )
    parser.add_argument(
        "--orientation",
        choices=("auto", "upright", "turned"),
        default="auto",
        help="How pages sit in their cells. auto turns them a quarter if that "
        "is what fits, except for the binding schemas, where it would move "
        "the fold. Default: %(default)s.",
    )
    parser.add_argument(
        "-n",
        "--dry-run",
        action="store_true",
        help="Show the page order and the sheet count; write nothing.",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Say nothing on success.",
    )


def build_parser() -> argparse.ArgumentParser:
    """The whole command line."""
    parser = argparse.ArgumentParser(
        prog="impose",
        description="Impose a PDF onto press sheets.",
        epilog="Sizes accept mm, cm, in, pt and pc. One inch is 72 points.",
    )
    parser.add_argument("--version", action="version", version=f"impose {__version__}")
    subcommands = parser.add_subparsers(dest="command", metavar="SCHEMA")

    descriptions = {
        "saddle": "Nested sheets, stapled through the fold. Magazines.",
        "perfect": "Sections gathered, spine milled and glued. Paperbacks.",
        "nup": "Consecutive pages on a grid, read as a stack.",
        "cutstack": "Cut into stacks that reassemble in order.",
        "steprepeat": "One item repeated to fill the sheet. Cards, labels.",
    }
    for name in SCHEMAS:
        schema = subcommands.add_parser(
            name, help=descriptions[name], description=descriptions[name]
        )
        _common(schema)
        if name in _GRID_SCHEMAS:
            schema.add_argument(
                "--up",
                type=_grid,
                default=None,
                metavar="COLUMNSxROWS",
                help="How many pages across and down. Omit it and the densest "
                "grid that fits the press is chosen for you.",
            )
        if name == "saddle":
            schema.add_argument(
                "--max-nested-sheets",
                type=int,
                default=SADDLE_NESTING_LIMIT,
                metavar="N",
                help="Sheets that can be nested and stapled through the fold. "
                "Default: %(default)s, which holds for bond and coated up to "
                "about 150 gsm. Heavier stock staples fewer.",
            )
        if name in ("saddle", "perfect"):
            schema.add_argument(
                "--paper-caliper",
                type=_length,
                default=0.0,
                metavar="LENGTH",
                help="Thickness of one sheet of the stock, which turns on "
                "creep compensation. Nested sheets push out at the fore edge, "
                "and each sheet's image is slid toward the spine to match. "
                "Measure it: a micrometer on twenty sheets, divided by twenty.",
            )
        if name == "perfect":
            schema.add_argument(
                "--section-pages",
                type=int,
                default=4,
                metavar="N",
                help="Pages per gathered section, a multiple of 4. "
                "Default: %(default)s, one folded sheet per section.",
            )
        if name == "steprepeat":
            schema.add_argument(
                "--sides",
                type=int,
                choices=(1, 2),
                default=None,
                metavar="N",
                help="Sides per item: 1 for single-sided, 2 for a front and a "
                "back. Taken from the page count when left out -- an even "
                "document is read as front-and-back pairs.",
            )

    fit = subcommands.add_parser(
        "fit",
        help="How many fit on a sheet, and what the leftovers cost.",
        description="Work out how many pieces of a given finished size fit on "
        "a press sheet, and how much of the run is wasted.",
    )
    fit.set_defaults(command="fit")
    fit.add_argument(
        "size",
        metavar="SIZE_OR_PDF",
        help="What to fit. A size -- a name such as A6, or WIDTHxHEIGHT such "
        "as 90mmx55mm -- or a PDF, whose finished size is read off its "
        "TrimBox and whose page count stands in for the quantity.",
    )
    fit.add_argument(
        "--schema",
        choices=sorted(SCHEMAS),
        default=None,
        help="Answer for the schema that would be run. The bound schemas "
        "repeat a two-page spread rather than a single page, so this changes "
        "what is being fitted. Omit it to fit the size as a flat piece.",
    )
    fit.add_argument(
        "-n",
        "--quantity",
        type=int,
        default=0,
        metavar="N",
        help="Pieces wanted. With this, the sheet count and waste are shown. "
        "Taken from the page count when a PDF and a dividing schema are "
        "given, which is what imposing that file would weigh the grid "
        "against.",
    )
    fit.add_argument(
        "--press",
        default="indigo-5000",
        metavar="NAME",
        help="Press profile. Default: %(default)s.",
    )
    fit.add_argument("--sheet", metavar="SIZE", help="Sheet, if not the maximum.")
    fit.add_argument(
        "--gutter",
        "--gutters",
        dest="gutter",
        type=_length,
        default=DEFAULT_GUTTER,
        metavar="LENGTH",
        help="Gap between pieces, for the knife. Default: 4mm.",
    )
    _add_mark_options(fit)
    fit.add_argument(
        "--bleed",
        type=_length,
        default=_length(DEFAULT_BLEED),
        metavar="LENGTH",
        help="Bleed to allow room for, capped the same way imposing caps it. "
        "Default: 2mm.",
    )
    fit.add_argument(
        "--allowance",
        type=_length,
        default=None,
        metavar="LENGTH",
        help="Room kept clear on each edge, overriding what the marks and "
        "bleed work out to. Rarely needed: give the marks and the bleed and "
        "let this follow.",
    )

    presses = subcommands.add_parser(
        "presses", help="List the press profiles.", description="List press profiles."
    )
    presses.set_defaults(command="presses")
    return parser


def _style(args: argparse.Namespace) -> MarkStyle | None:
    """The mark style the options describe, or None for no marks."""
    if args.marks == "none":
        return None
    default = MarkStyle()
    return MarkStyle(
        offset=args.mark_offset if args.mark_offset is not None else default.offset,
        length=args.mark_length if args.mark_length is not None else default.length,
        width=args.mark_width if args.mark_width is not None else default.width,
        colour=args.marks,
    )


def _schema_options(args: argparse.Namespace) -> dict:
    """Options belonging to the chosen schema."""
    options: dict = {}
    if getattr(args, "up", None) is not None:
        options["columns"], options["rows"] = args.up
    if getattr(args, "section_pages", None) is not None:
        options["section_pages"] = args.section_pages
    if getattr(args, "sides", None) is not None:
        options["sides"] = args.sides
    return options


def _list_presses(out) -> int:
    """Print every press profile, for someone choosing one."""
    for name in press_names():
        press = get_press(name)
        print(f"  {press.describe()}", file=out)
        if press.description:
            print(f"      {press.description}", file=out)
    print(
        "\n  Figures are nominal. Confirm against your machine before "
        "committing a job.",
        file=out,
    )
    return 0


def _fit_allowance(args: argparse.Namespace) -> float:
    """Room to keep clear on each edge, from the marks and the bleed.

    Layout reserves whichever of the two reaches further on an edge, not their
    sum: a 3 mm bleed and a 5 mm mark reach need 5 mm, not 8. An explicit
    --allowance overrides both.
    """
    if args.allowance is not None:
        return args.allowance
    return max(_mark_reach(args), args.bleed)


@dataclasses.dataclass(frozen=True, slots=True)
class _Subject:
    """The thing being fitted, however it was named."""

    unit: Size
    label: str
    quantity: int
    allowance: float
    #: Sheets one bound copy takes, when the subject is a bound document.
    forms: int = 0


def _fit_subject(args: argparse.Namespace) -> _Subject:
    """What to fit, from either a size or a document.

    A PDF answers two questions a typed size cannot: what the artwork's own
    bleed is, which decides how much edge has to stay clear, and how many
    pages there are to divide, which is what imposing that file would weigh
    the grid against. Step and repeat is the exception -- it makes one sheet
    per item whatever the grid, so there is nothing to divide and the page
    count is not a quantity.
    """
    schema = args.schema
    path = pathlib.Path(args.size)
    if not path.is_file():
        unit = repeating_unit(paper(args.size), schema) if schema else paper(args.size)
        return _Subject(
            unit, format_mm(unit), max(0, args.quantity), _fit_allowance(args)
        )

    measured = measure(path)
    unit = repeating_unit(measured.trim_size, schema) if schema else measured.trim_size
    # Imposing caps the artwork's bleed rather than inventing it, so a file
    # with none needs no room for any. Match that, or fit answers a question
    # the imposer is not asking.
    bleed = measured.bleed_insets.capped(args.bleed)
    allowance = (
        args.allowance
        if args.allowance is not None
        else max(_mark_reach(args), bleed.left, bleed.right, bleed.bottom, bleed.top)
    )
    quantity = args.quantity
    # The page count is a quantity only where the pages are dealt across the
    # cells. Step and repeat fills every sheet with the same item however many
    # are wanted, and a bound job's quantity is booklets ordered, which the
    # file does not say. Neither has a quantity to read off the document.
    if quantity <= 0 and schema and schema not in ("steprepeat", *_SPREAD_SCHEMAS):
        quantity = measured.pages
    label = f"{path.name}, {format_mm(unit)}"
    forms = 0
    if schema in _SPREAD_SCHEMAS:
        label += f" spread ({format_mm(measured.trim_size)} page)"
        forms = build_plan(schema, measured.pages).sheets
    return _Subject(unit, label, max(0, quantity), allowance, forms)


def _two_stage_advice(args: argparse.Namespace, arrangement) -> str:
    """How to actually get more than one bound job onto the sheet.

    The bound schemas fold, so their grid is fixed by the binding and they
    cannot simply be told to run four up. The way a shop does it is two passes:
    impose the booklet onto a sheet the size of its own form, then treat that
    form as the piece and repeat it.
    """
    source = args.size if pathlib.Path(args.size).is_file() else "FILE.pdf"
    return (
        f"{arrangement.up} booklets fit one sheet. The binding fixes the grid, "
        f"so run it in two passes:\n"
        f"    impose {args.schema} {source} --sheet fit --marks none -o forms.pdf\n"
        f"    impose steprepeat forms.pdf -o sheets.pdf\n"
        f"  The second pass chooses its own grid; it should reach the same "
        f"{arrangement.columns} × {arrangement.rows}."
    )


def _fit(args: argparse.Namespace, out) -> int:  # pylint: disable=too-many-locals
    """Answer how many fit, and what a given order wastes."""
    press = get_press(args.press)
    sheet = paper(args.sheet) if args.sheet else press.sheet
    press.check_sheet(sheet)
    area = press.imageable_area(sheet)
    subject = _fit_subject(args)
    quantity = subject.quantity

    # With no quantity there is nothing to weigh density against, so the
    # arrangements are listed as they pack. With one, they are costed and
    # ordered by what the job actually takes.
    if quantity:
        runs = compare(
            subject.unit,
            area,
            quantity,
            gutter=args.gutter,
            allowance=subject.allowance,
        )
        options = [run.arrangement for run in runs]
    else:
        runs = []
        options = arrangements(
            subject.unit, area, gutter=args.gutter, allowance=subject.allowance
        )
    if not options:
        raise ImposeError(
            f"A finished size of {format_mm(subject.unit)} does not fit the "
            f"imageable area of {press.name} ({format_mm(area.size)}) even "
            f"one up."
        )

    print(
        f"{subject.label} on {press.name}, imageable {format_mm(area.size)}",
        file=out,
    )
    for index, arrangement in enumerate(options):
        line = f"  {arrangement.describe()}"
        if quantity:
            run = runs[index]
            line += f"  ->  {run.sheets} sheet(s), {run.waste} wasted"
            if index == 0:
                line += "   <- run this"
        print(line, file=out)

    if args.schema in _SPREAD_SCHEMAS:
        if options[0].up > 1:
            print(f"\n  {_two_stage_advice(args, options[0])}", file=out)
        if subject.forms:
            print(
                f"\n  Each booklet is {subject.forms} sheet(s) of that form, "
                f"so an order of N booklets runs "
                f"{subject.forms} × ceil(N ÷ {options[0].up}) sheets.",
                file=out,
            )

    if quantity:
        advice = runs[0].advice()
        if advice:
            print(f"\n  {advice}", file=out)
        densest = max(runs, key=lambda r: r.arrangement.up)
        if densest is not runs[0]:
            print(
                f"  {densest.arrangement.up} up is denser but costs the same "
                f"{densest.sheets} sheet(s) and throws away "
                f"{densest.waste} instead of {runs[0].waste}.",
                file=out,
            )
    return 0


def _dry_run(args: argparse.Namespace, out) -> int:
    """Show the ordering and the sheet count without writing anything."""
    import pikepdf  # pylint: disable=import-outside-toplevel

    with pikepdf.open(args.input) as source:
        boxes = source_boxes(source)
        plan = build_plan(args.command, len(source.pages), **_schema_options(args))
        plan.validate(exhaustive=args.command != "steprepeat")
        print(plan.describe(), file=out)
        print(
            f"\n  {plan.pages} pages, {plan.sheets} sheet(s), "
            f"{len(plan)} surface(s); finished page "
            f"{format_mm(boxes.trim_size)}",
            file=out,
        )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command line. Returns the process exit status."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 2
    out = sys.stdout

    try:
        if args.command == "presses":
            return _list_presses(out)
        if args.command == "fit":
            return _fit(args, out)
        if not args.input.exists():
            raise ImposeError(f"No such file: {args.input}")
        if args.dry_run:
            return _dry_run(args, out)

        result = impose_document(
            args.input,
            args.output or _default_output(args.input),
            schema=args.command,
            press=args.press,
            sheet=args.sheet,
            gutters=args.gutters,
            marks=_style(args),
            orientation=args.orientation,
            max_nested_sheets=getattr(args, "max_nested_sheets", SADDLE_NESTING_LIMIT),
            paper_caliper=getattr(args, "paper_caliper", 0.0),
            bleed=args.bleed,
            page=args.page,
            registration=args.registration,
            colour_bar=args.colour_bar,
            **_schema_options(args),
        )
        if not args.quiet:
            print(result.describe(), file=out)
            print(f"wrote {args.output or _default_output(args.input)}", file=out)
        # Warnings go to stderr even when quiet: a job that will not staple is
        # not something to keep to ourselves because output was suppressed.
        for warning in result.warnings:
            print(f"impose: warning: {warning}", file=sys.stderr)
        return 0
    # ValueError as well as ImposeError: a schema rejects an impossible
    # request with one, and whichever it is, the person at the terminal asked
    # for something that cannot be done and should be told so in a sentence.
    except (ImposeError, ValueError) as error:
        print(f"impose: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
