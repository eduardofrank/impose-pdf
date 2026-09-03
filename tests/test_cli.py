# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

# pylint: disable=missing-class-docstring,missing-function-docstring

"""The `impose` command.

The command is thin, so these check the wiring and the failures: that words
become the right arguments, and that a person who asks for something impossible
is told so in a sentence rather than shown a traceback.
"""

import contextlib
import io
import pathlib
import tempfile
import unittest

import pikepdf

from impose.cli import _default_output, _grid, main
from impose.geometry import Size
from impose.units import MM

from .support import make_pdf


@contextlib.contextmanager
def workspace(pages=16, name="book.pdf", **kwargs):
    """A directory holding a source document."""
    with tempfile.TemporaryDirectory() as folder:
        path = pathlib.Path(folder) / name
        make_pdf(pages, **kwargs).save(path)
        yield path


def run(*argv):
    """Run the command, returning (status, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            status = main(list(argv))
        except SystemExit as exit_:  # argparse's own failures
            status = int(exit_.code or 0)
    return status, out.getvalue(), err.getvalue()


class TestImposing(unittest.TestCase):
    def test_every_schema_runs(self):
        cases = {
            "saddle": (),
            "perfect": ("--section-pages", "8"),
            "nup": ("--up", "2x2"),
            "cutstack": ("--up", "2x2"),
        }
        for schema, extra in cases.items():
            with self.subTest(schema=schema), workspace() as source:
                output = source.with_name("out.pdf")
                status, text, _ = run(schema, str(source), "-o", str(output), *extra)
                self.assertEqual(status, 0)
                self.assertTrue(output.exists())
                self.assertIn("sheet(s)", text)

    def test_step_and_repeat_runs_on_a_two_page_source(self):
        """Business cards, 85 x 55 mm, which is what the schema is for."""
        with workspace(pages=2, trim=Size(85 * MM, 55 * MM)) as source:
            output = source.with_name("cards.pdf")
            status, _, err = run(
                "steprepeat",
                str(source),
                "-o",
                str(output),
                "--up",
                "3x4",
                "--copies",
                "24",
            )
            self.assertEqual(status, 0, err)
            self.assertTrue(output.exists())

    def test_output_defaults_beside_the_input(self):
        with workspace() as source:
            status, text, _ = run("saddle", str(source))
            self.assertEqual(status, 0)
            expected = source.with_name("book-imposed.pdf")
            self.assertTrue(expected.exists())
            self.assertIn("book-imposed.pdf", text)

    def test_default_output_naming(self):
        self.assertEqual(
            _default_output(pathlib.Path("/x/book.pdf")).name, "book-imposed.pdf"
        )

    def test_quiet_says_nothing(self):
        with workspace() as source:
            status, text, _ = run("saddle", str(source), "-q")
            self.assertEqual(status, 0)
            self.assertEqual(text, "")

    def test_marks_can_be_chosen(self):
        with workspace() as source:
            for choice in ("registration", "black", "none"):
                with self.subTest(marks=choice):
                    output = source.with_name(f"{choice}.pdf")
                    status, _, _ = run(
                        "saddle", str(source), "-o", str(output), "--marks", choice
                    )
                    self.assertEqual(status, 0)
                    pdf = pikepdf.open(output)
                    resources = pdf.pages[0].obj["/Resources"]
                    self.assertEqual(
                        "/ColorSpace" in resources, choice == "registration"
                    )
                    pdf.close()

    def test_sheet_and_gutters_are_accepted(self):
        with workspace() as source:
            status, _, err = run(
                "nup",
                str(source),
                "-o",
                str(source.with_name("o.pdf")),
                "--up",
                "2x1",
                "--sheet",
                "SRA3",
                "--gutters",
                "4mm",
                "--press",
                "sra3",
            )
            self.assertEqual(status, 0, err)


class TestDryRun(unittest.TestCase):
    def test_shows_the_order_and_writes_nothing(self):
        with workspace() as source:
            status, text, _ = run("saddle", str(source), "--dry-run")
            self.assertEqual(status, 0)
            self.assertIn("sheet 1 front", text)
            self.assertIn("16 pages", text)
            self.assertFalse(source.with_name("book-imposed.pdf").exists())

    def test_reports_the_finished_size(self):
        with workspace() as source:
            _, text, _ = run("saddle", str(source), "-n")
            self.assertIn("105 × 148 mm", text)


class TestFailures(unittest.TestCase):
    def test_missing_file(self):
        status, _, err = run("saddle", "/nowhere/absent.pdf")
        self.assertEqual(status, 1)
        self.assertIn("No such file", err)

    def test_unknown_press_lists_the_alternatives(self):
        with workspace() as source:
            status, _, err = run("saddle", str(source), "--press", "gutenberg")
            self.assertEqual(status, 1)
            self.assertIn("indigo-5000", err)

    def test_a_schema_refusing_the_job_is_a_sentence(self):
        """Schemas raise ValueError, and that must not reach the terminal raw."""
        with workspace(pages=15) as source:
            status, _, err = run(
                "steprepeat", str(source), "--up", "2x2", "--sides", "2"
            )
            self.assertEqual(status, 1)
            self.assertTrue(err.startswith("impose: "))
            self.assertNotIn("Traceback", err)

    def test_a_form_too_big_names_both_sizes(self):
        with workspace() as source:
            status, _, err = run("nup", str(source), "--up", "4x4")
            self.assertEqual(status, 1)
            self.assertIn("does not fit", err)

    def test_bad_grid_is_rejected_by_the_parser(self):
        with workspace() as source:
            status, _, err = run("nup", str(source), "--up", "4by2")
            self.assertEqual(status, 2)
            self.assertIn("COLUMNSxROWS", err)

    def test_bad_length_names_the_units_we_take(self):
        with workspace() as source:
            status, _, err = run("saddle", str(source), "--gutters", "3furlong")
            self.assertEqual(status, 2)
            self.assertIn("mm", err)

    def test_grid_parser(self):
        self.assertEqual(_grid("4x2"), (4, 2))
        for bad in ("4by2", "0x2", "x", "4x2x1"):
            with self.subTest(bad=bad), self.assertRaises(Exception):
                _grid(bad)


class TestInformation(unittest.TestCase):
    def test_presses_are_listed_with_a_caveat(self):
        status, text, _ = run("presses")
        self.assertEqual(status, 0)
        self.assertIn("indigo-5000", text)
        self.assertIn("gripper", text)
        self.assertIn("nominal", text)

    def test_no_arguments_shows_help(self):
        status, text, _ = run()
        self.assertEqual(status, 2)
        self.assertIn("SCHEMA", text)

    def test_version(self):
        status, text, _ = run("--version")
        self.assertEqual(status, 0)
        self.assertIn("impose", text)


class TestFit(unittest.TestCase):
    """The question a shop asks first: how many to a sheet."""

    def test_without_a_quantity_the_densest_leads(self):
        """With nothing to weigh against, density is the only measure."""
        status, text, _ = run("fit", "A6", "--gutter", "4mm", "--allowance", "5mm")
        self.assertEqual(status, 0)
        self.assertIn("8 up", text)
        self.assertIn("turned", text)
        self.assertLess(text.index("8 up"), text.index("4 up"))

    def test_a_quantity_adds_sheets_and_waste(self):
        status, text, _ = run("fit", "90mmx55mm", "-n", "500")
        self.assertEqual(status, 0)
        self.assertIn("sheet(s)", text)
        self.assertIn("wasted", text)

    def test_offers_the_free_units(self):
        _, text, _ = run("fit", "90mmx55mm", "-n", "500")
        self.assertIn("504", text)
        self.assertIn("no more press time", text)

    def test_a_tie_on_sheets_goes_to_the_tidier_grid(self):
        """100 business cards: 20 up and 24 up both run five sheets, but 24
        up throws away twenty cards to do it."""
        _, text, _ = run("fit", "90mmx50mm", "-n", "100", "--allowance", "5mm")
        first = text.strip().splitlines()[1]
        self.assertIn("20 up", first)
        self.assertIn("run this", first)
        self.assertIn("denser but costs the same", text)

    def test_the_denser_grid_wins_once_it_saves_a_sheet(self):
        """200 of the same card: 24 up runs nine sheets against ten."""
        _, text, _ = run("fit", "90mmx50mm", "-n", "200", "--allowance", "5mm")
        first = text.strip().splitlines()[1]
        self.assertIn("24 up", first)
        self.assertIn("9 sheet(s)", first)

    def test_the_crossover_is_where_the_shop_puts_it(self):
        """Up to 100 the tidy grid; past it the dense one."""
        for quantity, expected in ((100, "20 up"), (101, "24 up")):
            with self.subTest(quantity=quantity):
                _, text, _ = run(
                    "fit", "90mmx50mm", "-n", str(quantity), "--allowance", "5mm"
                )
                self.assertIn(expected, text.strip().splitlines()[1])

    def test_a_size_that_does_not_fit_is_refused(self):
        status, _, err = run("fit", "A2")
        self.assertEqual(status, 1)
        self.assertIn("even one up", err)

    def test_press_can_be_chosen(self):
        status, text, _ = run("fit", "A6", "--press", "indigo-12000")
        self.assertEqual(status, 0)
        self.assertIn("indigo-12000", text)


class TestAutomaticGrid(unittest.TestCase):
    def test_the_grid_is_chosen_when_not_given(self):
        """Eight A6 on one Indigo sheet, without being told 2x4."""
        with workspace(pages=8) as source:
            status, text, err = run(
                "nup",
                str(source),
                "-o",
                str(source.with_name("o.pdf")),
                "--gutters",
                "4mm",
                "--mark-offset",
                "1mm",
                "--mark-length",
                "4mm",
            )
            self.assertEqual(status, 0, err)
            self.assertIn("1 sheet(s)", text)

    def test_an_explicit_grid_still_wins(self):
        with workspace(pages=4) as source:
            status, _, err = run(
                "nup",
                str(source),
                "-o",
                str(source.with_name("o.pdf")),
                "--up",
                "2x1",
            )
            self.assertEqual(status, 0, err)


class TestCreep(unittest.TestCase):
    def test_the_caliper_reaches_the_output(self):
        """Without the pass-through the flag parses and does nothing."""
        with workspace(pages=32) as source:
            plain = source.with_name("plain.pdf")
            crept = source.with_name("crept.pdf")
            self.assertEqual(run("saddle", str(source), "-o", str(plain), "-q")[0], 0)
            self.assertEqual(
                run(
                    "saddle",
                    str(source),
                    "-o",
                    str(crept),
                    "--paper-caliper",
                    "0.1mm",
                    "-q",
                )[0],
                0,
            )
            self.assertNotEqual(plain.read_bytes(), crept.read_bytes())

    def test_perfect_binding_takes_it_too(self):
        with workspace(pages=32) as source:
            status, _, err = run(
                "perfect",
                str(source),
                "-o",
                str(source.with_name("o.pdf")),
                "--section-pages",
                "16",
                "--paper-caliper",
                "0.1mm",
            )
            self.assertEqual(status, 0, err)

    def test_flat_schemas_do_not_offer_it(self):
        with workspace() as source:
            status, _, err = run("nup", str(source), "--paper-caliper", "0.1mm")
            self.assertEqual(status, 2)
            self.assertIn("unrecognized", err)


class TestFitAllowance(unittest.TestCase):
    """`fit` works its own allowance out from the marks and the bleed."""

    @staticmethod
    def leading_up(text):
        """The `n up` of the first arrangement listed."""
        return int(text.strip().splitlines()[1].strip().split()[0])

    def test_defaults_reserve_the_mark_reach(self):
        _, text, _ = run("fit", "A6", "--gutter", "4mm")
        self.assertEqual(self.leading_up(text), 8)

    def test_longer_marks_cost_a_row(self):
        """Three plus five reserves eight, and eight A6 no longer fit."""
        _, text, _ = run(
            "fit",
            "A6",
            "--gutter",
            "4mm",
            "--mark-offset",
            "3mm",
            "--mark-length",
            "5mm",
        )
        self.assertEqual(self.leading_up(text), 4)

    def test_no_marks_reserve_nothing(self):
        _, text, _ = run("fit", "A6", "--gutter", "4mm", "--marks", "none")
        self.assertEqual(self.leading_up(text), 8)

    def test_bleed_is_reserved_when_it_reaches_further(self):
        _, text, _ = run(
            "fit", "A6", "--gutter", "4mm", "--marks", "none", "--bleed", "8mm"
        )
        self.assertEqual(self.leading_up(text), 4)

    def test_the_larger_of_the_two_wins_not_their_sum(self):
        """A 3 mm bleed behind a 5 mm mark reach needs 5, not 8."""
        with_bleed = run("fit", "A6", "--gutter", "4mm", "--bleed", "3mm")[1]
        without = run("fit", "A6", "--gutter", "4mm")[1]
        self.assertEqual(self.leading_up(with_bleed), self.leading_up(without))

    def test_an_explicit_allowance_still_overrides(self):
        _, text, _ = run("fit", "A6", "--gutter", "4mm", "--allowance", "8mm")
        self.assertEqual(self.leading_up(text), 4)

    def test_fit_and_imposing_agree(self):
        """The reason fit takes mark options at all."""
        cases = (
            ([], []),
            (["--mark-length", "5mm"], ["--mark-length", "5mm"]),
            (["--marks", "none"], ["--marks", "none"]),
        )
        for fit_args, impose_args in cases:
            with self.subTest(args=fit_args), workspace(pages=8) as source:
                _, text, _ = run("fit", "A6", "--gutter", "4mm", *fit_args)
                predicted = self.leading_up(text)
                status, summary, err = run(
                    "nup",
                    str(source),
                    "-o",
                    str(source.with_name("o.pdf")),
                    "--gutter",
                    "4mm",
                    *impose_args,
                )
                self.assertEqual(status, 0, err)
                # n-up is duplex, so a sheet carries twice what fits on a side.
                sheets = -(-8 // (predicted * 2))
                self.assertIn(f"{sheets} sheet(s)", summary)
