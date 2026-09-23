# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

"""The flat a perfect-bound cover is wrapped from.

The spine panel is the thickness of the bound text block: how many leaves the
imposed book actually has, times the gauge of the paper those leaves are
printed on, plus the glue film if the cover should fit the book after it is
glued rather than the dry block. A leaf is one sheet, two pages. Blank leaves
added to finish a section are in the block, so the count is the imposed one.

The hinges are separate. They are the scores where the cover turns off the
glue, one each side of the spine, and they are usually about the thickness of
the cover stock or a small shop constant. Cover stock does not go into the
spine panel: a caliper on a finished book includes the two covers, and that
larger number makes the panel too wide.

Laid out flat, outside up:

    bleed + back + hinge + spine + hinge + front + bleed

Back and front are the finished trim of the text. Bleed stays outside that.
The scores are folds; the outer edges are cuts.
"""

from __future__ import annotations

import dataclasses

import pikepdf
from pikepdf import Array, Dictionary, Name

from . import ImposeError
from .boxes import read_boxes
from .font import describe, load, reserve
from .geometry import Rect, Size, approx
from .plan import blanks_needed
from .units import MM, format_mm, length, to_mm

#: How close two finished sizes must be to be the same cover.
_SAME_SIZE = 0.01

#: A section is folded sheets, four pages each, as perfect binding requires.
_SECTION = 4


@dataclasses.dataclass(frozen=True, slots=True)
class Cover:  # pylint: disable=too-many-instance-attributes
    """One perfect-bound cover, as a flat and the scores across it.

    *scores* are distances from the left edge of the trim to each score, in
    PDF points. The spine runs vertically; a score is a vertical line.
    """

    trim: Size
    pages: int
    imposed_pages: int
    caliper: float
    glue: float
    hinge: float
    spine: float
    flat: Size
    scores: tuple[float, ...]

    def describe(self) -> str:
        """The spine, what it was made of, and the flat it produces."""
        parts = [f"{self.imposed_pages // 2} leaves × {_mm(self.caliper)} mm"]
        if self.glue:
            parts.append(f"{_mm(self.glue)} mm glue")
        if self.imposed_pages != self.pages:
            blanks = self.imposed_pages - self.pages
            parts.append(f"{self.pages} pages plus {blanks} blanks")
        hinge = f", hinges {_mm(self.hinge)} mm" if self.hinge else ""
        return (
            f"cover: spine {_mm(self.spine)} mm ({', '.join(parts)})"
            f"{hinge}, flat {format_mm(self.flat)}"
        )


def flat(  # pylint: disable=too-many-arguments
    trim: Size,
    pages: int,
    caliper: float,
    *,
    hinge: float = 0.0,
    glue: float = 0.0,
    section_pages: int = _SECTION,
) -> Cover:
    """The cover wrapped around a text block of *pages* at this *trim*.

    *caliper* is one sheet of the text stock. *hinge* is the score allowance
    on each side of the spine. *glue* is the film added once the block is
    glued, and it widens the spine panel only.

    >>> from impose.units import MM
    >>> book = flat(Size(148 * MM, 210 * MM), 80, 0.1 * MM)
    >>> _mm(book.spine)
    '4'
    >>> format_mm(book.flat)
    '300 × 210 mm'
    >>> len(book.scores)
    2
    >>> flat(Size(100, 200), 81, 1).imposed_pages
    84
    """
    if pages < 1:
        raise ImposeError(f"A cover needs a text block; got {pages} pages.")
    if section_pages % _SECTION or section_pages < _SECTION:
        raise ImposeError(
            "A perfect-bound section is made of folded sheets, so it holds a "
            f"multiple of {_SECTION} pages; got {section_pages}."
        )
    if caliper <= 0:
        raise ImposeError(
            "A cover spine is the thickness of the text block, and that needs "
            "the gauge of the paper it is printed on. Measure it: a micrometer "
            "on twenty sheets, divided by twenty."
        )
    if hinge < 0 or glue < 0:
        raise ImposeError("A hinge or a glue film cannot be negative.")
    imposed = pages + blanks_needed(pages, section_pages)
    spine = (imposed // 2) * caliper + glue
    width = 2 * trim.width + spine + 2 * hinge
    scores = _scores(trim.width, spine, hinge)
    return Cover(
        trim=trim,
        pages=pages,
        imposed_pages=imposed,
        caliper=caliper,
        glue=glue,
        hinge=hinge,
        spine=spine,
        flat=Size(width, trim.height),
        scores=scores,
    )


def _scores(face: float, spine: float, hinge: float) -> tuple[float, ...]:
    """Where the flat scores, measured from the left trim edge."""
    marks = []
    cursor = face
    marks.append(cursor)
    if hinge:
        cursor += hinge
        marks.append(cursor)
    cursor += spine
    marks.append(cursor)
    if hinge:
        cursor += hinge
        marks.append(cursor)
    return tuple(marks)


def build_flat(
    cover: Cover,
    artwork: pikepdf.Pdf | str | None = None,
    *,
    bleed: float | str = 2 * MM,
) -> pikepdf.Pdf:
    """A one- or two-page PDF of the flat, with the scores recorded on it.

    Without *artwork* the page is a template: the faces are labelled, and it
    is for agreeing the flat rather than for the press. With *artwork*, that
    file is the flat -- one page the outside, or two the outside and the
    inside -- and it has to be the calculated size. Either way the scores are
    a private ``/Impose`` record, which the imposition draws as fold marks
    outside the trim.
    """
    margin = length(bleed)
    if artwork is None:
        return _template(cover, margin)
    opened = artwork if isinstance(artwork, pikepdf.Pdf) else _open(artwork)
    try:
        return _from_artwork(opened, cover)
    finally:
        if opened is not artwork:
            opened.close()


def impose_cover(  # pylint: disable=too-many-arguments
    source,
    output,
    *,
    paper_caliper: float | str,
    hinge: float | str = 0.0,
    glue: float | str = 0.0,
    section_pages: int = _SECTION,
    artwork=None,
    bleed: float | str = 2 * MM,
    **options,
):
    """Build the flat for *source* and impose it onto the press.

    *source* is the text block. Its finished size and its page count, padded
    out to a whole section, decide the spine. The returned cover describes
    that flat; the result is the imposition of it, the same object
    :func:`impose.job.impose_document` returns.
    """
    # Imported here so that calculating a spine does not pull the renderer in,
    # and so this module and job.py do not import each other at load time.
    from .job import impose_document, measure  # pylint: disable=C0415

    measured = measure(source)
    cover = flat(
        measured.trim_size,
        measured.pages,
        length(paper_caliper),
        hinge=length(hinge),
        glue=length(glue),
        section_pages=section_pages,
    )
    document = build_flat(cover, artwork, bleed=bleed)
    result = impose_document(document, output, schema="cover", bleed=bleed, **options)
    return cover, result, measured.warnings


def _open(path) -> pikepdf.Pdf:
    """Open a cover artwork, as a sentence if it cannot be read."""
    try:
        return pikepdf.open(path)
    except Exception as error:
        raise ImposeError(f"Cannot open {path}: {error}") from error


def _from_artwork(artwork: pikepdf.Pdf, cover: Cover) -> pikepdf.Pdf:
    """Copy *artwork* and note the scores on each page."""
    count = len(artwork.pages)
    if count not in (1, 2):
        raise ImposeError(
            "A cover artwork is the outside, or the outside and the inside; "
            f"got {count} pages."
        )
    for number, page in enumerate(artwork.pages, start=1):
        boxes = read_boxes(page)
        if boxes.rotation:
            raise ImposeError(
                f"Page {number} of the cover artwork carries /Rotate "
                f"{boxes.rotation}. Build the flat upright, with the spine "
                f"running vertically, so the scores land on the hinges."
            )
        if not _same_size(boxes.trim_size, cover.flat):
            raise ImposeError(
                f"{cover.describe()}, but page {number} of the artwork is "
                f"{format_mm(boxes.trim_size)}."
            )
    flat_pdf = pikepdf.Pdf.new()
    for page in artwork.pages:
        flat_pdf.pages.append(page)
    for page in flat_pdf.pages:
        _record_scores(page, cover)
    return flat_pdf


def _template(cover: Cover, bleed: float) -> pikepdf.Pdf:
    """A labelled flat, for agreeing the spine before any artwork exists."""
    pdf = pikepdf.Pdf.new()
    media = Size(cover.flat.width + 2 * bleed, cover.flat.height + 2 * bleed)
    page = pdf.add_blank_page(page_size=(media.width, media.height))
    origin = bleed
    page.obj["/TrimBox"] = Array(
        [origin, origin, origin + cover.flat.width, origin + cover.flat.height]
    )
    page.obj["/BleedBox"] = Array([0, 0, media.width, media.height])
    _paint(pdf, page, cover, origin)
    _record_scores(page, cover)
    return pdf


def _paint(pdf, page, cover: Cover, origin: float) -> None:
    """Name the faces, and say what the spine was made of."""
    font = load()
    font_object = reserve(pdf)
    name = page.add_resource(font_object, Name.Font)
    back = Rect(origin, origin, origin + cover.trim.width, origin + cover.flat.height)
    front_x = origin + cover.flat.width - cover.trim.width
    front = Rect(front_x, origin, front_x + cover.trim.width, back.y1)
    note = cover.describe()
    note_size = _fitting(font, note, back.width)
    note_band = Rect(back.x0, back.y0, back.x1, back.y0 + back.height * 0.22)
    parts = [_score_lines(cover, origin, back.y0, back.y1)]
    parts.append(_show("BACK", name, 14, _centred(font, "BACK", 14, back)))
    parts.append(_show("FRONT", name, 14, _centred(font, "FRONT", 14, front)))
    parts.append(
        _show(note, name, note_size, _centred(font, note, note_size, note_band))
    )
    page.obj["/Contents"] = pikepdf.Stream(pdf, "".join(parts).encode("latin-1"))
    describe(pdf, font_object, font, "BACKFRONT" + note)


def _score_lines(cover: Cover, origin: float, bottom: float, top: float) -> str:
    """Light rules at the scores, so a template shows where the cover turns."""
    parts = ["q\n0.75 G\n0.4 w\n"]
    for score in cover.scores:
        x = origin + score
        parts.append(f"{_numbers(x, bottom)} m {_numbers(x, top)} l S\n")
    parts.append("Q\n")
    return "".join(parts)


def _record_scores(page, cover: Cover) -> None:
    """Note the scores in this page's own space, for the imposition to draw."""
    boxes = read_boxes(page)
    page.obj["/Impose"] = Dictionary(
        Version=1,
        Folds=Dictionary(
            X=Array([boxes.trim.x0 + score for score in cover.scores]),
            Y=Array(),
        ),
    )


def _fitting(font, text: str, width: float) -> float:
    """The largest size at which *text* still sits in *width*, down to 5 pt."""
    size = 8.0
    while size > 5 and font.width(text, size) > width * 0.92:
        size -= 0.5
    return size


def _centred(font, text: str, size: float, rect: Rect):
    """A text matrix that centres *text* in *rect*."""
    width = font.width(text, size)
    baseline = (font.ascent + font.descent) * size / 2000.0
    return (
        size,
        0,
        0,
        size,
        rect.x0 + (rect.width - width) / 2,
        (rect.y0 + rect.y1) / 2 - baseline,
    )


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


def _same_size(found: Size, expected: Size) -> bool:
    """Whether two sizes are the same cover, to within press-irrelevant noise."""
    return approx(found.width, expected.width, tolerance=_SAME_SIZE) and approx(
        found.height, expected.height, tolerance=_SAME_SIZE
    )


def _mm(points: float) -> str:
    """Millimetres, trailing zeros removed, for a sentence."""
    return f"{to_mm(points):.2f}".rstrip("0").rstrip(".") or "0"


def _numbers(*values: float) -> str:
    """Format coordinates for a content stream, without exponent notation."""
    return " ".join(f"{value:.5f}".rstrip("0").rstrip(".") or "0" for value in values)
