# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

# pylint: disable=missing-class-docstring,missing-function-docstring

"""One call from a source document to an imposed file."""

import io
import unittest

import pikepdf

from impose import ImposeError
from impose.geometry import Size
from impose.job import DEFAULT_MARKS, SCHEMAS, build_plan, impose_document, source_boxes
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
        result, _ = run(source=card, schema="steprepeat", columns=3, rows=4, copies=24)
        self.assertEqual(result.plan.schema, "step-and-repeat")
        self.assertEqual(result.sheets, 2)

    def test_a_form_too_big_for_the_press_is_refused_with_both_sizes(self):
        with self.assertRaises(ImposeError) as caught:
            run(source=make_pdf(2), schema="steprepeat", columns=4, rows=2)
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

    def test_reports_the_sheet(self):
        result, _ = run()
        self.assertAlmostEqual(to_mm(result.sheet_size.height), 470.0, places=3)


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
        """A 5 mm mark reach, which is what an A6 six-up needs to fit."""
        return MarkStyle(offset=1 * MM, length=4 * MM)

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
            run(pages=6, schema="nup", columns=2, rows=3, gutters="4mm")
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
