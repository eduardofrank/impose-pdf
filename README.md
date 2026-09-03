# impose

Imposition for commercial print.

`impose` arranges finished pages onto press sheets. It works from the page
boxes a print-ready PDF already carries — TrimBox is the finished page,
BleedBox is the margin that gets trimmed away — and targets a named press whose
sheet size and imageable area it knows.

> **Status: complete for the five schemas it covers.** Library and command line
> both work end to end. Still to come: a slug line, and documents whose pages
> differ in size. See [Roadmap](#roadmap).

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

**Gutters follow the binding.** Cut work defaults to 4 mm between pieces —
what a guillotine needs to come down without shaving a neighbour. A folded
spread defaults to none: its two pages meet across the fold, and a gap there is
a gap in the middle of the reader's page. `--gutter` overrides either.

**Bleed is capped, not requested.** `--bleed` says the most to place, and the
default is 2 mm. Artwork arriving with 5 mm is shaved to 2; artwork with 1 mm
keeps its 1; artwork with none stays with none, because bleed that is not in
the file cannot be manufactured. On a small sheet the difference is real estate
the job gets instead.

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

`--dry-run` shows the page order and sheet count without writing anything:

```
$ impose saddle book.pdf --dry-run
sheet 1 front
    16    1
sheet 1 back
     2   15
...
  16 pages, 4 sheet(s), 8 surface(s); finished page 105 × 148 mm
```

Refusals are sentences:

```
$ impose nup report.pdf --up 4x4
impose: The imposed form is 436 × 608 mm including bleed and marks, and the
imageable area is 310 × 450 mm. It does not fit either way round.
```

Every command and option is listed below.

## Command line reference

```
impose SCHEMA INPUT [options]     impose a document
impose fit SIZE [options]         how many fit, before there is a file
impose presses                    list the press profiles
```

Sizes and lengths accept `mm`, `cm`, `in`, `pt`, `pc`, or a bare number meaning
PDF points. One inch is 72 points. Paper names work anywhere a size does: `A4`,
`SRA3`, `letter`, `tabloid`, and the rest of the ISO A/B/C, RA/SRA and ANSI
series.

### Schemas

| command | binding | grid |
|---|---|---|
| `impose saddle` | nested, stapled through the fold | fixed 2-up spread |
| `impose perfect` | sections gathered, spine glued | fixed 2-up spread |
| `impose nup` | none; read as a stack | yours, or chosen |
| `impose cutstack` | none; cut into stacks | yours, or chosen |
| `impose steprepeat` | none; cut apart | yours, or chosen |

### Options every schema takes

| option | default | what it does |
|---|---|---|
| `INPUT` | — | the PDF to impose |
| `-o`, `--output FILE` | `INPUT-imposed.pdf` | where to write |
| `--press NAME` | `indigo-5000` | press profile; see `impose presses` |
| `--sheet SIZE` | the press maximum | run a smaller sheet than the press takes |
| `--bleed LENGTH` | `2mm` | most bleed to place; caps what the artwork brought |
| `--gutter LENGTH` | `4mm` cut, none folded | space between pages, for the knife (`--gutters` also accepted) |
| `--marks {registration,black,none}` | `registration` | colour of cut and fold marks |
| `--mark-offset LENGTH` | `2mm` | gap between the trim and the start of a mark |
| `--mark-length LENGTH` | `3mm` | how long each mark is |
| `--mark-width LENGTH` | `0.25pt` | stroke width |
| `--registration` | off | bullseye on each side of the form |
| `--colour-bar` | off | ink patches along the tail (`--color-bar` also accepted) |
| `--orientation {auto,upright,turned}` | `auto` | how pages sit in their cells |
| `-n`, `--dry-run` | off | show the page order and sheet count, write nothing |
| `-q`, `--quiet` | off | say nothing on success; warnings still go to stderr |

### Options for particular schemas

| option | schemas | default | what it does |
|---|---|---|---|
| `--up COLUMNSxROWS` | `nup`, `cutstack`, `steprepeat` | chosen for you | pages across and down |
| `--copies N` | `steprepeat` | one sheet's worth | finished pieces wanted |
| `--section-pages N` | `perfect` | `4` | pages per gathered section, a multiple of 4 |
| `--paper-caliper LENGTH` | `saddle`, `perfect` | off | one sheet's thickness; turns on creep |
| `--max-nested-sheets N` | `saddle` | `15` | how many sheets will staple |

`saddle` and `perfect` have no `--up`: a spread is two pages by definition, and
asking for another grid is refused rather than quietly ignored.

### `impose fit`

Answers how many pieces of a size go on a sheet, and what an order wastes,
without needing a file.

| option | default | what it does |
|---|---|---|
| `SIZE` | — | finished size: `A6`, or `90mmx50mm` |
| `-n`, `--quantity N` | none | pieces wanted; adds sheet counts and waste |
| `--press NAME` | `indigo-5000` | press profile |
| `--sheet SIZE` | the press maximum | sheet to run |
| `--gutter LENGTH` | `4mm` | gap between pieces |
| `--marks {registration,black,none}` | `registration` | `none` reserves no room for marks |
| `--mark-offset LENGTH` | `2mm` | gap between the trim and the start of a mark |
| `--mark-length LENGTH` | `3mm` | how long each mark is |
| `--bleed LENGTH` | `2mm` | bleed to allow room for |
| `--allowance LENGTH` | from the marks and bleed | override the room kept clear each edge |

`fit` takes the same mark options as the schemas and works the allowance out
itself, so quoting how many fit and then imposing them cannot disagree:

```
$ impose fit A6 --gutter 4mm                          # 5 mm reserved
  8 up, 2 × 4 turned, form 300 × 432 mm

$ impose fit A6 --gutter 4mm --mark-length 5mm        # 7 mm reserved
  4 up, 2 × 2 upright, form 214 × 300 mm
```

Marks and bleed are not added together: layout reserves whichever reaches
further on an edge, so a 3 mm bleed behind a 5 mm mark reach needs 5 mm, not 8.
`--allowance` overrides both, and is rarely what you want.

`--mark-width` is accepted here for symmetry with the schemas, so the same
flags can be pasted to both, but a stroke width cannot change how many pieces
fit and it is ignored.

Note that `-n` means `--quantity` here and `--dry-run` on the schemas. `fit`
never writes a file, so it has no dry run to ask for.

Without a quantity the arrangements are listed as they pack. With one they are
costed and ordered by what the job actually takes — fewest sheets first, then
least waste.

### Exit codes

| code | meaning |
|---|---|
| `0` | done |
| `1` | the job cannot be done: file missing, unknown press, form will not fit |
| `2` | the arguments do not parse |

Warnings — a book too thick to staple, say — go to stderr and do **not** change
the exit code. The job still runs; it is your press and your stapler.

### Worked examples

```bash
# A magazine on the default press, with creep for 100 micron stock
impose saddle magazine.pdf --paper-caliper 0.1mm

# Check the page order before committing anything
impose saddle magazine.pdf --dry-run

# A paperback in 16-page sections on the larger press
impose perfect novel.pdf --section-pages 16 --press indigo-7000

# Business cards: how many fit, and what 500 wastes
impose fit 90mmx50mm -n 500

# ...then run them, letting the grid be chosen
impose steprepeat card.pdf --copies 500 --gutter 4mm --marks black

# A6 flyers, eight up on one sheet without being told the grid
impose nup flyers.pdf --gutter 4mm

# Full press furniture for a proofing sheet
impose nup artwork.pdf --registration --colour-bar

# A long document cut into stacks that reassemble in order
impose cutstack manual.pdf --up 2x2 --gutter 3mm
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
$ impose nup a6.pdf --gutter 4mm
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

## Creep

Nested sheets push out. An inner sheet's fold sits further toward the opening,
so its leaf protrudes, and trimming the folded book at one common line takes
more off the inside than the outside. Left alone, the fore-edge margin shrinks
page by page as you work inward — visible by the middle of a thick booklet.

Give `impose` the thickness of one sheet and it compensates, sliding each
sheet's image toward the spine by as much as its own fold has been displaced:

```bash
impose saddle book.pdf --paper-caliper 0.1mm
```

Measure the caliper rather than guess it — a micrometer on twenty sheets,
divided by twenty, is how a shop gets that number. The outermost sheet has
nothing wrapping it and does not creep at all; depth restarts with each section
of a perfect-bound book, since sections are gathered rather than nested.

What moves is the **image inside its cell**, never the cell. The fold is where
the fold is, and sliding both halves of a spread toward it would only overlap
them.

## Bindery limits

A saddle-stitched book can only be so thick before the stapler struggles: the
constraint is bulk at the spine, not page count. Fifteen nested sheets — sixty
pages — holds for thin stock, bond and coated up to about 150 gsm. Heavier
paper bulks up faster and staples fewer, so the figure is a parameter rather
than a constant.

```
$ impose saddle book-64pp.pdf
impose: warning: 16 nested sheets exceeds the 15 that staple cleanly (60
pages). Thicker books are usually gathered into sections and perfect bound
instead.
```

The job still runs — it is your press and your stapler — and
`--max-nested-sheets` sets the limit for the stock in hand. Warnings go to
stderr even under `--quiet`, since a book that will not staple is not something
to keep quiet about.

## Marks

Marks start 2 mm clear of the trim and run 3 mm, reserving 5 mm beyond the trim
on each marked edge.

They are deliberately small, and the reason is the sheet. On an SRA3-class
press every millimetre of margin is a millimetre not available to the artwork,
and the difference between reserving 5 mm and 8 mm is the difference between
eight A6 up and four. A 3 mm mark is short but plenty to line a guillotine up
on. Raise them where the sheet can afford it; nothing depends on the defaults.

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

### Registration targets and colour bars

Two more things a press sheet usually carries, both off unless asked for:

```bash
impose saddle book.pdf --registration --colour-bar
```

**Registration targets** — a ringed bullseye with a crosshair, one on each side
of the form, in registration colour. Where the separations are out, the rings
and the cross stop agreeing, which is what makes them readable at a glance
rather than by measurement.

**A colour bar** — each process ink solid and in quarter steps, the two-colour
overprints that show trapping, and a three-colour grey. It sits flush to the
tail of the sheet, in the waste, and the patches are laid down in DeviceCMYK
directly, since their whole purpose is to put a known ink value on the sheet
for a densitometer to read back.

Both are placed only where the margin has room, and the bar is dropped
entirely if the patches would come out narrower than an instrument aperture can
read — an unreadable bar is worse than none, because it looks like a check that
was made.

This is a working bar, not a standardised one. Fogra, Ugra and GATF wedges are
specified objects with their own patch geometry; a job that needs one of those
needs the real thing rather than an approximation of it.


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
| ✅ | `marks` — registration targets and colour bar |
| ⬜ | Slug line (needs an embedded font to stay PDF/X) |
| ✅ | `fit` — densest grid, orientation, and run waste |
| ✅ | `creep` — fore-edge push-out compensated per sheet |

## Checking artwork

Imposition cannot fix a page whose ground stops short of its own TrimBox. It
prints as an uneven margin at a cut edge, or as a hairline down the spine where
the neighbouring page reaches and this one does not — invisible on screen,
obvious once folded.

```bash
pip install pypdfium2
python tools/check-artwork.py catalogue.pdf
```

It renders a narrow band along each trim edge of each page and reports how far
in the first ink appears. Deliberately not part of `impose` and never run when
imposing: it needs a renderer, which the library takes some trouble not to
depend on, and it costs around 50 ms a page on image-heavy work because the
images must be decoded before anything can be measured. Run it on a job you
have reason to doubt.

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
