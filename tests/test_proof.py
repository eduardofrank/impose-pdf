# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

# pylint: disable=missing-class-docstring,missing-function-docstring

"""The sheet an operator signs.

The proof is right or wrong by what it says is in each cell, and by being the
same size as the press sheet. Pixels are not the question.
"""

import io
import re
import unittest

import pikepdf

from impose.job import impose_document
from impose.units import to_mm

from .support import make_pdf


def content(page):
    """The page's content stream, joined and decompressed."""
    obj = page.obj["/Contents"]
    if isinstance(obj, pikepdf.Array):
        return b"".join(stream.read_bytes() for stream in obj).decode("latin-1")
    return obj.read_bytes().decode("latin-1")


def folios(page):
    """``(first matrix number, label)`` for every text object on *page*."""
    found = []
    for matrix, label in re.findall(r"([0-9.\- ]+) Tm\n\(([^)]*)\) Tj", content(page)):
        found.append((float(matrix.split()[0]), label))
    return found


def labels(page):
    """The folio and blank labels on *page*, caption excluded."""
    return [
        label for _, label in folios(page) if label != "PROOF" and "sheet" not in label
    ]


def proof_of(source, **options):
    """Impose *source* as a proof only, and return the opened document."""
    buffer = io.BytesIO()
    impose_document(source, io.BytesIO(), plan_only=True, proof=buffer, **options)
    buffer.seek(0)
    return pikepdf.open(buffer)


class TestProof(unittest.TestCase):
    def test_saddle_front_carries_the_outer_pages(self):
        """Page 1 sits beside the last page, which is the whole of saddle stitch."""
        with proof_of(make_pdf(8), schema="saddle") as document:
            self.assertEqual(len(document.pages), 4)
            front = labels(document.pages[0])
            self.assertEqual(set(front), {"8", "1"})
            self.assertIn("sheet 1/2 front", content(document.pages[0]))
            self.assertIn("sheet 1/2 back", content(document.pages[1]))
            self.assertIn("[3 3] 0 d", content(document.pages[0]))

    def test_a_blank_is_named_blank(self):
        with proof_of(make_pdf(2), schema="saddle") as document:
            self.assertIn("blank", labels(document.pages[0]))
            self.assertIn("1", labels(document.pages[0]))
            self.assertNotIn("2", labels(document.pages[0]))
            self.assertIn("2", labels(document.pages[1]))

    def test_a_repeated_page_is_numbered_in_every_cell(self):
        with proof_of(make_pdf(1), schema="steprepeat", columns=2, rows=2) as document:
            self.assertEqual(labels(document.pages[0]).count("1"), 4)

    def test_an_upside_down_page_reads_upside_down(self):
        with proof_of(make_pdf(8), schema="signature", columns=2, rows=2) as document:
            by_label = {label: scale for scale, label in folios(document.pages[0])}
            self.assertGreater(by_label["1"], 0)
            self.assertLess(by_label["5"], 0)

    def test_the_page_is_the_press_page(self):
        source = make_pdf(8)
        press = io.BytesIO()
        picture = io.BytesIO()
        impose_document(source, press, schema="saddle", proof=picture)
        press.seek(0)
        picture.seek(0)
        with pikepdf.open(press) as sheets, pikepdf.open(picture) as proof:
            self.assertEqual(len(proof.pages), len(sheets.pages))
            for approved, imposed in zip(proof.pages, sheets.pages):
                self.assertEqual(
                    [round(float(v), 3) for v in approved.mediabox],
                    [round(float(v), 3) for v in imposed.mediabox],
                )
            media = [float(v) for v in proof.pages[0].mediabox]
            self.assertAlmostEqual(to_mm(media[2] - media[0]), 310.0, places=2)
            self.assertAlmostEqual(to_mm(media[3] - media[1]), 450.0, places=2)

    def test_the_artwork_is_not_in_the_proof(self):
        with proof_of(make_pdf(4), schema="nup", columns=2, rows=1) as document:
            self.assertNotIn("1 0 0 rg", content(document.pages[0]))

    def test_a_dry_run_writes_the_proof_and_not_the_press_file(self):
        output = io.BytesIO()
        picture = io.BytesIO()
        impose_document(
            make_pdf(4), output, schema="saddle", plan_only=True, proof=picture
        )
        self.assertEqual(output.getvalue(), b"")
        self.assertTrue(picture.getvalue().startswith(b"%PDF"))
