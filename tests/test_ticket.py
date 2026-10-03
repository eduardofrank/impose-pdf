# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

# pylint: disable=missing-function-docstring
"""A job file is the same job as the command that wrote it."""

import json
import unittest

from impose import ImposeError
from impose.ticket import load
from impose.units import MM

from .test_cli import run, workspace


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
            status, text, err = run("run", str(job))
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
