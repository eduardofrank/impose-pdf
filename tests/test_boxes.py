# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

# pylint: disable=missing-class-docstring,missing-function-docstring

"""Reading the boxes a print-ready file carries."""

import dataclasses
import unittest

import pikepdf

from impose import ImposeError
from impose.boxes import (
    PageBoxes,
    assumed_trim_notes,
    has_output_intent,
    pdfx_version,
    read_boxes,
    require_trim,
    rotate_insets,
)
from impose.geometry import Insets, Rect, Size, same_size
from impose.units import MM, format_mm, to_mm

from .support import (
    OFFICE_SIZE,
    declare_pdfx,
    declared_boxes,
    make_office_pdf,
    make_pdf,
)


class TestReadBoxes(unittest.TestCase):
    def test_reads_what_the_file_declares(self):
        pdf = make_pdf(1)
        boxes = read_boxes(pdf.pages[0])
        self.assertAlmostEqual(to_mm(boxes.trim.width), 105.0, places=6)
        self.assertAlmostEqual(to_mm(boxes.trim.height), 148.0, places=6)
        # MediaBox is trim plus 3 mm bleed plus 6 mm slug, each side.
        self.assertAlmostEqual(to_mm(boxes.media.width), 123.0, places=6)
        self.assertTrue(boxes.has_explicit_trim)
        self.assertTrue(boxes.has_explicit_bleed)

    def test_bleed_insets(self):
        pdf = make_pdf(1, bleed=3 * MM)
        boxes = read_boxes(pdf.pages[0])
        for edge in ("left", "right", "bottom", "top"):
            with self.subTest(edge=edge):
                self.assertAlmostEqual(
                    to_mm(getattr(boxes.bleed_insets, edge)), 3.0, places=6
                )
        self.assertTrue(boxes.has_bleed)

    def test_defaults_when_boxes_are_absent(self):
        """Missing TrimBox and BleedBox both fall back to CropBox."""
        pdf = make_pdf(1, with_trimbox=False, with_bleedbox=False)
        boxes = read_boxes(pdf.pages[0])
        self.assertEqual(boxes.trim, boxes.crop)
        self.assertEqual(boxes.bleed, boxes.crop)
        self.assertFalse(boxes.has_explicit_trim)
        self.assertFalse(boxes.has_explicit_bleed)
        self.assertFalse(boxes.has_bleed)

    def test_no_bleedbox_means_no_bleed(self):
        """A file without BleedBox gets zero bleed, not an invented default."""
        pdf = make_pdf(1, with_bleedbox=False)
        boxes = read_boxes(pdf.pages[0])
        self.assertEqual(boxes.bleed_insets, Insets(0.0, 0.0, 0.0, 0.0))

    def test_cropbox_defaults_to_mediabox(self):
        pdf = pikepdf.Pdf.new()
        pdf.add_blank_page(page_size=(612, 792))
        boxes = read_boxes(pdf.pages[0])
        self.assertEqual(boxes.crop, Rect(0, 0, 612, 792))
        self.assertEqual(boxes.media, boxes.crop)

    def test_boxes_are_clipped_to_mediabox(self):
        """A TrimBox reaching past the sheet is clipped, per the specification."""
        pdf = pikepdf.Pdf.new()
        page = pdf.add_blank_page(page_size=(100, 100))
        page.obj["/TrimBox"] = pikepdf.Array([-50, -50, 150, 150])
        self.assertEqual(read_boxes(pdf.pages[0]).trim, Rect(0, 0, 100, 100))

    def test_box_outside_mediabox_is_an_error(self):
        pdf = pikepdf.Pdf.new()
        page = pdf.add_blank_page(page_size=(100, 100))
        page.obj["/TrimBox"] = pikepdf.Array([200, 200, 300, 300])
        with self.assertRaises(ImposeError):
            read_boxes(pdf.pages[0])

    def test_reversed_coordinates_are_normalized(self):
        """A box written x1,y1,x0,y0 is still that rectangle."""
        pdf = pikepdf.Pdf.new()
        page = pdf.add_blank_page(page_size=(100, 200))
        page.obj["/TrimBox"] = pikepdf.Array([80, 150, 20, 50])
        self.assertEqual(read_boxes(pdf.pages[0]).trim, Rect(20, 50, 80, 150))

    def test_nonzero_origin_mediabox(self):
        """Origins need not be zero, and nothing may assume they are."""
        pdf = pikepdf.Pdf.new()
        page = pdf.add_blank_page(page_size=(100, 100))
        page.obj["/MediaBox"] = pikepdf.Array([10, 20, 110, 120])
        page.obj["/TrimBox"] = pikepdf.Array([30, 40, 90, 100])
        boxes = read_boxes(pdf.pages[0])
        self.assertEqual(boxes.media, Rect(10, 20, 110, 120))
        self.assertEqual(boxes.trim, Rect(30, 40, 90, 100))
        self.assertEqual(boxes.trim_size, Size(60, 60))


class TestRotation(unittest.TestCase):
    def test_rotation_is_read(self):
        pdf = make_pdf(1, rotation=90)
        self.assertEqual(read_boxes(pdf.pages[0]).rotation, 90)

    def test_trim_size_is_what_a_reader_sees(self):
        upright_pdf, turned_pdf = make_pdf(1), make_pdf(1, rotation=90)
        upright = read_boxes(upright_pdf.pages[0]).trim_size
        turned = read_boxes(turned_pdf.pages[0]).trim_size
        self.assertEqual(turned, upright.swapped())

    def test_invalid_rotation_is_ignored(self):
        pdf = pikepdf.Pdf.new()
        page = pdf.add_blank_page(page_size=(100, 100))
        page.obj["/Rotate"] = 45
        self.assertEqual(read_boxes(pdf.pages[0]).rotation, 0)

    def test_rotation_normalizes(self):
        pdf = pikepdf.Pdf.new()
        page = pdf.add_blank_page(page_size=(100, 100))
        page.obj["/Rotate"] = -90
        self.assertEqual(read_boxes(pdf.pages[0]).rotation, 270)

    def test_quarter_turn_carries_left_edge_to_the_top(self):
        """/Rotate 90 displays the page turned clockwise."""
        self.assertEqual(rotate_insets(Insets(left=3), 90), Insets(top=3))
        self.assertEqual(rotate_insets(Insets(top=3), 90), Insets(right=3))

    def test_rotation_round_trips(self):
        insets = Insets(left=1, right=2, bottom=3, top=4)
        result = insets
        for _ in range(4):
            result = rotate_insets(result, 90)
        self.assertEqual(result, insets)

    def test_displayed_bleed_follows_rotation(self):
        pdf = make_pdf(1)
        boxes = dataclasses_replace_rotation(read_boxes(pdf.pages[0]), 90)
        self.assertAlmostEqual(
            boxes.displayed_bleed_insets.top, boxes.bleed_insets.left, places=9
        )


def dataclasses_replace_rotation(boxes: PageBoxes, rotation: int) -> PageBoxes:
    """A copy of *boxes* turned, without rebuilding the fixture."""
    return dataclasses.replace(boxes, rotation=rotation)


class TestRequireTrim(unittest.TestCase):
    """A file that never said what its finished size is.

    The specification's defaults answer, but with whatever the artwork was
    drawn on. That is the one measurement imposition cannot get anywhere else,
    so the page is refused and the refusal names the size that would have been
    assumed -- which is what tells the operator whether a box is missing or the
    artwork is wrong.
    """

    @staticmethod
    def boxes(**kwargs):
        pdf = make_pdf(1, **kwargs)
        return read_boxes(pdf.pages[0])

    def refusal(self, **kwargs) -> str:
        boxes = self.boxes(**kwargs)
        with self.assertRaises(ImposeError) as caught:
            require_trim(boxes, page_number=1)
        return str(caught.exception)

    def test_a_declared_trim_passes_in_silence(self):
        self.assertIsNone(require_trim(self.boxes(), page_number=1))
        self.assertEqual(self.boxes().trim_source, "TrimBox")

    def test_without_a_trimbox_the_size_is_named_and_so_is_its_box(self):
        boxes = self.boxes(with_trimbox=False, with_bleedbox=False)
        self.assertEqual(boxes.trim_source, "MediaBox")
        message = self.refusal(with_trimbox=False, with_bleedbox=False)
        self.assertIn("no TrimBox", message)
        self.assertIn("MediaBox", message)
        self.assertIn(format_mm(boxes.trim_size), message)

    def test_a_bleedbox_without_a_trimbox_is_said_more_plainly(self):
        """The file has declared bleed and not declared a page, so the size
        taken would definitely be the bleed rather than merely possibly it."""
        self.assertTrue(self.boxes(with_trimbox=False).has_explicit_bleed)
        message = self.refusal(with_trimbox=False)
        self.assertIn("BleedBox", message)
        self.assertIn("certainly bigger than the finished page", message)

    def test_a_cropbox_is_named_when_it_is_the_one_that_answered(self):
        pdf = make_pdf(1, with_trimbox=False, with_bleedbox=False)
        for page in pdf.pages:
            media = [float(v) for v in page.obj["/MediaBox"]]
            page.obj["/CropBox"] = pikepdf.Array(
                [media[0] + 6, media[1] + 6, media[2] - 6, media[3] - 6]
            )
        boxes = read_boxes(pdf.pages[0])
        self.assertEqual(boxes.trim_source, "CropBox")
        with self.assertRaises(ImposeError) as caught:
            require_trim(boxes, page_number=1)
        self.assertIn("CropBox", str(caught.exception))

    def test_the_size_named_is_the_size_that_was_on_offer(self):
        """The whole value of naming it: it is checkable at a glance, and it
        is not the finished size the artwork was drawn to."""
        boxes = self.boxes(with_trimbox=False, with_bleedbox=False)
        self.assertIn(
            format_mm(boxes.trim_size),
            self.refusal(with_trimbox=False, with_bleedbox=False),
        )
        self.assertNotEqual(boxes.trim_size, Size(105 * MM, 148 * MM))

    def test_the_page_that_is_wrong_is_the_one_named(self):
        boxes = self.boxes(with_trimbox=False, with_bleedbox=False)
        with self.assertRaises(ImposeError) as caught:
            require_trim(boxes, page_number=7)
        self.assertIn("Page 7", str(caught.exception))


class TestPdfX(unittest.TestCase):
    def test_plain_file_claims_nothing(self):
        self.assertIsNone(pdfx_version(make_pdf(1)))
        self.assertFalse(has_output_intent(make_pdf(1)))

    def test_declared_version_is_found(self):
        pdf = declare_pdfx(make_pdf(1), "PDF/X-4")
        self.assertIn("PDF/X-4", pdfx_version(pdf) or "")

    def test_pdfx_without_trimbox_is_refused_as_non_conformance(self):
        """Every file without a TrimBox is refused. This one is told that the
        standard it claims requires the box, because then the fault is in the
        export rather than in the hand-off."""
        pdf = make_pdf(1, with_trimbox=False)
        boxes = read_boxes(pdf.pages[0])
        with self.assertRaises(ImposeError) as caught:
            require_trim(boxes, page_number=1, pdfx="PDF/X-4")
        self.assertIn("PDF/X-4", str(caught.exception))
        self.assertIn("that standard requires", str(caught.exception))

    def test_trimbox_present_is_accepted(self):
        pdf = make_pdf(1)
        boxes = read_boxes(pdf.pages[0])
        self.assertIsNone(require_trim(boxes, page_number=1, pdfx="PDF/X-4"))


class TestTrimFromMediaBox(unittest.TestCase):
    """The opt-in for a file that never declared its finished size.

    An office export, a print-to-PDF or a scan has a MediaBox that genuinely
    is the finished page. Saying so is allowed; having it assumed is not.
    """

    @staticmethod
    def boxes(trim_from, **kwargs):
        pdf = make_pdf(1, with_trimbox=False, with_bleedbox=False, **kwargs)
        return read_boxes(pdf.pages[0], trim_from=trim_from)

    def test_the_size_comes_from_the_mediabox_and_says_so(self):
        boxes = self.boxes("mediabox")
        self.assertEqual(boxes.trim, boxes.media)
        self.assertEqual(boxes.trim_source, "MediaBox")
        self.assertEqual(boxes.assumed_from, "MediaBox")
        self.assertFalse(boxes.has_explicit_trim)

    def test_the_page_is_no_longer_refused(self):
        self.assertIsNone(require_trim(self.boxes("mediabox"), page_number=1))

    def test_a_pdfx_page_is_let_through_as_well(self):
        """The standard is broken either way. Whether to run the file anyway is
        the operator's call, and this is the operator making it."""
        boxes = self.boxes("mediabox")
        self.assertIsNone(require_trim(boxes, page_number=1, pdfx="PDF/X-4"))

    def test_a_cropbox_is_not_what_was_asked_for(self):
        """The specification would fall back to the CropBox, but a CropBox is a
        view somebody set in a reader. The opt-in names the MediaBox and gets
        the MediaBox."""
        pdf = make_pdf(1, with_trimbox=False, with_bleedbox=False)
        media = [float(value) for value in pdf.pages[0].obj["/MediaBox"]]
        pdf.pages[0].obj["/CropBox"] = pikepdf.Array(
            [media[0] + 6, media[1] + 6, media[2] - 6, media[3] - 6]
        )
        boxes = read_boxes(pdf.pages[0], trim_from="mediabox")
        self.assertEqual(boxes.trim, boxes.media)
        self.assertEqual(boxes.trim_source, "MediaBox")

    def test_a_declared_trim_is_read_off_the_trimbox_regardless(self):
        """The opt-in answers a question this file already answered."""
        pdf = make_pdf(1)
        declared = read_boxes(pdf.pages[0])
        opted_in = read_boxes(pdf.pages[0], trim_from="mediabox")
        self.assertEqual(opted_in.trim, declared.trim)
        self.assertEqual(opted_in.trim_source, "TrimBox")
        self.assertEqual(opted_in.assumed_from, "")

    def test_an_undeclared_bleed_is_still_no_bleed(self):
        """Taking the page from the MediaBox says nothing about bleed: there is
        no room outside the page to place any."""
        self.assertEqual(self.boxes("mediabox").bleed_insets, Insets())

    def test_an_unknown_box_is_refused_by_name(self):
        with self.assertRaises(ImposeError) as caught:
            self.boxes("bleedbox")
        self.assertIn("bleedbox", str(caught.exception))
        self.assertIn("trimbox or mediabox", str(caught.exception))

    def test_the_refusal_mentions_the_way_past_it(self):
        """Only the plainest refusal does. The operator who has 200 office
        exports to run should not have to find the option by accident."""
        boxes = self.boxes("trimbox")
        with self.assertRaises(ImposeError) as caught:
            require_trim(boxes, page_number=1)
        self.assertIn("ask for the MediaBox explicitly", str(caught.exception))

    def test_a_bleedbox_refusal_does_not_mention_it(self):
        """That file has said its MediaBox is bigger than its page, so the
        opt-in would be advice to impose a known-wrong size."""
        pdf = make_pdf(1, with_trimbox=False)
        boxes = read_boxes(pdf.pages[0])
        with self.assertRaises(ImposeError) as caught:
            require_trim(boxes, page_number=1)
        self.assertNotIn("MediaBox explicitly", str(caught.exception))


class TestOfficeExport(unittest.TestCase):
    """The population the opt-in exists for, in a file of that actual shape.

    :func:`make_pdf` with ``with_trimbox=False`` is a supplier's export with
    the box taken off it: the MediaBox still has bleed and slug around the
    page, so the opt-in there takes a size that is wrong by 18 mm. This file
    never had a finished size to declare, and its MediaBox is the page.
    """

    def setUp(self):
        # Held for the test's lifetime: a page outlives its document only as
        # far as the next collection, and then reads as destroyed.
        self.pdf = make_office_pdf(1)

    def page(self):
        return self.pdf.pages[0]

    def test_the_file_carries_one_box_and_only_one(self):
        """The property under test is a box that is absent, so assert it: an
        edit that hands the fixture a TrimBox back would otherwise pass."""
        self.assertEqual(declared_boxes(self.page()), ("/MediaBox",))

    def test_it_is_refused_by_default_like_any_other(self):
        """Being the honest case does not make it a readable one. Nothing in
        the file distinguishes it from the converted one."""
        with self.assertRaises(ImposeError) as caught:
            require_trim(read_boxes(self.page()), page_number=1)
        self.assertIn("210 × 297 mm", str(caught.exception))

    def test_the_opt_in_lands_on_the_finished_page_exactly(self):
        """Not approximately, and with nothing to subtract: this is the whole
        point of the option."""
        boxes = read_boxes(self.page(), trim_from="mediabox")
        self.assertTrue(same_size(boxes.trim_size, OFFICE_SIZE))
        self.assertEqual(boxes.assumed_from, "MediaBox")

    def test_there_is_nothing_outside_the_page_to_bleed_into(self):
        boxes = read_boxes(self.page(), trim_from="mediabox")
        self.assertEqual(boxes.trim, boxes.media)
        self.assertEqual(boxes.bleed_insets, Insets())
        self.assertFalse(boxes.has_bleed)

    def test_what_gets_reported_is_the_size_an_operator_recognises(self):
        """A4. An operator reading the warning can confirm it at a glance,
        which is the only check there is."""
        boxes = read_boxes(self.page(), trim_from="mediabox")
        note = assumed_trim_notes([(1, boxes)], pages=1)[0]
        self.assertIn("210 × 297 mm", note)
        self.assertIn("page 1", note)


class TestAssumedTrimNotes(unittest.TestCase):
    """What gets said about a size that was taken rather than declared."""

    @staticmethod
    def assumed(count, pages=None, **kwargs):
        pdf = make_pdf(
            pages or count, with_trimbox=False, with_bleedbox=False, **kwargs
        )
        return [
            (number, read_boxes(pdf.pages[number - 1], trim_from="mediabox"))
            for number in range(1, count + 1)
        ]

    def test_a_declared_document_is_not_news(self):
        self.assertEqual(assumed_trim_notes([], pages=8), ())

    def test_the_size_taken_is_named(self):
        """The whole point of the note: 105 × 148 mm is a page, 123 × 166 mm is
        a page with something added to it, and only the number says which."""
        notes = assumed_trim_notes(self.assumed(4), pages=4)
        self.assertEqual(len(notes), 1)
        self.assertIn("123 × 166 mm", notes[0])
        self.assertIn("MediaBox", notes[0])
        self.assertIn("all 4 pages", notes[0])

    def test_one_page_of_several_is_named_as_itself(self):
        notes = assumed_trim_notes(self.assumed(1, pages=8), pages=8)
        self.assertIn("page 1", notes[0])
        self.assertNotIn("all", notes[0])

    def test_pages_of_different_sizes_are_not_given_one_size(self):
        other = make_pdf(1, trim=Size(50 * MM, 90 * MM), with_trimbox=False)
        mixed = self.assumed(1, pages=1) + [
            (2, read_boxes(other.pages[0], trim_from="mediabox"))
        ]
        notes = assumed_trim_notes(mixed, pages=2)
        self.assertIn("each finished size", notes[0])

    def test_a_pdfx_claim_earns_a_second_sentence(self):
        """A file that claims the standard has lost a box it was required to
        write, which is a reason to doubt the size more, not less."""
        notes = assumed_trim_notes(self.assumed(2), pages=2, pdfx="PDF/X-4")
        self.assertEqual(len(notes), 2)
        self.assertIn("PDF/X-4", notes[1])
        self.assertIn("export", notes[1])
