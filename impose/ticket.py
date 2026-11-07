# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

"""A job the shop can store.

A run is otherwise a command line, and a command line is gone when the
terminal is. A quote system, a hot folder, or a press that asks again
tomorrow needs the same fields written down. This is that writing: a JSON
document whose keys are the arguments :func:`impose.job.impose_document`
already takes, so imposing the file and imposing the command are one job.

Paths in the file are relative to the file itself. A job moved with its
artwork still finds the artwork.

A job that names no source is a folder's standing policy rather than one
job: the file to impose and where it goes are given to :func:`run` per file,
which is what a hot folder has and a stored document cannot.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

from . import ImposeError
from .cover import impose_cover
from .destination import writing
from .geometry import Size
from .job import SCHEMAS, impose_document
from .layout import Gutters
from .marks import MarkStyle
from .press import EDGES, Press
from .press import resolve as resolve_press
from .units import length, to_mm

#: The only edition of the file this version of impose reads.
VERSION = 1

#: Options a run may make but a job file may not. Taking a finished size from
#: the MediaBox is a judgement about one file in front of somebody, not a
#: standing instruction: a job that carried it would go on assuming a size for
#: every file a hot folder ever hands it, including the one that arrives next
#: year with its boxes dropped by a converter. Reading past a rebuilt page
#: count is the same judgement and worse as a standing one -- stored, it means
#: "impose whatever survived the copy", for every file, for ever.
_PER_RUN = frozenset({"trim_from", "damaged", "overwrite"})

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
        "lay",
        "max_nested_sheets",
        "paper_caliper",
        "bleed",
        "expect_size",
        "registration",
        "colour_bar",
        "cut",
        "cut_name",
        "strip",
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

_PATHS = ("source", "output", "proof", "artwork", "strip")


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


def add_command(subcommands) -> argparse.ArgumentParser:
    """The ``run`` command: impose a job file.

    Returned so that the caller can add the options a job file may not carry
    -- see :data:`_PER_RUN`. Running a stored job is still a run, and those
    three are a run's to make.
    """
    command = subcommands.add_parser(
        "run",
        help="Impose a stored job.",
        description="Impose a job file. Paths in the file are relative to "
        "the file, so a folder of jobs can move with its artwork.",
    )
    command.add_argument("job", type=pathlib.Path, help="The job file, JSON.")
    # A folder's policy is a job with no source: the schema, the press, the
    # size it expects, and nothing about which file. The watcher has the
    # file, so it says so here, and one job file serves every file that
    # lands. Given both, the command line is the file in front of somebody
    # and wins; paths here are relative to the terminal, where paths in the
    # job are relative to the job.
    command.add_argument(
        "source",
        nargs="?",
        type=pathlib.Path,
        help="The PDF to impose, if the job does not name one, or instead "
        "of the one it names.",
    )
    command.add_argument(
        "-o",
        "--output",
        type=pathlib.Path,
        help="Where to write, instead of what the job says. Default: what "
        "the job says, or the source with -imposed appended.",
    )
    command.add_argument(
        "--proof",
        type=pathlib.Path,
        metavar="FILE",
        help="Where to write the proof, instead of what the job says.",
    )
    command.add_argument(
        "-n",
        "--dry-run",
        action="store_true",
        help="Show the ordering and write no press file. Overrides the file.",
    )
    command.set_defaults(command="run")
    return command


def recorded(args, options: dict, output, proof) -> dict:
    """The job a command just described, ready to store.

    Everything except the options that are a run's to make and not a file's:
    see :data:`_PER_RUN`. Dropping one here is why :data:`_KEYS` has no name
    for it, so a job file that names it is refused rather than obeyed.
    """
    job = {
        key: value
        for key, value in options.items()
        if value is not None and key != "collation" and key not in _PER_RUN
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


def load(path: str | pathlib.Path, *, needs_source: bool = True) -> dict:
    """Read a job file. Paths come back absolute, beside the file.

    *needs_source* is false when the caller is supplying the file itself, as
    a watched folder does: the job is then a policy, and a policy that named
    a source would impose that one file for ever.
    """
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
    if "schema" not in data:
        raise ImposeError(f"{file} needs a schema: it is what the job is.")
    if needs_source and "source" not in data:
        raise ImposeError(
            f"{file} names no source, so it is a folder's policy rather than "
            f"a job. Name the file to impose on the command line."
        )
    if data["schema"] not in SCHEMAS:
        raise ImposeError(
            f"Unknown schema {data['schema']!r}. Known schemas: "
            f"{', '.join(sorted(SCHEMAS))}."
        )
    if data.get("press") is not None:
        # Read the press now, so a job naming a machine it cannot describe
        # fails on opening the file rather than part-way through a run.
        resolve_press(data["press"])
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
    with writing(path) as target:
        pathlib.Path(target).write_text(
            json.dumps(body, indent=2) + "\n", encoding="utf-8"
        )


def run(  # pylint: disable=too-many-arguments
    path: str | pathlib.Path,
    out,
    *,
    source=None,
    output=None,
    proof=None,
    trim_from: str | None = None,
    damaged: str | None = None,
    plan_only: bool = False,
    overwrite: bool = False,
):
    """Impose the job in *path*. Returns the same result imposing it would.

    *source*, *output* and *proof* are the three facts about one file, and a
    caller that has them overrides whatever the job stored. That is what lets
    one job file be a folder's policy: the folder's watcher knows which file
    arrived and the job knows everything else. A job with no source needs
    one here.

    *trim_from* and *damaged* are the judgements a job file may not store,
    and this is a run, so it may make them.
    """
    job = load(path, needs_source=source is None)
    job.pop("version", None)
    # The two options a job file is refused for naming, put in by hand
    # because this is a run and they are a run's to make. A folder of office
    # exports is a stored policy and `--trim-from mediabox`, and there is
    # nowhere else for that to be said.
    if trim_from is not None:
        job["trim_from"] = trim_from
    if damaged is not None:
        job["damaged"] = damaged
    dry = plan_only or bool(job.pop("dry_run", False))
    source, output, proof = _paths(job, source, output, proof)
    schema = _schema(job)
    _expand_up(job)
    # Back into the job rather than into variables of their own: both are
    # arguments the schemas take, and everything left in `job` is handed over
    # as keyword arguments anyway.
    job["marks"] = _marks(job.pop("marks", "registration"))
    job["gutters"] = _gutters(job.pop("gutters", None))
    if schema == "cover":
        return _run_cover(
            job, source, output, proof, dry=dry, out=out, overwrite=overwrite
        )
    result = impose_document(
        source,
        output,
        schema=schema,
        proof=proof,
        plan_only=dry,
        overwrite=overwrite,
        **job,
    )
    _report(out, result, output, proof, dry=dry)
    return result


def _schema(job: dict) -> str:
    """The schema to impose, with the sidedness it implies folded in.

    Sidedness is one question in a job file and two in the schemas: step and
    repeat counts the sides of an item, and the schemas that deal a document
    across the cells count the sides of the sheet. And a perfect-bound book
    whose sections are folded is the signature schema under another name,
    which is what ``folded`` says.
    """
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
        return "signature"
    return schema


def _run_cover(  # pylint: disable=too-many-arguments
    job, source, output, proof, *, dry, out, overwrite=False
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
    cover, result = impose_cover(
        source,
        output,
        paper_caliper=job.pop("paper_caliper"),
        hinge=hinge,
        glue=job.pop("glue", 0) or 0,
        section_pages=job.pop("section_pages", 4),
        artwork=job.pop("artwork", None),
        bleed=job.pop("bleed", "2mm"),
        proof=proof,
        plan_only=dry,
        overwrite=overwrite,
        **job,
    )
    print(cover.describe(), file=out)
    _report(out, result, output, proof, dry=dry)
    return result


def _paths(job: dict, source, output, proof):
    """The three facts about one file: the run's, or else the job's.

    All three are taken out of *job* whether or not they are being
    overridden, because what is left in it is handed to the schema as
    keyword arguments and a key that stayed behind would arrive twice.
    """
    stored_source = job.pop("source", None)
    stored_output = job.pop("output", None)
    stored_proof = job.pop("proof", None)
    source = stored_source if source is None else source
    return (
        source,
        output or stored_output or _beside(source),
        stored_proof if proof is None else proof,
    )


def _report(out, result, output, proof, *, dry: bool) -> None:
    """Say what the job did, in the same words the command line uses."""
    if dry:
        print(result.plan.describe(), file=out)
    print(f"  {result.describe()}", file=out)
    if not dry:
        print(f"wrote {output}", file=out)
    if proof is not None:
        print(f"proof {proof}", file=out)
    for warning in result.warnings:
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


def _mm(points: float) -> str:
    """A length in millimetres, as a job file writes one."""
    return f"{to_mm(points):g}mm"


def _plain(value):
    """A value JSON can store. A mark style becomes its four numbers."""
    if isinstance(value, Press):
        # Stored as the millimetres an operator would read off the machine,
        # not as the points we work in: a job file is a document a person
        # checks, and it has to read the press back the way it was given.
        return {
            "name": value.name,
            "sheet": f"{_mm(value.sheet.width)}x{_mm(value.sheet.height)}",
            "margins": {edge: _mm(getattr(value.margins, edge)) for edge in EDGES},
            "gripper": value.gripper,
        }
    if isinstance(value, Size):
        # In the millimetres an operator would check, like the press sheet
        # above: a job file is a document somebody reads.
        return f"{_mm(value.width)}x{_mm(value.height)}"
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
