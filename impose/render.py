# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

"""Writing the imposed sheets.

Everything upstream of here is arithmetic. This is the only module that knows
what a PDF is, and its job is narrow: put each source page where the layout
says, clipped to what the layout kept, and draw the marks in a colour that will
survive separation.

Pages are placed as form XObjects and moved with a matrix. Nothing is scaled --
a finished page is the size it is, and a tool that quietly resizes artwork to
make it fit has destroyed the one measurement the customer specified.
"""

from __future__ import annotations

import pikepdf
from pikepdf import Array, Dictionary, Name

from . import __version__
from .geometry import Rect
from .layout import PlacedPage, SheetLayout
from .marks import MarkStyle, Patch, Segment, Target, circle_path
from .pdfx import Identity, carry_over, minimum_version
from .pdfx import read as read_identity


def _registration_colorspace(pdf: pikepdf.Pdf) -> Array:
    """The Separation /All colour space, as an indirect colour space array.

    The tint transform ramps every CMYK component from nothing to full, so a
    tint of 1 lays down 100% of each separation and the mark appears on every
    plate.
    """
    tint = pdf.make_indirect(
        Dictionary(
            FunctionType=2,
            Domain=[0, 1],
            C0=[0, 0, 0, 0],
            C1=[1, 1, 1, 1],
            N=1,
        )
    )
    return Array([Name.Separation, Name.All, Name.DeviceCMYK, tint])


def _overprint_state(pdf: pikepdf.Pdf) -> Dictionary:
    """A graphics state that overprints, so marks knock nothing out."""
    return pdf.make_indirect(Dictionary(OP=True, op=True, OPM=1))


def _placement_matrix(clip: Rect, paint: Rect, rotation: int) -> tuple[float, ...]:
    """The matrix carrying *clip* in source space onto *paint* on the sheet.

    Rotation is clockwise, matching /Rotate. No scaling: the extents of the
    clip and the paint rectangle are equal by construction, and if they ever
    disagree that is a layout bug worth surfacing rather than papering over.
    """
    turn = rotation % 360
    if turn == 0:
        return (1, 0, 0, 1, paint.x0 - clip.x0, paint.y0 - clip.y0)
    if turn == 90:
        return (0, -1, 1, 0, paint.x0 - clip.y0, paint.y0 + clip.x1)
    if turn == 180:
        return (-1, 0, 0, -1, paint.x0 + clip.x1, paint.y0 + clip.y1)
    if turn == 270:
        return (0, 1, -1, 0, paint.x0 + clip.y1, paint.y0 - clip.x0)
    raise ValueError(f"Rotation must be a quarter turn, got {rotation}.")


def _numbers(*values: float) -> str:
    """Format coordinates for a content stream, without exponent notation."""
    return " ".join(f"{value:.5f}".rstrip("0").rstrip(".") or "0" for value in values)


def _place(page: PlacedPage, name: Name, source_rotation: int = 0) -> str:
    """The content stream fragment that draws one placed page."""
    matrix = _placement_matrix(page.clip, page.paint, page.rotation + source_rotation)
    return (
        "q\n"
        f"{_numbers(page.paint.x0, page.paint.y0, page.paint.width, page.paint.height)}"
        " re W n\n"
        f"{_numbers(*matrix)} cm\n"
        f"{name} Do\n"
        "Q\n"
    )


def _draw_marks(
    marks: list[Segment], colour_name: Name | None, state_name: Name | None
) -> str:
    """The content stream fragment that draws every mark.

    All marks share one stream and one graphics state. Emitting a separate
    stream per line, as some tools do, leaves a sheet carrying dozens of
    fragments for no benefit.
    """
    if not marks:
        return ""
    parts = ["q\n"]
    if colour_name is not None:
        parts.append(f"{colour_name} CS\n1 SCN\n")
    else:
        parts.append("0 0 0 1 K\n")  # DeviceCMYK black: K only
    if state_name is not None:
        parts.append(f"{state_name} gs\n")
    dashed = None
    for mark in marks:
        if mark.dashed != dashed:
            parts.append("[3 3] 0 d\n" if mark.dashed else "[] 0 d\n")
            dashed = mark.dashed
        parts.append(f"{_numbers(mark.width)} w\n")
        parts.append(
            f"{_numbers(mark.x0, mark.y0)} m {_numbers(mark.x1, mark.y1)} l S\n"
        )
    parts.append("Q\n")
    return "".join(parts)


def _draw_patches(patches: list[Patch]) -> str:
    """Colour-bar patches, filled in DeviceCMYK.

    Patches are laid down in process inks directly rather than through the
    output intent, because their whole purpose is to put a known ink value on
    the sheet for a densitometer to read back.
    """
    if not patches:
        return ""
    parts = ["q\n"]
    for patch in patches:
        cyan, magenta, yellow, black = patch.cmyk
        parts.append(f"{_numbers(cyan, magenta, yellow, black)} k\n")
        parts.append(
            f"{_numbers(patch.rect.x0, patch.rect.y0, patch.rect.width, patch.rect.height)}"
            " re f\n"
        )
    parts.append("Q\n")
    return "".join(parts)


def _draw_targets(
    targets: list[Target], colour_name: Name | None, state_name: Name | None
) -> str:
    """Registration bullseyes: two rings and a crosshair through them."""
    if not targets:
        return ""
    parts = ["q\n"]
    if colour_name is not None:
        parts.append(f"{colour_name} CS\n1 SCN\n")
    else:
        parts.append("0 0 0 1 K\n")
    if state_name is not None:
        parts.append(f"{state_name} gs\n")
    for target in targets:
        parts.append(f"{_numbers(target.width)} w\n")
        for radius in (target.radius, target.radius / 2):
            parts.append(f"{_numbers(target.x + radius, target.y)} m\n")
            for curve in circle_path(target.x, target.y, radius):
                parts.append(f"{_numbers(*curve)} c\n")
            parts.append("h S\n")
        reach = target.reach
        parts.append(
            f"{_numbers(target.x - reach, target.y)} m "
            f"{_numbers(target.x + reach, target.y)} l S\n"
        )
        parts.append(
            f"{_numbers(target.x, target.y - reach)} m "
            f"{_numbers(target.x, target.y + reach)} l S\n"
        )
    parts.append("Q\n")
    return "".join(parts)


class Renderer:
    """Builds an imposed document, one surface at a time."""

    def __init__(self, style: MarkStyle | None = None) -> None:
        self.pdf = pikepdf.Pdf.new()
        self.style = style or MarkStyle()
        self._colorspace: Name | None = None
        self._state: Name | None = None
        self._min_version = "1.4"

    def carry_over(self, source: pikepdf.Pdf) -> Identity:
        """Copy *source*'s printing condition and PDF/X claim onto the output.

        Returns what was found, so a caller can report a source that claimed
        PDF/X without ever carrying an OutputIntent to back it.
        """
        identity = read_identity(source)
        carry_over(self.pdf, source, identity)
        required = minimum_version(identity.version)
        if identity.declares_pdfx:
            # A PDF/X file conformed at the version it was written at, and the
            # older parts pin that version rather than set a floor. Writing it
            # newer than it arrived would break the claim we are preserving.
            self._min_version = max(str(source.pdf_version), required or "1.3")
        else:
            for candidate in (str(source.pdf_version), required):
                if candidate:
                    self._min_version = max(self._min_version, candidate)
        return identity

    def add(  # pylint: disable=too-many-arguments,too-many-locals
        self,
        layout: SheetLayout,
        source: pikepdf.Pdf,
        *,
        marks: list[Segment] | None = None,
        targets: list[Target] | None = None,
        bar: list[Patch] | None = None,
        source_rotation: int = 0,
        trim_is_sheet: bool = False,
    ) -> pikepdf.Page:
        """Draw one imposed surface as a new page."""
        sheet = Rect.from_size(layout.sheet)
        page = self.pdf.add_blank_page(
            page_size=(layout.sheet.width, layout.sheet.height)
        )
        stream: list[str] = []
        for placed in layout.printed:
            foreign = pikepdf.Page(source.pages[placed.source])
            form = foreign.as_form_xobject()
            # as_form_xobject() sets /BBox from the source TrimBox, which
            # would clip the bleed away before it could be placed. The form
            # must carry the whole sheet the page was drawn on; what actually
            # shows is decided by this renderer's own clip.
            form.BBox = Array(list(foreign.mediabox))
            xobject = self.pdf.copy_foreign(form)
            name = page.add_resource(xobject, Name.XObject)
            stream.append(_place(placed, name, source_rotation))
        if marks or targets:
            resources = self._mark_resources(page)
            if marks:
                stream.append(_draw_marks(marks, *resources))
            if targets:
                stream.append(_draw_targets(targets, *resources))
        if bar:
            stream.append(_draw_patches(bar))
        page.contents_add(pikepdf.Stream(self.pdf, "".join(stream).encode("ascii")))
        _set_boxes(page, sheet, layout, trim_is_sheet=trim_is_sheet)
        return page

    def _mark_resources(self, page: pikepdf.Page) -> tuple[Name | None, Name | None]:
        """Colour space and graphics state for marks, added to *page*."""
        if self.style.colour == "black":
            return (None, None)
        colorspace = page.add_resource(
            _registration_colorspace(self.pdf), Name.ColorSpace
        )
        state = page.add_resource(_overprint_state(self.pdf), Name.ExtGState)
        return (colorspace, state)

    def save(self, path, *, linearize: bool = False) -> None:
        """Write the document, compressed and with unused objects dropped."""
        with self.pdf.open_metadata(set_pikepdf_as_editor=False) as meta:
            meta["dc:creator"] = ["impose"]
            meta["pdf:Producer"] = f"impose {__version__}"
        # Object streams are a PDF 1.5 feature. A file that must stay at 1.3 or
        # 1.4 -- which the older PDF/X parts require -- cannot have them, and
        # compressing it that way would quietly break the conformance this went
        # to trouble to carry across.
        streams = (
            pikepdf.ObjectStreamMode.generate
            if self._min_version >= "1.5"
            else pikepdf.ObjectStreamMode.disable
        )
        self.pdf.save(
            path,
            compress_streams=True,
            object_stream_mode=streams,
            linearize=linearize,
            min_version=self._min_version,
        )


def _set_boxes(
    page: pikepdf.Page,
    sheet: Rect,
    layout: SheetLayout,
    *,
    trim_is_sheet: bool = False,
) -> None:
    """Describe the imposed sheet in its own page boxes.

    MediaBox is the sheet as it goes through the press. TrimBox is the whole
    form, so a downstream tool can see the finished area, and BleedBox is that
    plus whatever bleed survived.

    With *trim_is_sheet* the trim becomes the sheet itself. That is for a form
    made to be imposed again: the next pass cuts the blanks apart on the form's
    own outer edge, so that edge is the finished size as far as it is
    concerned, and the marks inside stay with the piece instead of being
    clipped away as if they were somebody's bleed.
    """
    page.obj["/MediaBox"] = Array([sheet.x0, sheet.y0, sheet.x1, sheet.y1])
    boxes = (
        (("/TrimBox", sheet), ("/BleedBox", sheet))
        if trim_is_sheet
        else (("/TrimBox", layout.trim_bounds), ("/BleedBox", layout.bleed_bounds))
    )
    for name, rect in boxes:
        clipped = Rect(
            max(rect.x0, sheet.x0),
            max(rect.y0, sheet.y0),
            min(rect.x1, sheet.x1),
            min(rect.y1, sheet.y1),
        )
        page.obj[name] = Array([clipped.x0, clipped.y0, clipped.x1, clipped.y1])
