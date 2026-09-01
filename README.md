# impose

Imposition for commercial print.

`impose` arranges finished pages onto press sheets. It works from the page
boxes a print-ready PDF already carries — TrimBox is the finished page,
BleedBox is the margin that gets trimmed away — and targets a named press whose
sheet size and imageable area it knows.

> **Status: complete for the five schemas it covers.** Library and command line
> both work end to end. Still to come: registration targets and colour bars,
> creep compensation, and documents whose pages differ in size. See
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

**Pages are turned if that is what fits.** Six A6 pages will not go on an
Indigo upright — two across by three down is 462 mm tall against a 450 mm
imageable area — but the same six fit comfortably on their sides, at 310 × 333
mm. `orientation="auto"` tries upright first and turns the pages if it must.
Binding schemas are never turned automatically, because moving the fold turns a
side-bound booklet into a top-bound one.

**Bleed is not invented.** Where two pages meet at a spine they share one cut
line, so bleed is shaved to nothing there and the two trims are snapped onto
one coordinate. Where a file declares no BleedBox, the answer is no bleed — the
space between TrimBox and CropBox is just as likely to be the supplier's own
slug and marks, and placing those into a gutter is worse than placing nothing.

## Command line

```bash
impose saddle book.pdf                      # -> book-imposed.pdf
impose nup report.pdf --up 2x2
impose steprepeat card.pdf --up 3x4 --copies 250 --marks black
impose perfect novel.pdf --section-pages 16 --press indigo-7000
```

Each schema is a subcommand, so options that suit only one of them appear only
there. `impose presses` lists the profiles; `--dry-run` shows the page order
and sheet count without writing anything:

```
$ impose saddle book.pdf --dry-run
sheet 1 front
    16    1
sheet 1 back
     2   15
...
  16 pages, 4 sheet(s), 8 surface(s); finished page 105 × 148 mm
```

Refusals are sentences, and exit non-zero — 1 when the job cannot be done, 2
when the arguments do not parse:

```
$ impose nup report.pdf --up 4x4
impose: The imposed form is 436 × 608 mm including bleed and marks, and the
imageable area is 310 × 450 mm. It does not fit either way round.
```

## Using it as a library

```python
from impose.job import impose_document

result = impose_document("book.pdf", "book-imposed.pdf", schema="saddle")
print(result.describe())
```

```
saddle-stitch: 16 pages onto 4 sheet(s) of 320 × 470 mm on indigo-5000;
finished page 105 × 148 mm
```

That reads the source's page boxes, checks every page is the same finished
size, orders the pages for the binding, lays each surface out on the press,
draws crop marks with the spine dashed, and writes the sheets.

More of a job than the defaults:

```python
impose_document(
    "cards.pdf", "cards-imposed.pdf",
    schema="steprepeat",
    press="sra3",
    columns=3, rows=4, copies=250,
    gutters="4mm",
    marks=MarkStyle(colour="black"),   # K only, for a digital press
)
```

The schema's own options pass straight through: `columns` and `rows` for the
grid schemas, `section_pages` for perfect binding, `copies` for step and
repeat. `marks=None` draws none.

Refusals name the problem rather than producing an unusable sheet:

```
Page 4 has a finished size of 80 × 100 mm, but page 1 is 105 × 148 mm.
Every page must be the same size to go on one grid.

The imposed form is 436 × 312 mm including bleed and marks, and the
imageable area is 310 × 450 mm. It does not fit either way round.
```

The pieces underneath are all public, and `impose_document` is only their
assembly — read `impose/job.py` if you want to drive `plan`, `layout`,
`marks`, and `render` yourself.

## How many fit

Before the page order comes the question a shop asks first: how many pieces of
this size go on a sheet, and what do the leftovers cost.

```
$ impose fit 90mmx50mm -n 100
90 × 50 mm on indigo-5000, imageable 310 × 450 mm
  20 up, 5 × 4 turned, form 266 × 372 mm   ->  5 sheet(s), 0 wasted   <- run this
  24 up, 3 × 8 upright, form 278 × 428 mm  ->  5 sheet(s), 20 wasted

  24 up is denser but costs the same 5 sheet(s) and throws away 20 instead of 0.
```

**Density is not cheapness.** A 90 × 50 mm business card goes 24 up on an
Indigo or 20 up the other way round. For 100 cards both run five sheets — but
24 up throws away twenty cards to do it, and 20 up fills the sheet exactly.
Past that the denser grid starts saving sheets:

```
$ impose fit 90mmx50mm -n 200
  24 up, 3 × 8 upright, form 278 × 428 mm  ->  9 sheet(s), 16 wasted   <- run this
  20 up, 5 × 4 turned, form 266 × 372 mm   -> 10 sheet(s), 0 wasted
```

So arrangements are ranked by sheets first and waste second, and density only
breaks a remaining tie. With no quantity given there is nothing to weigh
against, and they are simply listed as they pack.

The same choice is made when imposing, so the grid is picked for you unless
you pin it with `--up`:

```
$ impose nup a6.pdf --gutters 4mm --mark-offset 1mm --mark-length 4mm
n-up: 8 pages onto 1 sheet(s) of 320 × 470 mm on indigo-5000
```

Counting along a span allows for gutters correctly: *n* pieces have *n−1* gaps
between them, so the gap is added to the span once before dividing rather than
charged against every piece.

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

## PDF/X

A PDF/X file says two things beyond ordinary PDF: it names the printing
condition it was prepared for — an OutputIntent holding the ICC profile the
separations assume — and it declares which part of ISO 15930 it claims. Both
are carried onto the imposed sheets, along with `/Trapped` and a PDF version no
older than the claim requires.

```python
result = impose_document("book.pdf", "book-imposed.pdf")
print(result.pdfx)     # 'PDF/X-4'
```

An OutputIntent is carried across even when no PDF/X part is claimed, since it
names what the separations were built for either way.

**This preserves a declaration; it does not create or check one.** Conformance
is a preflight question — embedded fonts, colour spaces, transparency — and
answering it is a different program. If the source conformed and the imposition
adds nothing that breaks it, the output should too, but only preflight can tell
you it does. `Identity.is_complete` will tell you if the *source* claimed
PDF/X without an OutputIntent to back it, which the imposed file inherits.

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
| ✅ | `job` — one call from source document to imposed file |
| ✅ | `pdfx` — OutputIntent and conformance keys carried through |
| ✅ | `cli` — the `impose` command |
| ⬜ | Registration targets, colour bars, slug line |
| ✅ | `fit` — densest grid, orientation, and run waste |
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
