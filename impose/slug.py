# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

"""The slug line: what this sheet is, printed on the sheet.

A press sheet that has left the prepress desk carries no record of where it
came from. The slug is that record -- which file, which sheet and side, what it
was imposed for -- set small in the margin and cut away when the job is
trimmed. It is read by whoever is standing at the press wondering whether the
stack in front of them is the job they think it is.

Where it goes is decided by what it must not cost. Every millimetre of margin
is a millimetre not available to the artwork, so the slug is not allowed to
enlarge the form's allowance: it lives in the margin the sheet already has
spare, and where there is no room it is left off rather than made to fit.

Three places it is deliberately not put:

**Not in the bleed.** That band is the artwork running past the trim so the
knife has tolerance, and it is exactly where the cut is allowed to wander. Ink
there can be delivered on the finished piece.

**Not in the crop-mark band.** Ten-point type needs about 4.6 mm and the band
is 3 mm, so it would not fit; and marks and text in the same strip are two
things to read where there should be one.

**Not at the head or tail.** On a full sheet that margin comes to half a
millimetre. The sides keep eight to eighteen, because a form on a press whose
sheet is taller than it is wide runs out of width first.

So the slug sets vertically in a side margin, reading up the sheet, within the
span the form occupies.
"""

from __future__ import annotations

import dataclasses
import datetime

from .font import Font
from .geometry import Rect
from .units import MM

#: Text size. Large enough to read at arm's length on the stacker without
#: leaning in, which is the whole point of it.
DEFAULT_SIZE = 10.0

#: Clearance kept between the slug and whatever is on either side of it.
GAP = 1.0 * MM

#: Between the parts of the line. A middle dot rather than a pipe or a slash,
#: both of which occur in filenames and paths.
SEPARATOR = " · "


@dataclasses.dataclass(frozen=True, slots=True)
class Slug:
    """A line of text placed on the sheet, with the baseline it sets on.

    *rotation* is a quarter turn counter-clockwise, so the text reads up the
    sheet. Ascenders point away from the form, which puts the tallest part of
    the line furthest from the artwork.
    """

    text: str
    x: float
    y: float
    size: float = DEFAULT_SIZE
    rotation: int = 90


def compose(  # pylint: disable=too-many-arguments
    *,
    source: str,
    sheet: int,
    side: str,
    sheets: int,
    schema: str,
    grid: tuple[int, int],
    press: str,
    when: datetime.datetime | None = None,
) -> str:
    """The line of text for one surface.

    Sheet and side come first after the name, because that is what someone
    holding a stack is trying to settle. The press and the grid are there to
    catch a sheet imposed for one machine being run on another.

    >>> compose(source="Catálogo.pdf", sheet=0, side="front", sheets=4,
    ...         schema="saddle-stitch", grid=(2, 1), press="indigo-5000",
    ...         when=datetime.datetime(2026, 9, 12, 21, 30))
    'Catálogo.pdf · sheet 1/4 front · saddle-stitch 2×1 · indigo-5000 · 2026-09-12 21:30'
    """
    stamp = (when or datetime.datetime.now()).strftime("%Y-%m-%d %H:%M")
    columns, rows = grid
    return SEPARATOR.join(
        (
            source,
            f"sheet {sheet + 1}/{sheets} {side}",
            f"{schema} {columns}×{rows}",
            press,
            stamp,
        )
    )


def place(  # pylint: disable=too-many-arguments
    text: str,
    *,
    page: Rect,
    form: Rect,
    reach: float,
    font: Font,
    size: float = DEFAULT_SIZE,
) -> Slug | None:
    """Where the slug sets, or ``None`` when the margin has no room.

    *form* is the trims' outer bounds and *reach* how far the marks go beyond
    them; together they say what the slug must stay clear of. Returning
    ``None`` rather than shrinking the type or moving inward is deliberate --
    the colour bar already works this way, because a mark that has been quietly
    made to fit somewhere it should not be is worse than no mark.
    """
    strip = font.height(size)
    outer = form.x0 - reach
    if outer - page.x0 < strip + 2 * GAP:
        return None

    # Centre the strip in the clear band. Turned a quarter counter-clockwise
    # the text matrix is [0 1 -1 0 x y], so a glyph at height gy lands at
    # x - gy: the strip runs from x - ascent to x - descent, and the baseline
    # sits at the middle plus half their sum.
    middle = (page.x0 + outer) / 2
    baseline = middle + (font.ascent + font.descent) * size / 2000.0

    # Up the sheet, from the bottom of the form. Staying inside the form's own
    # height keeps the line clear of the corner marks at either end.
    room = form.height
    return Slug(_fit(text, font, size, room), baseline, form.y0, size)


def _fit(text: str, font: Font, size: float, room: float) -> str:
    """*text*, reduced until it fits in *room*.

    Whole fields are dropped from the end rather than characters from either
    side, because the fields are already in order of what someone at the press
    needs: which job, which sheet, what it was imposed for, when. The stamp is
    the first to go and the file name and the sheet number are the last, and
    only if even those two will not fit does the name itself get shortened --
    from its end, since the beginning of a name is what identifies it.

    >>> from .font import load
    >>> font = load()
    >>> line = "book.pdf · sheet 1/4 front · saddle-stitch 2×1 · indigo-5000"
    >>> _fit(line, font, 10, 280)
    'book.pdf · sheet 1/4 front · saddle-stitch 2×1'
    >>> _fit(line, font, 10, 160)
    'book.pdf · sheet 1/4 front'
    >>> _fit(line, font, 10, 150)
    'book.p… · sheet 1/4 front'
    """
    per_character = font.advance * size / 1000.0
    if per_character <= 0:
        return text
    limit = int(room // per_character)
    if len(text) <= limit:
        return text

    fields = text.split(SEPARATOR)
    while len(fields) > 2:
        fields.pop()
        if len(SEPARATOR.join(fields)) <= limit:
            return SEPARATOR.join(fields)

    kept = SEPARATOR.join(fields[1:])
    spare = limit - len(kept) - len(SEPARATOR) - 1
    if spare < 1:
        return kept[:limit]
    return fields[0][:spare] + "…" + SEPARATOR + kept
