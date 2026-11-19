# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE.

# pylint: disable=missing-function-docstring

"""The version an install reports, and the record of what it contains.

`impose --version` is how a shop finds out what it is running, and
`CHANGELOG.md` is how it finds out what that means. They are only useful
together: a number with no entry tells nobody what changed, and a number set
in one of its two places but not the other reports a different version
depending on who asks. This keeps the three in step.
"""

import pathlib
import re
import unittest

from impose import __version__

ROOT = pathlib.Path(__file__).resolve().parent.parent


class TestTheVersionIsRecorded(unittest.TestCase):
    """One number, in the package, in its metadata, and in the changelog."""

    def setUp(self):
        self.changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

    def test_the_package_and_its_metadata_agree(self):
        # Read with a pattern, not tomllib, which Python 3.10 does not have.
        project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        found = re.search(r'^version = "([^"]+)"$', project, re.MULTILINE)
        self.assertIsNotNone(found)
        assert found is not None
        self.assertEqual(found.group(1), __version__)

    def test_this_version_has_an_entry(self):
        headings = re.findall(r"^## (\S+)", self.changelog, re.MULTILINE)
        self.assertIn(__version__, headings)

    def test_unreleased_comes_first_and_this_version_next(self):
        # Newest first, so the version an install reports is the first
        # numbered entry: anything above it has not been released.
        headings = re.findall(r"^## (\S+)", self.changelog, re.MULTILINE)
        self.assertEqual(headings[:2], ["Unreleased", __version__])


if __name__ == "__main__":
    unittest.main()
