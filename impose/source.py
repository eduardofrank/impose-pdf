# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE.

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
geometry is read, and the operator is told what was rebuilt. A page tree
with something in it that is not a page is refused on the same grounds:
QPDF skips it and the document reads a page short. Measured, 42 of 3000
damaged copies of a six-page file were imposed as five pages at exit 0,
every one of them with that warning and only that one about the pages. Lesser damage
is reported and imposed: a stream whose length QPDF had to recover is one
page's content to look at, not a reason to turn away artwork a shop may
have no better copy of.

A page with no size is refused as well, and nothing overrides that. Every
page must carry a MediaBox, and when one is missing or is not four numbers
QPDF puts US Letter in its place as the file is opened -- so by the time a
page is looked at it is a well-formed Letter page, and the file never said
so. Measured: a page whose TrimBox said A3 was clipped to the invented
Letter page and imposed at 213 x 276 mm, exit 0. ``recover`` is not offered
for it because there is nothing to recover: a rebuilt cross-reference table
is read out of the file, and this size is not in the file anywhere.
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
    raw = tuple(str(line) for line in pdf.get_warnings())
    warnings = tuple(_PREFIX.sub("", line) for line in raw)
    rebuilt = tuple(line for line in warnings if _is_reconstruction(line))
    pruned = tuple(line for line in warnings if _is_pruned(line))
    if (rebuilt or pruned) and damaged == "refuse":
        pages = len(pdf.pages)
        pdf.close()
        if rebuilt:
            raise SourceError(_refusal(_name(source), what, pages))
        raise SourceError(_pruned(_name(source), what, pages))
    unsized = [line for line in raw if _is_invented_size(line)]
    if unsized:
        numbers = _unsized_pages(pdf, unsized)
        pdf.close()
        raise SourceError(_no_size(_name(source), what, numbers))
    return pdf, tuple(_notes(warnings, rebuilt, pruned, pages=len(pdf.pages)))


def _is_reconstruction(warning: str) -> bool:
    """Whether *warning* says the cross-reference table was rebuilt.

    Matched on two words rather than the whole sentence, because the sentence
    is QPDF's to reword. A test pins this: if a qpdf release changes the
    wording, CI fails rather than the refusal quietly going away on files in
    a shop somewhere.
    """
    folded = warning.casefold()
    return "reconstruct" in folded and "cross-reference" in folded


def _is_pruned(warning: str) -> bool:
    """Whether *warning* says QPDF skipped something in the page tree.

    What it skipped was where a page should have been, so the count is one
    short or more. Matched and pinned like :func:`_is_reconstruction`.
    """
    folded = warning.casefold()
    return "pages tree" in folded and "non-dictionary" in folded


def _pruned(named: str, what: str, pages: int) -> str:
    """Why a file whose page tree lost an entry is not imposed."""
    return (
        f"The {what} {named}is damaged: its page tree holds something that "
        f"is not a page, where a page should be, and reading it skips that "
        f"entry. It reads as {pages} {'page' if pages == 1 else 'pages'}, "
        f"which may be fewer than were sent. Ask for the file again, or ask "
        f"to impose what can be read."
    )


def _is_invented_size(warning: str) -> bool:
    """Whether *warning* says QPDF gave a page a MediaBox it did not have.

    Two words again, for the same reason as :func:`_is_reconstruction`, and
    pinned by a test the same way.
    """
    folded = warning.casefold()
    return "mediabox" in folded and "undefined" in folded


#: Where QPDF says a page had no MediaBox: the page's own object.
_OBJECT = re.compile(r"\bobject (\d+) (\d+)\b")


def _unsized_pages(pdf: pikepdf.Pdf, warnings: list[str]) -> list[int]:
    """The page numbers *warnings* are about, as far as they can be told.

    QPDF names the page by its object, not its number, so this looks the
    object up in the document's own order. A warning that names no page is
    left out rather than guessed at: the refusal stands without the number.
    """
    order = {page.objgen: number for number, page in enumerate(pdf.pages, 1)}
    numbers = set()
    for warning in warnings:
        found = _OBJECT.search(warning)
        if found is not None:
            key = (int(found.group(1)), int(found.group(2)))
            if key in order:
                numbers.add(order[key])
    return sorted(numbers)


def _no_size(named: str, what: str, numbers: list[int]) -> str:
    """Why a file with a page of no stated size is not imposed."""
    if not numbers:
        which, verb = "a page", "has"
    elif len(numbers) == 1:
        which, verb = f"page {numbers[0]}", "has"
    else:
        shown = ", ".join(str(number) for number in numbers[:-1])
        which, verb = f"pages {shown} and {numbers[-1]}", "have"
    return (
        f"The {what} {named}does not say what size {which} {verb}: the "
        f"MediaBox every page must carry is missing, or is not four numbers. "
        f"Reading it, QPDF put US Letter in its place, and imposing that "
        f"would print a size nobody chose. Ask for the file to be exported "
        f"again."
    )


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
    warnings: tuple[str, ...],
    rebuilt: tuple[str, ...],
    pruned: tuple[str, ...],
    *,
    pages: int,
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
    if pruned:
        was = "page was" if pages == 1 else "pages were"
        return [
            f"{pages} {was} read out of a file whose page tree held something "
            f"that is not a page, as this run asked. A page may be missing: "
            f"check the count against what was sent before this goes to press."
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
