# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE.

# pylint: disable=missing-function-docstring

"""Every job file an earlier version wrote is one this version imposes.

A shop records a job once and runs it for years: a folder's ticket, the
quote system's copy of a repeat order. The promise in the README is that
within one edition of the file -- `"version": 1` -- a key is never renamed,
removed or given another meaning, so a job any version of impose wrote is
imposed the same way by every later one.

`tests/jobs/<version>/` is what that version's `--record` wrote, one job per
schema, kept exactly as written: every key, defaults and all, which is the
form that leans hardest on the promise, since every one of those keys has to
keep its name. A version adds a directory of its own and never edits an
earlier one's. A job here that stops imposing, or imposes onto a different
number of sheets, is a stored job broken in every shop that has one.
"""

import io
import pathlib
import shutil
import tempfile
import unittest

from impose import ImposeError
from impose.geometry import Size
from impose.job import SCHEMAS
from impose.ticket import VERSION, run
from impose.units import MM

from .support import make_pdf

JOBS = pathlib.Path(__file__).resolve().parent / "jobs"

#: What each stored job imposed when it was recorded: sheets, then pages to a
#: surface. The same for every version so far, because every version's jobs
#: were recorded from the same commands on the same sources below.
RECORDED = {
    "saddle": (4, 2),
    "perfect": (4, 2),
    "nup": (4, 2),
    "cutstack": (2, 4),
    "steprepeat": (1, 21),
    "signature": (2, 4),
    "cover": (1, 1),
    "gang": (1, 6),
}


def _sources(folder: pathlib.Path) -> None:
    """The files the stored jobs name, made where the jobs will look."""
    make_pdf(16, trim=Size(148 * MM, 210 * MM)).save(folder / "book.pdf")
    make_pdf(1, trim=Size(85 * MM, 55 * MM)).save(folder / "card.pdf")
    make_pdf(4, trim=Size(85 * MM, 55 * MM)).save(folder / "cards.pdf")


class TestStoredJobsStillImpose(unittest.TestCase):
    """Each version's recorded jobs, imposed by this one."""

    def test_there_is_a_stored_job_for_every_schema(self):
        # So that a new schema cannot ship without one, and the oldest
        # directory says which version the promise has been kept since.
        for edition in sorted(JOBS.iterdir()):
            with self.subTest(edition.name):
                stored = {job.stem for job in edition.glob("*.json")}
                self.assertEqual(stored, set(SCHEMAS))

    def test_every_stored_job_imposes_as_it_did_when_recorded(self):
        for edition in sorted(JOBS.iterdir()):
            for job in sorted(edition.glob("*.json")):
                with self.subTest(f"{edition.name}/{job.name}"):
                    with tempfile.TemporaryDirectory() as folder:
                        here = pathlib.Path(folder)
                        _sources(here)
                        shutil.copy(job, here / job.name)
                        # As a shop runs it: `impose run saddle.json`, with
                        # the source and the output the file itself names.
                        result = run(here / job.name, io.StringIO())
                        self.assertEqual((result.sheets, result.up), RECORDED[job.stem])
                        self.assertTrue(any(here.glob("*-out.pdf")))

    def test_an_edition_this_impose_does_not_read_is_refused_by_name(self):
        job = JOBS / "0.3.0" / "nup.json"
        with tempfile.TemporaryDirectory() as folder:
            later = pathlib.Path(folder) / "nup.json"
            text = job.read_text(encoding="utf-8")
            later.write_text(
                text.replace(f'"version": {VERSION}', f'"version": {VERSION + 1}'),
                encoding="utf-8",
            )
            with self.assertRaises(ImposeError) as refused:
                run(later, io.StringIO())
        self.assertIn(f"is job version {VERSION + 1}", str(refused.exception))
        self.assertIn(f"This impose reads version {VERSION}", str(refused.exception))


if __name__ == "__main__":
    unittest.main()
