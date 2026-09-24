# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

"""A job the shop can store.

A run is otherwise a command line, and a command line is gone when the
terminal is. A quote system, a hot folder, or a press that asks again
tomorrow needs the same fields written down. This is that writing: a JSON
document whose keys are the arguments :func:`impose.job.impose_document`
already takes, so imposing the file and imposing the command are one job.

Paths in the file are relative to the file itself. A job moved with its
artwork still finds the artwork.
"""

from __future__ import annotations

import json
import pathlib
import sys

from . import ImposeError
from .cover import impose_cover
from .job import SCHEMAS, impose_document
from .layout import Gutters
from .marks import MarkStyle
from .units import length

#: The only edition of the file this version of impose reads.
VERSION = 1

#: Keys a job may carry. Anything else is a mistake to name, not to ignore.
_KEYS = frozenset(
    {
        "version",
        "source",
        "output",
        "schema",
        "press",
        "sheet",
        "gutters",
        "marks",
        "orientation",
        "max_nested_sheets",
        "paper_caliper",
        "bleed",
        "registration",
        "colour_bar",
        "page",
        "fold",
        "slug",
        "slug_size",
        "repeat",
        "proof",
        "grind",
        "lap",
        "collation",
        "columns",
        "rows",
        "section_pages",
        "sides",
        "flip",
        "style",
        "duplex",
        "hinge",
        "cover_caliper",
        "glue",
        "artwork",
        "dry_run",
        "up",
        "folded",
    }
)

_PATHS = ("source", "output", "proof", "artwork")


def schema_options(args, schema: str | None = None) -> dict:
    """Options belonging to the chosen schema.

    Sidedness is one question at the terminal and two in the schemas: step and
    repeat counts the sides of an item, and the schemas that deal a document
    across the cells count the sides of the sheet.
    """
    options: dict = {}
    if getattr(args, "up", None) is not None:
        options["columns"], options["rows"] = args.up
    if getattr(args, "section_pages", None) is not None:
        options["section_pages"] = args.section_pages
    if getattr(args, "flip", None) is not None:
        options["flip"] = args.flip
    if getattr(args, "fold_style", None) is not None:
        options["style"] = args.fold_style
    sides = getattr(args, "sides", None)
    if sides is not None:
        if (schema or args.command) == "steprepeat":
            options["sides"] = sides
        else:
            options["duplex"] = sides == 2
    return options


def add_command(subcommands) -> None:
    """The ``run`` command: impose a job file."""
    command = subcommands.add_parser(
        "run",
        help="Impose a stored job.",
        description="Impose a job file. Paths in the file are relative to "
        "the file, so a folder of jobs can move with its artwork.",
    )
    command.add_argument("job", type=pathlib.Path, help="The job file, JSON.")
    command.add_argument(
        "-n",
        "--dry-run",
        action="store_true",
        help="Show the ordering and write no press file. Overrides the file.",
    )
    command.set_defaults(command="run")


def recorded(args, options: dict, output, proof) -> dict:
    """The job a command just described, ready to store."""
    job = {
        key: value
        for key, value in options.items()
        if value is not None and key != "collation"
    }
    if options.get("collation") is False:
        job["collation"] = False
    job["source"] = args.input
    job["output"] = output
    if proof is not None:
        job["proof"] = proof
    for key in ("hinge", "cover_caliper", "glue", "artwork"):
        value = getattr(args, key, None)
        if value:
            job[key] = value
    return job


def load(path: str | pathlib.Path) -> dict:
    """Read a job file. Paths come back absolute, beside the file."""
    file = pathlib.Path(path)
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ImposeError(f"{file} is not a job file: {error}") from error
    except OSError as error:
        raise ImposeError(f"Cannot open {file}: {error}") from error
    if not isinstance(data, dict):
        raise ImposeError(f"{file} is not a job file: it should be one object.")
    unknown = sorted(set(data) - _KEYS)
    if unknown:
        raise ImposeError(f"{file} has {unknown[0]!r}, which is not a field of a job.")
    version = data.get("version", VERSION)
    if version != VERSION:
        raise ImposeError(
            f"{file} is job version {version}. This impose reads version {VERSION}."
        )
    if "source" not in data or "schema" not in data:
        raise ImposeError(f"{file} needs a source and a schema.")
    if data["schema"] not in SCHEMAS:
        raise ImposeError(
            f"Unknown schema {data['schema']!r}. Known schemas: "
            f"{', '.join(sorted(SCHEMAS))}."
        )
    base = file.parent
    job = dict(data)
    for key in _PATHS:
        if job.get(key):
            found = pathlib.Path(job[key])
            job[key] = found if found.is_absolute() else base / found
    return job


def dump(path: str | pathlib.Path, job: dict) -> None:
    """Write *job* as JSON. Paths are stored as given."""
    body = {"version": VERSION}
    for key in sorted(job):
        if key == "version" or job[key] is None:
            continue
        body[key] = _plain(job[key])
    pathlib.Path(path).write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")


def run(path: str | pathlib.Path, out, *, plan_only: bool = False):
    """Impose the job in *path*. Returns the same result imposing it would."""
    job = load(path)
    job.pop("version", None)
    dry = plan_only or bool(job.pop("dry_run", False))
    source = job.pop("source")
    output = job.pop("output", None) or _beside(source)
    proof = job.pop("proof", None)
    schema = job.pop("schema")
    sides = job.pop("sides", None)
    if sides is not None:
        if schema == "steprepeat":
            job["sides"] = sides
        else:
            job["duplex"] = sides == 2
    if job.pop("folded", False):
        if schema not in ("perfect", "signature"):
            raise ImposeError(
                "Folding a section into one sheet is how a perfect-bound "
                f"book is made. The {schema} schema does not gather sections."
            )
        schema = "signature"
    _expand_up(job)
    marks = _marks(job.pop("marks", "registration"))
    gutters = _gutters(job.pop("gutters", None))
    if schema == "cover":
        return _run_cover(
            job, source, output, proof, marks=marks, gutters=gutters, dry=dry, out=out
        )
    result = impose_document(
        source,
        output,
        schema=schema,
        marks=marks,
        gutters=gutters,
        proof=proof,
        plan_only=dry,
        **job,
    )
    _report(out, result, output, proof, dry=dry)
    return result


def _run_cover(  # pylint: disable=too-many-arguments
    job, source, output, proof, *, marks, gutters, dry, out
):
    """A cover job is the text block plus the gauge, not the flat itself."""
    if "paper_caliper" not in job:
        raise ImposeError(
            "A cover spine is the thickness of the text block, and that needs "
            "the gauge of the paper it is printed on. The job needs "
            "paper_caliper, measured on the stock."
        )
    hinge = job.pop("hinge", None)
    if hinge is None:
        hinge = job.pop("cover_caliper", 0) or 0
    else:
        job.pop("cover_caliper", None)
    cover, result, warnings = impose_cover(
        source,
        output,
        paper_caliper=job.pop("paper_caliper"),
        hinge=hinge,
        glue=job.pop("glue", 0) or 0,
        section_pages=job.pop("section_pages", 4),
        artwork=job.pop("artwork", None),
        bleed=job.pop("bleed", "2mm"),
        marks=marks,
        gutters=gutters,
        proof=proof,
        plan_only=dry,
        **job,
    )
    print(cover.describe(), file=out)
    for warning in (*warnings, *result.warnings):
        print(f"impose: warning: {warning}", file=sys.stderr)
    _report(out, result, output, proof, dry=dry, warnings=())
    return result


def _report(  # pylint: disable=too-many-arguments
    out, result, output, proof, *, dry: bool, warnings=None
) -> None:
    """Say what the job did, in the same words the command line uses."""
    if dry:
        print(result.plan.describe(), file=out)
    print(f"  {result.describe()}", file=out)
    if not dry:
        print(f"wrote {output}", file=out)
    if proof is not None:
        print(f"proof {proof}", file=out)
    pending = result.warnings if warnings is None else warnings
    for warning in pending:
        print(f"impose: warning: {warning}", file=sys.stderr)


def _expand_up(job: dict) -> None:
    """``up`` is columns and rows, which is how the schemas take a grid."""
    grid = job.pop("up", None)
    if grid is None:
        return
    if "columns" in job or "rows" in job:
        raise ImposeError("A job can give up, or columns and rows, not both.")
    text = str(grid)
    if "x" not in text:
        raise ImposeError(f"up should be COLUMNSxROWS, got {grid!r}.")
    across, down = text.lower().split("x", 1)
    job["columns"] = int(across)
    job["rows"] = int(down)


def _marks(value):
    """A mark style from ``"black"``, ``"none"``, or a small object."""
    if value in (None, "registration"):
        return MarkStyle()
    if value == "none":
        return None
    if isinstance(value, str):
        return MarkStyle(colour=value)
    if not isinstance(value, dict):
        raise ImposeError(f"marks should name a colour, got {value!r}.")
    default = MarkStyle()
    return MarkStyle(
        colour=value.get("colour", default.colour),
        offset=length(value.get("offset", default.offset)),
        length=length(value.get("length", default.length)),
        width=length(value.get("width", default.width)),
    )


def _gutters(value):
    """A gap from a length, or horizontal and vertical separately."""
    if value is None:
        return None
    if isinstance(value, dict):
        return Gutters(
            length(value.get("horizontal", 0)),
            length(value.get("vertical", 0)),
        )
    return value


def _beside(source: pathlib.Path) -> pathlib.Path:
    """``book.pdf`` becomes ``book-imposed.pdf``, beside the original."""
    return source.with_name(f"{source.stem}-imposed{source.suffix or '.pdf'}")


def _plain(value):
    """A value JSON can store. A mark style becomes its four numbers."""
    if isinstance(value, MarkStyle):
        return {
            "colour": value.colour,
            "offset": value.offset,
            "length": value.length,
            "width": value.width,
        }
    if isinstance(value, pathlib.Path):
        return str(value)
    return value
