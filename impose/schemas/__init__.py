# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

"""Imposition schemas: the orderings.

Each schema turns a page count and a grid into a :class:`~impose.plan.Plan`.
None of them touches a millimetre. What distinguishes them is how the finished
work is assembled -- nested and stapled, gathered and glued, cut into piles and
stacked -- and that assembly is entirely a question of which page number goes
in which cell.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Mapping
from typing import Literal

from .. import ImposeError

#: How the press turns the sheet to print its reverse.
#:
#: Long edge is the common default: the sheet turns about its long axis, so
#: the columns reverse. Short edge turns it about the short axis instead, and
#: the rows reverse. Getting this wrong backs every page up against the wrong
#: neighbour, and the error is invisible until the job is cut.
Flip = Literal["long-edge", "short-edge"]

#: The ways a duplex unit can turn a sheet, for anything offering the choice.
FLIP_CHOICES: tuple[str, ...] = ("long-edge", "short-edge")

#: Column indices of a two-page spread, named so the binding schemas read as
#: what they are rather than as arithmetic.
LEFT = 0
RIGHT = 1


def backing_cell(
    column: int, row: int, columns: int, rows: int, flip: Flip = "long-edge"
) -> tuple[int, int]:
    """Where a front cell lands on the reverse once the sheet is turned.

    >>> backing_cell(0, 0, 2, 1)
    (1, 0)
    >>> backing_cell(0, 0, 1, 2, "short-edge")
    (0, 1)
    """
    if flip == "long-edge":
        return (columns - 1 - column, row)
    if flip == "short-edge":
        return (column, rows - 1 - row)
    raise ValueError(f"Unknown flip {flip!r}; use 'long-edge' or 'short-edge'.")


def reading_order(columns: int, rows: int):
    """Cells left to right, top to bottom, as a person reads a laid-out sheet.

    >>> list(reading_order(2, 2))
    [(0, 0), (1, 0), (0, 1), (1, 1)]
    """
    for row in range(rows):
        for column in range(columns):
            yield (column, row)


def check_grid(columns: int, rows: int) -> None:
    """Refuse a grid that cannot hold anything."""
    if columns < 1 or rows < 1:
        raise ValueError(f"Grid must be at least 1x1, got {columns}x{rows}.")


def accepted_options(build: Callable[..., object]) -> frozenset[str] | None:
    """The options an ordering takes, or ``None`` where it takes any.

    Read off the function's own signature rather than tabulated beside it, so
    the answer cannot drift from the schema it describes.

    >>> def impose(pages, *, columns, rows, flip="long-edge"): ...
    >>> sorted(accepted_options(impose))
    ['columns', 'flip', 'rows']
    >>> accepted_options(lambda pages, **rest: None) is None
    True
    """
    parameters = inspect.signature(build).parameters
    if any(p.kind is p.VAR_KEYWORD for p in parameters.values()):
        return None
    return frozenset(parameters) - {"pages"}


def check_options(
    schema: str, builds: Mapping[str, Callable[..., object]], options: dict
) -> None:
    """Refuse an option the named schema has no use for.

    The schemas take different options, and a stored job or a library call can
    carry one belonging to a different schema -- a fold style on a sheet
    nobody folds, a section size on one that gathers nothing. Left alone it
    reaches the ordering as a stray keyword argument, and Python's own answer
    is a TypeError about a keyword: a traceback, saying nothing about
    imposition, where everything else this tool refuses is a sentence.

    Where another schema does take the option, the refusal says which, because
    that is usually where the mistake is -- the schema named in the job is
    wrong rather than the option.

    >>> builds = {"nup": lambda pages, *, columns, rows: None,
    ...           "signature": lambda pages, *, columns, style="x": None}
    >>> check_options("nup", builds, {"columns": 2, "rows": 1})
    >>> check_options("nup", builds, {"style": "foot-to-foot"})
    Traceback (most recent call last):
        ...
    impose.ImposeError: The nup schema takes no 'style'. It is an option of \
signature.
    """
    accepted = accepted_options(builds[schema])
    if accepted is None:
        return
    stray = sorted(set(options) - accepted)
    if not stray:
        return
    name = stray[0]
    elsewhere = sorted(
        other
        for other, build in builds.items()
        if other != schema and name in (accepted_options(build) or ())
    )
    belongs = f" It is an option of {_spoken(elsewhere)}." if elsewhere else ""
    raise ImposeError(f"The {schema} schema takes no {name!r}.{belongs}")


def _spoken(names: list[str]) -> str:
    """Names as a reader would say them.

    >>> _spoken(["perfect"])
    'perfect'
    >>> _spoken(["cutstack", "signature", "steprepeat"])
    'cutstack, signature and steprepeat'
    """
    if len(names) == 1:
        return names[0]
    return f"{', '.join(names[:-1])} and {names[-1]}"
