# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

# pylint: disable=missing-class-docstring,missing-function-docstring

"""Reading the bundled font, and describing it to a PDF.

The metrics are checked against the font's own tables rather than against
numbers written down here, because a number written down here would only say
what the reader did, not whether it was right.
"""

import io
import pathlib
import struct
import tempfile
import unittest

import pikepdf

from impose import ImposeError
from impose.font import BUNDLED, FIRST_CHAR, FLAGS, LAST_CHAR, embed, load


def table(data, tag):
    """Where a table starts, read independently of impose.font."""
    count = struct.unpack(">H", data[4:6])[0]
    for index in range(count):
        at = 12 + 16 * index
        name, _checksum, offset, _length = struct.unpack(">4sIII", data[at : at + 16])
        if name.decode().strip() == tag:
            return offset
    raise AssertionError(f"no {tag} table")


class TestMeasuring(unittest.TestCase):
    def setUp(self):
        self.font = load()
        self.data = BUNDLED.read_bytes()

    def test_the_bundled_font_loads(self):
        self.assertEqual(self.font.name, "IBMPlexMono-Regular")

    def test_it_is_fixed_pitch(self):
        """Everything else here leans on this: one width, no hmtx walk."""
        self.assertTrue(self.font.fixed_pitch)

    def test_metrics_match_the_font_tables(self):
        head, hhea = table(self.data, "head"), table(self.data, "hhea")
        upem = struct.unpack(">H", self.data[head + 18 : head + 20])[0]
        self.assertEqual(upem, 1000)  # so glyph space needs no scaling
        self.assertEqual(
            self.font.bbox, struct.unpack(">hhhh", self.data[head + 36 : head + 44])
        )
        self.assertEqual(
            (self.font.ascent, self.font.descent),
            struct.unpack(">hh", self.data[hhea + 4 : hhea + 8]),
        )

    def test_the_advance_is_the_one_in_hmtx(self):
        at = table(self.data, "hmtx")
        self.assertEqual(
            self.font.advance, struct.unpack(">H", self.data[at : at + 2])[0]
        )

    def test_width_is_a_multiplication(self):
        for count in (0, 1, 40, 200):
            with self.subTest(count=count):
                self.assertAlmostEqual(
                    self.font.width("x" * count, 10), count * 6.0, places=9
                )

    def test_height_is_ascender_to_descender(self):
        self.assertAlmostEqual(self.font.height(10), 13.0, places=9)
        self.assertAlmostEqual(self.font.height(20), 26.0, places=9)

    def test_loading_is_cached(self):
        self.assertIs(load(), load())


class TestEncoding(unittest.TestCase):
    def setUp(self):
        self.font = load()

    def test_ascii_passes_through(self):
        self.assertEqual(self.font.encode("sheet 1 front"), b"sheet 1 front")

    def test_spanish_accents_survive(self):
        """A job called Catálogo has to set as Catálogo, not Cat?logo."""
        self.assertEqual(self.font.encode("Catálogo"), b"Cat\xe1logo")
        self.assertEqual(self.font.encode("Año Ñandú"), b"A\xf1o \xd1and\xfa")

    def test_what_winansi_cannot_say_is_substituted_not_refused(self):
        """Refusing a sheet over one character in a job name is the wrong
        trade; the sheet still has to print."""
        self.assertEqual(self.font.encode("a→b"), b"a?b")
        self.assertEqual(self.font.encode("日本"), b"??")

    def test_every_encodable_character_has_the_same_width(self):
        """The claim /Widths makes, checked across the whole range."""
        text = "".join(
            bytes([code]).decode("cp1252", errors="ignore")
            for code in range(FIRST_CHAR, LAST_CHAR + 1)
        )
        self.assertAlmostEqual(self.font.width(text, 10), len(text) * 6.0, places=9)


class TestEmbedding(unittest.TestCase):
    def setUp(self):
        self.pdf = pikepdf.new()
        self.font = load()
        self.obj = embed(self.pdf, self.font)

    def test_it_is_a_simple_truetype_font(self):
        self.assertEqual(str(self.obj["/Subtype"]), "/TrueType")
        self.assertEqual(str(self.obj["/Encoding"]), "/WinAnsiEncoding")
        self.assertEqual(str(self.obj["/BaseFont"]), "/IBMPlexMono-Regular")

    def test_widths_cover_the_encoding_and_are_all_one_number(self):
        widths = self.obj["/Widths"]
        self.assertEqual(int(self.obj["/FirstChar"]), FIRST_CHAR)
        self.assertEqual(int(self.obj["/LastChar"]), LAST_CHAR)
        self.assertEqual(len(widths), LAST_CHAR - FIRST_CHAR + 1)
        self.assertEqual({int(w) for w in widths}, {self.font.advance})

    def test_the_font_file_is_actually_embedded(self):
        """PDF/X requires it; naming a font and hoping is not an option."""
        descriptor = self.obj["/FontDescriptor"]
        stream = descriptor["/FontFile2"]
        self.assertEqual(stream.read_bytes(), self.font.data)
        self.assertEqual(int(stream["/Length1"]), len(self.font.data))

    def test_the_descriptor_says_fixed_pitch_and_nonsymbolic(self):
        """Nonsymbolic is what makes WinAnsiEncoding mean anything."""
        flags = int(self.obj["/FontDescriptor"]["/Flags"])
        self.assertEqual(flags, FLAGS)
        self.assertTrue(flags & 1)
        self.assertTrue(flags & 32)

    def test_the_descriptor_carries_a_stem_width(self):
        """No table has one, but a descriptor without it is incomplete."""
        self.assertGreater(int(self.obj["/FontDescriptor"]["/StemV"]), 0)

    def test_it_survives_a_save_and_reopen(self):
        page = self.pdf.add_blank_page(page_size=(200, 100))
        name = page.add_resource(self.obj, pikepdf.Name.Font)
        page.contents_add(
            pikepdf.Stream(
                self.pdf,
                f"BT {name} 10 Tf 10 40 Td (Cat\\341logo) Tj ET".encode("latin-1"),
            )
        )
        buffer = io.BytesIO()
        self.pdf.save(buffer)
        buffer.seek(0)
        with pikepdf.open(buffer) as reopened:
            fonts = reopened.pages[0].obj["/Resources"]["/Font"]
            embedded = next(iter(fonts.values()))
            self.assertEqual(
                len(embedded["/FontDescriptor"]["/FontFile2"].read_bytes()),
                len(self.font.data),
            )


class TestRefusals(unittest.TestCase):
    def test_a_missing_file_is_named(self):
        with self.assertRaises(ImposeError) as caught:
            load("/no/such/font.ttf")
        self.assertIn("Cannot read the font", str(caught.exception))

    def test_an_opentype_cff_font_is_refused_by_name(self):
        with tempfile.TemporaryDirectory() as folder:
            path = pathlib.Path(folder) / "fake.otf"
            path.write_bytes(b"OTTO" + b"\0" * 64)
            with self.assertRaises(ImposeError) as caught:
                load(path)
            self.assertIn("FontFile2", str(caught.exception))

    def test_a_font_missing_tables_is_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            path = pathlib.Path(folder) / "empty.ttf"
            path.write_bytes(struct.pack(">IHHHH", 0x00010000, 0, 0, 0, 0))
            with self.assertRaises(ImposeError) as caught:
                load(path)
            self.assertIn("table", str(caught.exception))
