# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

# pylint: disable=missing-class-docstring,missing-function-docstring

"""Cutting the bundled font down to what a slug uses.

A subsetter is the kind of code that can be wrong in ways nothing complains
about: a font that parses, embeds and renders every glyph but one. So the
checks here are structural, because the suite depends on no system libraries
and so cannot put both fonts through a renderer. The strongest of them
compares the outline bytes glyph by glyph, which catches a missing, truncated
or misnumbered glyph as surely as looking at it would.
"""

import dataclasses
import struct
import unittest

import pikepdf

from impose import ImposeError
from impose.font import embed, glyphs, load
from impose.subset import (
    DISCARD,
    _directory,
    _with_components,
    subset,
    tag_for,
)

SLUG = "Catálogo.pdf · sheet 1/4 front · saddle-stitch 2×1 · indigo-5000 · 2026-09-21"


def directory(data):
    """Table tag -> (offset, length), read independently of impose.subset."""
    count = struct.unpack(">H", data[4:6])[0]
    found = {}
    for index in range(count):
        at = 12 + 16 * index
        tag, _checksum, offset, length = struct.unpack(">4sIII", data[at : at + 16])
        found[tag.decode().strip()] = (offset, length)
    return found


def outlines(data):
    """How many glyphs actually carry an outline."""
    tables = directory(data)
    head, maxp, loca = tables["head"][0], tables["maxp"][0], tables["loca"][0]
    long_format = struct.unpack(">h", data[head + 50 : head + 52])[0]
    count = struct.unpack(">H", data[maxp + 4 : maxp + 6])[0]
    if long_format:
        offsets = struct.unpack(f">{count + 1}I", data[loca : loca + 4 * (count + 1)])
    else:
        offsets = [
            v * 2
            for v in struct.unpack(
                f">{count + 1}H", data[loca : loca + 2 * (count + 1)]
            )
        ]
    return sum(1 for i in range(count) if offsets[i + 1] > offsets[i])


class TestWhatItRemoves(unittest.TestCase):
    def setUp(self):
        self.font = load()
        self.cut = subset(self.font.data, glyphs(self.font, SLUG))

    def test_it_is_much_smaller(self):
        self.assertLess(len(self.cut), len(self.font.data) / 5)

    def test_only_the_wanted_glyphs_keep_an_outline(self):
        """Everything else becomes a zero-length loca entry."""
        wanted = glyphs(self.font, SLUG)
        self.assertLess(outlines(self.cut), len(wanted) + 12)
        self.assertGreater(outlines(self.font.data), 900)

    def test_the_layout_tables_go(self):
        """A simple TrueType font in a PDF never consults them."""
        before, after = directory(self.font.data), directory(self.cut)
        self.assertTrue(DISCARD & set(before))
        self.assertFalse(DISCARD & set(after))

    def test_glyph_names_go(self):
        """post 2.0 carries a name per glyph; a PDF reaches glyphs through
        the encoding and the cmap, never by name."""
        at, _ = directory(self.cut)["post"]
        self.assertEqual(struct.unpack(">I", self.cut[at : at + 4])[0], 0x00030000)


class TestWhatItKeeps(unittest.TestCase):
    def setUp(self):
        self.font = load()
        self.cut = subset(self.font.data, glyphs(self.font, SLUG))

    def test_the_glyph_numbering_is_unchanged(self):
        """The whole design rests on this: cmap, hmtx and every composite's
        component references stay correct because nothing is renumbered."""
        before, after = directory(self.font.data), directory(self.cut)
        for table in ("cmap", "hmtx", "maxp", "hhea"):
            with self.subTest(table=table):
                start, length = before[table]
                at, size = after[table]
                self.assertEqual(
                    self.cut[at : at + size], self.font.data[start : start + length]
                )

    def test_notdef_is_always_kept(self):
        tables = directory(self.cut)
        head, loca = tables["head"][0], tables["loca"][0]
        long_format = struct.unpack(">h", self.cut[head + 50 : head + 52])[0]
        form = ">2I" if long_format else ">2H"
        first, second = struct.unpack(
            form, self.cut[loca : loca + struct.calcsize(form)]
        )
        self.assertGreater(second, first)

    def test_an_accent_brings_its_components(self):
        """An accented letter is a composite; dropping a component leaves the
        accent off, which on a Spanish job name is the failure this font was
        chosen to avoid."""
        plain = subset(self.font.data, glyphs(self.font, "a"))
        accented = subset(self.font.data, glyphs(self.font, "á"))
        self.assertGreater(outlines(accented), 1)
        self.assertGreater(len(accented), len(plain) - 2000)

    def test_it_still_loads_as_a_font(self):
        reread = dataclasses.replace(self.font, data=self.cut)
        self.assertEqual(reread.advance, self.font.advance)
        self.assertEqual(reread.bbox, self.font.bbox)


def glyph_outline(data, glyph):
    """One glyph's raw outline bytes, or b"" if it carries none."""
    tables = directory(data)
    head, maxp, loca, glyf = (
        tables["head"][0],
        tables["maxp"][0],
        tables["loca"][0],
        tables["glyf"][0],
    )
    long_format = struct.unpack(">h", data[head + 50 : head + 52])[0]
    count = struct.unpack(">H", data[maxp + 4 : maxp + 6])[0]
    if long_format:
        offsets = struct.unpack(f">{count + 1}I", data[loca : loca + 4 * (count + 1)])
    else:
        offsets = [
            v * 2
            for v in struct.unpack(
                f">{count + 1}H", data[loca : loca + 2 * (count + 1)]
            )
        ]
    return data[glyf + offsets[glyph] : glyf + offsets[glyph + 1]]


class TestTheOutlinesSurvive(unittest.TestCase):
    """What a renderer would show, checked without one.

    The suite depends on no system libraries, so it cannot put both fonts
    through Ghostscript and compare pixels -- that was done by hand and the
    two came out identical. What it can do is stronger than a smoke test: for
    every glyph the slug needs, the outline bytes in the subset must be the
    same bytes, at the same glyph number, as in the whole face. A missing or
    misnumbered glyph fails that; so does a truncated one.
    """

    def setUp(self):
        self.font = load()
        self.wanted = glyphs(self.font, SLUG)
        self.cut = subset(self.font.data, self.wanted)

    def test_every_needed_outline_is_byte_identical(self):
        for glyph in sorted(self.wanted):
            with self.subTest(glyph=glyph):
                before = glyph_outline(self.font.data, glyph)
                after = glyph_outline(self.cut, glyph)
                # A short loca counts in pairs, so an odd outline is padded.
                self.assertEqual(after[: len(before)], before)
                self.assertLessEqual(len(after) - len(before), 1)

    def test_nothing_unasked_for_survives_except_components(self):
        """A glyph keeps its outline only if the slug needs it or something
        the slug needs is built out of it."""
        needed = _with_components(
            self.font.data, _directory(self.font.data), self.wanted | {0}
        )
        kept = {g for g in range(1028) if glyph_outline(self.cut, g)}
        self.assertLessEqual(kept, needed)
        self.assertGreater(len(needed) - len(self.wanted), 0)

    def test_a_dropped_glyph_still_had_one_before(self):
        """Otherwise the test above would pass on a font of empty glyphs."""
        unused = sorted(set(range(200)) - self.wanted)
        self.assertTrue(any(glyph_outline(self.font.data, g) for g in unused))

    def test_the_accent_component_keeps_its_outline_too(self):
        accented = glyphs(self.font, "á").pop()
        cut = subset(self.font.data, {accented})
        components = [
            g for g in range(1028) if glyph_outline(cut, g) and g not in (0, accented)
        ]
        self.assertTrue(components)
        for glyph in components:
            with self.subTest(glyph=glyph):
                self.assertEqual(
                    glyph_outline(cut, glyph)[
                        : len(glyph_outline(self.font.data, glyph))
                    ],
                    glyph_outline(self.font.data, glyph),
                )


class TestTheSubsetTag(unittest.TestCase):
    def test_it_is_six_capitals(self):
        tag = tag_for({1, 2, 3})
        self.assertEqual(len(tag), 6)
        self.assertTrue(tag.isupper() and tag.isalpha())

    def test_the_same_subset_gets_the_same_tag(self):
        self.assertEqual(tag_for({5, 9, 1}), tag_for({1, 5, 9}))

    def test_different_subsets_get_different_tags(self):
        self.assertNotEqual(tag_for({1, 2}), tag_for({1, 3}))

    def test_an_embedded_subset_is_named_with_it(self):
        """PDF requires it, so a reader can tell a subset from the whole face
        of the same name."""
        font = load()
        pdf = pikepdf.new()
        obj = embed(pdf, font, SLUG)
        name = str(obj["/BaseFont"])
        self.assertRegex(name, r"^/[A-Z]{6}\+IBMPlexMono-Regular$")
        self.assertEqual(name, str(obj["/FontDescriptor"]["/FontName"]))

    def test_the_whole_face_is_not_tagged(self):
        font = load()
        pdf = pikepdf.new()
        self.assertEqual(str(embed(pdf, font)["/BaseFont"]), "/IBMPlexMono-Regular")


class TestRefusals(unittest.TestCase):
    def test_something_that_is_not_a_font_is_refused(self):
        with self.assertRaises(ImposeError):
            subset(b"nope", {1})

    def test_a_font_without_outlines_is_refused_by_name(self):
        with self.assertRaises(ImposeError) as caught:
            subset(struct.pack(">IHHHH", 0x00010000, 0, 0, 0, 0), {1})
        self.assertIn("glyf", str(caught.exception))
