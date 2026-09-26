# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

# pylint: disable=missing-class-docstring,missing-function-docstring
"""A cutter path, and a control strip embedded whole."""

import io
import pathlib
import tempfile
import unittest

import pikepdf

from impose import ImposeError
from impose.finishing import layer_note, place_strip, spot_name
from impose.geometry import Rect, Size
from impose.job import impose_document
from impose.press import INDIGO_5000
from impose.units import MM

from .support import make_pdf
from .test_cli import run, workspace


def _content(data: bytes) -> str:
    pdf = pikepdf.open(io.BytesIO(data))
    obj = pdf.pages[0].obj["/Contents"]
    raw = (
        b"".join(item.read_bytes() for item in obj)
        if isinstance(obj, pikepdf.Array)
        else obj.read_bytes()
    )
    return raw.decode("latin-1")


def _wedge(
    folder: pathlib.Path, width: float, height: float, pages: int = 1, rotation: int = 0
):
    pdf = pikepdf.Pdf.new()
    for _ in range(pages):
        page = pdf.add_blank_page(page_size=(width, height))
        # A mark that is the wedge's own, so a redraw would not be this stream.
        page.contents_add(pikepdf.Stream(pdf, b"0.2 0.4 0.6 rg 0 0 4 4 re f\n"))
        if rotation:
            page.obj["/Rotate"] = rotation
    path = folder / "wedge.pdf"
    pdf.save(path)
    return path


class TestCutterPath(unittest.TestCase):
    def test_each_piece_is_a_closed_path(self):
        buffer = io.BytesIO()
        impose_document(
            make_pdf(2),
            buffer,
            schema="nup",
            columns=2,
            rows=1,
            duplex=False,
            cut=True,
        )
        text = _content(buffer.getvalue())
        self.assertEqual(text.count("h S\n"), 2)
        pdf = pikepdf.open(io.BytesIO(buffer.getvalue()))
        meta = pdf.Root.OCProperties.OCGs[0].GTS_Metadata
        self.assertEqual(str(meta.GTS_ProcStepsGroup), "/Structural")
        self.assertEqual(str(meta.GTS_ProcStepsType), "/Cutting")
        separations = _separations(pdf.pages[0])
        self.assertIn("/CutContour", separations)

    def test_an_empty_cell_is_not_a_piece(self):
        buffer = io.BytesIO()
        impose_document(
            make_pdf(1),
            buffer,
            schema="nup",
            columns=2,
            rows=2,
            duplex=False,
            cut=True,
            marks=None,
        )
        self.assertEqual(_content(buffer.getvalue()).count("h S\n"), 1)

    def test_a_gang_outlines_each_size(self):
        card = make_pdf(pages=1, trim=Size(90 * MM, 50 * MM))
        flyer = make_pdf(pages=1, trim=Size(105 * MM, 148 * MM))
        card.pages.append(flyer.pages[0])
        buffer = io.BytesIO()
        impose_document(card, buffer, schema="gang", cut=True)
        self.assertEqual(_content(buffer.getvalue()).count("h S\n"), 2)

    def test_a_cover_is_cut_out(self):
        buffer = io.BytesIO()
        impose_document(make_pdf(1), buffer, schema="cover", cut=True)
        self.assertEqual(_content(buffer.getvalue()).count("h S\n"), 1)

    def test_a_bound_book_is_refused_by_name(self):
        with self.assertRaises(ImposeError) as caught:
            impose_document(make_pdf(8), io.BytesIO(), schema="saddle", cut=True)
        self.assertIn("saddle", str(caught.exception))

    def test_a_process_ink_cannot_name_the_path(self):
        with self.assertRaises(ImposeError) as caught:
            impose_document(
                make_pdf(1),
                io.BytesIO(),
                schema="nup",
                columns=1,
                rows=1,
                duplex=False,
                cut=True,
                cut_name="Black",
            )
        self.assertIn("Black", str(caught.exception))

    def test_a_spot_name_may_contain_a_space(self):
        self.assertEqual(spot_name(" Through Cut "), "Through Cut")
        buffer = io.BytesIO()
        impose_document(
            make_pdf(1),
            buffer,
            schema="nup",
            columns=1,
            rows=1,
            duplex=False,
            cut=True,
            cut_name="Through Cut",
        )
        pdf = pikepdf.open(io.BytesIO(buffer.getvalue()))
        self.assertIn("/Through#20Cut", _separations(pdf.pages[0]))

    def test_an_old_pdfx_claim_is_told_it_has_no_layers(self):
        note = layer_note("PDF/X-1a:2003", "CutContour")
        self.assertIn("PDF/X-1a:2003", note[0])
        self.assertEqual(layer_note("PDF/X-4", "CutContour"), ())

    def test_the_command_carries_the_flag(self):
        with workspace(pages=4, name="cards.pdf") as source:
            status, _, err = run("nup", str(source), "--cut", "--dry-run")
            self.assertEqual(status, 0, err)
            status, _, err = run("saddle", str(source), "--cut", "--dry-run")
            self.assertEqual(status, 1)
            self.assertIn("saddle", err)


class TestControlStrip(unittest.TestCase):
    def test_the_page_is_embedded_whole_at_the_tail(self):
        width, height = 40 * MM, 8 * MM
        buffer = io.BytesIO()
        with tempfile.TemporaryDirectory() as folder:
            path = _wedge(pathlib.Path(folder), width, height)
            impose_document(
                make_pdf(2),
                buffer,
                schema="nup",
                columns=1,
                rows=1,
                duplex=False,
                strip=path,
                colour_bar=True,
            )
        pdf = pikepdf.open(io.BytesIO(buffer.getvalue()))
        form = _wedge_form(pdf.pages[0], width)
        self.assertAlmostEqual(
            float(form.BBox[2]) - float(form.BBox[0]), width, places=3
        )
        self.assertIn(b"0.2 0.4 0.6 rg", form.read_bytes())
        self.assertIn("1 0 0 1", _content(buffer.getvalue()))
        # Both sheets share the one copy.
        first = _wedge_form(pdf.pages[0], width).objgen
        self.assertEqual(first, _wedge_form(pdf.pages[1], width).objgen)

    def test_the_working_bar_steps_aside(self):
        buffer = io.BytesIO()
        with tempfile.TemporaryDirectory() as folder:
            path = _wedge(pathlib.Path(folder), 30 * MM, 6 * MM)
            result = impose_document(
                make_pdf(1),
                buffer,
                schema="nup",
                columns=1,
                rows=1,
                duplex=False,
                strip=str(path),
                colour_bar=True,
            )
        self.assertIn("control strip", result.warnings[0])
        self.assertNotIn(" k\n", _content(buffer.getvalue()))

    def test_a_strip_that_does_not_fit_is_named(self):
        with tempfile.TemporaryDirectory() as folder:
            path = _wedge(pathlib.Path(folder), 400 * MM, 10 * MM)
            with self.assertRaises(ImposeError) as caught:
                impose_document(
                    make_pdf(1),
                    io.BytesIO(),
                    schema="nup",
                    columns=1,
                    rows=1,
                    duplex=False,
                    strip=path,
                )
        self.assertIn("400", str(caught.exception))
        self.assertIn("control strip", str(caught.exception))

    def test_several_pages_are_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            path = _wedge(pathlib.Path(folder), 20 * MM, 8 * MM, pages=2)
            with self.assertRaises(ImposeError) as caught:
                impose_document(
                    make_pdf(1),
                    io.BytesIO(),
                    schema="nup",
                    columns=1,
                    rows=1,
                    duplex=False,
                    strip=path,
                )
        self.assertIn("2 pages", str(caught.exception))

    def test_a_rotated_strip_is_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            path = _wedge(pathlib.Path(folder), 20 * MM, 8 * MM, rotation=90)
            with self.assertRaises(ImposeError) as caught:
                impose_document(
                    make_pdf(1),
                    io.BytesIO(),
                    schema="nup",
                    columns=1,
                    rows=1,
                    duplex=False,
                    strip=path,
                )
        self.assertIn("/Rotate", str(caught.exception))

    def test_placement_is_native_size_on_the_tail(self):
        area = INDIGO_5000.imageable_area()
        form = Rect(area.x0 + 20 * MM, area.y0 + 30 * MM, area.x1 - 20 * MM, area.y1)
        slot = place_strip(form, area, Size(40 * MM, 8 * MM), 5 * MM)
        self.assertAlmostEqual(slot.y0, area.y0, places=6)
        self.assertAlmostEqual(slot.width, 40 * MM, places=6)
        self.assertAlmostEqual(slot.height, 8 * MM, places=6)


def _separations(page) -> list[str]:
    found = []
    spaces = page.obj.get("/Resources", {}).get("/ColorSpace", {})
    for value in spaces.values():
        if str(value[0]) == "/Separation":
            found.append(str(value[1]))
    return found


def _wedge_form(page, width: float):
    for value in page.obj["/Resources"]["/XObject"].values():
        box = value.get("/BBox")
        if box is not None and abs(float(box[2]) - float(box[0]) - width) < 0.1:
            return value
    raise AssertionError("the strip was not embedded")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
