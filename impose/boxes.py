# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

"""ISO 32000 page boxes: what a print-ready PDF already tells us.

A file prepared for print carries its own answers. TrimBox is the finished
page -- where the guillotine goes. BleedBox is TrimBox plus the margin of
image that may be trimmed away. MediaBox is the sheet the page was drawn on,
usually with room for the marks the supplier added.

Imposition works from TrimBox. Laying out from MediaBox, as tools do when they
treat a page as a picture, places whatever slug and marks the supplier left in
the file, and gets the finished size wrong by however much bleed there is.
"""

from __future__ import annotations

import dataclasses
import re

import pikepdf

from . import ImposeError
from .geometry import Insets, Rect, Size

# Boxes other than MediaBox and CropBox are not inheritable page attributes
# (ISO 32000-1 table 30), so an explicit TrimBox is one written on the page.
_INHERITABLE = frozenset({"/MediaBox", "/CropBox", "/Rotate"})

_PDFX_RE = re.compile(r"PDF/X[-\w:.]*", re.IGNORECASE)

# A page displays rotated clockwise by /Rotate. Turning a portrait sheet a
# quarter turn clockwise carries its left edge to the top of the display, so
# `_ROTATED_EDGE[90]["top"] == "left"`: read a display edge, get the page edge
# that lands there.
_ROTATED_EDGE: dict[int, dict[str, str]] = {
    0: {"left": "left", "right": "right", "bottom": "bottom", "top": "top"},
    90: {"top": "left", "right": "top", "bottom": "right", "left": "bottom"},
    180: {"left": "right", "right": "left", "bottom": "top", "top": "bottom"},
    270: {"bottom": "left", "left": "top", "top": "right", "right": "bottom"},
}


@dataclasses.dataclass(frozen=True, slots=True)
class PageBoxes:
    """The boxes of one page, in unrotated PDF user space.

    Rectangles are as written in the file. :attr:`rotation` is applied by the
    properties that describe what a reader sees, and by the renderer; keeping
    the raw boxes means nothing is rotated twice.
    """

    media: Rect
    crop: Rect
    bleed: Rect
    trim: Rect
    rotation: int = 0
    has_explicit_trim: bool = False
    has_explicit_bleed: bool = False

    @property
    def trim_size(self) -> Size:
        """The finished page as a reader sees it, rotation applied."""
        return self.trim.size.rotated(self.rotation)

    @property
    def bleed_insets(self) -> Insets:
        """How far BleedBox reaches past TrimBox, in unrotated page space.

        Zero on every edge when the file declares no BleedBox. The
        specification defaults BleedBox to CropBox, but that default says
        nothing about bleed: the space between TrimBox and CropBox is just as
        likely to be the supplier's own slug and marks. Treating it as bleed
        would place those marks into the gutter of the imposed sheet, so an
        undeclared bleed is no bleed.
        """
        if not self.has_explicit_bleed:
            return Insets()
        return Insets(
            left=max(0.0, self.trim.x0 - self.bleed.x0),
            right=max(0.0, self.bleed.x1 - self.trim.x1),
            bottom=max(0.0, self.trim.y0 - self.bleed.y0),
            top=max(0.0, self.bleed.y1 - self.trim.y1),
        )

    @property
    def displayed_bleed_insets(self) -> Insets:
        """:attr:`bleed_insets` as they fall once the page is rotated."""
        return rotate_insets(self.bleed_insets, self.rotation)

    @property
    def has_bleed(self) -> bool:
        """Whether any edge carries bleed."""
        return bool(self.bleed_insets)


def rotate_insets(insets: Insets, rotation: int) -> Insets:
    """Map *insets* from page space to display space under ``/Rotate``.

    >>> rotate_insets(Insets(left=3), 90)
    Insets(left=0.0, right=0.0, bottom=0.0, top=3)
    """
    mapping = _ROTATED_EDGE[rotation % 360]
    return Insets(**{edge: getattr(insets, source) for edge, source in mapping.items()})


def _rect(array) -> Rect:
    """A pikepdf box array as a normalized Rect."""
    x0, y0, x1, y1 = (float(value) for value in array)
    return Rect(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))


def _intersect(inner: Rect, outer: Rect, *, what: str) -> Rect:
    """Clip *inner* to *outer*, as the specification requires of every box."""
    x0, y0 = max(inner.x0, outer.x0), max(inner.y0, outer.y0)
    x1, y1 = min(inner.x1, outer.x1), min(inner.y1, outer.y1)
    if x1 <= x0 or y1 <= y0:
        raise ImposeError(f"{what} does not overlap the MediaBox.")
    return Rect(x0, y0, x1, y1)


def _rotation(page: pikepdf.Page) -> int:
    """The page's /Rotate, normalized to 0, 90, 180, or 270."""
    value = page.obj.get("/Rotate", 0)
    try:
        degrees = int(value)
    except (TypeError, ValueError):
        return 0
    if degrees % 90:
        # A non-quarter-turn /Rotate is invalid; ignoring it beats guessing.
        return 0
    return degrees % 360


def read_boxes(page: pikepdf.Page) -> PageBoxes:
    """Read the boxes of *page*, applying the specification's defaults.

    CropBox defaults to MediaBox; BleedBox and TrimBox default to CropBox. Each
    is clipped to the MediaBox, since content outside it is not imageable.
    """
    media = _rect(page.mediabox)
    crop = _intersect(_rect(page.cropbox), media, what="CropBox")
    has_trim = "/TrimBox" in page.obj
    has_bleed = "/BleedBox" in page.obj
    trim = _intersect(_rect(page.trimbox), media, what="TrimBox") if has_trim else crop
    bleed = (
        _intersect(_rect(page.bleedbox), media, what="BleedBox") if has_bleed else crop
    )
    return PageBoxes(
        media=media,
        crop=crop,
        bleed=bleed,
        trim=trim,
        rotation=_rotation(page),
        has_explicit_trim=has_trim,
        has_explicit_bleed=has_bleed,
    )


def pdfx_version(pdf: pikepdf.Pdf) -> str | None:
    """The PDF/X conformance the document claims, if any.

    Checked in the order a validator would: the document info key, then XMP.
    """
    try:
        if pdf.docinfo is not None:
            declared = pdf.docinfo.get("/GTS_PDFXVersion")
            if declared is not None:
                return str(declared)
    except (KeyError, AttributeError):
        pass
    try:
        with pdf.open_metadata() as meta:
            for key in ("pdfxid:GTS_PDFXVersion", "pdfx:GTS_PDFXVersion"):
                if key in meta:
                    return str(meta[key])
            match = _PDFX_RE.search(str(meta))
            if match:
                return match.group(0)
    # XMP is optional, frequently malformed, and parsed by a third-party
    # stack: any failure here means "no claim found", never a crash.
    except Exception:  # pylint: disable=broad-exception-caught
        pass
    return None


def has_output_intent(pdf: pikepdf.Pdf) -> bool:
    """Whether the document declares an OutputIntent -- the printing condition."""
    intents = pdf.Root.get("/OutputIntents")
    return bool(intents) and len(intents) > 0


def require_trim(boxes: PageBoxes, *, page_number: int, pdfx: str | None) -> None:
    """Refuse a PDF/X page with no TrimBox.

    PDF/X requires a TrimBox (or an ArtBox) on every page. A file that claims
    conformance and omits it is not something to guess about: the finished size
    is exactly what we would be guessing.
    """
    if pdfx and not boxes.has_explicit_trim:
        raise ImposeError(
            f"Page {page_number} declares {pdfx} but carries no TrimBox. "
            f"The finished page size cannot be determined."
        )
