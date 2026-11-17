# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE.

# pylint: disable=missing-class-docstring,missing-function-docstring

"""A file that is wrong is told so in a sentence, whatever is wrong with it.

A watched folder takes its files from strangers, and what impose says about
one is filed beside it for whoever opens the folder. So a file that breaks
something inside impose must not come back as a stack trace: that is a
sentence about impose's source code, handed to a customer about their
artwork, under a status that says the *job* was described wrongly.

Found by damaging a valid file a byte at a time and imposing each result:
38 of 676 mutations left as a traceback and exit 1, from two places. Both are
pinned here by a file built to reach them, and the search that found them is
kept, with a fixed seed, so that a third place is a failing test.
"""

import pathlib
import random
import tempfile
import unittest

import pikepdf

from tests.support import make_pdf
from tests.test_cli import run

#: What a file being at fault is allowed to come back as: imposed, the job, or
#: the source. Never 4, which is the destination, and never 70, which is what
#: the command line makes of an exception nobody expected -- so a new place a
#: file can break impose is still a failing test here, and not a status.
ANSWERS = {0, 1, 3}


class Malformed(unittest.TestCase):
    """A directory to build a bad file in, and a run over it."""

    def setUp(self):
        self.folder = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(self._clear)
        self.source = self.folder / "book.pdf"
        self.output = self.folder / "press.pdf"

    def _clear(self):
        for path in self.folder.iterdir():
            path.unlink()
        self.folder.rmdir()

    def impose(self, *extra):
        """Impose the file two-up, returning (status, stderr)."""
        status, _, err = run(
            "nup", str(self.source), "-o", str(self.output), "--up", "1x2", *extra
        )
        return status, err


class TestABoxThatIsNotFourNumbers(Malformed):
    """ISO 32000 says a box is four numbers. A file can say anything."""

    def build(self, box, value, *, page=0):
        """Four good pages, one of them with *box* set to *value*."""
        with make_pdf(4) as pdf:
            pdf.pages[page].obj[box] = value
            pdf.save(self.source)

    def test_a_name_where_a_number_belongs_is_the_file_s_fault(self):
        self.build("/TrimBox", pikepdf.Array([pikepdf.Name("/left"), 0, 300, 400]))
        status, err = self.impose()
        self.assertEqual(status, 3, err)
        self.assertIn("Page 1's TrimBox is not four numbers", err)
        self.assertNotIn("Traceback", err)
        self.assertFalse(self.output.exists())

    def test_three_numbers_are_not_a_box_either(self):
        self.build("/BleedBox", pikepdf.Array([0, 0, 300]))
        status, err = self.impose()
        self.assertEqual(status, 3, err)
        self.assertIn("Page 1's BleedBox is not four numbers", err)

    def test_the_page_that_is_wrong_is_the_page_that_is_named(self):
        self.build("/TrimBox", pikepdf.String("A4"), page=2)
        status, err = self.impose()
        self.assertEqual(status, 3, err)
        self.assertIn("Page 3's TrimBox is not four numbers", err)


class TestAPageWithNoSize(Malformed):
    """Every page must carry a MediaBox. QPDF gives one that has none US Letter.

    It does it as the file is opened, so nothing after that can tell the page
    was not always Letter. Measured before this was refused: a page whose
    TrimBox said A3 was clipped to the invented page and imposed at
    213 x 276 mm, exit 0.
    """

    def build(self, harm, *, pages=4):
        with make_pdf(pages) as pdf:
            harm(pdf)
            pdf.save(self.source)

    def assert_refused(self, *extra, page="page 3 has"):
        status, err = self.impose(*extra)
        self.assertEqual(status, 3, err)
        self.assertIn(f"does not say what size {page}", err)
        self.assertIn("US Letter", err)
        self.assertNotIn("Traceback", err)
        self.assertFalse(self.output.exists())

    def test_a_name_in_the_box_is_a_page_of_no_size(self):
        self.build(
            lambda pdf: pdf.pages[2].obj.__setitem__(
                "/MediaBox", pikepdf.Array([0, 0, pikepdf.Name("/wide"), 400])
            )
        )
        self.assert_refused()

    def test_a_missing_box_is_the_same(self):
        self.build(lambda pdf: pdf.pages[2].obj.__delitem__("/MediaBox"))
        self.assert_refused()

    def test_every_page_that_has_none_is_named(self):
        def harm(pdf):
            for number in (0, 3):
                del pdf.pages[number].obj["/MediaBox"]

        self.build(harm)
        self.assert_refused(page="pages 1 and 4 have")

    def test_a_trimbox_larger_than_letter_is_not_cut_down_to_it(self):
        """The case that was imposed wrong at exit 0."""
        a3 = pikepdf.Array([8.5, 8.5, 850.4, 1199.1])

        def harm(pdf):
            for page in pdf.pages:
                page.obj["/MediaBox"] = pikepdf.Array([0, 0, pikepdf.Name("/w"), 1])
                page.obj["/TrimBox"] = a3
                for box in ("/CropBox", "/BleedBox"):
                    if box in page.obj:
                        del page.obj[box]

        self.build(harm)
        self.assert_refused(page="pages 1, 2, 3 and 4 have")

    def test_asking_to_recover_does_not_change_it(self):
        """There is nothing to recover: the size is not in the file."""
        self.build(lambda pdf: pdf.pages[2].obj.__delitem__("/MediaBox"))
        self.assert_refused("--damaged", "recover")

    def test_a_box_inherited_from_the_page_tree_is_a_box(self):
        """Legal, and common: the size is stated once, for every page."""

        def harm(pdf):
            pdf.Root.Pages.MediaBox = pdf.pages[0].obj.MediaBox
            for page in pdf.pages:
                del page.obj["/MediaBox"]

        self.build(harm)
        status, err = self.impose()
        self.assertEqual(status, 0, err)
        self.assertTrue(self.output.exists())

    def test_four_numbers_with_no_area_between_them_are_no_size_either(self):
        self.build(
            lambda pdf: pdf.pages[1].obj.__setitem__(
                "/MediaBox", pikepdf.Array([0, 0, 0, 0])
            )
        )
        status, err = self.impose()
        self.assertEqual(status, 3, err)
        self.assertIn("Page 2's MediaBox has no area", err)


class TestAPageTreeThatLostAPage(Malformed):
    """Something in the page tree that is not a page, where a page should be.

    QPDF skips it, and the document reads short. Found by the search below,
    run 3000 times: 42 damaged copies of a six-page file were imposed as five
    pages at exit 0. The page count could not be trusted, which is the
    cross-reference refusal's case, so it is refused the same way and
    recovered the same way.
    """

    def setUp(self):
        super().setUp()
        with make_pdf(3) as pdf:
            kids = list(pdf.Root.Pages.Kids)
            pdf.Root.Pages.Kids = pikepdf.Array([7, *kids[1:]])
            pdf.save(self.source)

    def test_it_is_refused_rather_than_imposed_short(self):
        status, err = self.impose()
        self.assertEqual(status, 3, err)
        self.assertIn("page tree holds something that is not a page", err)
        self.assertIn("reads as 2 pages", err)
        self.assertFalse(self.output.exists())

    def test_asking_to_recover_imposes_what_is_there_and_says_so(self):
        status, err = self.impose("--damaged", "recover")
        self.assertEqual(status, 0, err)
        self.assertIn("2 pages were read", err)
        self.assertIn("A page may be missing", err)


class TestContentThatCannotBeRead(Malformed):
    """A page whose content stream does not decode.

    Nothing reads a page's content until the page is copied onto a sheet, so
    this is found late -- after the boxes were read and the grid was chosen
    -- and QPDF's exception used to come straight out of the copy.
    """

    def setUp(self):
        super().setUp()
        with make_pdf(4) as pdf:
            broken = pikepdf.Stream(pdf, b"")
            broken.write(b"this was never compressed", filter=pikepdf.Name.FlateDecode)
            pdf.pages[1].obj["/Contents"] = broken
            pdf.save(self.source)

    def test_it_is_the_file_s_fault_and_says_which_page(self):
        status, err = self.impose()
        self.assertEqual(status, 3, err)
        self.assertIn("Page 2 cannot be copied onto a sheet", err)
        self.assertNotIn("Traceback", err)

    def test_nothing_is_left_where_the_press_file_was_going(self):
        self.impose()
        self.assertEqual(
            sorted(path.name for path in self.folder.iterdir()), ["book.pdf"]
        )


class TestDamagedAByteAtATime(Malformed):
    """The search that found both, kept: no file makes impose raise.

    Fixed seeds, so a failure names a file that can be built again. Three
    kinds of damage, the three a file meets in practice: cut short, a piece
    missing from the middle, and bytes changed in place.
    """

    RUNS = 240

    @staticmethod
    def damage(seed: bytes, rng: random.Random) -> bytes:
        """One damaged copy of *seed*."""
        data = bytearray(seed)
        kind = rng.random()
        if kind < 0.2:
            return bytes(data[: rng.randrange(len(data))])
        if kind < 0.4:
            start = rng.randrange(len(data))
            del data[start : start + rng.randrange(1, 200)]
            return bytes(data)
        for _ in range(rng.choice((1, 1, 2, 4, 16))):
            data[rng.randrange(len(data))] = rng.randrange(256)
        return bytes(data)

    def test_every_one_is_answered_with_a_status(self):
        with make_pdf(6) as pdf:
            pdf.save(self.source)
        seed = self.source.read_bytes()
        rng = random.Random(20261115)
        for number in range(self.RUNS):
            self.source.write_bytes(self.damage(seed, rng))
            self.output.unlink(missing_ok=True)
            with self.subTest(mutation=number):
                # main() answers for an exception it did not expect with 70
                # and the stack, and neither is among the answers.
                status, err = self.impose()
                self.assertIn(status, ANSWERS, err)
                self.assertNotIn("Traceback", err)
                if status:
                    self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
