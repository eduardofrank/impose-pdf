# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

# pylint: disable=missing-class-docstring,missing-function-docstring

"""Writing the imposed sheet.

These assert the structure of the PDF rather than its pixels: the matrix that
carries a page into place, the boxes describing the sheet, and the colour the
marks are laid down in.
"""

import io
import unittest

import pikepdf

from impose.boxes import read_boxes
from impose.geometry import Rect
from impose.layout import lay_out
from impose.marks import MarkStyle, trim_marks
from impose.plan import BLANK, Placement, Surface
from impose.press import INDIGO_5000
from impose.render import Renderer, _placement_matrix
from impose.units import to_mm

from .support import make_pdf


def apply(matrix, point):
    """Apply a PDF matrix to a point, as the renderer's `cm` operator would."""
    a, b, c, d, e, f = matrix
    x, y = point
    return (a * x + c * y + e, b * x + d * y + f)


class TestPlacementMatrix(unittest.TestCase):
    """The matrix must carry the clip exactly onto the paint rectangle."""

    def _check(self, rotation, clip, paint):
        matrix = _placement_matrix(clip, paint, rotation)
        corners = [
            apply(matrix, (clip.x0, clip.y0)),
            apply(matrix, (clip.x1, clip.y0)),
            apply(matrix, (clip.x1, clip.y1)),
            apply(matrix, (clip.x0, clip.y1)),
        ]
        xs = [round(x, 6) for x, _ in corners]
        ys = [round(y, 6) for _, y in corners]
        self.assertAlmostEqual(min(xs), paint.x0, places=6)
        self.assertAlmostEqual(max(xs), paint.x1, places=6)
        self.assertAlmostEqual(min(ys), paint.y0, places=6)
        self.assertAlmostEqual(max(ys), paint.y1, places=6)

    def test_upright(self):
        self._check(0, Rect(10, 20, 110, 220), Rect(0, 0, 100, 200))

    def test_half_turn(self):
        self._check(180, Rect(10, 20, 110, 220), Rect(0, 0, 100, 200))

    def test_quarter_turns_swap_the_extents(self):
        clip = Rect(10, 20, 110, 220)
        self._check(90, clip, Rect(0, 0, 200, 100))
        self._check(270, clip, Rect(0, 0, 200, 100))

    def test_nothing_is_scaled(self):
        """A finished page is the size it is; resizing artwork is destruction."""
        matrix = _placement_matrix(Rect(0, 0, 100, 200), Rect(5, 5, 105, 205), 0)
        a, b, c, d, _, _ = matrix
        self.assertEqual((abs(a) + abs(c), abs(b) + abs(d)), (1, 1))

    def test_rejects_partial_turn(self):
        with self.assertRaises(ValueError):
            _placement_matrix(Rect(0, 0, 1, 1), Rect(0, 0, 1, 1), 45)


def build(marks=True, style=None, pages=4):
    """Impose a 2-up spread and return the written document."""
    source = make_pdf(pages)
    boxes = read_boxes(source.pages[0])
    layout = lay_out(
        Surface(0, "front", (Placement(3, 0, 0), Placement(0, 1, 0))),
        columns=2,
        rows=1,
        trim=boxes.trim_size,
        trim_origin=boxes.trim,
        bleed=boxes.bleed_insets,
        press=INDIGO_5000,
        mark_allowance=(style or MarkStyle()).reach,
    )
    renderer = Renderer(style=style)
    segments = (
        trim_marks([p.trim for p in layout.pages], style=style) if marks else None
    )
    renderer.add(layout, source, marks=segments)
    return renderer, layout


def content(page):
    """The page's content stream, joined."""
    obj = page.obj["/Contents"]
    if isinstance(obj, pikepdf.Array):
        return b"".join(s.read_bytes() for s in obj).decode("ascii")
    return obj.read_bytes().decode("ascii")


class TestBoxes(unittest.TestCase):
    def test_mediabox_is_the_press_sheet(self):
        renderer, _ = build()
        page = renderer.pdf.pages[0]
        media = [float(v) for v in page.obj["/MediaBox"]]
        self.assertAlmostEqual(to_mm(media[2] - media[0]), 320.0, places=3)
        self.assertAlmostEqual(to_mm(media[3] - media[1]), 470.0, places=3)

    def test_trimbox_is_the_whole_form(self):
        renderer, _ = build()
        trim = [float(v) for v in renderer.pdf.pages[0].obj["/TrimBox"]]
        self.assertAlmostEqual(to_mm(trim[2] - trim[0]), 210.0, places=3)
        self.assertAlmostEqual(to_mm(trim[3] - trim[1]), 148.0, places=3)

    def test_bleedbox_surrounds_the_trimbox(self):
        renderer, _ = build()
        page = renderer.pdf.pages[0]
        trim = [float(v) for v in page.obj["/TrimBox"]]
        bleed = [float(v) for v in page.obj["/BleedBox"]]
        self.assertLess(bleed[0], trim[0])
        self.assertGreater(bleed[2], trim[2])


class TestPlacement(unittest.TestCase):
    def test_form_bbox_is_the_source_sheet_not_its_trimbox(self):
        """Otherwise the bleed is clipped away before it can be placed."""
        renderer, _ = build()
        page = renderer.pdf.pages[0]
        source = make_pdf(1)
        expected = [round(float(v), 4) for v in source.pages[0].mediabox]
        for _, xobject in page.obj["/Resources"]["/XObject"].items():
            self.assertEqual([round(float(v), 4) for v in xobject["/BBox"]], expected)

    def test_each_placed_page_is_clipped(self):
        renderer, _ = build()
        self.assertEqual(content(renderer.pdf.pages[0]).count("re W n"), 2)

    def test_blank_cells_place_nothing(self):
        source = make_pdf(2)
        boxes = read_boxes(source.pages[0])
        layout = lay_out(
            Surface(0, "front", (Placement(0, 0, 0), Placement(BLANK, 1, 0))),
            columns=2,
            rows=1,
            trim=boxes.trim_size,
            trim_origin=boxes.trim,
            press=INDIGO_5000,
        )
        renderer = Renderer()
        renderer.add(layout, source)
        self.assertEqual(len(renderer.pdf.pages[0].obj["/Resources"]["/XObject"]), 1)


class TestMarkColour(unittest.TestCase):
    def test_registration_uses_separation_all(self):
        """A mark must appear on every plate, not only on black."""
        renderer, _ = build()
        spaces = renderer.pdf.pages[0].obj["/Resources"]["/ColorSpace"]
        self.assertEqual(len(spaces), 1)
        for _, space in spaces.items():
            self.assertEqual(str(space[0]), "/Separation")
            self.assertEqual(str(space[1]), "/All")
            self.assertEqual(str(space[2]), "/DeviceCMYK")
            self.assertEqual(int(space[3]["/FunctionType"]), 2)
            self.assertEqual([float(v) for v in space[3]["/C1"]], [1, 1, 1, 1])

    def test_registration_overprints(self):
        renderer, _ = build()
        states = renderer.pdf.pages[0].obj["/Resources"]["/ExtGState"]
        for _, state in states.items():
            self.assertTrue(bool(state["/OP"]))
            self.assertTrue(bool(state["/op"]))

    def test_black_marks_use_k_only(self):
        renderer, _ = build(style=MarkStyle(colour="black"))
        page = renderer.pdf.pages[0]
        self.assertNotIn("/ColorSpace", page.obj["/Resources"])
        self.assertIn("0 0 0 1 K", content(page))

    def test_marks_share_one_graphics_state(self):
        """One stream for every mark, not one stream per line."""
        renderer, _ = build()
        self.assertEqual(content(renderer.pdf.pages[0]).count("SCN"), 1)

    def test_no_marks_when_none_are_asked_for(self):
        renderer, _ = build(marks=False)
        page = renderer.pdf.pages[0]
        self.assertNotIn("/ColorSpace", page.obj["/Resources"])
        self.assertNotIn(" l S", content(page))


class TestSave(unittest.TestCase):
    def test_saved_document_reopens(self):
        renderer, _ = build()
        buffer = io.BytesIO()
        renderer.save(buffer)
        buffer.seek(0)
        with pikepdf.open(buffer) as written:
            self.assertEqual(len(written.pages), 1)
