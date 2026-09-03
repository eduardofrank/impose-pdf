#!/usr/bin/env python3
# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

"""Find artwork that stops short of its own trim.

A page whose ground does not reach the TrimBox prints a white sliver at the
cut. On an outer edge that reads as an uneven margin; where two pages butt at a
fold it reads as a hairline down the spine, because the neighbour reaches and
this one does not. Neither shows at screen zoom, in a thumbnail, or in any
geometric check -- the boxes are all correct, the artwork inside them is not --
and both show perfectly once the sheet is printed and folded.

So this renders a narrow band along each trim edge of each page and measures how
far in the first ink appears.

    python tools/check-artwork.py catalogue.pdf

It is deliberately not part of `impose` and not run when imposing. It needs a
rendering engine, which the library goes to some trouble not to depend on, and
it costs roughly 50 ms a page on image-heavy work because the images must be
decoded before anything can be measured. Run it on a job you have reason to
doubt, not on all of them.

    pip install pypdfium2

The figure runs about one pixel optimistic. The edge of a ground is
antialiased, so the pixel straddling it is partly inked and counts as ink,
putting the first ink a touch closer to the trim than it truly is: a 0.42 mm
shortfall measures as 0.34 mm at 300 dpi. It flags the fault, which is the
point; do not quote the number to three decimal places.

Two things it cannot tell you. White artwork that legitimately reaches the trim
is indistinguishable from artwork that is not there at all, so a page designed
white to the edge reads as "no ink". And a ground that stops a long way short is
reported but not flagged, because that is far more likely to be a designed
margin than an export fault; --threshold sets where that line falls.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass

EDGES = ("left", "right", "bottom", "top")


@dataclass(frozen=True)
class Reading:
    """How far in from one trim edge the artwork begins."""

    page: int
    edge: str
    shortfall: float | None  # mm; None when the band holds no ink at all
    reaching: int
    samples: int

    @property
    def blank(self) -> bool:
        """Whether the band is empty, so there is nothing to be short of."""
        return self.shortfall is None

    def verdict(self, threshold: float) -> str:
        if self.blank:
            return "no ink at this edge"
        if self.shortfall <= 0.02:
            return "reaches the trim"
        if self.shortfall <= threshold:
            return f"SHORT by {self.shortfall:.2f} mm"
        return f"starts {self.shortfall:.2f} mm in (a margin, most likely)"


def _bands(trim, media_height, media_width, strip):
    """Crop tuples, as pdfium wants them: how much to remove from each side."""
    left, bottom, right, top = trim
    return {
        "left": (left, bottom, media_width - (left + strip), media_height - top),
        "right": (right - strip, bottom, media_width - right, media_height - top),
        "bottom": (left, bottom, media_width - right, media_height - (bottom + strip)),
        "top": (left, top - strip, media_width - right, media_height - top),
    }


def _scan(image, edge, dpi, background):
    """Distance in mm from *edge* to the first ink, for each sample line."""
    width, height = image.size
    pixels = image.load()
    across = height if edge in ("left", "right") else width
    depth = width if edge in ("left", "right") else height
    step = max(1, across // 200)

    def inked(i, d):
        if edge == "left":
            x, y = d, i
        elif edge == "right":
            x, y = width - 1 - d, i
        elif edge == "top":
            x, y = i, d
        else:
            x, y = i, height - 1 - d
        return min(pixels[x, y][:3]) <= background

    found = []
    for i in range(0, across, step):
        for d in range(depth):
            if inked(i, d):
                found.append(d / dpi * 25.4)
                break
    return found, len(range(0, across, step))


def read_page(page, boxes, *, dpi, strip_mm, background):
    """One reading per edge for a single page."""
    import pypdfium2 as pdfium  # noqa: F401  (imported for the caller's benefit)

    media_w, media_h = page.get_size()
    strip = strip_mm * 72 / 25.4
    trim = (boxes.trim.x0, boxes.trim.y0, boxes.trim.x1, boxes.trim.y1)
    out = {}
    for edge, crop in _bands(trim, media_h, media_w, strip).items():
        crop = tuple(max(0.0, c) for c in crop)
        image = page.render(scale=dpi / 72, crop=crop).to_pil().convert("RGB")
        found, samples = _scan(image, edge, dpi, background)
        out[edge] = (min(found) if found else None, len(found), samples)
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="check-artwork",
        description="Find artwork that stops short of its own TrimBox.",
    )
    parser.add_argument("input", help="PDF to check.")
    parser.add_argument(
        "--threshold", type=float, default=1.0, metavar="MM",
        help="A shortfall up to this is called a fault; more is assumed to be "
             "a designed margin. Default: %(default)s mm.",
    )
    parser.add_argument(
        "--strip", type=float, default=3.0, metavar="MM",
        help="How far in to look from each edge. Default: %(default)s mm.",
    )
    parser.add_argument(
        "--dpi", type=float, default=300,
        help="Resolution of the band. A pixel is 25.4/dpi mm, and that is the "
             "measurement's precision. Costs almost nothing: on image-heavy "
             "work the decode dominates and 300 measures no slower than 72. "
             "Default: %(default)s.",
    )
    parser.add_argument(
        "--background", type=int, default=225, metavar="LEVEL",
        help="A pixel is ink when its darkest channel is at or below this. "
             "Default: %(default)s.",
    )
    parser.add_argument(
        "--all", action="store_true",
        help="Show every edge, not only the faults.",
    )
    args = parser.parse_args(argv)

    try:
        import pypdfium2 as pdfium
    except ImportError:
        print(
            "check-artwork needs a renderer: pip install pypdfium2",
            file=sys.stderr,
        )
        return 2

    import pikepdf

    from impose.boxes import read_boxes

    doc = pdfium.PdfDocument(args.input)
    source = pikepdf.open(args.input)
    faults: list[Reading] = []
    rows: list[Reading] = []
    try:
        for number in range(len(doc)):
            boxes = read_boxes(source.pages[number])
            found = read_page(
                doc[number], boxes,
                dpi=args.dpi, strip_mm=args.strip, background=args.background,
            )
            for edge in EDGES:
                short, reaching, samples = found[edge]
                reading = Reading(number + 1, edge, short, reaching, samples)
                rows.append(reading)
                if not reading.blank and 0.02 < reading.shortfall <= args.threshold:
                    faults.append(reading)
    finally:
        source.close()
        doc.close()

    shown = rows if args.all else faults
    if not shown:
        print(f"{args.input}: every page's artwork reaches its trim.")
        return 0
    print(f"{'page':>5}  {'edge':<7} {'shortfall':>10}  verdict")
    for r in shown:
        value = "-" if r.blank else f"{r.shortfall:.2f} mm"
        print(f"{r.page:>5}  {r.edge:<7} {value:>10}  {r.verdict(args.threshold)}")
    if faults:
        print(
            f"\n{len(faults)} edge(s) short of the trim. Ask for the ground to "
            f"be extended to the trim, and past it into the bleed."
        )
    return 1 if faults else 0


if __name__ == "__main__":
    sys.exit(main())
