# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

# pylint: disable=missing-class-docstring,missing-function-docstring

"""The command run by something other than a person.

A watched folder invokes `impose` per incoming PDF and reads the exit status,
which means the failures matter as much as the impositions: a file that is
still being copied, a press file that is already there, an output path that
is also the input. These are the refusals that make unattended running safe,
and they are grouped here because that is one subject rather than a handful
of odd cases.
"""

import contextlib
import pathlib
import tempfile
import unittest

import pikepdf

from impose.geometry import Size
from impose.units import MM

from .support import make_office_pdf, make_pdf, truncated_pdf
from .test_cli import run, workspace


class TestClobber(unittest.TestCase):
    """Nothing already written is replaced without being asked.

    A shop resends a job under the name it sent it under the first time. The
    second arrival is usually a correction and sometimes the first one is
    already on the press, and replacing it silently loses the only record of
    what was printed.
    """

    def test_an_existing_press_file_is_refused_and_left_alone(self):
        with workspace(pages=8) as source:
            output = source.with_name("out.pdf")
            output.write_bytes(b"yesterday's press file")
            status, text, err = run("nup", str(source), "-o", str(output))
            self.assertNotEqual(status, 0)
            self.assertEqual(output.read_bytes(), b"yesterday's press file")
            self.assertIn("already there", err)
            self.assertIn("already on the press", err)
            self.assertNotIn("Traceback", err)
            self.assertEqual(text, "")

    def test_asking_replaces_it(self):
        with workspace(pages=8) as source:
            output = source.with_name("out.pdf")
            output.write_bytes(b"yesterday's press file")
            status, _, err = run("nup", str(source), "-o", str(output), "--overwrite")
            self.assertEqual(status, 0, err)
            with pikepdf.open(output) as written:
                # Eight pages two-up on both sides: one sheet, two surfaces.
                self.assertEqual(len(written.pages), 2)

    def test_output_naming_the_input_is_refused_and_the_artwork_survives(self):
        """This imposed the sheets over the artwork and reported success: the
        renderer builds a fresh document, so nothing underneath noticed that
        the file it read was the file it was writing."""
        with workspace(pages=8) as source:
            before = source.read_bytes()
            status, _, err = run("nup", str(source), "-o", str(source))
            self.assertNotEqual(status, 0)
            self.assertEqual(source.read_bytes(), before)
            self.assertIn("no undo", err)

    def test_overwrite_does_not_licence_eating_the_input(self):
        """--overwrite is permission to replace a press file, not permission
        to destroy the artwork."""
        with workspace(pages=8) as source:
            before = source.read_bytes()
            status, _, _ = run("nup", str(source), "-o", str(source), "--overwrite")
            self.assertNotEqual(status, 0)
            self.assertEqual(source.read_bytes(), before)

    def test_an_existing_proof_is_refused_too(self):
        with workspace(pages=8) as source:
            proof = source.with_name("proof.pdf")
            proof.write_bytes(b"signed off yesterday")
            status, _, err = run(
                "nup",
                str(source),
                "-o",
                str(source.with_name("o.pdf")),
                "--proof",
                str(proof),
            )
            self.assertNotEqual(status, 0)
            self.assertEqual(proof.read_bytes(), b"signed off yesterday")
            self.assertIn("proof is not replaced", err)

    def test_an_existing_job_file_is_refused_before_anything_is_imposed(self):
        """--record is written before the imposition, so its destination has
        to be checked before it too."""
        with workspace(pages=8) as source:
            job = source.with_name("job.json")
            job.write_text("{}", encoding="utf-8")
            output = source.with_name("out.pdf")
            status, _, err = run(
                "nup", str(source), "-o", str(output), "--record", str(job)
            )
            self.assertNotEqual(status, 0)
            self.assertEqual(job.read_text(encoding="utf-8"), "{}")
            self.assertFalse(output.exists())
            self.assertIn("job file is not replaced", err)

    def test_a_refused_output_leaves_no_proof_and_no_job_file(self):
        """The proof used to be written well before the press file, so a run
        that was going to be refused still left one behind."""
        with workspace(pages=8) as source:
            output = source.with_name("out.pdf")
            output.write_bytes(b"already here")
            proof = source.with_name("proof.pdf")
            job = source.with_name("job.json")
            status, _, _ = run(
                "nup",
                str(source),
                "-o",
                str(output),
                "--proof",
                str(proof),
                "--record",
                str(job),
            )
            self.assertNotEqual(status, 0)
            self.assertFalse(proof.exists())
            self.assertFalse(job.exists())

    def test_a_fresh_name_is_simply_written(self):
        with workspace(pages=8) as source:
            output = source.with_name("out.pdf")
            status, _, err = run("nup", str(source), "-o", str(output))
            self.assertEqual(status, 0, err)
            self.assertTrue(output.exists())
            self.assertNotIn("already there", err)


class TestDamagedAtTheCommand(unittest.TestCase):
    """A file still being copied, which is what a watched folder hands over.

    The whole point is that this used to be exit 0 and a clean summary.
    """

    @staticmethod
    @contextlib.contextmanager
    def partial(fraction=0.4, pages=16):
        with tempfile.TemporaryDirectory() as folder:
            path = pathlib.Path(folder) / "book.pdf"
            path.write_bytes(truncated_pdf(make_pdf(pages), fraction))
            yield path

    def test_it_is_refused_and_nothing_is_written(self):
        with self.partial() as source:
            output = source.with_name("out.pdf")
            status, text, err = run("saddle", str(source), "-o", str(output))
            self.assertNotEqual(status, 0)
            self.assertFalse(output.exists())
            self.assertIn("cross-reference table", err)
            self.assertIn("15 pages", err)
            self.assertNotIn("Traceback", err)
            self.assertEqual(text, "")

    def test_the_opt_in_imposes_and_warns(self):
        with self.partial() as source:
            output = source.with_name("out.pdf")
            status, text, err = run(
                "saddle", str(source), "-o", str(output), "--damaged", "recover"
            )
            self.assertEqual(status, 0)
            self.assertTrue(output.exists())
            self.assertIn("15 pages were read", err)
            self.assertIn("15 pages onto", text)

    def test_the_warning_survives_quiet(self):
        with self.partial() as source:
            _, text, err = run(
                "saddle",
                str(source),
                "-o",
                str(source.with_name("o.pdf")),
                "--damaged",
                "recover",
                "-q",
            )
            self.assertEqual(text, "")
            self.assertIn("cross-reference table", err)

    def test_fit_refuses_it_as_well(self):
        with self.partial() as source:
            status, text, err = run("fit", str(source), "--schema", "saddle")
            self.assertNotEqual(status, 0)
            self.assertIn("cross-reference table", err)
            self.assertNotIn("up,", text)

    def test_an_unknown_choice_is_argparse_s_to_refuse(self):
        with self.partial() as source:
            status, _, err = run("saddle", str(source), "--damaged", "maybe")
            self.assertEqual(status, 2)
            self.assertIn("invalid choice", err)

    def test_a_whole_file_says_nothing_about_damage(self):
        with workspace(pages=16) as source:
            status, _, err = run(
                "saddle", str(source), "-o", str(source.with_name("o.pdf"))
            )
            self.assertEqual(status, 0)
            self.assertNotIn("cross-reference", err)


class TestFolderPolicy(unittest.TestCase):
    """One watched folder's standing instruction, at the command.

    `--trim-from mediabox --expect-size A4` is what a folder of Word
    documents is told, and the pair is the point: the first says where the
    size comes from and the second says what it has to be.
    """

    def test_the_export_it_is_for_is_imposed_with_the_note(self):
        with workspace(pages=8, build=make_office_pdf) as source:
            output = source.with_name("out.pdf")
            status, text, err = run(
                "nup",
                str(source),
                "-o",
                str(output),
                "--trim-from",
                "mediabox",
                "--expect-size",
                "A4",
            )
            self.assertEqual(status, 0, err)
            self.assertTrue(output.exists())
            self.assertIn("210 × 297 mm", err)
            self.assertIn("2 sheet", text)

    def test_a_file_carrying_bleed_in_its_mediabox_is_turned_away(self):
        with workspace(
            pages=8, build=make_office_pdf, size=Size(216 * MM, 303 * MM)
        ) as source:
            output = source.with_name("out.pdf")
            status, _, err = run(
                "nup",
                str(source),
                "-o",
                str(output),
                "--trim-from",
                "mediabox",
                "--expect-size",
                "A4",
            )
            self.assertNotEqual(status, 0)
            self.assertFalse(output.exists())
            self.assertIn("216 × 303 mm", err)
            self.assertIn("210 × 297 mm", err)
            self.assertNotIn("Traceback", err)

    def test_without_the_expectation_that_file_is_imposed(self):
        """Documenting the hole, so that deleting the option would show up
        here as a test that suddenly passes for the wrong reason."""
        with workspace(
            pages=8, build=make_office_pdf, size=Size(216 * MM, 303 * MM)
        ) as source:
            status, text, _ = run(
                "nup",
                str(source),
                "-o",
                str(source.with_name("o.pdf")),
                "--trim-from",
                "mediabox",
            )
            self.assertEqual(status, 0)
            self.assertIn("216 × 303 mm", text)

    def test_a_typo_in_the_size_fails_before_the_file_is_opened(self):
        with workspace(pages=8, build=make_office_pdf) as source:
            status, _, err = run("nup", str(source), "--expect-size", "A4furlong")
            self.assertEqual(status, 2)
            self.assertIn("paper size", err)

    def test_fit_answers_under_the_same_policy(self):
        with workspace(pages=8, build=make_office_pdf) as source:
            status, text, _ = run(
                "fit", str(source), "--schema", "nup", "--trim-from", "mediabox"
            )
            self.assertEqual(status, 0)
            self.assertIn("up,", text)
