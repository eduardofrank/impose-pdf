# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

"""Gathered signatures: one sheet folded more than once, sections glued.

This is how a book is made. A signature is a single sheet folded two, three or
four times, giving eight, sixteen or thirty-two pages from one pass through the
press. The signatures are gathered -- set one on the next in order -- and the
spine milled and glued, exactly as :mod:`impose.schemas.perfect` does with its
singly-folded sections.

The difference is the fold. A sheet folded once carries four pages and needs a
sheet twice the finished size; folded twice it carries eight and needs a sheet
four times the size, which on a press whose sheet is much larger than the book
is the difference between running sixteen sheets and running four.

Folding across the sheet as well as down it turns half the pages upside down.
That is not a convention to choose -- it is what the paper does, and
:mod:`impose.fold` derives it rather than asserting it. What is a choice is
which half goes over, and so whether the pages meet head to head or foot to
foot at the trimmed fold. That belongs to the folding machine, so it is an
argument here.
"""

from __future__ import annotations

from ..fold import HEAD_TO_HEAD, Fold, leaves, pages_per_sheet, signature_folds
from ..plan import BLANK, Placement, Plan, Surface, blanks_needed
from . import Flip


def impose(  # pylint: disable=too-many-arguments
    pages: int,
    *,
    columns: int,
    rows: int,
    style: str = HEAD_TO_HEAD,
    flip: Flip = "long-edge",
) -> Plan:
    """Impose *pages* as gathered signatures on a ``columns`` x ``rows`` sheet.

    Each sheet is one signature and holds ``columns * rows * 2`` pages. A
    2 x 1 sheet is the ordinary folded sheet, and gives what perfect binding
    has always given:

    >>> print(impose(8, columns=2, rows=1).describe())
    sheet 1 front
         4    1
    sheet 1 back
         2    3
    sheet 2 front
         8    5
    sheet 2 back
         6    7

    Fold it again and one sheet carries eight pages instead of four. The second
    fold puts the top row head to head with the bottom, so those pages are
    imposed upside down, which the listing marks with a star:

    >>> print(impose(8, columns=2, rows=2).describe())
    sheet 1 front
         5*    4*
         8    1
    sheet 1 back
         3*    6*
         2    7
    """
    folds = signature_folds(columns, rows, style=style)
    per_sheet = pages_per_sheet(columns, rows)
    total = pages + blanks_needed(pages, per_sheet)

    surfaces: list[Surface] = []
    for sheet in range(total // per_sheet):
        base = sheet * per_sheet
        surfaces.extend(
            _sheet(
                sheet,
                base,
                pages=pages,
                columns=columns,
                rows=rows,
                folds=folds,
                flip=flip,
            )
        )

    return Plan(
        columns=columns,
        rows=rows,
        surfaces=tuple(surfaces),
        pages=pages,
        fold_columns=tuple(sorted({f.at for f in folds if f.axis == "vertical"})),
        fold_rows=tuple(sorted({f.at for f in folds if f.axis == "horizontal"})),
        schema="signature",
    )


def _sheet(  # pylint: disable=too-many-arguments
    sheet: int,
    base: int,
    *,
    pages: int,
    columns: int,
    rows: int,
    folds: tuple[Fold, ...],
    flip: Flip,
) -> list[Surface]:
    """The two surfaces of one folded signature.

    The faces come back in the order a reader meets them, so the *n*th face
    carries the *n*th page of this signature. Which surface it belongs to and
    which way up it goes are the face's own business.
    """
    placed: dict[str, list[Placement]] = {"front": [], "back": []}
    for offset, face in enumerate(leaves(columns, rows, folds, flip=flip)):
        index = base + offset
        placed[face.side].append(
            Placement(
                index if 0 <= index < pages else BLANK,
                face.column,
                face.row,
                face.rotation,
            )
        )
    return [Surface(sheet, side, tuple(placed[side])) for side in ("front", "back")]
