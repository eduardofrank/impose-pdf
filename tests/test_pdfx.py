# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

# pylint: disable=missing-class-docstring,missing-function-docstring

"""Carrying a source's printing condition onto the imposed sheets."""

import io
import unittest

import pikepdf

from impose.job import impose_document
from impose.pdfx import Identity, carry_over, minimum_version, read

from .support import (
    ICC_MARKER,
    add_output_intent,
    declare_pdfx,
    make_pdf,
    set_trapped,
)


def imposed(source, **kwargs):
    """Impose *source* and reopen the result."""
    buffer = io.BytesIO()
    impose_document(source, buffer, **kwargs)
    buffer.seek(0)
    return pikepdf.open(buffer)


class TestRead(unittest.TestCase):
    def test_plain_file_declares_nothing(self):
        identity = read(make_pdf(2))
        self.assertIsNone(identity.version)
        self.assertEqual(identity.output_intents, 0)
        self.assertFalse(identity.declares_pdfx)

    def test_claim_and_condition_are_both_found(self):
        identity = read(add_output_intent(declare_pdfx(make_pdf(2))))
        self.assertIn("PDF/X-4", identity.version)
        self.assertEqual(identity.output_intents, 1)
        self.assertTrue(identity.is_complete)

    def test_a_claim_without_a_condition_was_never_backed(self):
        identity = read(declare_pdfx(make_pdf(2)))
        self.assertTrue(identity.declares_pdfx)
        self.assertFalse(identity.is_complete)
        self.assertIn("never backed", identity.describe())

    def test_trapping_is_read(self):
        self.assertEqual(read(set_trapped(make_pdf(2), "/True")).trapped, "/True")

    def test_describe_covers_both_shapes(self):
        self.assertIn("no PDF/X claim", read(make_pdf(2)).describe())
        self.assertIn(
            "PDF/X-4", read(add_output_intent(declare_pdfx(make_pdf(2)))).describe()
        )


class TestMinimumVersion(unittest.TestCase):
    def test_known_parts(self):
        self.assertEqual(minimum_version("PDF/X-4"), "1.6")
        self.assertEqual(minimum_version("PDF/X-1a:2003"), "1.4")
        self.assertEqual(minimum_version("PDF/X-3:2002"), "1.3")

    def test_matching_is_forgiving_about_form(self):
        self.assertEqual(minimum_version("pdf/x-4"), "1.6")
        self.assertEqual(minimum_version("PDF/X-4 "), "1.6")

    def test_unfamiliar_suffix_lands_on_its_family(self):
        self.assertEqual(minimum_version("PDF/X-5g:2010"), "1.6")

    def test_nothing_claimed(self):
        self.assertIsNone(minimum_version(None))
        self.assertIsNone(minimum_version("not a part"))


class TestCarryOver(unittest.TestCase):
    def test_output_intent_survives_with_its_profile(self):
        """The ICC profile is the printing condition; a copy without it is empty."""
        out = imposed(add_output_intent(declare_pdfx(make_pdf(4))))
        intents = out.Root.get("/OutputIntents")
        self.assertEqual(len(intents), 1)
        intent = intents[0]
        self.assertEqual(str(intent["/S"]), "/GTS_PDFX")
        self.assertEqual(str(intent["/OutputConditionIdentifier"]), "FOGRA39")
        self.assertIn(ICC_MARKER, intent["/DestOutputProfile"].read_bytes())
        out.close()

    def test_claim_is_restated_in_both_places(self):
        """Older tools read the info dictionary; ISO 15930 wants XMP."""
        out = imposed(add_output_intent(declare_pdfx(make_pdf(4))))
        self.assertIn("PDF/X-4", str(out.docinfo.get("/GTS_PDFXVersion")))
        with out.open_metadata() as meta:
            self.assertIn("PDF/X-4", meta.get("pdfxid:GTS_PDFXVersion"))
        out.close()

    def test_a_condition_is_kept_even_without_a_pdfx_claim(self):
        """It names what the separations were built for, claim or no claim."""
        out = imposed(add_output_intent(make_pdf(4)))
        self.assertEqual(len(out.Root.get("/OutputIntents")), 1)
        out.close()

    def test_trapping_is_carried_when_definite(self):
        out = imposed(set_trapped(add_output_intent(make_pdf(4)), "/True"))
        self.assertEqual(str(out.docinfo["/Trapped"]), "/True")
        out.close()

    def test_trapping_becomes_definite_when_it_was_not(self):
        """PDF/X requires an answer, and an untrapped digital job is the norm."""
        for source in (make_pdf(4), set_trapped(make_pdf(4), "/Unknown")):
            with self.subTest(source=source):
                out = imposed(source)
                self.assertEqual(str(out.docinfo["/Trapped"]), "/False")
                out.close()

    def test_plain_source_gains_no_intents(self):
        out = imposed(make_pdf(4))
        self.assertIsNone(out.Root.get("/OutputIntents"))
        out.close()

    def test_version_is_raised_to_meet_the_claim(self):
        out = imposed(add_output_intent(declare_pdfx(make_pdf(4), "PDF/X-4")))
        self.assertGreaterEqual(str(out.pdf_version), "1.6")
        out.close()

    def test_an_old_part_is_written_at_its_own_version(self):
        """PDF/X-1a:2003 is defined against PDF 1.4, so 1.4 is what to write.

        The output used to come out 1.5 because object streams were switched on
        unconditionally, which is a PDF 1.5 feature and breaks the claim.
        """
        out = imposed(add_output_intent(declare_pdfx(make_pdf(4), "PDF/X-1a:2003")))
        self.assertEqual(str(out.pdf_version), "1.4")
        out.close()

    def test_carry_over_is_callable_directly(self):
        source = add_output_intent(declare_pdfx(make_pdf(2)))
        target = pikepdf.Pdf.new()
        target.add_blank_page(page_size=(100, 100))
        carry_over(target, source, read(source))
        self.assertEqual(len(target.Root.get("/OutputIntents")), 1)


class TestReporting(unittest.TestCase):
    def test_the_result_names_the_claim(self):
        buffer = io.BytesIO()
        result = impose_document(add_output_intent(declare_pdfx(make_pdf(8))), buffer)
        self.assertIn("PDF/X-4", result.pdfx)
        self.assertIn("PDF/X-4", result.describe())

    def test_a_plain_job_reports_no_claim(self):
        buffer = io.BytesIO()
        result = impose_document(make_pdf(8), buffer)
        self.assertIsNone(result.pdfx)

    def test_identity_defaults_are_empty(self):
        self.assertFalse(Identity().declares_pdfx)


class TestRealWorldShapes(unittest.TestCase):
    """Shapes that real exports use and a convenient fixture does not."""

    @staticmethod
    def direct_intent(pdf):
        """An OutputIntent written directly, with only the profile indirect.

        Which is how a real PDF/X-1a export from a layout application does it.
        """
        profile = pikepdf.Stream(pdf, ICC_MARKER + b"\x00" * 64, N=4)
        pdf.Root.OutputIntents = pikepdf.Array(
            [
                pikepdf.Dictionary(
                    Type=pikepdf.Name.OutputIntent,
                    S=pikepdf.Name.GTS_PDFX,
                    OutputConditionIdentifier="CGATS TR 001",
                    DestOutputProfile=profile,
                )
            ]
        )
        return pdf

    def test_a_direct_output_intent_is_copied(self):
        """copy_foreign refuses direct objects; the intent has to be rebuilt."""
        source = self.direct_intent(declare_pdfx(make_pdf(4), "PDF/X-1:2001"))
        out = imposed(source)
        intents = out.Root.get("/OutputIntents")
        self.assertEqual(len(intents), 1)
        self.assertIn(ICC_MARKER, intents[0]["/DestOutputProfile"].read_bytes())
        self.assertEqual(str(intents[0]["/OutputConditionIdentifier"]), "CGATS TR 001")
        out.close()

    def test_the_x1_family_is_recognised(self):
        """Files claim PDF/X-1:2001 as well as PDF/X-1a:2001."""
        self.assertEqual(minimum_version("PDF/X-1:2001"), "1.3")
        self.assertEqual(minimum_version("PDF/X-1a:2001"), "1.3")

    def test_an_old_part_is_not_written_newer_than_it_arrived(self):
        """PDF/X-1a is defined against PDF 1.3, and object streams are 1.5."""
        source = self.direct_intent(declare_pdfx(make_pdf(4), "PDF/X-1:2001"))
        # Round-trip through a save so the document really carries 1.3, the way
        # an export from a layout application would.
        buffer = io.BytesIO()
        source.save(
            buffer,
            min_version="1.3",
            object_stream_mode=pikepdf.ObjectStreamMode.disable,
        )
        buffer.seek(0)
        out = imposed(pikepdf.open(buffer))
        self.assertEqual(str(out.pdf_version), "1.3")
        out.close()

    def test_a_modern_part_still_gets_object_streams(self):
        source = add_output_intent(declare_pdfx(make_pdf(4), "PDF/X-4"))
        out = imposed(source)
        self.assertGreaterEqual(str(out.pdf_version), "1.6")
        out.close()
