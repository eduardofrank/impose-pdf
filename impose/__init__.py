# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

"""Imposition for commercial print.

`impose` lays finished pages onto press sheets: saddle stitch, perfect bound,
signatures folded from one sheet and the cover that wraps them, n-up, step and
repeat, cut and stack, and a gang of different finished sizes cut apart
afterwards. It works from the ISO 32000 page boxes a print-ready PDF already
carries -- TrimBox is the finished page, BleedBox is what may be trimmed away
-- and targets a press profile it knows, or one a caller describes: its sheet,
the border it cannot image, and the edge the grippers hold.

All lengths are PDF points: 1 inch is 72 points, exactly as in PDF user space.
All geometry is in PDF coordinates, with the origin at the bottom-left of the
sheet and y growing upward.
"""

__version__ = "0.1.0"


class ImposeError(Exception):
    """A job that cannot be imposed as asked.

    Raised for conditions the operator can act on -- a form that will not fit
    the press, a source without a TrimBox, a signature that is not achievable.
    It derives from :class:`Exception`, so an embedding application's
    ``except Exception`` handles it.
    """


class SourceError(ImposeError):
    """A file handed in cannot be trusted to say what it contains.

    A document still being copied, one whose cross-reference table had to be
    reconstructed, one that cannot be opened at all, or one with no pages.
    Separate from :class:`ImposeError` because the answer is different: an
    unattended caller should stop and wait for, or send back, the file --
    where a job that merely cannot be imposed as described needs the
    description changed. It derives from :class:`ImposeError`, so an existing
    ``except ImposeError`` still catches it.
    """


class DestinationError(ImposeError):
    """Where the work would be written refuses to take it.

    A press file that already exists, an output path that is also the input,
    a directory that is not there. Separate for the same reason
    :class:`SourceError` is: nothing about the artwork or the schema is wrong,
    and a watched folder retries this class of failure once somebody has
    fixed the shelf it writes to.
    """
