# impose

Imposition for commercial print.

`impose` arranges finished pages onto press sheets. It works from the page
boxes a print-ready PDF already carries — TrimBox is the finished page,
BleedBox is the margin that gets trimmed away — and targets a named press whose
sheet size and imageable area it knows.

> **Status: early.** The foundation is built and tested. The schemas, the
> renderer, and the command line are not written yet. See
> [Roadmap](#roadmap) for what exists today.

## Why this exists

It began as a fork of [pdfimpose](https://framagit.org/spalax/pdfimpose), and
an audit of that codebase found the foundation unsound for press work:

- **Every dimension was 0.375% too large.** It measured in TeX points
  (1 inch = 72.27) and wrote PDF points (1 inch = 72). A 470 mm press sheet was
  described as 471.76 mm.
- **Trim marks were DeviceRGB black**, so they separated onto the black plate
  alone and gave the cutter no cross-plate reference.
- **The imageable area was centred on the sheet**, which no press does — the
  grippers hold the lead edge, and that strip is not the same as the tail.
- **Page order could not be tested** without rendering a PDF and comparing
  pictures, so ordering bugs were invisible.

Those are foundation problems, not surface ones, so this is a rewrite rather
than a patch. No code is shared with pdfimpose; the schemas are written from
the printing domain and the geometry from the ISO and PDF specifications.

## Design

**Everything is in PDF points.** One inch is 72 points and there is no other
point. Sheets are tabulated in the unit their standard defines them in, so
`letter` is exactly 612 × 792 and SRA3 exactly 320 × 450 mm.

**Geometry is PDF-native** — origin bottom-left, y upward, the same convention
as every box in a print-ready file. Conversion to a rendering library's
convention happens once, at the boundary.

**Ordering is separated from geometry.** A schema returns a `Plan`: which
source page sits in which cell of which surface, as integers. That is checkable
without producing a PDF at all:

```python
>>> print(plan.describe())
sheet 1 front
     4    1
sheet 1 back
     2    3
```

`Plan.validate()` then asserts every page is imposed exactly once — the check
that catches an off-by-one before it becomes a silent blank page in a bound
book.

**Presses have a gripper edge.** A `Press` carries asymmetric margins and the
edge that feeds first. On an Indigo 5000 that is 12 mm at the lead edge and
8 mm at the tail. A form that will not fit is turned; the sheet never is,
because the gripper edge is fixed with respect to the machine.

**Bleed is not invented.** Where two pages meet at a spine they share one cut
line, so bleed is shaved to nothing there and the two trims are snapped onto
one coordinate. Where a file declares no BleedBox, the answer is no bleed — the
space between TrimBox and CropBox is just as likely to be the supplier's own
slug and marks, and placing those into a gutter is worse than placing nothing.

## Installation

```bash
pip install impose-pdf
```

The distribution is `impose-pdf` because `impose` on PyPI belongs to an
unrelated imaging project. The import package and the command are both
`impose`.

From source:

```bash
git clone https://github.com/eduardofrank/impose-pdf.git
cd impose-pdf
python -m venv .venv && ./.venv/bin/pip install -e ".[dev]"
```

## Presses

| profile | sheet | imageable | gripper |
|---|---|---|---|
| `indigo-5000` | 320 × 470 mm | 310 × 450 mm | 12 mm |
| `indigo-7000` | 330 × 482 mm | 317 × 464 mm | 12 mm |
| `indigo-12000` | 750 × 530 mm | 740 × 510 mm | 12 mm |
| `sra3` | 320 × 450 mm | 310 × 440 mm | 5 mm |

These figures are **nominal**. A press is a physical machine with its own
history — confirm them against yours before committing a job, and override
where they differ:

```python
from impose.geometry import Insets
from impose.press import custom
from impose.units import MM

mine = custom("mine", sheet="SRA3", margins=Insets(
    left=5 * MM, right=5 * MM, bottom=12 * MM, top=8 * MM,
))
```

## Roadmap

| | |
|---|---|
| ✅ | `geometry` — PDF-native value types |
| ✅ | `units` — PDF points, ISO/ANSI/RA/SRA sheets |
| ✅ | `boxes` — ISO 32000 page boxes, `/Rotate`, PDF/X detection |
| ✅ | `press` — sheet, asymmetric margins, gripper edge |
| ✅ | `plan` — page order as integers, with validation |
| ✅ | `layout` — gutters, bleed shaving, form fitting |
| ⬜ | Schemas: saddle stitch, perfect bound, n-up, step and repeat, cut and stack |
| ⬜ | `render` — pikepdf output, registration marks with overprint |
| ⬜ | PDF/X passthrough: OutputIntent, conformance keys |
| ⬜ | Command line |

## Development

```bash
./.venv/bin/python -m unittest discover -s tests -t .
./.venv/bin/python -m pylint impose tests
./.venv/bin/python -m black --check . && ./.venv/bin/python -m isort --check .
```

The suite asserts geometry, not pixels, so it needs no renderer and no system
libraries. An imposition is right or wrong by where the trims land on the
sheet, measured in millimetres, and expectations are literals from ISO 216 and
ISO 217 rather than restatements of what the code computes.

## Licence

MIT — see [LICENSE](LICENSE).

The single dependency is [pikepdf](https://github.com/pikepdf/pikepdf)
(MPL-2.0, over QPDF's Apache-2.0). PyMuPDF is deliberately not used: it is
AGPL-or-commercial, which would make the MIT licence here misleading to anyone
redistributing.
