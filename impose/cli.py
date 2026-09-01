# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

"""The `impose` command.

Deliberately thin. Everything it does is available from :mod:`impose.job`, and
nothing decided here should be unavailable to a caller using the library. Its
work is turning words into the arguments that module already takes, and turning
failures back into a sentence rather than a traceback.

Each schema is a subcommand, so the options that only make sense for one of
them -- section size for perfect binding, copies for step and repeat -- appear
only where they apply.
"""

from __future__ import annotations

import argparse
import pathlib
import sys
from collections.abc import Sequence

from . import ImposeError, __version__
from .fit import DEFAULT_GUTTER, arrangements, compare
from .job import SCHEMAS, build_plan, impose_document, source_boxes
from .marks import MarkStyle
from .press import get as get_press
from .press import press_names
from .schemas.saddle import MAX_NESTED_SHEETS as SADDLE_NESTING_LIMIT
from .units import format_mm, length, paper

#: Schemas whose grid the operator chooses.
_GRID_SCHEMAS = ("nup", "cutstack", "steprepeat")


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
        help="Sheet to run, if smaller than the press maximum. A name such as "
        "SRA3, or WIDTHxHEIGHT such as 320mmx450mm.",
    )
    parser.add_argument(
        "--gutters",
        "--gutter",
        dest="gutters",
        type=_length,
        default=0.0,
        metavar="LENGTH",
        help="Space between pages, for the knife. Default: none.",
    )
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
        help="Gap between the trim and the start of a mark. Default: 3mm.",
    )
    parser.add_argument(
        "--mark-length",
        type=_length,
        metavar="LENGTH",
        help="How long each mark is. Default: 5mm.",
    )
    parser.add_argument(
        "--mark-width",
        type=_length,
        metavar="LENGTH",
        help="Stroke width of marks. Default: 0.25pt.",
    )
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
                "--copies",
                type=int,
                metavar="N",
                help="Finished pieces wanted. Default: one sheet's worth.",
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
        help="Finished size: a name such as A6, or WIDTHxHEIGHT such " "as 90mmx55mm.",
    )
    fit.add_argument(
        "-n",
        "--quantity",
        type=int,
        default=0,
        metavar="N",
        help="Pieces wanted. With this, the sheet count and waste are shown.",
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
    fit.add_argument(
        "--allowance",
        type=_length,
        default=5 * 72 / 25.4,
        metavar="LENGTH",
        help="Room kept clear on each edge for marks and bleed. Default: 5mm.",
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
    if getattr(args, "copies", None) is not None:
        options["copies"] = args.copies
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


def _fit(args: argparse.Namespace, out) -> int:
    """Answer how many fit, and what a given order wastes."""
    press = get_press(args.press)
    sheet = paper(args.sheet) if args.sheet else press.sheet
    press.check_sheet(sheet)
    area = press.imageable_area(sheet)
    trim = paper(args.size)
    quantity = max(0, args.quantity)

    # With no quantity there is nothing to weigh density against, so the
    # arrangements are listed as they pack. With one, they are costed and
    # ordered by what the job actually takes.
    if quantity:
        runs = compare(
            trim, area, quantity, gutter=args.gutter, allowance=args.allowance
        )
        options = [run.arrangement for run in runs]
    else:
        runs = []
        options = arrangements(trim, area, gutter=args.gutter, allowance=args.allowance)
    if not options:
        raise ImposeError(
            f"A finished size of {format_mm(trim)} does not fit the imageable "
            f"area of {press.name} ({format_mm(area.size)}) even one up."
        )

    print(
        f"{format_mm(trim)} on {press.name}, imageable {format_mm(area.size)}",
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
