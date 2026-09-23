# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

"""The cover flat, one to a surface.

A perfect-bound cover is not a spread of the text. The text is gathered and
glued; the cover is a separate sheet wrapped around that block, and this
schema only places that sheet. The flat itself -- back, hinges, spine, front,
and where it scores -- is built by :mod:`impose.cover` before it gets here.

One page is the outside. Two pages are the outside and the inside, and the
inside is placed as drawn: a cover is a single cell, so the press flip has no
column to swap.
"""

from __future__ import annotations

from ..plan import Placement, Plan, Surface


def impose(pages: int) -> Plan:
    """Place a cover flat, outside and optionally inside.

    >>> print(impose(1).describe())
    sheet 1 front
         1
    >>> print(impose(2).describe())
    sheet 1 front
         1
    sheet 1 back
         2
    """
    if pages < 1 or pages > 2:
        raise ValueError(
            "A cover is the outside, or the outside and the inside; "
            f"got {pages} pages."
        )
    surfaces = [Surface(0, "front", (Placement(0, 0, 0),))]
    if pages == 2:
        surfaces.append(Surface(0, "back", (Placement(1, 0, 0),)))
    return Plan(
        columns=1,
        rows=1,
        surfaces=tuple(surfaces),
        pages=pages,
        schema="cover",
    )
