# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

"""What a cutter and a press check need beyond the crop marks.

Crop marks tell a person where to put a guillotine. A Zünd or a Kongsberg
follows a path, and it finds that path by the spot colour it was given and by
the ISO 19593-1 Cutting step on the layer. The path is the outline of each
piece, closed, so the knife goes around the piece rather than across the sheet.

A Fogra or Ugra wedge is a licensed drawing with its own patch geometry. It is
embedded whole, at the size it was made, or the job is refused. Redrawing one
would be a different wedge.
"""

from __future__ import annotations

import argparse
import dataclasses
import pathlib

import pikepdf

from . import ImposeError
from .boxes import read_boxes
from .geometry import Rect, Size
from .units import format_mm

#: Work the knife separates. A bound schema is trimmed on a guillotine after
#: it is folded or gathered, and a closed path around each page would cut the
#: book apart on the flat sheet.
SEPARATED = frozenset({"nup", "cutstack", "steprepeat", "gang", "cover"})

#: Spot names a press already owns. Using one of these would print the path.
_PROCESS = frozenset({"all", "none", "cyan", "magenta", "yellow", "black"})

#: The name Fiery, ONYX, and most Zünd workflows are set to extract.
DEFAULT_SPOT = "CutContour"

_BAR_NOTE = "The working colour bar is left off. The control strip is the bar."


@dataclasses.dataclass
class Strip:
    """A control strip opened for embedding, still at its own size."""

    pdf: pikepdf.Pdf
    media: Rect

    def close(self) -> None:
        """Release the file."""
        self.pdf.close()


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Cutter path, control strip, and the margin furniture they share an edge with."""
    parser.add_argument(
        "--registration",
        action="store_true",
        help="Add a registration bullseye on each side of the form, in "
        "registration colour. Placed only where the margin has room.",
    )
    parser.add_argument(
        "--colour-bar",
        "--color-bar",
        dest="colour_bar",
        action="store_true",
        help="Add a row of process-ink patches along the tail of the sheet, "
        "for reading density on press.",
    )
    parser.add_argument(
        "--cut",
        action="store_true",
        help="Draw a closed path around each piece, in a spot colour a cutter "
        "reads, on an ISO 19593 Cutting layer. For work that is cut apart.",
    )
    parser.add_argument(
        "--cut-name",
        default=DEFAULT_SPOT,
        metavar="NAME",
        help="Spot colour the cutter is set to pick up. Default: %(default)s.",
    )
    parser.add_argument(
        "--strip",
        default=None,
        metavar="FILE",
        help="A control strip to embed whole at the tail, at its own size. "
        "The file you are licensed to use; it is not redrawn.",
    )


def prepare_cut(schema: str, cut: bool, name: str) -> str | None:
    """The spot name to cut in, or none when the job asked for no path."""
    if not cut:
        return None
    if schema not in SEPARATED:
        raise ImposeError(
            f"A cutter path is the outline of each piece that is cut apart. "
            f"{schema} is bound, and the trim is a guillotine cut."
        )
    return spot_name(name)


def spot_name(name: str) -> str:
    """The separation a cutter is set to read.

    >>> spot_name("  CutContour ")
    'CutContour'
    """
    cleaned = str(name).strip()
    if not cleaned or cleaned.casefold() in _PROCESS:
        raise ImposeError(
            f"A cutter spot cannot be named {name!r}. A press treats that "
            "name as a process ink and would print the path."
        )
    return cleaned


def outlines(layout) -> list[Rect]:
    """One closed trim per piece. An empty cell is not a piece."""
    return [page.trim for page in layout.printed]


def open_strip(path: str | pathlib.Path) -> Strip:
    """Open a one-page control strip. The page is kept whole."""
    file = pathlib.Path(path)
    try:
        pdf = pikepdf.open(file)
    except Exception as error:
        raise ImposeError(f"Cannot open {file}: {error}") from error
    try:
        return _checked(file, pdf)
    except Exception:
        pdf.close()
        raise


def place_strip(form: Rect, area: Rect, size: Size, reach: float) -> Rect:
    """Where the strip sits: native size, flush to the tail, clear of the marks.

    The same edge the working colour bar uses. Nothing is scaled: a wedge
    whose patches have moved is a different wedge, so a strip that does not
    fit is refused rather than squeezed.
    """
    room = form.y0 - reach - area.y0
    if size.width > area.width + 0.01 or size.height > room + 0.01:
        clear = Size(area.width, max(0.0, room))
        raise ImposeError(
            f"The control strip is {format_mm(size)}. The tail has "
            f"{format_mm(clear)} clear of the form."
        )
    x = area.x0 + (area.width - size.width) / 2
    return Rect(x, area.y0, x + size.width, area.y0 + size.height)


def strip_slots(wedge: Strip | None, layouts, style, colour_bar: bool):
    """A slot per surface, and a note when the working bar would share it."""
    if wedge is None:
        return (), None
    reach = style.reach if style else 0.0
    slots = tuple(
        place_strip(layout.trim_bounds, layout.imageable, wedge.media.size, reach)
        for layout in layouts
    )
    return slots, _BAR_NOTE if colour_bar else None


def layer_note(version: str | None, spot: str) -> tuple[str, ...]:
    """Warn when the carried PDF/X claim cannot hold a layer."""
    if version and not _layers(version):
        return (
            f"{version} has no layers. The cut path is still there, "
            f"in the spot colour {spot}.",
        )
    return ()


def _layers(version: str) -> bool:
    """Whether this PDF/X part allows optional content."""
    key = version.strip().upper().replace(" ", "")
    return not key.startswith(("PDF/X-1", "PDF/X-3"))


def _checked(file: pathlib.Path, pdf: pikepdf.Pdf) -> Strip:
    """Refuse anything other than a single upright page."""
    count = len(pdf.pages)
    if count != 1:
        raise ImposeError(
            f"{file.name} has {count} pages. A control strip is one page, "
            "embedded whole."
        )
    boxes = read_boxes(pdf.pages[0])
    if boxes.rotation:
        raise ImposeError(
            f"{file.name} carries /Rotate {boxes.rotation}. Embed the strip "
            "upright, at the size it was made."
        )
    if boxes.media.width <= 0 or boxes.media.height <= 0:
        raise ImposeError(f"{file.name} has no page to embed.")
    return Strip(pdf, boxes.media)
