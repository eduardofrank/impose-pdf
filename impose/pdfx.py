# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

"""Carrying a source's PDF/X identity onto the imposed sheets.

A PDF/X file says two things beyond ordinary PDF. It names the printing
condition it was prepared for -- an OutputIntent, holding or naming the ICC
profile the separations assume -- and it declares which part of ISO 15930 it
claims to satisfy. Imposition rearranges pages onto larger sheets; it does not
change the inks, so both of those should survive to the file that goes to the
press. A tool that drops them hands the printer a file that no longer says what
it was made for, and a PDF/X workflow will bounce it.

What this module does *not* do is make a file conformant. Conformance is a
preflight question -- embedded fonts, colour spaces, transparency, versions --
and answering it is a different program. This carries the declaration and the
printing condition across from a source that already had them. If the source
was conformant and the imposition adds nothing that breaks it, the output
should be too, but only a preflight tool can tell you that it is.
"""

from __future__ import annotations

import dataclasses

import pikepdf
from pikepdf import Array, Name

from .boxes import pdfx_version

#: PDF/X requires /Trapped to be a definite answer. A file that omits it, or
#: says /Unknown, is not conformant -- and for a digital press job the true
#: answer is almost always that it is not trapped.
_UNTRAPPED = Name("/False")

_DEFINITE_TRAPPING = ("/True", "/False")

#: The PDF version each PDF/X part is defined against. Writing an older one
#: than the claim requires contradicts the claim, so the output is raised to
#: meet it -- never lowered, since the source may legitimately be newer.
_MINIMUM_VERSION = {
    "PDF/X-1A:2001": "1.3",
    "PDF/X-3:2002": "1.3",
    "PDF/X-1A:2003": "1.4",
    "PDF/X-3:2003": "1.4",
    "PDF/X-4": "1.6",
    "PDF/X-4P": "1.6",
    "PDF/X-5G": "1.6",
    "PDF/X-5N": "1.6",
    "PDF/X-5PG": "1.6",
    "PDF/X-6": "2.0",
}


def minimum_version(version: str | None) -> str | None:
    """The lowest PDF version a claimed PDF/X part may be written as.

    Matching is loose because the string in a file is not consistent: it may
    carry a year, a conformance letter, or different case.

    >>> minimum_version("PDF/X-4")
    '1.6'
    >>> minimum_version("PDF/X-1a:2003")
    '1.4'
    >>> minimum_version(None) is None
    True
    """
    if not version:
        return None
    key = version.strip().upper().replace(" ", "")
    if key in _MINIMUM_VERSION:
        return _MINIMUM_VERSION[key]
    # Fall back to the longest declared part that prefixes the claim, so an
    # unfamiliar suffix still lands on the right family.
    matches = [known for known in _MINIMUM_VERSION if key.startswith(known)]
    if matches:
        return _MINIMUM_VERSION[max(matches, key=len)]
    for family, floor in (("PDF/X-6", "2.0"), ("PDF/X-5", "1.6"), ("PDF/X-4", "1.6")):
        if key.startswith(family):
            return floor
    return None


@dataclasses.dataclass(frozen=True, slots=True)
class Identity:
    """What a source declares about the condition it was prepared for."""

    version: str | None = None
    trapped: str | None = None
    output_intents: int = 0

    @property
    def declares_pdfx(self) -> bool:
        """Whether the source claims a PDF/X part at all."""
        return bool(self.version)

    @property
    def is_complete(self) -> bool:
        """Whether the claim is backed by a printing condition.

        A file claiming PDF/X with no OutputIntent was never conformant. That
        is worth knowing before the job goes out, because the imposed file will
        inherit exactly the same gap.
        """
        return self.declares_pdfx and self.output_intents > 0

    def describe(self) -> str:
        """A line for an operator, or for a log."""
        if not self.declares_pdfx:
            return "no PDF/X claim" + (
                f"; {self.output_intents} output intent(s)"
                if self.output_intents
                else ""
            )
        condition = (
            f"{self.output_intents} output intent(s)"
            if self.output_intents
            else "no output intent, so the claim was never backed"
        )
        return f"{self.version}; {condition}"


def read(pdf: pikepdf.Pdf) -> Identity:
    """What *pdf* declares about its printing condition."""
    intents = pdf.Root.get("/OutputIntents")
    trapped = None
    try:
        value = pdf.docinfo.get("/Trapped")
        if value is not None:
            trapped = str(value)
    except (AttributeError, KeyError):  # pragma: no cover - absent docinfo
        trapped = None
    return Identity(
        version=pdfx_version(pdf),
        trapped=trapped,
        output_intents=len(intents) if intents is not None else 0,
    )


def carry_over(target: pikepdf.Pdf, source: pikepdf.Pdf, identity: Identity) -> None:
    """Copy *source*'s printing condition and PDF/X claim onto *target*.

    The OutputIntent is copied whether or not a PDF/X part is claimed: it names
    the condition the separations were built for, and that is worth keeping on
    any file heading for a press.
    """
    _copy_output_intents(target, source)
    _set_trapping(target, identity)
    if identity.declares_pdfx:
        _declare_version(target, identity.version)


def _copy_output_intents(target: pikepdf.Pdf, source: pikepdf.Pdf) -> None:
    """Bring the source's OutputIntents across, ICC profile and all."""
    intents = source.Root.get("/OutputIntents")
    if intents is None or len(intents) == 0:
        return
    target.Root.OutputIntents = Array(
        [target.copy_foreign(intent) for intent in intents]
    )


def _set_trapping(target: pikepdf.Pdf, identity: Identity) -> None:
    """Give /Trapped a definite value, since PDF/X requires one."""
    if identity.trapped in _DEFINITE_TRAPPING:
        target.docinfo["/Trapped"] = Name(identity.trapped)
    else:
        target.docinfo["/Trapped"] = _UNTRAPPED


def _declare_version(target: pikepdf.Pdf, version: str | None) -> None:
    """Restate the PDF/X part, where a validator looks for it.

    Both places: the document info dictionary, which older tools read, and
    XMP, which is where ISO 15930 has required it since PDF/X-4.
    """
    if not version:
        return
    target.docinfo["/GTS_PDFXVersion"] = version
    with target.open_metadata(set_pikepdf_as_editor=False) as meta:
        meta["pdfxid:GTS_PDFXVersion"] = version
