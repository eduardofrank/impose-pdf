# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

# pylint: disable=missing-class-docstring,missing-function-docstring

"""One call from a source document to an imposed file."""

import io
import unittest

import pikepdf

from impose import ImposeError
from impose.geometry import Size
from impose.job import (
    DEFAULT_MARKS,
    SCHEMAS,
    build_plan,
    default_gutter,
    impose_document,
    source_boxes,
)
from impose.marks import MarkStyle
from impose.units import MM, to_mm

from .support import declare_pdfx, make_pdf


def run(pages=16, **kwargs):
    """Impose a generated document and return (result, written bytes)."""
    source = kwargs.pop("source", None) or make_pdf(pages)
    buffer = io.BytesIO()
    result = impose_document(source, buffer, **kwargs)
    return result, buffer.getvalue()


def content(data: bytes, page: int = 0) -> str:
    """The content stream of one page of a written document."""
    pdf = pikepdf.open(io.BytesIO(data))
    obj = pdf.pages[page].obj["/Contents"]
    text = (
        b"".join(s.read_bytes() for s in obj)
        if isinstance(obj, pikepdf.Array)
        else obj.read_bytes()
    ).decode("ascii")
    pdf.close()
    return text


class TestSchemas(unittest.TestCase):
    def test_every_schema_produces_a_file(self):
        cases = {
            "saddle": {},
            "perfect": {"section_pages": 8},
            "nup": {"columns": 2, "rows": 2},
            "cutstack": {"columns": 2, "rows": 2},
        }
        for schema, options in cases.items():
            with self.subTest(schema=schema):
                result, data = run(schema=schema, **options)
                self.assertGreater(result.sheets, 0)
                pdf = pikepdf.open(io.BytesIO(data))
                self.assertEqual(len(pdf.pages), result.surfaces)
                pdf.close()

    def test_step_and_repeat_places_one_page_many_times(self):
        """Business cards: 85 x 55 mm, three across and four down."""
        card = make_pdf(2, trim=Size(85 * MM, 55 * MM))
        result, _ = run(source=card, schema="steprepeat", columns=3, rows=4)
        self.assertEqual(result.plan.schema, "step-and-repeat")
        self.assertEqual(result.sheets, 1)

    def test_a_form_too_big_for_the_press_is_refused_with_both_sizes(self):
        with self.assertRaises(ImposeError) as caught:
            run(source=make_pdf(2), schema="steprepeat", columns=4, rows=4)
        message = str(caught.exception)
        self.assertIn("does not fit", message)
        self.assertIn("310 × 450 mm", message)

    def test_unknown_schema_lists_the_alternatives(self):
        with self.assertRaises(ImposeError) as caught:
            run(schema="stapled")
        self.assertIn("saddle", str(caught.exception))

    def test_bound_schemas_have_a_fixed_grid(self):
        for schema in ("saddle", "perfect"):
            with self.subTest(schema=schema), self.assertRaises(ImposeError) as c:
                run(schema=schema, columns=4, rows=2)
            self.assertIn("fixed by the binding", str(c.exception))

    def test_build_plan_defaults_the_grid_for_open_schemas(self):
        self.assertEqual(build_plan("nup", 8).grid, (2, 1))

    def test_registry_matches_the_documented_five(self):
        self.assertEqual(
            set(SCHEMAS), {"saddle", "perfect", "nup", "cutstack", "steprepeat"}
        )


class TestResult(unittest.TestCase):
    def test_describes_the_job(self):
        result, _ = run()
        text = result.describe()
        self.assertIn("saddle-stitch", text)
        self.assertIn("16 pages", text)
        self.assertIn("indigo-5000", text)

    def test_reports_the_finished_page_size(self):
        result, _ = run()
        self.assertAlmostEqual(to_mm(result.trim_size.width), 105.0, places=3)

    def test_reports_the_page(self):
        """The page is the imageable area, not the sheet it is cut from."""
        result, _ = run()
        self.assertAlmostEqual(to_mm(result.sheet_size.height), 450.0, places=3)
        self.assertAlmostEqual(to_mm(result.sheet_size.width), 310.0, places=3)


class TestMarks(unittest.TestCase):
    def test_marks_are_drawn_by_default(self):
        """A sheet with no indication of where to cut is no use to a bindery."""
        self.assertIn(" l S", content(run()[1]))
        self.assertIsInstance(DEFAULT_MARKS, MarkStyle)

    def test_marks_can_be_turned_off(self):
        self.assertNotIn(" l S", content(run(marks=None)[1]))

    def test_a_spine_is_dashed_but_a_cut_is_not(self):
        self.assertIn("[3 3] 0 d", content(run(schema="saddle")[1]))
        self.assertNotIn("[3 3] 0 d", content(run(schema="nup", columns=2, rows=1)[1]))

    def test_black_marks_use_no_separation(self):
        data = run(marks=MarkStyle(colour="black"))[1]
        self.assertIn("0 0 0 1 K", content(data))
        self.assertNotIn("SCN", content(data))


class TestSourceChecks(unittest.TestCase):
    def test_mixed_page_sizes_are_refused_by_page_number(self):
        source = make_pdf(3)
        odd = make_pdf(1, trim=Size(80 * MM, 100 * MM))
        source.pages.append(odd.pages[0])
        with self.assertRaises(ImposeError) as caught:
            run(source=source)
        self.assertIn("Page 4", str(caught.exception))
        self.assertIn("same size", str(caught.exception))

    def test_pdfx_without_a_trimbox_is_refused(self):
        source = declare_pdfx(make_pdf(4, with_trimbox=False))
        with self.assertRaises(ImposeError) as caught:
            run(source=source)
        self.assertIn("TrimBox", str(caught.exception))

    def test_a_plain_file_without_a_trimbox_is_accepted(self):
        """Without a PDF/X claim, CropBox is a reasonable finished size."""
        result, _ = run(source=make_pdf(4, with_trimbox=False))
        self.assertEqual(result.sheets, 1)

    def test_source_boxes_returns_the_shared_geometry(self):
        source = make_pdf(4)
        boxes = source_boxes(source)
        self.assertAlmostEqual(to_mm(boxes.trim_size.width), 105.0, places=3)

    def test_unopenable_source_is_reported(self):
        with self.assertRaises(ImposeError) as caught:
            impose_document("/nonexistent/nope.pdf", io.BytesIO())
        self.assertIn("Cannot open", str(caught.exception))


class TestOptions(unittest.TestCase):
    def test_gutters_accept_a_length(self):
        wide = run(schema="nup", columns=2, rows=1, gutters="10mm")[0]
        self.assertEqual(wide.sheets, 4)

    def test_press_can_be_named_or_given(self):
        result, _ = run(press="sra3")
        self.assertEqual(result.press, "sra3")

    def test_unknown_press_is_refused(self):
        with self.assertRaises(ImposeError):
            run(press="gutenberg")

    def test_a_sheet_larger_than_the_press_is_refused(self):
        with self.assertRaises(ImposeError) as caught:
            run(sheet="A1")
        self.assertIn("at most", str(caught.exception))

    def test_an_open_document_is_not_closed_by_the_caller(self):
        source = make_pdf(8)
        run(source=source)
        self.assertEqual(len(source.pages), 8)


class TestOrientation(unittest.TestCase):
    """Pages are turned in their cells when that is what fits."""

    @staticmethod
    def small_marks():
        """The default reach, spelled out: 2 mm clear then a 3 mm mark."""
        return MarkStyle(offset=2 * MM, length=3 * MM)

    def test_eight_a6_up_fits_on_the_default_marks(self):
        """The reason the defaults are 2 mm and 3 mm: five is what fits."""
        result, _ = run(pages=8, schema="nup", columns=2, rows=4, gutters="4mm")
        self.assertEqual(result.sheets, 1)
        self.assertTrue(
            all(p.rotation == 90 for s in result.plan for p in s.placements)
        )

    def test_six_a6_up_fits_only_once_the_pages_are_turned(self):
        """2x3 upright is 462 mm tall; on their sides the same six fit."""
        result, _ = run(
            pages=6,
            schema="nup",
            columns=2,
            rows=3,
            gutters="4mm",
            marks=self.small_marks(),
        )
        self.assertEqual(result.sheets, 1)
        self.assertTrue(
            all(p.rotation == 90 for s in result.plan for p in s.placements)
        )

    def test_eight_a6_up_also_fits(self):
        result, _ = run(
            pages=8,
            schema="nup",
            columns=2,
            rows=4,
            gutters="4mm",
            marks=self.small_marks(),
        )
        self.assertEqual(result.sheets, 1)

    def test_upright_is_preferred_when_it_fits(self):
        result, _ = run(pages=4, schema="nup", columns=2, rows=1)
        self.assertTrue(all(p.rotation == 0 for s in result.plan for p in s.placements))

    def test_upright_can_be_pinned(self):
        with self.assertRaises(ImposeError):
            run(
                pages=6,
                schema="nup",
                columns=2,
                rows=3,
                gutters="4mm",
                marks=self.small_marks(),
                orientation="upright",
            )

    def test_turned_can_be_pinned(self):
        result, _ = run(pages=4, schema="nup", columns=2, rows=1, orientation="turned")
        self.assertTrue(
            all(p.rotation == 90 for s in result.plan for p in s.placements)
        )

    def test_binding_schemas_are_never_turned_automatically(self):
        """Turning a saddle spread moves the fold and makes a top-bound book."""
        result, _ = run(pages=8, schema="saddle")
        self.assertTrue(all(p.rotation == 0 for s in result.plan for p in s.placements))

    def test_unknown_orientation_is_refused(self):
        with self.assertRaises(ImposeError) as caught:
            run(schema="nup", orientation="sideways")
        self.assertIn("auto, upright, or turned", str(caught.exception))

    def test_page_order_is_unchanged_by_turning(self):
        upright = build_plan("nup", 12, columns=2, rows=3)
        self.assertEqual(upright.placed_sources(), upright.turned().placed_sources())

    def test_the_refusal_names_what_is_taking_the_room(self):
        with self.assertRaises(ImposeError) as caught:
            run(pages=16, schema="nup", columns=4, rows=4, gutters="4mm")
        message = str(caught.exception)
        self.assertIn("for marks per edge", message)
        self.assertIn("misses by", message)


class TestWarnings(unittest.TestCase):
    """Things worth saying about a job that is otherwise imposable."""

    def test_a_thick_saddle_book_warns_about_stapling(self):
        result, _ = run(pages=64, schema="saddle")
        self.assertEqual(result.sheets, 16)
        self.assertTrue(any("staple" in w for w in result.warnings))

    def test_a_book_within_the_limit_says_nothing(self):
        result, _ = run(pages=60, schema="saddle")
        self.assertEqual(result.warnings, ())

    def test_the_limit_can_be_lowered_for_heavier_stock(self):
        result, _ = run(pages=40, schema="saddle", max_nested_sheets=8)
        self.assertTrue(any("exceeds the 8" in w for w in result.warnings))

    def test_other_schemas_do_not_warn_about_stapling(self):
        result, _ = run(pages=64, schema="nup")
        self.assertEqual(result.warnings, ())

    def test_a_warning_does_not_stop_the_job(self):
        result, data = run(pages=64, schema="saddle")
        self.assertTrue(result.warnings)
        self.assertGreater(len(data), 0)


class TestBleedCap(unittest.TestCase):
    """Bleed is capped at what the shop places, not at what the client sent."""

    @staticmethod
    def placed(source, **kwargs):
        """Bleed actually placed on the outer edge of the imposed form."""
        buffer = io.BytesIO()
        impose_document(source, buffer, schema="nup", gutters="4mm", **kwargs)
        buffer.seek(0)
        pdf = pikepdf.open(buffer)
        page = pdf.pages[0]
        trim = [float(v) for v in page.obj["/TrimBox"]]
        bleed = [float(v) for v in page.obj["/BleedBox"]]
        pdf.close()
        return to_mm(trim[0] - bleed[0])

    def test_generous_artwork_is_shaved_to_the_default(self):
        self.assertAlmostEqual(self.placed(make_pdf(8, bleed=5 * MM)), 2.0, places=3)

    def test_exactly_the_default_is_kept(self):
        self.assertAlmostEqual(self.placed(make_pdf(8, bleed=2 * MM)), 2.0, places=3)

    def test_less_than_the_default_is_not_invented(self):
        """Bleed that is not in the file cannot be manufactured."""
        self.assertAlmostEqual(self.placed(make_pdf(8, bleed=1 * MM)), 1.0, places=3)

    def test_no_bleed_stays_none(self):
        self.assertAlmostEqual(
            self.placed(make_pdf(8, with_bleedbox=False)), 0.0, places=3
        )

    def test_the_cap_is_editable(self):
        self.assertAlmostEqual(
            self.placed(make_pdf(8, bleed=5 * MM), bleed="5mm"), 5.0, places=3
        )

    def test_it_can_be_turned_off(self):
        self.assertAlmostEqual(
            self.placed(make_pdf(8, bleed=5 * MM), bleed=0), 0.0, places=3
        )


class TestGutterDefault(unittest.TestCase):
    """Cut work wants room for the knife; a folded spread wants none."""

    def test_cut_schemas_leave_room_for_the_knife(self):
        for schema in ("nup", "cutstack", "steprepeat"):
            with self.subTest(schema=schema):
                self.assertAlmostEqual(to_mm(default_gutter(schema)), 4.0, places=6)

    def test_folded_schemas_butt_at_the_spine(self):
        for schema in ("saddle", "perfect"):
            with self.subTest(schema=schema):
                self.assertEqual(default_gutter(schema), 0.0)

    def test_a_saddle_spread_still_meets_at_the_fold(self):
        """A gap here is a gap in the middle of the reader's page."""
        result, data = run(pages=8, schema="saddle")
        self.assertEqual(result.plan.grid, (2, 1))
        pdf = pikepdf.open(io.BytesIO(data))
        trim = [float(v) for v in pdf.pages[0].obj["/TrimBox"]]
        pdf.close()
        # Two A6 pages, no gutter: the form is exactly twice the page width.
        self.assertAlmostEqual(to_mm(trim[2] - trim[0]), 210.0, places=3)

    def test_an_explicit_gutter_still_wins_everywhere(self):
        result, _ = run(pages=8, schema="nup", gutters="10mm")
        self.assertEqual(result.sheets, 1)

    def test_zero_can_be_asked_for_explicitly(self):
        """None means 'the schema's default'; zero means zero."""
        result, data = run(pages=8, schema="nup", gutters=0)
        pdf = pikepdf.open(io.BytesIO(data))
        trim = [float(v) for v in pdf.pages[0].obj["/TrimBox"]]
        pdf.close()
        columns = result.plan.columns
        self.assertAlmostEqual(to_mm(trim[2] - trim[0]), columns * 148.0, places=3)


class TestFitSheet(unittest.TestCase):
    """A form sized to itself, for the first pass of a two-stage job."""

    def test_the_sheet_becomes_the_form(self):
        result, data = run(pages=8, schema="saddle", sheet="fit")
        self.assertEqual(result.press, "form")
        pdf = pikepdf.open(io.BytesIO(data))
        media = [float(v) for v in pdf.pages[0].obj["/MediaBox"]]
        pdf.close()
        # Two A6 pages side by side, plus the mark reach on each edge.
        self.assertAlmostEqual(to_mm(media[2] - media[0]), 210.0 + 10, places=3)
        self.assertAlmostEqual(to_mm(media[3] - media[1]), 148.0 + 10, places=3)

    def test_a_form_keeps_its_natural_boxes(self):
        """The next pass places it by its trim and keeps its bleed.

        That is what makes two forms meet correctly in a gutter: their bleeds
        abut in the middle of it and one cut serves both.
        """
        _, data = run(pages=8, schema="saddle", sheet="fit", marks=None)
        pdf = pikepdf.open(io.BytesIO(data))
        page = pdf.pages[0]
        media = [float(v) for v in page.obj["/MediaBox"]]
        trim = [float(v) for v in page.obj["/TrimBox"]]
        bleed = [float(v) for v in page.obj["/BleedBox"]]
        pdf.close()
        self.assertNotEqual(media, trim)
        self.assertEqual(media, bleed)
        self.assertAlmostEqual(to_mm(trim[0] - bleed[0]), 2.0, places=3)

    def test_no_marks_makes_a_smaller_form(self):
        _, with_marks = run(pages=8, schema="saddle", sheet="fit")
        _, bare = run(pages=8, schema="saddle", sheet="fit", marks=None)

        def width(data):
            pdf = pikepdf.open(io.BytesIO(data))
            box = [float(v) for v in pdf.pages[0].obj["/MediaBox"]]
            pdf.close()
            return box[2] - box[0]

        self.assertGreater(width(with_marks), width(bare))

    def test_the_press_is_ignored_because_this_is_not_run(self):
        """A form may be larger than any press; it is not going on one."""
        result, _ = run(pages=8, schema="saddle", sheet="fit", press="sra3")
        self.assertEqual(result.press, "form")

    def test_the_output_feeds_a_second_imposition(self):
        """Stage two: cut-and-stack keeps each form's front and back paired."""
        _, forms = run(pages=8, schema="saddle", sheet="fit", marks=None)
        source = pikepdf.open(io.BytesIO(forms))
        self.assertEqual(len(source.pages), 4)  # 2 spreads, front and back
        second = io.BytesIO()
        result = impose_document(
            source, second, schema="cutstack", columns=1, rows=2, gutters=0
        )
        source.close()
        self.assertEqual(result.sheets, 1)  # 4 forms -> 1 press sheet


class TestPageSize(unittest.TestCase):
    """What the output page is: the printable area, or the whole sheet."""

    @staticmethod
    def media(data):
        pdf = pikepdf.open(io.BytesIO(data))
        box = [float(v) for v in pdf.pages[0].obj["/MediaBox"]]
        pdf.close()
        return (to_mm(box[2] - box[0]), to_mm(box[3] - box[1]))

    def test_the_page_is_the_imageable_area_by_default(self):
        """A form that fits the page is a form that runs."""
        width, height = self.media(run(pages=8, schema="saddle")[1])
        self.assertAlmostEqual(width, 310.0, places=3)
        self.assertAlmostEqual(height, 450.0, places=3)

    def test_the_whole_sheet_can_be_asked_for(self):
        width, height = self.media(run(pages=8, schema="saddle", page="sheet")[1])
        self.assertAlmostEqual(width, 320.0, places=3)
        self.assertAlmostEqual(height, 470.0, places=3)

    def test_the_form_is_unchanged_either_way(self):
        """Only the page around it differs; the layout does not move."""

        def trim(data):
            pdf = pikepdf.open(io.BytesIO(data))
            box = [float(v) for v in pdf.pages[0].obj["/TrimBox"]]
            pdf.close()
            return (round(to_mm(box[2] - box[0]), 6), round(to_mm(box[3] - box[1]), 6))

        self.assertEqual(
            trim(run(pages=8, schema="saddle")[1]),
            trim(run(pages=8, schema="saddle", page="sheet")[1]),
        )

    def test_an_unknown_page_is_refused(self):
        with self.assertRaises(ImposeError) as caught:
            run(pages=8, schema="saddle", page="paper")
        self.assertIn("imageable or sheet", str(caught.exception))

    def test_a_form_sized_sheet_ignores_it(self):
        """--sheet fit already says exactly what the page is."""
        width, _ = self.media(run(pages=8, schema="saddle", sheet="fit", marks=None)[1])
        self.assertLess(width, 310.0)


class TestChosenGrid(unittest.TestCase):
    """Which grid gets picked when none is given."""

    def test_step_and_repeat_takes_the_densest(self):
        """It makes one sheet per item, so more copies a sheet is always better.

        Ranking it by sheets-for-a-quantity, as the schemas that divide a
        document are ranked, picks 42 up on a label that fits 50.
        """
        label = make_pdf(2, trim=Size(40 * MM, 55 * MM))
        result, _ = run(source=label, schema="steprepeat", gutters="4mm")
        self.assertEqual(result.plan.columns * result.plan.rows, 50)

    def test_the_dividing_schemas_still_weigh_the_page_count(self):
        """n-up spreads a document across cells; fewest sheets wins there."""
        result, _ = run(pages=8, schema="nup", gutters="4mm")
        self.assertEqual(result.sheets, 1)

    def test_an_explicit_grid_beats_either_rule(self):
        label = make_pdf(2, trim=Size(40 * MM, 55 * MM))
        result, _ = run(source=label, schema="steprepeat", columns=2, rows=2)
        self.assertEqual(result.plan.grid, (2, 2))
