# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

"""Opening a file the shop was handed.

QPDF reads a damaged PDF by rebuilding what it can, which is the right
default for a reader and the wrong one for a press. The table it rebuilds
when a file is truncated is the cross-reference table, and that table is
what says how many pages the document has: a file still being copied reads
short, silently, and the imposition is then built around a page count that
was never in the artwork. A sixteen-page book arriving over a slow share
reads as fifteen, or seven, or one, depending on when it was looked at --
and the grid chosen for a sheet changes with it.

So a page count that had to be reconstructed is refused here, before any
geometry is read, and the operator is told what was rebuilt. Lesser damage
is reported and imposed: a stream whose length QPDF had to recover is one
page's content to look at, not a reason to turn away artwork a shop may
have no better copy of.
"""

from __future__ import annotations

import pathlib
import re

import pikepdf

from . import SourceError

#: What a run may do with a file whose page count had to be reconstructed.
#: ``"refuse"`` is the default; ``"recover"`` is an operator saying they know
#: what this file is and will take what can be read out of it.
DAMAGED_CHOICES = ("refuse", "recover")

#: QPDF prefixes every warning with the source it came from -- a filename, or
#: for a stream a Python ``repr`` that has no business in a sentence shown to
#: an operator. Both forms end at the first colon-space after an optional
#: parenthesised position.
_PREFIX = re.compile(r"^.*?(?: \([^)]*\))?: ")


def _name(source) -> str:
    """How to refer to *source* in a sentence.

    A path is worth naming, because an operator with a folder of files needs
    to know which one. A stream has only a ``repr``, which names a memory
    address and tells nobody anything.
    """
    if isinstance(source, (str, pathlib.Path)):
        return f"{source} "
    return ""


def open_source(
    source: pikepdf.Pdf | str | pathlib.Path,
    *,
    what: str = "file",
    damaged: str = "refuse",
) -> tuple[pikepdf.Pdf, tuple[str, ...]]:
    """Open *source*, refusing one whose page count was reconstructed.

    Returns the document and any notes about damage that was tolerated. An
    already-open :class:`pikepdf.Pdf` passes straight through with no notes:
    a caller who opened it made whatever judgement there was to make.

    *what* names the file's role in the refusal -- ``"file"``, ``"cover
    artwork"``, ``"control strip"``. *damaged* is one of
    :data:`DAMAGED_CHOICES`.
    """
    if damaged not in DAMAGED_CHOICES:
        raise SourceError(
            f"Unknown damaged {damaged!r}; use {' or '.join(DAMAGED_CHOICES)}."
        )
    if isinstance(source, pikepdf.Pdf):
        return source, ()
    try:
        pdf = pikepdf.open(source)
    except Exception as error:
        raise SourceError(f"Cannot open {source}: {error}") from error
    # Once only: QPDF hands the list over and forgets it, so a second call
    # reports a clean file and the damage goes unmentioned.
    warnings = tuple(_PREFIX.sub("", str(line)) for line in pdf.get_warnings())
    rebuilt = tuple(line for line in warnings if _is_reconstruction(line))
    if rebuilt and damaged == "refuse":
        pages = len(pdf.pages)
        pdf.close()
        raise SourceError(_refusal(_name(source), what, pages))
    return pdf, tuple(_notes(warnings, rebuilt, pages=len(pdf.pages)))


def _is_reconstruction(warning: str) -> bool:
    """Whether *warning* says the cross-reference table was rebuilt.

    Matched on two words rather than the whole sentence, because the sentence
    is QPDF's to reword. A test pins this: if a qpdf release changes the
    wording, CI fails rather than the refusal quietly going away on files in
    a shop somewhere.
    """
    folded = warning.casefold()
    return "reconstruct" in folded and "cross-reference" in folded


def _refusal(named: str, what: str, pages: int) -> str:
    """Why a file whose page count was rebuilt is not imposed."""
    return (
        f"The {what} {named}is damaged: its cross-reference table had to be "
        f"reconstructed to read it at all, and that table is what says how "
        f"many pages there are. It reads as {pages} "
        f"{'page' if pages == 1 else 'pages'}, which is as much of it as "
        f"survived. A file still being copied reads short, and the "
        f"imposition would be built around the wrong count. Wait for the "
        f"copy to finish, or ask to impose what can be read."
    )


def _notes(
    warnings: tuple[str, ...], rebuilt: tuple[str, ...], *, pages: int
) -> list[str]:
    """What to say about damage that was read past rather than refused."""
    if rebuilt:
        # Everything else QPDF said about a truncated file -- the missing
        # startxref, the unexpected EOF, the objects it could not parse --
        # are symptoms of this one event, and listing seven of them buries
        # the number that matters.
        was = "page was" if pages == 1 else "pages were"
        return [
            f"{pages} {was} read out of a file whose cross-reference table "
            f"had to be reconstructed, as this run asked. That table is what "
            f"states the page count, so check it against what was sent "
            f"before this goes to press."
        ]
    lesser = sorted(set(warnings))
    if not lesser:
        return []
    return [
        "The file was readable but not clean. QPDF reported: "
        + "; ".join(lesser)
        + ". Content on the pages those objects belong to is worth looking "
        "at before the sheet is printed."
    ]
