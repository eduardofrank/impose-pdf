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
from .job import SCHEMAS, build_plan, impose_document, source_boxes
from .marks import MarkStyle
from .press import get as get_press
from .press import press_names
from .units import format_mm, length

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
                default=(2, 1),
                metavar="COLUMNSxROWS",
                help="How many pages across and down. Default: 2x1.",
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
    if hasattr(args, "up"):
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
            **_schema_options(args),
        )
        if not args.quiet:
            print(result.describe(), file=out)
            print(f"wrote {args.output or _default_output(args.input)}", file=out)
        return 0
    # ValueError as well as ImposeError: a schema rejects an impossible
    # request with one, and whichever it is, the person at the terminal asked
    # for something that cannot be done and should be told so in a sentence.
    except (ImposeError, ValueError) as error:
        print(f"impose: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
