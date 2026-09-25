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


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
