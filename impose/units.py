# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

"""Lengths and paper sizes, in PDF points.

One inch is 72 points, exactly as PDF user space defines it. That sounds too
obvious to state, but the TeX point of 1/72.27 inch is only 0.375% away, and a
tool that confuses the two describes a 470 mm press sheet as 471.76 mm. Every
length entering the library passes through here.

    >>> round(length("1mm"), 6)
    2.834646
    >>> format_mm(paper("SRA3"))
    '320 × 450 mm'
    >>> round(to_mm(paper("A4").width), 9)
    210.0
"""

from __future__ import annotations

import re

from .geometry import Size

#: One inch, in PDF points.
INCH = 72.0

#: One millimetre, in PDF points.
MM = INCH / 25.4

# Unit suffixes accepted in a length. `pt` is the PostScript point, which is
# what PDF means by a point and what prepress means by it; there is no TeX
# point here. `bp` is accepted as its explicit synonym.
_UNITS: dict[str, float] = {
    "": 1.0,
    "pt": 1.0,
    "bp": 1.0,
    "pc": 12.0,
    "in": INCH,
    "mm": MM,
    "cm": 10 * MM,
    "m": 1000 * MM,
}

# Sheet sizes in millimetres, as published. The ISO series are defined by
# standard rather than derived, so they are tabulated rather than halved from
# A0 -- the rounding is part of the definition.
_PAPER: dict[str, str] = {
    # ISO 216 A series, defined in millimetres.
    "4a0": "1682mm x 2378mm",
    "2a0": "1189mm x 1682mm",
    "a0": "841mm x 1189mm",
    "a1": "594mm x 841mm",
    "a2": "420mm x 594mm",
    "a3": "297mm x 420mm",
    "a4": "210mm x 297mm",
    "a5": "148mm x 210mm",
    "a6": "105mm x 148mm",
    "a7": "74mm x 105mm",
    "a8": "52mm x 74mm",
    "a9": "37mm x 52mm",
    "a10": "26mm x 37mm",
    # ISO 216 B series
    "b0": "1000mm x 1414mm",
    "b1": "707mm x 1000mm",
    "b2": "500mm x 707mm",
    "b3": "353mm x 500mm",
    "b4": "250mm x 353mm",
    "b5": "176mm x 250mm",
    "b6": "125mm x 176mm",
    "b7": "88mm x 125mm",
    "b8": "62mm x 88mm",
    "b9": "44mm x 62mm",
    "b10": "31mm x 44mm",
    # ISO 269 C series (envelopes)
    "c0": "917mm x 1297mm",
    "c1": "648mm x 917mm",
    "c2": "458mm x 648mm",
    "c3": "324mm x 458mm",
    "c4": "229mm x 324mm",
    "c5": "162mm x 229mm",
    "c6": "114mm x 162mm",
    "c7": "81mm x 114mm",
    # ISO 217 RA / SRA -- untrimmed press stock. SRA3 is the digital press
    # workhorse: an A3 job with room for bleed and marks.
    "ra0": "860mm x 1220mm",
    "ra1": "610mm x 860mm",
    "ra2": "430mm x 610mm",
    "ra3": "305mm x 430mm",
    "ra4": "215mm x 305mm",
    "sra0": "900mm x 1280mm",
    "sra1": "640mm x 900mm",
    "sra2": "450mm x 640mm",
    "sra3": "320mm x 450mm",
    "sra4": "225mm x 320mm",
    # North American, defined in inches -- kept in inches so they stay exact.
    "letter": "8.5in x 11in",
    "legal": "8.5in x 14in",
    "tabloid": "11in x 17in",
    "ledger": "17in x 11in",
    "executive": "7.25in x 10.5in",
    "statement": "5.5in x 8.5in",
    "ansia": "8.5in x 11in",
    "ansib": "11in x 17in",
    "ansic": "17in x 22in",
    "ansid": "22in x 34in",
    "ansie": "34in x 44in",
}

_NAME_RE = re.compile(r"[^a-z0-9]+")


def _normalize_name(value: str) -> str:
    """Fold a sheet name so `ANSI-A`, `ansi a`, and `ansia` are one key."""
    return _NAME_RE.sub("", value.lower())


_LENGTH_RE = re.compile(
    r"^\s*(?P<number>[+-]?(?:\d+\.?\d*|\.\d+))\s*(?P<unit>[a-zA-Z]*)\s*$"
)

# "210mm x 297mm", "210mmx297mm", "21cm × 29.7cm", "595 842"
_SEPARATOR_RE = re.compile(r"\s*(?:[x×*]|\s)\s*", re.IGNORECASE)


def length(value: str | float | int) -> float:
    """A length in PDF points, from a number or a string such as ``"3mm"``.

    Numbers pass through: they are already points.

    >>> length("1in")
    72.0
    >>> length("12")
    12.0
    >>> length(12)
    12.0
    >>> length("0.5pt")
    0.5
    """
    if not isinstance(value, str):
        return float(value)
    match = _LENGTH_RE.match(value)
    if match is None:
        raise ValueError(f"Cannot read {value!r} as a length.")
    unit = match.group("unit").lower()
    if unit not in _UNITS:
        raise ValueError(
            f"Unknown unit {unit!r} in {value!r}. "
            f"Known units: {', '.join(sorted(u for u in _UNITS if u))}."
        )
    return float(match.group("number")) * _UNITS[unit]


def paper(value: str | Size | tuple[float, float]) -> Size:
    """A :class:`~impose.geometry.Size` from a paper name or ``WIDTHxHEIGHT``.

    >>> paper("A4").width
    595.2755905511812
    >>> paper("letter")
    Size(width=612.0, height=792.0)
    >>> paper("100x200")
    Size(width=100.0, height=200.0)
    """
    if isinstance(value, Size):
        return value
    if not isinstance(value, str):
        width, height = value
        return Size(float(width), float(height))

    definition = _PAPER.get(_normalize_name(value))
    if definition is not None:
        value = definition

    parts = [part for part in _SEPARATOR_RE.split(value.strip()) if part]
    if len(parts) != 2:
        raise ValueError(
            f"Cannot read {value!r} as a paper size. "
            f"Use a name such as A4 or SRA3, or WIDTHxHEIGHT such as 320mmx450mm."
        )
    return Size(length(parts[0]), length(parts[1]))


def to_mm(points: float) -> float:
    """Millimetres from PDF points -- for reporting, and for tests.

    >>> round(to_mm(72), 4)
    25.4
    """
    return points / MM


def format_mm(size: Size) -> str:
    """A size written the way a press operator would say it.

    >>> format_mm(paper("SRA3"))
    '320 × 450 mm'
    """

    def trim(value: float) -> str:
        text = f"{value:.2f}".rstrip("0").rstrip(".")
        return text or "0"

    return f"{trim(to_mm(size.width))} × {trim(to_mm(size.height))} mm"


def paper_names() -> tuple[str, ...]:
    """Every sheet name :func:`paper` accepts, sorted."""
    return tuple(sorted(_PAPER))
