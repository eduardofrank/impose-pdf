# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

"""Several complete bound copies on one press sheet.

A bound form is smaller than the press sheet -- a half-letter saddle spread is
279 x 216 mm on a 310 x 450 mm area, using 43 per cent of it -- so the room
left over will hold another whole copy of the same book. Cut the sheet apart
and there are two identical folded sets, one for each copy, with no collating
to get wrong.

It is done as two passes: the booklet is imposed onto a sheet exactly the size
of its own form, and that form is then stepped and repeated onto real paper.
One wider grid would be the obvious alternative and is the wrong one. The
form's own folds butt and the cut between copies does not, so a single pass
would need a gutter that differs from boundary to boundary rather than per
axis. Two passes also mean the output is what the shop already runs by hand,
through the code that has always produced it -- checked, and identical.

The intermediate never reaches the disk. That is not only tidiness: an unmarked
form looks like a finished imposition and is a trap if someone sends it to
press by mistake.
"""

from __future__ import annotations

import dataclasses
import io
import pathlib
from typing import IO

import pikepdf

from . import ImposeError
from .press import FIT_SHEET
from .units import format_mm

#: Schemas a repeat means something for. A bound job makes a form that is
#: smaller than the sheet, so several complete copies can share one. The flat
#: schemas already fill the sheet: step and repeat repeats by definition, and
#: n-up and cut and stack divide a document across the cells rather than
#: copying it.
BOUND_SCHEMAS = frozenset({"saddle", "perfect", "signature"})

#: Options belonging to the booklet rather than to the sheet it is copied onto.
#: Everything else -- the press, the marks, the furniture -- describes the
#: press sheet and belongs to the second pass.
_BOOKLET_OPTIONS = frozenset(
    {
        "schema",
        "gutters",
        "orientation",
        "max_nested_sheets",
        "paper_caliper",
        "bleed",
        "fold",
        "columns",
        "rows",
        "section_pages",
        "style",
        "flip",
    }
)


def repeated(
    source: pikepdf.Pdf | str | pathlib.Path,
    output: str | pathlib.Path | IO[bytes],
    repeat: str | int | tuple[int, int],
    options: dict,
    *,
    impose,
):
    """Impose a bound job several complete copies to a press sheet.

    This is the two-stage route run for you: the booklet is imposed onto a
    sheet exactly the size of its own form, and that form is then stepped and
    repeated onto real paper. Doing it as two passes rather than as one wider
    grid is deliberate. The form's own folds butt and the cut between copies
    does not, so one pass would need a gutter that differs from boundary to
    boundary; and this way the output is what the shop already runs by hand,
    through the same code that has always produced it.

    *impose* is the imposing function, handed in rather than imported, so that
    this module depends on nothing that depends on it.
    """
    schema = options.get("schema", "saddle")
    if schema not in BOUND_SCHEMAS:
        raise ImposeError(
            f"Only a bound job can be repeated, and {schema} is not one. It "
            f"already fills the sheet: {', '.join(sorted(BOUND_SCHEMAS))} "
            f"make a form smaller than the sheet, which is what leaves room "
            f"for a second copy."
        )

    booklet = {key: value for key, value in options.items() if key in _BOOKLET_OPTIONS}
    sheet_options = {
        key: value for key, value in options.items() if key not in _BOOKLET_OPTIONS
    }

    form = io.BytesIO()
    # No marks on the form: they would sit outside its TrimBox and the second
    # pass clips to that, so they would be silently discarded. The fold is
    # carried across as a record instead, and the second pass draws it.
    first = impose(source, form, sheet=FIT_SHEET, marks=None, **booklet)
    form.seek(0)

    grid = _repeat_grid(repeat)
    try:
        second = impose(form, output, schema="steprepeat", **sheet_options, **grid)
    except ImposeError as error:
        # The second pass knows nothing about booklets, so its refusal talks
        # about a form that will not fit. Say what that form is, or the
        # measurement in the message looks unrelated to anything asked for.
        raise ImposeError(
            f"{repeat} copies of the {first.plan.schema} form "
            f"({format_mm(first.sheet_size)} each) do not fit. {error}"
        ) from error
    copies = second.plan.columns * second.plan.rows
    return dataclasses.replace(
        first,
        sheets=second.sheets,
        surfaces=second.surfaces,
        sheet_size=second.sheet_size,
        press=second.press,
        turned=second.turned,
        pages_turned=second.pages_turned,
        pdfx=second.pdfx,
        repeat=copies,
        warnings=first.warnings + second.warnings,
    )


def _repeat_grid(repeat: str | int | tuple[int, int]) -> dict:
    """The grid to hand the second pass, if the caller pinned one.

    ``"auto"`` hands it nothing, so the same chooser that decides any step and
    repeat grid decides this one -- densest that fits, which for whole copies
    of a booklet is simply most books a sheet.
    """
    if isinstance(repeat, tuple):
        return {"columns": repeat[0], "rows": repeat[1]}
    return {}
