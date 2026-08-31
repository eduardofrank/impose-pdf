# impose

Imposition for commercial print.

`impose` arranges finished pages onto press sheets. It works from the page
boxes a print-ready PDF already carries — TrimBox is the finished page,
BleedBox is the margin that gets trimmed away — and targets a named press whose
sheet size and imageable area it knows.

> **Status: usable as a library, no command line yet.** All five schemas, the
> layout engine, marks, and the renderer are built and tested — the library
> imposes a document and writes a press-ready file. What is missing is PDF/X
> passthrough, a high-level entry point, and the `impose` command itself. See
> [Roadmap](#roadmap).

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

## Using it

There is no command line yet, and no single-call entry point, so a job is
assembled from the pieces. This is a 16-page A6 booklet, saddle stitched, on an
Indigo 5000:

```python
import pikepdf

from impose.boxes import read_boxes
from impose.layout import lay_out
from impose.marks import MarkStyle, trim_marks
from impose.press import get
from impose.render import Renderer
from impose.schemas import saddle

source = pikepdf.open("book.pdf")
boxes = read_boxes(source.pages[0])
press = get("indigo-5000")
style = MarkStyle()

plan = saddle.impose(len(source.pages))
plan.validate()

renderer = Renderer(style=style)
for surface in plan:
    layout = lay_out(
        surface,
        columns=plan.columns,
        rows=plan.rows,
        trim=boxes.trim_size,
        trim_origin=boxes.trim,
        bleed=boxes.bleed_insets,
        press=press,
        mark_allowance=style.reach,
    )
    fold = layout.pages[0].trim.x1
    renderer.add(
        layout,
        source,
        marks=trim_marks(
            [page.trim for page in layout.pages], style=style, folds=(fold,)
        ),
    )
renderer.save("book-imposed.pdf")
```

That produces four sheets, 320 × 470 mm, each carrying a 210 × 148 mm spread
with crop marks, a dashed fold at the spine, and bleed everywhere except the
spine itself.

It is more ceremony than it should be — wiring the boxes through by hand, and
picking the fold coordinate out of the layout, are jobs the library should do.
An `impose.job` entry point is the next thing to be written, and the command
line after it.

## Schemas

| schema | assembly | ordering |
|---|---|---|
| `saddle` | sheets nested, stapled through the fold | page 1 is beside page *n* |
| `perfect` | sections gathered, spine milled and glued | nested within a section, sequential between |
| `nup` | read as a stack, not cut | consecutive, reading order |
| `cutstack` | guillotined into stacks, stacks set on each other | each cell holds a consecutive block |
| `steprepeat` | cut apart | one artwork, repeated |

The dividing line between them is whether the sheet gets **cut**, because that
decides whether it matters which page lands physically behind which.

`nup` is what a print driver means by "2 pages per sheet". Both sides are laid
out in plain reading order and the duplex unit turns the sheet; mirroring the
back in the PDF would be doing the press's job twice, and would back every page
against the wrong neighbour with nothing looking wrong until the job is cut.

`cutstack` and `steprepeat` really are cut, so each finished piece takes its
reverse from the *mirrored* cell of the back surface.

## Marks

Marks sit at the ends of each cut line, out beyond the form, because that is
how a guillotine is used: the operator lines the blade up on a pair of marks at
opposite edges of the sheet and cuts the whole way across. A mark in the middle
of the form would be cut through; one inside the trim would be delivered to the
customer. A fold, such as a saddle spine, is drawn dashed.

Colour is selectable, and both answers are right somewhere:

```python
MarkStyle(colour="registration")   # default
MarkStyle(colour="black")
```

`registration` is a Separation `/All` colorant at full strength with overprint
on, so the mark appears on every plate at once. That is what offset work needs:
a black mark sits on the black plate alone, which gives no colour-to-colour
reference and gives the cutter nothing at all on a job with no black in it.

`black` is K only. On a digital press there are no plates to register — the
marks are only guiding the knife and the folder — and 400% coverage in the trim
zone risks setting off onto the next sheet.

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
| ✅ | `schemas.saddle` — saddle stitch, sheets nested and stapled on the fold |
| ✅ | `schemas.perfect` — perfect bound, sections gathered and glued |
| ✅ | `schemas.nup` — consecutive pages in reading order |
| ✅ | `schemas.steprepeat` — one item repeated to fill the sheet |
| ✅ | `schemas.cutstack` — cut into stacks that reassemble in order |
| ✅ | `marks` — cut and fold marks, registration or K-only |
| ✅ | `render` — pikepdf output, registration marks with overprint |
| ⬜ | `job` — one call from source document to imposed file |
| ⬜ | PDF/X passthrough: OutputIntent, conformance keys |
| ⬜ | Command line |
| ⬜ | Registration targets, colour bars, slug line |
| ⬜ | Creep compensation for thick saddle-stitched work |

## Development

```bash
./.venv/bin/python -m unittest discover -s tests -t .
./.venv/bin/python -m pylint impose tests
./.venv/bin/python -m black --check . && ./.venv/bin/python -m isort --check .
```

Over 200 tests, no system libraries, under a second. The suite asserts geometry and
structure rather than pixels: an imposition is right or wrong by where the
trims land on the sheet, and expectations are literals from ISO 216 and ISO 217
rather than restatements of what the code computes.

The binding schemas are checked by **assembling the book and reading it**.
`tests/booklet.py` turns the pages of a nested set of sheets — inward along the
right-hand pages, then back out along the left — and the tests assert the
result reads 1, 2, 3. Cut and stack is checked by simulating the guillotine:
cut the plan into stacks, set them on each other, read the pages. A page-order
bug is invisible in a rendered sheet and obvious the moment the pages are
turned, which is why the old codebase's image-comparison tests could not see
them.

## Licence

MIT — see [LICENSE](LICENSE).

The single dependency is [pikepdf](https://github.com/pikepdf/pikepdf)
(MPL-2.0, over QPDF's Apache-2.0). PyMuPDF is deliberately not used: it is
AGPL-or-commercial, which would make the MIT licence here misleading to anyone
redistributing.
