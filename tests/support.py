# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

"""Building print-ready fixtures.

Real prepress files carry a TrimBox, bleed around it, and a slug area holding
the supplier's own marks. These builders make the same shape, and paint the
bleed a different colour from the trim so a test can tell whether a clip kept
the bleed or cut it away.
"""

from __future__ import annotations

import pikepdf

from impose.geometry import Insets, Rect, Size
from impose.units import MM

#: Colours, as DeviceRGB fill operands.
TRIM_FILL = (1, 0, 0)  # red: inside the finished page
BLEED_FILL = (0, 0, 1)  # blue: the margin that gets trimmed off
SLUG_FILL = (0, 1, 0)  # green: outside BleedBox, never placed


def _fill(rect: Rect, colour: tuple[float, float, float]) -> bytes:
    red, green, blue = colour
    return (
        f"{red} {green} {blue} rg "
        f"{rect.x0} {rect.y0} {rect.width} {rect.height} re f\n"
    ).encode("ascii")


def make_pdf(  # pylint: disable=too-many-arguments
    pages: int = 4,
    *,
    trim: Size | None = None,
    bleed: float = 3 * MM,
    slug: float = 6 * MM,
    with_trimbox: bool = True,
    with_bleedbox: bool = True,
    rotation: int = 0,
) -> pikepdf.Pdf:
    """A document whose pages carry TrimBox, BleedBox, and a slug area.

    The MediaBox is TrimBox grown by *bleed* then *slug* on every edge, which
    is how a supplier's export usually arrives.
    """
    trim = trim or Size(105 * MM, 148 * MM)  # A6
    margin = bleed + slug
    media = Size(trim.width + 2 * margin, trim.height + 2 * margin)
    trim_rect = Rect.from_size(trim, at=(margin, margin))
    bleed_rect = trim_rect.expanded(Insets.uniform(bleed))

    pdf = pikepdf.Pdf.new()
    for index in range(pages):
        page = pdf.add_blank_page(page_size=(media.width, media.height))
        stream = (
            _fill(Rect.from_size(media), SLUG_FILL)
            + _fill(bleed_rect, BLEED_FILL)
            + _fill(trim_rect, TRIM_FILL)
            + _page_number(trim_rect, index + 1)
        )
        page.contents_add(pikepdf.Stream(pdf, stream))
        if with_bleedbox:
            page.obj["/BleedBox"] = pikepdf.Array(
                [bleed_rect.x0, bleed_rect.y0, bleed_rect.x1, bleed_rect.y1]
            )
        if with_trimbox:
            page.obj["/TrimBox"] = pikepdf.Array(
                [trim_rect.x0, trim_rect.y0, trim_rect.x1, trim_rect.y1]
            )
        if rotation:
            page.obj["/Rotate"] = rotation
    return pdf


def _page_number(trim: Rect, number: int) -> bytes:
    """A filled bar whose width encodes the page number.

    Cheap to draw and, unlike text, needs no font: a test can read the number
    back by measuring, and a human can see the sequence in a viewer.
    """
    unit = trim.width / 40
    return (
        f"0 0 0 rg {trim.x0 + unit} {trim.y0 + unit} " f"{unit * number} {unit} re f\n"
    ).encode("ascii")


def declare_pdfx(pdf: pikepdf.Pdf, version: str = "PDF/X-4") -> pikepdf.Pdf:
    """Mark *pdf* as claiming PDF/X conformance."""
    with pdf.open_metadata(set_pikepdf_as_editor=False) as meta:
        meta["pdfxid:GTS_PDFXVersion"] = version
    return pdf
