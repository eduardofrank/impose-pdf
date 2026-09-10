# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

"""What folding a sheet does to the pages printed on it.

A signature is one sheet folded more than once. Each fold halves the sheet and
doubles the leaves, so a sheet folded twice carries eight pages and one folded
three times carries sixteen. This is how a book is made: sections of eight or
sixteen are gathered and glued, not stacks of singly-folded sheets.

The ordering cannot be written down from memory for every case, so it is
derived. The sheet is modelled as physical cells, the folds are applied to it,
and the finished pile is read the way a person reads the booklet -- top leaf
face up, then turn it over, then the next. Whatever order that yields is the
order the pages have to be printed in.

Two things fall out of the model rather than being asserted.

**A fold about a horizontal axis turns its half upside down.** Folding mirrors
the moving half about the fold line, and turning the paper over mirrors it
again about the perpendicular axis; two perpendicular mirrors are a half turn.
A vertical fold mirrors and un-mirrors on the same axis, so it turns nothing.
This is why a signature has pages head to head across the fold and a plain
folded sheet does not.

**The moving half goes underneath.** Fold a sheet with its printed side out --
which is what you do, or the fold marks end up inside -- and the half that
swings over lands beneath the half that stayed, back to back with it. Get this
backwards and every page comes out on the wrong side of the paper.
"""

from __future__ import annotations

import dataclasses

from . import ImposeError
from .schemas import Flip, backing_cell

#: The two rows of a folded signature meet at the head, and the fold there is
#: trimmed off. The commoner of the two.
HEAD_TO_HEAD = "head-to-head"

#: They meet at the foot instead. Which one a job wants is a property of the
#: folding machine, not of the document.
FOOT_TO_FOOT = "foot-to-foot"

STYLES = (HEAD_TO_HEAD, FOOT_TO_FOOT)

#: Pages on one leaf: a leaf is a sheet of paper and has two sides.
PAGES_PER_LEAF = 2


@dataclasses.dataclass(frozen=True, slots=True)
class Fold:
    """One fold of the sheet.

    *at* is the grid line the sheet folds on, counted in cells. *moves* names
    which side of that line swings over: ``"low"`` for the columns or rows
    before it, ``"high"`` for the ones after.
    """

    axis: str
    at: int
    moves: str = "low"

    def __post_init__(self) -> None:
        if self.axis not in ("vertical", "horizontal"):
            raise ValueError(f"A fold is vertical or horizontal; got {self.axis!r}.")
        if self.moves not in ("low", "high"):
            raise ValueError(f"A fold moves the low or high half; got {self.moves!r}.")


@dataclasses.dataclass(frozen=True, slots=True)
class Face:
    """One printable face of the folded sheet, and how it must be printed."""

    side: str
    column: int
    row: int
    rotation: int = 0


@dataclasses.dataclass(frozen=True, slots=True)
class _Cell:
    """A physical cell of the sheet, part-way through being folded."""

    column: int
    row: int
    turned: int
    rotation: int


def leaves(
    columns: int,
    rows: int,
    folds: tuple[Fold, ...],
    *,
    flip: Flip = "long-edge",
) -> tuple[Face, ...]:
    """The faces of a folded sheet, in the order a reader meets them.

    The first face is page one of the signature, the second is page two, and so
    on. Each says which surface of the sheet to print on, which cell, and what
    rotation the page needs so that it reads upright once folded.

    A single vertical fold is the ordinary folded sheet the bound schemas
    already impose -- four pages, nothing turned:

    >>> for n, face in enumerate(leaves(2, 1, (Fold("vertical", 1),)), 1):
    ...     print(n, face.side, face.column, face.rotation)
    1 front 1 0
    2 back 0 0
    3 back 1 0
    4 front 0 0
    """
    stacks = {
        (column, row): [_Cell(column, row, 0, 0)]
        for row in range(rows)
        for column in range(columns)
    }
    for fold in folds:
        _apply(stacks, fold)
    if len(stacks) != 1:
        raise ImposeError(
            f"These folds leave {len(stacks)} separate pieces rather than one "
            f"folded pile. A signature is folded down to a single leaf."
        )
    (pile,) = stacks.values()

    faces: list[Face] = []
    for cell in reversed(pile):  # the top of the pile is read first
        up = "back" if cell.turned % 2 else "front"
        for side in (up, "front" if up == "back" else "back"):
            column, row = (
                (cell.column, cell.row)
                if side == "front"
                else backing_cell(cell.column, cell.row, columns, rows, flip)
            )
            faces.append(Face(side, column, row, cell.rotation))
    return tuple(faces)


def _apply(stacks: dict[tuple[int, int], list[_Cell]], fold: Fold) -> None:
    """Fold one half of the sheet under the other, in place."""
    turn = 180 if fold.axis == "horizontal" else 0
    for (column, row), pile in sorted(stacks.items()):
        index = column if fold.axis == "vertical" else row
        moving = index < fold.at if fold.moves == "low" else index >= fold.at
        if not moving:
            continue
        mirrored = 2 * fold.at - 1 - index
        target = (mirrored, row) if fold.axis == "vertical" else (column, mirrored)
        if target not in stacks:
            raise ImposeError(
                f"A fold at {fold.axis} line {fold.at} sends a cell off the "
                f"sheet. The fold must halve what is left of it."
            )
        moved = [
            _Cell(c.column, c.row, c.turned + 1, (c.rotation + turn) % 360)
            for c in reversed(pile)
        ]
        stacks[target] = moved + stacks[target]
        del stacks[(column, row)]


def signature_folds(
    columns: int, rows: int, *, style: str = HEAD_TO_HEAD
) -> tuple[Fold, ...]:
    """How to fold a *columns* x *rows* sheet into one leaf, spine last.

    The head fold comes first and the spine last, which is the right-angle
    sequence a folder does and the one that yields the familiar eight-page
    signature. *style* decides which half the head fold takes, and so whether
    the two rows meet head to head or foot to foot.

    >>> signature_folds(2, 1)
    (Fold(axis='vertical', at=1, moves='low'),)
    >>> for fold in signature_folds(2, 2):
    ...     print(fold.axis, fold.at, fold.moves)
    horizontal 1 low
    vertical 1 low
    """
    if style not in STYLES:
        raise ImposeError(f"Unknown fold style {style!r}; use {' or '.join(STYLES)}.")
    for name, count in (("columns", columns), ("rows", rows)):
        if count < 1 or count & (count - 1):
            raise ImposeError(
                f"Each fold halves the sheet, so a signature is a power of two "
                f"cells each way; got {count} {name}."
            )
    moves = "low" if style == HEAD_TO_HEAD else "high"
    folds: list[Fold] = []
    folds.extend(_halve("horizontal", rows, moves))
    folds.extend(_halve("vertical", columns, "low"))
    return tuple(folds)


def _halve(axis: str, count: int, moves: str) -> list[Fold]:
    """Folds that reduce *count* cells along *axis* to one.

    The fold line is not simply the midpoint each time: after the first fold
    the half that survives is at one end of the sheet, not spanning it, so the
    next line has to be found from where that half now lies.
    """
    folds: list[Fold] = []
    low, high = 0, count - 1
    while low < high:
        at = (low + high + 1) // 2
        folds.append(Fold(axis, at, moves))
        low, high = (at, high) if moves == "low" else (low, at - 1)
    return folds


def pages_per_sheet(columns: int, rows: int) -> int:
    """Pages a folded sheet of this grid carries, both sides counted."""
    return columns * rows * PAGES_PER_LEAF
