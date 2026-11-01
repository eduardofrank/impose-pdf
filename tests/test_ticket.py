# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

# pylint: disable=missing-function-docstring
"""A job file is the same job as the command that wrote it."""

import contextlib
import json
import pathlib
import tempfile
import unittest

from impose import ImposeError
from impose.ticket import load
from impose.units import MM

from .support import make_pdf, truncated_pdf
from .test_cli import run, workspace


@contextlib.contextmanager
def damaged_workspace(pages=16, fraction=0.4):
    """A directory holding a file that is still being copied."""
    with tempfile.TemporaryDirectory() as folder:
        path = pathlib.Path(folder) / "book.pdf"
        path.write_bytes(truncated_pdf(make_pdf(pages), fraction))
        yield path


class TestStoredJob(unittest.TestCase):
    """What was run can be stored, moved, and run again."""

    def test_record_then_run_is_the_same_job(self):
        with workspace(pages=8) as source:
            job = source.with_name("job.json")
            status, _, err = run(
                "perfect",
                str(source),
                "--section-pages",
                "4",
                "--grind",
                "3mm",
                "--record",
                str(job),
                "--dry-run",
            )
            self.assertEqual(status, 0, err)
            stored = json.loads(job.read_text(encoding="utf-8"))
            self.assertEqual(stored["schema"], "perfect")
            self.assertAlmostEqual(stored["grind"], 3 * MM, places=3)
            status, text, err = run("run", str(job), "--dry-run")
            self.assertEqual(status, 0, err)
            self.assertIn("sheet 1 front", text)

    def test_lay_is_a_field_of_the_job(self):
        with workspace(pages=4) as source:
            job = source.with_name("job.json")
            status, _, err = run(
                "nup",
                str(source),
                "--lay",
                "left",
                "--record",
                str(job),
                "--dry-run",
            )
            self.assertEqual(status, 0, err)
            stored = json.loads(job.read_text(encoding="utf-8"))
            self.assertEqual(stored["lay"], "left")
            status, _, err = run("run", str(job), "--dry-run")
            self.assertEqual(status, 0, err)

    def test_a_path_is_read_beside_the_job(self):
        with workspace(pages=8) as source:
            job = source.with_name("job.json")
            job.write_text(
                json.dumps({"source": source.name, "schema": "saddle"}),
                encoding="utf-8",
            )
            loaded = load(job)
            self.assertEqual(loaded["source"], source)

    def test_an_unknown_field_is_named(self):
        with workspace(pages=4) as source:
            job = source.with_name("job.json")
            job.write_text(
                json.dumps({"source": source.name, "schema": "saddle", "plate": 1}),
                encoding="utf-8",
            )
            status, _, err = run("run", str(job))
            self.assertEqual(status, 1)
            self.assertIn("plate", err)

    def test_a_field_belonging_to_another_schema_is_a_sentence(self):
        # 'style' is a field of a job, so the unknown-field check passes it,
        # and the nup ordering has no use for it. A hand-written or hand-edited
        # job used to reach that ordering and raise a TypeError about a
        # keyword argument, with a traceback.
        with workspace(pages=4) as source:
            job = source.with_name("job.json")
            job.write_text(
                json.dumps(
                    {
                        "source": source.name,
                        "schema": "nup",
                        "up": "2x2",
                        "style": "foot-to-foot",
                    }
                ),
                encoding="utf-8",
            )
            status, _, err = run("run", str(job))
            self.assertEqual(status, 1)
            self.assertNotIn("Traceback", err)
            self.assertIn(
                "The nup schema takes no 'style'. It is an option of signature.",
                err,
            )

    def test_the_library_refuses_a_missing_source(self):
        with workspace(pages=4) as source:
            job = source.with_name("job.json")
            job.write_text(json.dumps({"schema": "saddle"}), encoding="utf-8")
            with self.assertRaises(ImposeError) as caught:
                load(job)
            self.assertIn("source", str(caught.exception))


class TestStoredPress(unittest.TestCase):
    """A press the profiles do not describe is still a job that can be stored."""

    def test_a_custom_press_is_recorded_and_run_again(self):
        with workspace(pages=4) as source:
            job = source.with_name("job.json")
            status, _, err = run(
                "nup",
                str(source),
                "--up",
                "2x1",
                "--press",
                "320mmx450mm",
                "--margins",
                "bottom=12mm,top=5mm",
                "--gripper",
                "bottom",
                "--record",
                str(job),
                "-o",
                str(source.with_name("out.pdf")),
            )
            self.assertEqual(status, 0, err)
            stored = json.loads(job.read_text(encoding="utf-8"))
            self.assertEqual(
                stored["press"],
                {
                    "name": "320mmx450mm",
                    "sheet": "320mmx450mm",
                    "margins": {
                        "bottom": "12mm",
                        "top": "5mm",
                        "left": "0mm",
                        "right": "0mm",
                    },
                    "gripper": "bottom",
                },
            )
            # Running a stored job a second time lands on the press file the
            # recording run wrote, so the re-run says it means to replace it.
            status, text, err = run("run", str(job), "--overwrite")
            self.assertEqual(status, 0, err)
            self.assertIn("320 × 433 mm", text)

    def test_a_profile_with_nothing_overriding_it_stays_a_name(self):
        """A name reads the profile of the day, not a frozen copy of it."""
        with workspace(pages=4) as source:
            job = source.with_name("job.json")
            status, _, err = run(
                "nup", str(source), "--up", "2x1", "--record", str(job), "--dry-run"
            )
            self.assertEqual(status, 0, err)
            stored = json.loads(job.read_text(encoding="utf-8"))
            self.assertEqual(stored["press"], "indigo-5000")

    def test_a_press_written_by_hand_is_read(self):
        with workspace(pages=4) as source:
            job = source.with_name("job.json")
            job.write_text(
                json.dumps(
                    {
                        "source": source.name,
                        "schema": "nup",
                        "up": "2x1",
                        "press": {
                            "name": "the-old-heidelberg",
                            "sheet": "320mmx450mm",
                            "margins": {"bottom": "12mm", "top": "5mm"},
                        },
                    }
                ),
                encoding="utf-8",
            )
            status, text, err = run("run", str(job), "--dry-run")
            self.assertEqual(status, 0, err)
            self.assertIn("the-old-heidelberg", text)

    def test_a_press_the_file_cannot_describe_fails_on_opening_it(self):
        with workspace(pages=4) as source:
            job = source.with_name("job.json")
            job.write_text(
                json.dumps(
                    {"source": source.name, "schema": "saddle", "press": "gutenberg"}
                ),
                encoding="utf-8",
            )
            with self.assertRaises(ImposeError) as caught:
                load(job)
            self.assertIn("indigo-5000", str(caught.exception))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()


class TestPerRunOptions(unittest.TestCase):
    """--trim-from is a judgement about the file in front of somebody.

    A job file is run again tomorrow, by a hot folder, on whatever arrives. An
    assumption that was sound once would there become a standing instruction to
    assume a finished size for every file, including the one whose boxes a
    converter dropped. So it is not a field of a job, and recording a run that
    used it says so rather than storing it quietly.
    """

    def test_it_is_not_written_into_the_job(self):
        with workspace(pages=8, with_trimbox=False, with_bleedbox=False) as source:
            job = source.with_name("job.json")
            status, _, err = run(
                "nup",
                str(source),
                "--trim-from",
                "mediabox",
                "--record",
                str(job),
                "--dry-run",
            )
            self.assertEqual(status, 0, err)
            stored = json.loads(job.read_text(encoding="utf-8"))
            self.assertNotIn("trim_from", stored)

    def test_recording_one_says_it_was_not_recorded(self):
        with workspace(pages=8, with_trimbox=False, with_bleedbox=False) as source:
            job = source.with_name("job.json")
            _, _, err = run(
                "nup",
                str(source),
                "--trim-from",
                "mediabox",
                "--record",
                str(job),
                "--dry-run",
            )
            self.assertIn("applies to this run only", err)

    def test_the_stored_job_refuses_the_file_again(self):
        """Which is the point: the next run makes its own decision."""
        with workspace(pages=8, with_trimbox=False, with_bleedbox=False) as source:
            job = source.with_name("job.json")
            run(
                "nup",
                str(source),
                "--trim-from",
                "mediabox",
                "--record",
                str(job),
                "--dry-run",
            )
            status, _, err = run("run", str(job), "--dry-run")
            self.assertEqual(status, 1)
            self.assertIn("no TrimBox", err)

    def test_a_job_naming_it_is_refused_as_not_a_field(self):
        with workspace(pages=8) as source:
            job = source.with_name("job.json")
            job.write_text(
                json.dumps(
                    {
                        "source": source.name,
                        "schema": "nup",
                        "trim_from": "mediabox",
                    }
                ),
                encoding="utf-8",
            )
            status, _, err = run("run", str(job))
            self.assertEqual(status, 1)
            self.assertIn("'trim_from', which is not a field of a job", err)

    def test_a_run_that_did_not_use_it_says_nothing(self):
        with workspace(pages=8) as source:
            job = source.with_name("job.json")
            _, _, err = run("nup", str(source), "--record", str(job), "--dry-run")
            self.assertEqual(err, "")


class TestStoredExpectSize(unittest.TestCase):
    """The one new check a job file may carry, and why it may.

    `trim_from` is kept out because as a standing instruction it means
    "assume a size for every file". `expect_size` means "refuse any file
    that is not this size", which is the antidote to that rather than
    another instance of it -- so a folder's job file can hold it.
    """

    def test_it_round_trips_as_millimetres(self):
        """Stored the way the press sheet is: a job file is a document
        somebody reads. A Size reaching json.dumps unconverted would be a
        TypeError, which is what this catches."""
        with workspace(pages=8) as source:
            job = source.with_name("job.json")
            status, _, err = run(
                "nup",
                str(source),
                "--expect-size",
                "105mmx148mm",
                "--record",
                str(job),
                "--dry-run",
            )
            self.assertEqual(status, 0, err)
            stored = json.loads(job.read_text(encoding="utf-8"))
            self.assertEqual(stored["expect_size"], "105mmx148mm")

    def test_the_stored_job_applies_it_again(self):
        with workspace(pages=8) as source:
            job = source.with_name("job.json")
            run(
                "nup",
                str(source),
                "--expect-size",
                "A4",
                "--record",
                str(job),
                "--dry-run",
            )
            status, _, err = run("run", str(job), "--dry-run")
            self.assertNotEqual(status, 0)
            self.assertIn("expects 210 × 297 mm", err)

    def test_a_job_written_by_hand_is_read(self):
        with workspace(pages=8) as source:
            job = source.with_name("job.json")
            job.write_text(
                json.dumps(
                    {
                        "source": source.name,
                        "schema": "nup",
                        "expect_size": "105mmx148mm",
                    }
                ),
                encoding="utf-8",
            )
            status, _, err = run("run", str(job), "--dry-run")
            self.assertEqual(status, 0, err)


class TestDamagedIsPerRunToo(unittest.TestCase):
    """And for a stronger reason than --trim-from has.

    Stored, `--damaged recover` is a standing instruction to impose whatever
    survived the copy -- for every file the folder is ever handed, for ever.
    That is the defect the refusal was added to close, written into a file.
    """

    def test_it_is_not_written_into_the_job(self):
        with damaged_workspace() as source:
            job = source.with_name("job.json")
            status, _, err = run(
                "nup",
                str(source),
                "--damaged",
                "recover",
                "--record",
                str(job),
                "--dry-run",
            )
            self.assertEqual(status, 0, err)
            stored = json.loads(job.read_text(encoding="utf-8"))
            self.assertNotIn("damaged", stored)
            self.assertIn("applies to this run only", err)
            self.assertIn("page count had to be rebuilt", err)

    def test_the_stored_job_refuses_the_file_again(self):
        with damaged_workspace() as source:
            job = source.with_name("job.json")
            run(
                "nup",
                str(source),
                "--damaged",
                "recover",
                "--record",
                str(job),
                "--dry-run",
            )
            status, _, err = run("run", str(job), "--dry-run")
            self.assertNotEqual(status, 0)
            self.assertIn("cross-reference table", err)

    def test_a_job_naming_it_is_refused_as_not_a_field(self):
        with workspace(pages=8) as source:
            job = source.with_name("job.json")
            job.write_text(
                json.dumps(
                    {"source": source.name, "schema": "nup", "damaged": "recover"}
                ),
                encoding="utf-8",
            )
            status, _, err = run("run", str(job))
            self.assertEqual(status, 1)
            self.assertIn("'damaged', which is not a field of a job", err)
