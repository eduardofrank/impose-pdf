# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

# pylint: disable=missing-class-docstring,missing-function-docstring

"""The slug line: what the sheet says about itself, and where it says it."""

import datetime
import pathlib
import tempfile
import unittest

import pikepdf

from impose.font import load
from impose.geometry import Rect, Size
from impose.slug import GAP, compose, place
from impose.units import MM

from .support import make_pdf
from .test_cli import run, workspace

WHEN = datetime.datetime(2026, 9, 12, 21, 30)

#: An Indigo 5000 imageable area with a form the width of a half-letter spread.
PAGE = Rect(0, 0, 310 * MM, 450 * MM)
FORM = Rect(15.3 * MM, 7.1 * MM, 294.7 * MM, 442.9 * MM)
REACH = 5 * MM


def line(**overrides):
    fields = {
        "source": "Catálogo.pdf",
        "sheet": 0,
        "side": "front",
        "sheets": 4,
        "schema": "saddle-stitch",
        "grid": (2, 1),
        "press": "indigo-5000",
        "when": WHEN,
    }
    return compose(**{**fields, **overrides})


class TestComposing(unittest.TestCase):
    def test_it_says_which_sheet_and_side(self):
        self.assertIn("sheet 1/4 front", line())
        self.assertIn("sheet 3/4 back", line(sheet=2, side="back"))

    def test_the_sheet_number_is_counted_as_a_person_counts(self):
        """Plans number from zero; a press operator does not."""
        self.assertIn("sheet 1/4", line(sheet=0))

    def test_it_names_the_file(self):
        self.assertTrue(line().startswith("Catálogo.pdf"))

    def test_it_carries_the_press_and_the_grid(self):
        """So a sheet imposed for one machine is not run on another."""
        self.assertIn("indigo-5000", line())
        self.assertIn("saddle-stitch 2×1", line())

    def test_it_is_stamped(self):
        self.assertIn("2026-09-12 21:30", line())

    def test_a_time_is_taken_when_none_is_given(self):
        self.assertRegex(line(when=None), r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}")


class TestPlacing(unittest.TestCase):
    def setUp(self):
        self.font = load()

    def test_it_sets_in_the_side_margin(self):
        slug = place(line(), page=PAGE, form=FORM, reach=REACH, font=self.font)
        self.assertIsNotNone(slug)
        self.assertLess(slug.x, FORM.x0 - REACH)
        self.assertGreater(slug.x, PAGE.x0)

    def test_it_reads_up_the_sheet(self):
        slug = place(line(), page=PAGE, form=FORM, reach=REACH, font=self.font)
        self.assertEqual(slug.rotation, 90)

    def test_it_clears_the_crop_marks_and_the_sheet_edge(self):
        """Turned a quarter, the strip runs from x-ascent to x-descent."""
        slug = place(line(), page=PAGE, form=FORM, reach=REACH, font=self.font)
        left = slug.x - self.font.ascent * slug.size / 1000
        right = slug.x - self.font.descent * slug.size / 1000
        self.assertGreaterEqual(left, PAGE.x0)
        self.assertLessEqual(right, FORM.x0 - REACH)

    def test_the_strip_is_centred_in_the_clear_band(self):
        slug = place(line(), page=PAGE, form=FORM, reach=REACH, font=self.font)
        left = slug.x - self.font.ascent * slug.size / 1000
        right = slug.x - self.font.descent * slug.size / 1000
        self.assertAlmostEqual(
            (left + right) / 2, (PAGE.x0 + FORM.x0 - REACH) / 2, places=6
        )

    def test_it_starts_at_the_foot_of_the_form(self):
        slug = place(line(), page=PAGE, form=FORM, reach=REACH, font=self.font)
        self.assertAlmostEqual(slug.y, FORM.y0, places=9)

    def test_it_stays_within_the_form(self):
        """'Not beyond the crop marks': the line must not run into the
        corners where the end marks are."""
        slug = place(line(), page=PAGE, form=FORM, reach=REACH, font=self.font)
        self.assertLessEqual(
            slug.y + self.font.width(slug.text, slug.size), FORM.y1 + 1e-6
        )

    def test_a_margin_with_no_room_gets_no_slug(self):
        """Rather than shrinking the type or moving it somewhere it should not
        be, as the colour bar already does."""
        tight = Rect(0, 0, 310 * MM, 450 * MM)
        wide = Rect(6 * MM, 7 * MM, 304 * MM, 443 * MM)
        self.assertIsNone(
            place(line(), page=tight, form=wide, reach=REACH, font=self.font)
        )

    def test_the_boundary_is_the_strip_plus_its_clearances(self):
        strip = self.font.height(10)
        for slack, expected in ((0.2 * MM, True), (-0.2 * MM, False)):
            with self.subTest(slack=slack):
                need = strip + 2 * GAP + slack
                form = Rect(need + REACH, 7 * MM, 300 * MM, 443 * MM)
                placed = place(
                    line(), page=PAGE, form=form, reach=REACH, font=self.font
                )
                self.assertEqual(placed is not None, expected)


class TestShortening(unittest.TestCase):
    def setUp(self):
        self.font = load()

    def test_a_line_that_fits_is_untouched(self):
        slug = place(line(), page=PAGE, form=FORM, reach=REACH, font=self.font)
        self.assertEqual(slug.text, line())

    def test_fields_drop_from_the_least_useful_end(self):
        """The fields are already in the order someone at the press needs
        them, so the stamp goes before the press, and the name and the sheet
        number go last."""
        ladder = []
        for height in (250, 160, 80, 40):
            form = Rect(15.3 * MM, 0, 294.7 * MM, height * MM)
            slug = place(line(), page=PAGE, form=form, reach=REACH, font=self.font)
            ladder.append(slug.text)
        self.assertIn("2026-09-12", ladder[0])
        self.assertNotIn("2026-09-12", ladder[1])
        self.assertIn("indigo-5000", ladder[1])
        self.assertNotIn("indigo-5000", ladder[2])
        self.assertIn("Catálogo.pdf", ladder[2])
        self.assertIn("sheet 1/4 front", ladder[3])

    def test_the_name_is_shortened_from_its_end_and_only_last(self):
        """The beginning of a name is what identifies it."""
        short = Rect(15.3 * MM, 0, 294.7 * MM, 60 * MM)
        slug = place(line(), page=PAGE, form=short, reach=REACH, font=self.font)
        self.assertTrue(slug.text.startswith("Catálogo"))
        self.assertIn("…", slug.text)
        self.assertTrue(slug.text.endswith("sheet 1/4 front"))

    def test_what_is_kept_actually_fits(self):
        for height in (20, 40, 80, 160):
            with self.subTest(height=height):
                form = Rect(15.3 * MM, 0, 294.7 * MM, height * MM)
                slug = place(line(), page=PAGE, form=form, reach=REACH, font=self.font)
                self.assertLessEqual(
                    self.font.width(slug.text, slug.size), form.height + 1e-6
                )


class TestSlugLine(unittest.TestCase):
    """What the sheet says about itself, end to end."""

    @staticmethod
    def stream(path):
        with pikepdf.open(path) as pdf:
            contents = pdf.pages[0].obj["/Contents"]
            raw = (
                b"".join(part.read_bytes() for part in contents)
                if isinstance(contents, pikepdf.Array)
                else contents.read_bytes()
            )
        return raw.decode("latin-1")

    @staticmethod
    def embeds_the_font(path):
        with pikepdf.open(path) as pdf:
            return any(
                "IBMPlexMono" in str(obj.get("/BaseFont", ""))
                for obj in pdf.objects
                if isinstance(obj, pikepdf.Dictionary) and "/BaseFont" in obj
            )

    def test_it_is_off_unless_asked_for(self):
        with workspace(pages=8) as source:
            output = source.with_name("o.pdf")
            run("saddle", str(source), "-o", str(output))
            self.assertNotIn(" Tj", self.stream(output))
            self.assertFalse(self.embeds_the_font(output))

    def test_it_prints_the_sheet_and_side(self):
        with workspace(pages=8) as source:
            output = source.with_name("o.pdf")
            status, _, err = run("saddle", str(source), "--slug", "-o", str(output))
            self.assertEqual(status, 0, err)
            text = self.stream(output)
            self.assertIn("sheet 1/2 front", text)
            self.assertIn("saddle-stitch", text)
            self.assertIn("indigo-5000", text)

    def test_each_surface_gets_its_own(self):
        with workspace(pages=8) as source:
            output = source.with_name("o.pdf")
            run("saddle", str(source), "--slug", "-o", str(output))
            with pikepdf.open(output) as pdf:
                sides = []
                for page in pdf.pages:
                    contents = page.obj["/Contents"]
                    raw = (
                        b"".join(p.read_bytes() for p in contents)
                        if isinstance(contents, pikepdf.Array)
                        else contents.read_bytes()
                    )
                    body = raw.decode("latin-1")
                    sides.append("front" in body.split("sheet ")[1][:20])
            self.assertEqual(sides, [True, False, True, False])

    def test_the_font_is_embedded_only_when_it_is_used(self):
        """PDF/X needs it embedded; a job without a slug should not carry
        130 kB of font for nothing."""
        with workspace(pages=8) as source:
            with_slug = source.with_name("with.pdf")
            without = source.with_name("without.pdf")
            run("saddle", str(source), "--slug", "-o", str(with_slug))
            run("saddle", str(source), "-o", str(without))
            self.assertTrue(self.embeds_the_font(with_slug))
            self.assertFalse(self.embeds_the_font(without))

    def test_an_accented_job_name_reaches_the_sheet(self):
        """The content stream is bytes, and á is 0xE1. Encoding it as ASCII
        raised rather than printing, which is how this was found."""
        with tempfile.TemporaryDirectory() as folder:
            folder = pathlib.Path(folder)
            source = folder / "Catálogo.pdf"
            make_pdf(8, trim=Size(105 * MM, 148 * MM)).save(source)
            output = folder / "o.pdf"
            status, _, err = run("saddle", str(source), "--slug", "-o", str(output))
            self.assertEqual(status, 0, err)
            self.assertIn("Cat\xe1logo.pdf", self.stream(output))

    def test_it_is_left_off_where_the_margin_has_no_room(self):
        """--sheet fit makes the page the form, so there is no margin."""
        with workspace(pages=8) as source:
            output = source.with_name("o.pdf")
            status, _, err = run(
                "saddle", str(source), "--slug", "--sheet", "fit", "-o", str(output)
            )
            self.assertEqual(status, 0, err)
            self.assertNotIn(" Tj", self.stream(output))

    def test_it_is_set_in_black_not_registration(self):
        """A slug is for a person to read, not a device for registering
        plates; registration colour would be 400% ink in the margin."""
        with workspace(pages=8) as source:
            output = source.with_name("o.pdf")
            run("saddle", str(source), "--slug", "-o", str(output))
            text = self.stream(output)
            self.assertIn("/DeviceGray cs 0 sc", text)
