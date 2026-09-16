# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

# pylint: disable=missing-class-docstring,missing-function-docstring

"""Several complete bound copies on one press sheet.

A bound form is smaller than the sheet, so the spare room can hold another
whole copy. This is the two-stage route -- impose the booklet onto its own
form, then step and repeat that form -- run as one call, with the intermediate
never reaching the disk.
"""

import io
import pathlib
import re
import tempfile
import unittest

import pikepdf

from impose import ImposeError
from impose.geometry import Size
from impose.job import impose_document
from impose.units import MM, to_mm

from .support import make_pdf
from .test_cli import run, workspace

HALF_LETTER = Size(139.7 * MM, 215.9 * MM)
QUARTER = Size(108 * MM, 140 * MM)


def impose(trim, pages=16, **options):
    source = io.BytesIO()
    make_pdf(pages, trim=trim).save(source)
    source.seek(0)
    return impose_document(source, io.BytesIO(), schema="saddle", **options)


def marks(data):
    """Every mark on page one, with whether it was dashed."""
    with pikepdf.open(data) as pdf:
        contents = pdf.pages[0].obj["/Contents"]
        raw = (
            b"".join(part.read_bytes() for part in contents)
            if isinstance(contents, pikepdf.Array)
            else contents.read_bytes()
        )
    dashed, found = False, []
    for line in raw.decode("latin-1").splitlines():
        stripped = line.strip()
        if re.fullmatch(r"\[[\d.]+ [\d.]+\] 0 d", stripped):
            dashed = True
        elif stripped == "[] 0 d":
            dashed = False
        drawn = re.match(r"([-\d.]+) ([-\d.]+) m ([-\d.]+) ([-\d.]+) l", stripped)
        if drawn:
            x0, y0, x1, _ = (to_mm(float(v)) for v in drawn.groups())
            axis = "vertical" if abs(x0 - x1) < 0.01 else "horizontal"
            found.append((axis, round(x0 if axis == "vertical" else y0, 1), dashed))
    return found


class TestWhatItSaves(unittest.TestCase):
    """The point of it: fewer press sheets for the same books."""

    def test_two_half_letter_booklets_share_a_sheet(self):
        plain = impose(HALF_LETTER)
        repeated = impose(HALF_LETTER, repeat="auto")
        self.assertEqual(repeated.repeat, 2)
        self.assertEqual(plain.sheets / 1, 4)
        self.assertEqual(repeated.sheets / repeated.repeat, 2)

    def test_four_quarter_letter_booklets_share_a_sheet(self):
        repeated = impose(QUARTER, pages=12, repeat="auto")
        self.assertEqual(repeated.repeat, 4)
        self.assertLess(repeated.sheets / repeated.repeat, 1)

    def test_a_form_that_fills_the_sheet_gets_one_copy(self):
        """Nothing is saved and nothing is broken."""
        letter = impose(Size(215.9 * MM, 279.4 * MM), repeat="auto")
        self.assertEqual(letter.repeat, 1)

    def test_the_summary_says_how_many(self):
        self.assertIn(
            "2 copies per sheet", impose(HALF_LETTER, repeat="auto").describe()
        )
        self.assertNotIn("copies per sheet", impose(HALF_LETTER).describe())


class TestWhatItKeeps(unittest.TestCase):
    def test_the_booklet_ordering_is_the_one_reported(self):
        """The plan a caller reads back is the book's, not the sheet's: page
        order is what a bound job is, and the repeat is a press arrangement."""
        repeated = impose(HALF_LETTER, repeat="auto")
        self.assertEqual(repeated.plan.schema, "saddle-stitch")
        self.assertEqual(repeated.plan.pages, 16)
        self.assertEqual(repeated.plan.grid, (2, 1))

    def test_the_finished_size_is_the_books_not_the_forms(self):
        repeated = impose(HALF_LETTER, repeat="auto")
        # To press-irrelevant noise: the size round-trips through the PDF,
        # where coordinates are written to six decimal places.
        self.assertAlmostEqual(repeated.trim_size.width, HALF_LETTER.width, places=3)
        self.assertAlmostEqual(repeated.trim_size.height, HALF_LETTER.height, places=3)

    def test_the_spine_is_still_marked_as_a_fold(self):
        """It is carried across on the form and drawn by the second pass;
        a spine marked as a cut tells the bindery to guillotine the book."""
        output = io.BytesIO()
        source = io.BytesIO()
        make_pdf(16, trim=HALF_LETTER).save(source)
        source.seek(0)
        impose_document(source, output, schema="saddle", repeat="auto")
        output.seek(0)
        folds = [m for m in marks(output) if m[2]]
        self.assertTrue(folds)
        self.assertTrue(all(axis == "vertical" for axis, _at, _d in folds))

    def test_pdfx_survives_both_passes(self):
        source = pathlib.Path("/Users/efrank/Downloads/plantillas/Catálogo.pdf")
        if not source.exists():
            self.skipTest("shop file not present")
        result = impose_document(source, io.BytesIO(), schema="saddle", repeat="auto")
        self.assertEqual(result.pdfx, "PDF/X-1:2001")

    def test_the_press_is_the_second_passs(self):
        repeated = impose(HALF_LETTER, repeat="auto")
        self.assertEqual(repeated.press, "indigo-5000")
        self.assertEqual(repeated.sheet_size, Size(310 * MM, 450 * MM))


class TestTheIntermediate(unittest.TestCase):
    def test_nothing_is_written_beside_the_output(self):
        """An unmarked form is a trap if someone sends it to press."""
        with tempfile.TemporaryDirectory() as folder:
            folder = pathlib.Path(folder)
            source = folder / "book.pdf"
            make_pdf(16, trim=HALF_LETTER).save(source)
            output = folder / "out.pdf"
            impose_document(source, output, schema="saddle", repeat="auto")
            self.assertEqual(
                sorted(p.name for p in folder.iterdir()), ["book.pdf", "out.pdf"]
            )


class TestRefusals(unittest.TestCase):
    def test_a_flat_schema_is_refused_by_name(self):
        for schema in ("nup", "cutstack", "steprepeat"):
            with self.subTest(schema=schema):
                source = io.BytesIO()
                make_pdf(8, trim=HALF_LETTER).save(source)
                source.seek(0)
                with self.assertRaises(ImposeError) as caught:
                    impose_document(source, io.BytesIO(), schema=schema, repeat="auto")
                self.assertIn(schema, str(caught.exception))
                self.assertIn("already fills the sheet", str(caught.exception))

    def test_a_count_that_does_not_fit_says_what_does(self):
        with self.assertRaises(ImposeError) as caught:
            impose(HALF_LETTER, repeat=(2, 2))
        message = str(caught.exception)
        self.assertIn("copies of the saddle-stitch form", message)
        self.assertIn("do not fit", message)

    def test_repeat_of_one_is_the_plain_job(self):
        self.assertEqual(impose(HALF_LETTER, repeat=1).repeat, 1)
        self.assertNotIn("copies per sheet", impose(HALF_LETTER, repeat=1).describe())


class TestFromTheTerminal(unittest.TestCase):
    def test_it_does_in_one_command_what_two_did(self):
        """The output has to be what the shop already runs by hand, or this
        is a new imposition rather than a convenience."""
        with workspace(pages=16, trim=HALF_LETTER) as source:
            one = source.with_name("one.pdf")
            form = source.with_name("form.pdf")
            two = source.with_name("two.pdf")
            status, _, err = run(
                "saddle", str(source), "--repeat", "auto", "-o", str(one)
            )
            self.assertEqual(status, 0, err)
            run(
                "saddle",
                str(source),
                "--sheet",
                "fit",
                "--marks",
                "none",
                "-o",
                str(form),
                "-q",
            )
            run("steprepeat", str(form), "-o", str(two), "-q")
            self.assertEqual(self.geometry(one), self.geometry(two))

    @staticmethod
    def geometry(path):
        with pikepdf.open(path) as pdf:
            pages = len(pdf.pages)
            contents = pdf.pages[0].obj["/Contents"]
            raw = (
                b"".join(part.read_bytes() for part in contents)
                if isinstance(contents, pikepdf.Array)
                else contents.read_bytes()
            )
        body = raw.decode("latin-1")
        return (
            pages,
            sorted(re.findall(r"([-\d.]+) ([-\d.]+) [-\d.]+ [-\d.]+ re W n", body)),
            sorted(re.findall(r"([-\d.]+) ([-\d.]+) m ([-\d.]+) ([-\d.]+) l", body)),
        )

    def test_an_explicit_grid_is_accepted(self):
        with workspace(pages=16, trim=HALF_LETTER) as source:
            status, text, err = run(
                "saddle",
                str(source),
                "--repeat",
                "1x2",
                "-o",
                str(source.with_name("o.pdf")),
            )
            self.assertEqual(status, 0, err)
            self.assertIn("2 copies per sheet", text)

    def test_the_flat_schemas_are_not_offered_it(self):
        """They already fill the sheet; there is no room for a second copy."""
        with workspace(pages=8) as source:
            for schema in ("nup", "cutstack", "steprepeat"):
                with self.subTest(schema=schema):
                    status, _, err = run(schema, str(source), "--repeat", "auto")
                    self.assertEqual(status, 2)
                    self.assertIn("--repeat", err)

    def test_a_grid_that_will_not_fit_names_the_form(self):
        with workspace(pages=16, trim=HALF_LETTER) as source:
            status, _, err = run(
                "saddle",
                str(source),
                "--repeat",
                "2x2",
                "-o",
                str(source.with_name("o.pdf")),
            )
            self.assertEqual(status, 1)
            self.assertIn("copies of the saddle-stitch form", err)

    def test_the_slug_still_reaches_the_sheet(self):
        with workspace(pages=16, trim=HALF_LETTER) as source:
            output = source.with_name("o.pdf")
            run("saddle", str(source), "--repeat", "auto", "--slug", "-o", str(output))
            with pikepdf.open(output) as pdf:
                contents = pdf.pages[0].obj["/Contents"]
                raw = (
                    b"".join(p.read_bytes() for p in contents)
                    if isinstance(contents, pikepdf.Array)
                    else contents.read_bytes()
                )
            self.assertIn("sheet 1/4 front", raw.decode("latin-1"))
