# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

# pylint: disable=missing-class-docstring,missing-function-docstring

"""Gathered signatures.

The strongest check here is not one of these tests but the agreement between
two code paths: a signature folded once is the ordinary folded sheet, and must
come out identical to what perfect binding has always produced. Those two were
written months apart from different starting points, so if the folding model
were wrong they would disagree.
"""

import unittest

from impose import ImposeError
from impose.fold import FOOT_TO_FOOT, HEAD_TO_HEAD
from impose.geometry import Size
from impose.plan import BLANK
from impose.schemas import perfect, signature
from impose.units import MM

from .test_cli import run, workspace


def sources(plan):
    """Every placed page in surface order, blanks dropped."""
    return [
        placement.source
        for surface in plan.surfaces
        for placement in surface.placements
        if placement.source is not BLANK
    ]


class TestAgreesWithPerfectBinding(unittest.TestCase):
    """A 2 x 1 signature is one fold, which is what perfect already does."""

    def test_identical_for_every_length(self):
        for pages in (4, 8, 12, 16, 32, 100):
            with self.subTest(pages=pages):
                folded = signature.impose(pages, columns=2, rows=1)
                gathered = perfect.impose(pages, section_pages=4)
                self.assertEqual(
                    [(s.sheet, s.side, s.sources) for s in folded.surfaces],
                    [(s.sheet, s.side, s.sources) for s in gathered.surfaces],
                )

    def test_identical_sheet_counts(self):
        for pages in (4, 9, 16, 33):
            with self.subTest(pages=pages):
                self.assertEqual(
                    signature.impose(pages, columns=2, rows=1).sheets,
                    perfect.impose(pages, section_pages=4).sheets,
                )


class TestFoldedTwice(unittest.TestCase):
    def test_one_sheet_carries_eight_pages(self):
        plan = signature.impose(8, columns=2, rows=2)
        self.assertEqual(plan.sheets, 1)
        self.assertEqual(len(plan.surfaces), 2)

    def test_sixteen_pages_take_two_sheets_not_four(self):
        """The whole point: folding again halves the sheets."""
        self.assertEqual(signature.impose(16, columns=2, rows=2).sheets, 2)
        self.assertEqual(signature.impose(16, columns=2, rows=1).sheets, 4)

    def test_half_the_pages_are_upside_down(self):
        plan = signature.impose(8, columns=2, rows=2)
        turned = [p for s in plan.surfaces for p in s.placements if p.rotation]
        self.assertEqual(len(turned), 4)
        self.assertTrue(all(p.rotation == 180 for p in turned))

    def test_the_turned_pages_are_all_in_one_row(self):
        """Head to head: one row upright, the other inverted, meeting at the
        fold that gets trimmed."""
        plan = signature.impose(8, columns=2, rows=2)
        by_row = {}
        for surface in plan.surfaces:
            for placement in surface.placements:
                by_row.setdefault(placement.row, set()).add(placement.rotation)
        self.assertEqual(by_row, {0: {180}, 1: {0}})

    def test_foot_to_foot_inverts_the_other_row(self):
        plan = signature.impose(8, columns=2, rows=2, style=FOOT_TO_FOOT)
        by_row = {}
        for surface in plan.surfaces:
            for placement in surface.placements:
                by_row.setdefault(placement.row, set()).add(placement.rotation)
        self.assertEqual(by_row, {0: {0}, 1: {180}})

    def test_sixteen_page_signature(self):
        plan = signature.impose(32, columns=4, rows=2)
        plan.validate()
        self.assertEqual(plan.sheets, 2)
        self.assertEqual(plan.grid, (4, 2))


class TestGathering(unittest.TestCase):
    def test_sections_are_gathered_in_order(self):
        """Signature one holds the first pages, signature two the next --
        gathered, not nested."""
        plan = signature.impose(24, columns=2, rows=2)
        for sheet in range(plan.sheets):
            on_sheet = {
                placement.source
                for surface in plan.surfaces
                if surface.sheet == sheet
                for placement in surface.placements
                if placement.source is not BLANK
            }
            self.assertEqual(on_sheet, set(range(sheet * 8, sheet * 8 + 8)))

    def test_every_page_imposed_exactly_once(self):
        for pages in (8, 16, 24, 100):
            for grid in ((2, 1), (2, 2), (4, 2), (2, 4)):
                with self.subTest(pages=pages, grid=grid):
                    plan = signature.impose(pages, columns=grid[0], rows=grid[1])
                    plan.validate()
                    self.assertEqual(sorted(sources(plan)), list(range(pages)))

    def test_a_short_document_is_padded_to_a_whole_signature(self):
        plan = signature.impose(5, columns=2, rows=2)
        plan.validate()
        self.assertEqual(plan.pages, 5)
        self.assertEqual(plan.sheets, 1)
        blanks = [p for s in plan.surfaces for p in s.placements if p.source is BLANK]
        self.assertEqual(len(blanks), 3)

    def test_padding_falls_at_the_end_of_the_book(self):
        plan = signature.impose(5, columns=2, rows=2)
        self.assertEqual(sorted(sources(plan)), [0, 1, 2, 3, 4])


class TestFoldLines(unittest.TestCase):
    def test_one_fold_is_the_spine_only(self):
        plan = signature.impose(8, columns=2, rows=1)
        self.assertEqual(plan.fold_columns, (1,))
        self.assertEqual(plan.fold_rows, ())

    def test_folding_again_adds_a_crease_across_the_sheet(self):
        plan = signature.impose(8, columns=2, rows=2)
        self.assertEqual(plan.fold_columns, (1,))
        self.assertEqual(plan.fold_rows, (1,))

    def test_a_sixteen_page_signature_has_two_creases_one_way(self):
        plan = signature.impose(16, columns=4, rows=2)
        self.assertEqual(plan.fold_columns, (2, 3))
        self.assertEqual(plan.fold_rows, (1,))


class TestRefusals(unittest.TestCase):
    def test_a_grid_that_cannot_be_folded_is_refused(self):
        with self.assertRaises(ImposeError) as caught:
            signature.impose(8, columns=3, rows=1)
        self.assertIn("power of two", str(caught.exception))

    def test_an_unknown_style_is_refused(self):
        with self.assertRaises(ImposeError):
            signature.impose(8, columns=2, rows=2, style="sideways")

    def test_the_style_names_are_the_ones_offered(self):
        for style in (HEAD_TO_HEAD, FOOT_TO_FOOT):
            with self.subTest(style=style):
                signature.impose(8, columns=2, rows=2, style=style).validate()


class TestSignatureCommand(unittest.TestCase):
    """One sheet folded more than once, which is how a book is made."""

    def test_folding_again_halves_the_sheets(self):
        with workspace(pages=16) as source:
            out = str(source.with_name("o.pdf"))
            _, once, _ = run("signature", str(source), "--up", "2x1", "-o", out)
            _, twice, _ = run("signature", str(source), "--up", "2x2", "-o", out)
            self.assertIn("onto 4 sheet(s)", once)
            self.assertIn("onto 2 sheet(s)", twice)

    def test_the_grid_is_chosen_when_not_given(self):
        """The biggest signature the press can fold, without being told."""
        for trim, expected in (
            (Size(139.7 * MM, 215.9 * MM), "(2 × 2"),
            (Size(108 * MM, 140 * MM), "(4 × 2"),
        ):
            with self.subTest(trim=trim), workspace(pages=16, trim=trim) as source:
                status, text, err = run(
                    "signature", str(source), "-o", str(source.with_name("o.pdf"))
                )
                self.assertEqual(status, 0, err)
                self.assertIn(expected, text)

    def test_a_page_too_big_to_fold_says_so(self):
        with workspace(pages=8, trim=Size(400 * MM, 400 * MM)) as source:
            status, _, err = run(
                "signature", str(source), "-o", str(source.with_name("o.pdf"))
            )
            self.assertEqual(status, 1)
            self.assertIn("does not fold into a signature", err)

    def test_a_grid_that_cannot_be_folded_is_refused_in_a_sentence(self):
        with workspace(pages=16) as source:
            status, _, err = run(
                "signature",
                str(source),
                "--up",
                "3x2",
                "-o",
                str(source.with_name("o.pdf")),
            )
            self.assertEqual(status, 1)
            self.assertIn("power of two", err)

    def test_the_head_to_head_turn_reaches_the_sheet(self):
        with workspace(pages=8) as source:
            _, text, _ = run("signature", str(source), "--up", "2x2", "--dry-run")
            top, bottom = text.splitlines()[1], text.splitlines()[2]
            self.assertIn("*", top)  # the row that folds over is inverted
            self.assertNotIn("*", bottom)

    def test_foot_to_foot_turns_the_other_row(self):
        with workspace(pages=8) as source:
            _, text, _ = run(
                "signature",
                str(source),
                "--up",
                "2x2",
                "--fold-style",
                "foot-to-foot",
                "--dry-run",
            )
            top, bottom = text.splitlines()[1], text.splitlines()[2]
            self.assertNotIn("*", top)
            self.assertIn("*", bottom)

    def test_a_single_fold_matches_perfect_binding(self):
        """The listing is the same because the imposition is the same."""
        with workspace(pages=16) as source:
            _, folded, _ = run("signature", str(source), "--up", "2x1", "--dry-run")
            _, bound, _ = run("perfect", str(source), "--dry-run")
            self.assertEqual(
                folded.replace("signature", ""), bound.replace("perfect-bound", "")
            )

    def test_the_pages_are_never_turned_a_quarter_to_fit(self):
        """That would move both folds, which is a different product."""
        with workspace(pages=8, trim=Size(105 * MM, 148 * MM)) as source:
            _, text, _ = run(
                "signature",
                str(source),
                "--up",
                "2x2",
                "-o",
                str(source.with_name("o.pdf")),
            )
            self.assertIn("(2 × 2 upright)", text)


class TestSectionsInPages(unittest.TestCase):
    """A binder asks for a 16-page signature, not for a four-by-two grid."""

    QUARTER = Size(108 * MM, 140 * MM)
    HALF = Size(139.7 * MM, 215.9 * MM)

    def test_the_grid_is_worked_out_from_the_page_count(self):
        for section, grid in ((4, "(2 × 1"), (8, "(2 × 2"), (16, "(4 × 2")):
            with (
                self.subTest(section=section),
                workspace(pages=16, trim=self.QUARTER) as source,
            ):
                status, text, err = run(
                    "signature",
                    str(source),
                    "--section-pages",
                    str(section),
                    "-o",
                    str(source.with_name("o.pdf")),
                )
                self.assertEqual(status, 0, err)
                self.assertIn(grid, text)

    def test_bigger_sections_take_fewer_sheets(self):
        counts = []
        for section in (4, 8, 16):
            with workspace(pages=16, trim=self.QUARTER) as source:
                _, text, _ = run(
                    "signature",
                    str(source),
                    "--section-pages",
                    str(section),
                    "-o",
                    str(source.with_name("o.pdf")),
                )
                counts.append(int(text.split("onto ")[1].split(" ")[0]))
        self.assertEqual(counts, sorted(counts, reverse=True))
        self.assertEqual(counts, [4, 2, 1])

    def test_a_section_too_big_to_fit_says_what_does_fit(self):
        with workspace(pages=16, trim=self.HALF) as source:
            status, _, err = run(
                "signature",
                str(source),
                "--section-pages",
                "16",
                "-o",
                str(source.with_name("o.pdf")),
            )
            self.assertEqual(status, 1)
            self.assertIn("16-page signature", err)
            self.assertIn("largest that fits is 8 pages", err)

    def test_pages_and_a_grid_together_are_refused(self):
        with workspace(pages=16, trim=self.QUARTER) as source:
            status, _, err = run(
                "signature",
                str(source),
                "--section-pages",
                "8",
                "--up",
                "2x2",
                "-o",
                str(source.with_name("o.pdf")),
            )
            self.assertEqual(status, 1)
            self.assertIn("not both", err)


class TestPerfectBindingFolded(unittest.TestCase):
    """Perfect binding whose sections are folded rather than nested.

    Both make a section of the same page count and both gather it, so the book
    is the same book. What differs is the press: one folded sheet does the work
    of two nested ones.
    """

    QUARTER = Size(108 * MM, 140 * MM)

    def sheets(self, *extra, pages=12):
        with workspace(pages=pages, trim=self.QUARTER) as source:
            status, text, err = run(
                "perfect", str(source), "-o", str(source.with_name("o.pdf")), *extra
            )
            self.assertEqual(status, 0, err)
            return int(text.split("onto ")[1].split(" ")[0]), text

    def test_folding_halves_the_sheets(self):
        nested, _ = self.sheets("--section-pages", "8")
        folded, _ = self.sheets("--section-pages", "8", "--folded")
        self.assertEqual((nested, folded), (4, 2))

    def test_nesting_is_still_the_default(self):
        plain, _ = self.sheets("--section-pages", "8")
        nested, _ = self.sheets("--section-pages", "8")
        self.assertEqual(plain, nested)

    def test_it_reports_itself_as_the_signature_it_is(self):
        """Routing rather than reimplementing, so it says so."""
        _, text = self.sheets("--section-pages", "8", "--folded")
        self.assertIn("signature:", text)

    def test_a_folded_section_puts_half_its_pages_upside_down(self):
        with workspace(pages=8, trim=self.QUARTER) as source:
            _, text, _ = run(
                "perfect", str(source), "--section-pages", "8", "--folded", "--dry-run"
            )
            self.assertIn("*", text)
