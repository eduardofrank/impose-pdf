# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

"""A sheet an operator can approve.

``--dry-run`` lists the page numbers. The thing a bindery signs is a picture
of the sheet: each surface at the size the press file will be, the folio in
its cell, turned the way that page is turned, a blank named as a blank, and a
fold drawn dashed. None of the artwork is in it. It is for agreeing the order
before the file goes on the press, and it is not itself a file to print.
"""

from __future__ import annotations

import pikepdf
from pikepdf import Array, Name

from . import ImposeError, __version__
from .font import describe, load, reserve
from .geometry import Rect, approx
from .plan import Plan

#: How far inside the sheet corner the "PROOF" line sits.
_CAPTION_INSET = 8.0

#: Caption size. The folios are as large as their cells allow; this only has
#: to be readable in the corner.
_CAPTION_SIZE = 8.0


def write_proof(destination, plan: Plan, layouts, folds) -> None:
    """Write one page per surface of *plan* to *destination*.

    *layouts* are the surfaces as they will sit on the press sheet, and
    *folds* the dashed lines for each one -- ``(vertical, horizontal)`` in
    that sheet's coordinates, the same lines the press file marks as folds.
    Passing anything else would let the picture and the file disagree about
    where the spine is, which is the disagreement this exists to prevent.
    """
    if len(layouts) != len(plan.surfaces) or len(folds) != len(plan.surfaces):
        raise ImposeError(
            f"A proof needs one layout and one set of folds per surface; "
            f"got {len(layouts)} layouts and {len(folds)} folds for "
            f"{len(plan.surfaces)} surfaces."
        )
    pdf = pikepdf.Pdf.new()
    font = load()
    font_object = reserve(pdf)
    characters: set[str] = set()
    for surface, layout, fold in zip(plan.surfaces, layouts, folds):
        _add_surface(
            pdf,
            font_object,
            font,
            characters,
            surface=surface,
            layout=layout,
            fold=fold,
            sheets=plan.sheets,
        )
    if characters:
        describe(pdf, font_object, font, "".join(sorted(characters)))
    with pdf.open_metadata(set_pikepdf_as_editor=False) as meta:
        meta["dc:creator"] = ["impose"]
        meta["pdf:Producer"] = f"impose {__version__}"
    pdf.save(destination, compress_streams=True, min_version="1.4")


def _add_surface(  # pylint: disable=too-many-arguments
    pdf,
    font_object,
    font,
    characters: set[str],
    *,
    surface,
    layout,
    fold,
    sheets: int,
) -> None:
    """One proof page: the cells, the folios, the folds, and which sheet it is."""
    page = pdf.add_blank_page(page_size=(layout.sheet.width, layout.sheet.height))
    name = page.add_resource(font_object, Name.Font)
    sheet = Rect.from_size(layout.sheet)
    caption = f"PROOF · sheet {surface.sheet + 1}/{sheets} {surface.side}"
    characters.update(caption)
    page.contents_add(
        pikepdf.Stream(
            pdf,
            (
                _outlines(layout, sheet)
                + _folds(layout, fold)
                + _folios(layout, font, name, characters)
                + _show(
                    caption,
                    name,
                    _CAPTION_SIZE,
                    (
                        _CAPTION_SIZE,
                        0,
                        0,
                        _CAPTION_SIZE,
                        _CAPTION_INSET,
                        sheet.y1 - _CAPTION_INSET - font.height(_CAPTION_SIZE),
                    ),
                )
            ).encode("latin-1"),
        )
    )
    page.obj["/MediaBox"] = Array([sheet.x0, sheet.y0, sheet.x1, sheet.y1])


def _outlines(layout, sheet: Rect) -> str:
    """The cell trims, blanks filled, and the imageable area when it is inset."""
    parts = ["q\n0 G\n0.4 w\n"]
    if _inset(layout.imageable, sheet):
        parts.append(f"0.5 G\n0.25 w\n{_rect(layout.imageable)} S\n0 G\n0.4 w\n")
    parts.extend(
        f"0.92 g\n{_rect(placed.trim)} f\n"
        for placed in layout.pages
        if placed.is_blank
    )
    parts.append("0 g\n")
    parts.extend(_rect(placed.trim) + " S\n" for placed in layout.pages)
    parts.append("Q\n")
    return "".join(parts)


def _folds(layout, fold) -> str:
    """Dashed lines where the sheet folds, across the form."""
    vertical, horizontal = fold
    if not (vertical or horizontal):
        return ""
    bounds = layout.trim_bounds
    parts = ["q\n0 G\n0.6 w\n[3 3] 0 d\n"]
    parts.extend(
        f"{_numbers(x, bounds.y0)} m {_numbers(x, bounds.y1)} l S\n" for x in vertical
    )
    parts.extend(
        f"{_numbers(bounds.x0, y)} m {_numbers(bounds.x1, y)} l S\n" for y in horizontal
    )
    parts.append("Q\n")
    return "".join(parts)


def _folios(layout, font, font_name: Name, characters: set[str]) -> str:
    """The folio in each cell, or the word blank where the cell is empty."""
    parts = []
    for placed in layout.pages:
        label = "blank" if placed.is_blank else str(placed.source + 1)
        size = _folio_size(font, label, placed.trim, placed.rotation)
        parts.append(
            _show(
                label,
                font_name,
                size,
                _text_matrix(font, label, size, placed.rotation, placed.trim.center),
            )
        )
        characters.update(label)
    return "".join(parts)


def _inset(inner: Rect, outer: Rect) -> bool:
    """Whether *inner* sits strictly inside *outer*."""
    return any(
        not approx(getattr(inner, edge), getattr(outer, edge))
        for edge in ("x0", "y0", "x1", "y1")
    )


def _rect(rect: Rect) -> str:
    """A PDF rectangle operand, origin and size."""
    return _numbers(rect.x0, rect.y0, rect.width, rect.height) + " re"


def _show(text: str, font_name: Name, size: float, matrix) -> str:
    """A text object that sets *text* through *matrix*."""
    return (
        "q\n0 g\nBT\n"
        f"{font_name} {_numbers(size)} Tf\n"
        f"{_numbers(*matrix)} Tm\n"
        f"{_literal(text)} Tj\n"
        "ET\nQ\n"
    )


def _literal(text: str) -> str:
    """*text* as a PDF literal string, WinAnsi encoded."""
    escaped = bytearray()
    for byte in load().encode(text):
        if byte in b"()\\":
            escaped.append(0x5C)
        escaped.append(byte)
    return "(" + escaped.decode("latin-1") + ")"


def _folio_size(font, text: str, trim: Rect, rotation: int) -> float:
    """The largest size at which *text* still sits inside *trim*.

    A quarter turn swaps which side of the cell the line runs along, so the
    limit is taken on the side the glyphs actually occupy.
    """
    along, across = trim.width, trim.height
    if rotation % 180:
        along, across = across, along
    by_width = along * 0.72 * 1000.0 / (max(len(text), 1) * font.advance)
    by_height = across * 0.62 * 1000.0 / (font.ascent - font.descent)
    return min(by_width, by_height)


def _text_matrix(font, text: str, size: float, rotation: int, center):
    """A text matrix that centres *text* on *center*, turned with the page.

    Rotation is clockwise, the same way a page is turned in its cell, so a
    folio that reads upside down is a page that will read upside down.

    >>> _text_matrix(load(), "1", 10, 0, (100, 100))[0]
    10
    >>> _text_matrix(load(), "1", 10, 180, (100, 100))[0]
    -10
    """
    dx = font.width(text, size) / 2
    dy = (font.ascent + font.descent) * size / 2000.0
    cx, cy = center
    turn = rotation % 360
    if turn == 0:
        return (size, 0, 0, size, cx - dx, cy - dy)
    if turn == 90:
        return (0, -size, size, 0, cx - dy, cy + dx)
    if turn == 180:
        return (-size, 0, 0, -size, cx + dx, cy + dy)
    if turn == 270:
        return (0, size, -size, 0, cx + dy, cy - dx)
    raise ValueError(f"Rotation must be a quarter turn, got {rotation}.")


def _numbers(*values: float) -> str:
    """Format coordinates for a content stream, without exponent notation."""
    return " ".join(f"{value:.5f}".rstrip("0").rstrip(".") or "0" for value in values)
