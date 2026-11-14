# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

"""The `impose-hotfolder` command, and what it hands over.

The files it carries are tested elsewhere -- `tests/test_unattended.py` starts
the watchers, `tests/shell/watch-inotify.bats` runs one against a live event
source, and CI reads the unit with `systemd-analyze verify`. What is tested
here is that an install *has* them, and that a copy made from one is a file
the service templates can actually start: executable, byte for byte the same,
and refused rather than overwritten.
"""

from __future__ import annotations

import io
import pathlib
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

from impose.hotfolder.cli import FILES, Bundled, main, require

#: What the listing puts against the two files this machine can use.
MARKER = "<- this machine"


class TestWhatShips(unittest.TestCase):
    """The four files are there, in the package, with content."""

    def test_every_bundled_file_is_in_the_install(self):
        """Each name in the catalogue is a file here, with something in it."""
        for bundled in FILES:
            with self.subTest(bundled.name):
                self.assertTrue(
                    bundled.path.is_file(),
                    f"{bundled.name} is in the catalogue and not in the package",
                )
                self.assertGreater(bundled.path.stat().st_size, 0)

    def test_the_catalogue_is_the_directory(self):
        """Nothing ships that the command will not admit to carrying.

        The other direction of the test above. A fifth file added to the
        directory and not to `FILES` would be in the wheel, unmentioned by
        `impose-hotfolder` and so invisible to anybody who installed it.
        """
        directory = FILES[0].path.parent
        shipped = {
            path.name
            for path in directory.iterdir()
            if path.suffix in {".sh", ".service", ".plist"}
        }
        self.assertEqual(shipped, {bundled.name for bundled in FILES})

    def test_the_scripts_are_shell_and_the_templates_are_not(self):
        """Each one is what the catalogue says it is, by its first line."""
        for bundled in FILES:
            with self.subTest(bundled.name):
                first = bundled.path.read_text(encoding="utf-8").splitlines()[0]
                if bundled.name.endswith(".sh"):
                    self.assertTrue(first.startswith("#!/bin/"), first)
                    self.assertEqual(bundled.mode, 0o755)
                else:
                    self.assertFalse(first.startswith("#!"), first)
                    self.assertEqual(bundled.mode, 0o644)


class TestListing(unittest.TestCase):
    """What `impose-hotfolder` says with no arguments."""

    def _listing(self, platform: str) -> str:
        out = io.StringIO()
        saved, sys.stdout = sys.stdout, out
        try:
            # The platform is read from sys.platform, which is what decides
            # which pair of files this machine can use.
            saved_platform, sys.platform = sys.platform, platform
            try:
                status = main([])
            finally:
                sys.platform = saved_platform
        finally:
            sys.stdout = saved
        self.assertEqual(status, 0)
        return out.getvalue()

    def test_it_names_every_file_and_where_they_are(self):
        """The listing is the answer to "what did I just install, and where"."""
        listing = self._listing("linux")
        for bundled in FILES:
            self.assertIn(bundled.name, listing)
            self.assertIn(bundled.what, listing)
        self.assertIn(str(FILES[0].path.parent), listing)

    def test_linux_is_told_which_two_are_its_own(self):
        """On Linux the inotify watcher and the unit are the marked pair."""
        listing = self._listing("linux")
        marked = [line for line in listing.splitlines() if MARKER in line]
        self.assertEqual(len(marked), 2)
        self.assertIn("watch-inotify.sh", marked[0])
        self.assertIn("impose-folder@.service", marked[1])
        self.assertIn("--path watch-inotify.sh", listing)

    def test_macos_is_told_the_other_two(self):
        """On macOS it is the fswatch watcher and the launchd agent."""
        listing = self._listing("darwin")
        marked = [line for line in listing.splitlines() if MARKER in line]
        self.assertEqual(len(marked), 2)
        self.assertIn("watch-fswatch.sh", marked[0])
        self.assertIn("impose-folder.plist", marked[1])
        self.assertIn("--path watch-fswatch.sh", listing)

    def test_a_third_platform_is_told_so_rather_than_sold_a_watcher(self):
        """Neither script works over a kernel that has neither interface.

        Printing the Linux line anyway would be an instruction to install a
        watcher that cannot watch, and the status it would fail with -- a
        missing `inotifywait` is exit 127 a file at a time -- is the one this
        project goes out of its way to turn into a refusal at startup.
        """
        listing = self._listing("freebsd")
        self.assertNotIn(MARKER, listing)
        self.assertIn("Neither watcher is for this machine (freebsd)", listing)
        self.assertNotIn("install -m 755", listing)


class TestAnInstallThatLostAFile(unittest.TestCase):
    """A file in the catalogue and not on disk is a sentence, not a path."""

    def test_a_missing_file_is_refused_by_name(self):
        """Nothing here can produce this; a repackager can."""
        absent = Bundled("watch-kqueue.sh", "a watcher nobody ships", "openbsd")
        with self.assertRaises(FileNotFoundError) as raised:
            require(absent)
        sentence = str(raised.exception)
        self.assertIn("watch-kqueue.sh is not in this install", sentence)
        self.assertIn(str(absent.path), sentence)
        # One sentence, no errno: this is read by whoever installed impose.
        self.assertNotIn("Errno", sentence)

    def test_every_bundled_file_passes_it(self):
        """The same check, over what actually ships."""
        for bundled in FILES:
            with self.subTest(bundled.name):
                self.assertEqual(require(bundled), bundled.path)


class TestPath(unittest.TestCase):
    """`--path` is the argument to install(1), so it is one line and a path."""

    def test_it_prints_one_readable_path_and_nothing_else(self):
        """One absolute path, no heading: it is going inside "$(...)"."""
        out = io.StringIO()
        saved, sys.stdout = sys.stdout, out
        try:
            status = main(["--path", "watch-inotify.sh"])
        finally:
            sys.stdout = saved
        self.assertEqual(status, 0)
        printed = out.getvalue().splitlines()
        self.assertEqual(len(printed), 1)
        path = pathlib.Path(printed[0])
        self.assertTrue(path.is_absolute())
        self.assertTrue(path.read_text(encoding="utf-8").startswith("#!/bin/sh"))

    def test_a_name_it_does_not_carry_is_a_usage_error(self):
        """A misspelled name is exit 2 and the four names it does carry."""
        with self.assertRaises(SystemExit) as raised:
            main(["--path", "watch-kqueue.sh"])
        self.assertEqual(raised.exception.code, 2)


class TestInstall(unittest.TestCase):
    """`--install` is the copy you are about to edit."""

    def setUp(self):
        directory = tempfile.mkdtemp(prefix="impose-hotfolder-")
        self.addCleanup(shutil.rmtree, directory)
        self.directory = pathlib.Path(directory).resolve()

    def _install(self, *argv: str) -> tuple[int, str, str]:
        """Run `--install` into the temporary directory, capturing both streams."""
        out, errors = io.StringIO(), io.StringIO()
        saved = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = out, errors
        try:
            status = main(["--install", str(self.directory), *argv])
        finally:
            sys.stdout, sys.stderr = saved
        return status, out.getvalue(), errors.getvalue()

    def test_all_four_arrive_byte_for_byte(self):
        """A copy is the file, not a rendering of it, and is reported."""
        status, printed, _ = self._install()
        self.assertEqual(status, 0)
        for bundled in FILES:
            with self.subTest(bundled.name):
                copy = self.directory / bundled.name
                self.assertEqual(copy.read_bytes(), bundled.path.read_bytes())
                self.assertIn(f"wrote {copy}", printed)

    def test_the_scripts_are_executable_whatever_the_wheel_did(self):
        """The mode of a copy comes from the name, not from its source.

        A wheel does carry the executable bit: measured on one built from
        this tree and pip-installed into a fresh virtual environment, both
        scripts land 0755. This holds anyway, which is the point -- the
        watcher that reaches /usr/local/libexec at 0644 is an `ExecStart=`
        systemd cannot start, and that should not depend on whether the
        install the copy came from kept a mode bit.
        """
        self._install()
        for bundled in FILES:
            with self.subTest(bundled.name):
                mode = stat.S_IMODE((self.directory / bundled.name).stat().st_mode)
                self.assertEqual(mode, bundled.mode, oct(mode))

    def test_a_directory_that_is_not_there_is_made(self):
        """`--install ~/impose-hotfolder` makes the directory it names."""
        nested = self.directory / "a" / "b"
        out = io.StringIO()
        saved, sys.stdout = sys.stdout, out
        try:
            status = main(["--install", str(nested)])
        finally:
            sys.stdout = saved
        self.assertEqual(status, 0)
        self.assertTrue((nested / "watch-inotify.sh").is_file())

    def test_a_second_install_is_refused_and_changes_nothing(self):
        """The second run keeps the edits the first copy has since had."""
        self._install()
        edited = self.directory / "watch-fswatch.sh"
        edited.write_text("# mine now\n", encoding="utf-8")
        status, printed, errors = self._install()
        self.assertEqual(status, 4)
        self.assertEqual(printed, "")
        self.assertIn("is already there", errors)
        self.assertEqual(edited.read_text(encoding="utf-8"), "# mine now\n")

    def test_the_refusal_comes_before_any_of_the_four_is_written(self):
        """Half a copy is worse than none: four names, one check each, first.

        The fourth file is the one left in the directory, so a run that
        checked and copied one at a time would write three and then refuse,
        and the operator would be reading a sentence about `impose-folder.
        plist` with three files beside it that they did not have before.
        """
        (self.directory / "impose-folder.plist").write_text("mine\n")
        status, printed, _ = self._install()
        self.assertEqual(status, 4)
        self.assertEqual(printed, "")
        self.assertEqual(
            sorted(path.name for path in self.directory.iterdir()),
            ["impose-folder.plist"],
        )

    def test_overwrite_replaces_what_is_there(self):
        """Asked for, the replacement happens: the edit is gone."""
        self._install()
        edited = self.directory / "watch-fswatch.sh"
        edited.write_text("# mine now\n", encoding="utf-8")
        status, _, _ = self._install("--overwrite")
        self.assertEqual(status, 0)
        self.assertEqual(
            edited.read_bytes(), (FILES[1].path).read_bytes()  # watch-fswatch.sh
        )

    def test_overwrite_on_its_own_is_refused(self):
        """--overwrite with nothing to overwrite is a usage error, not a no-op."""
        with self.assertRaises(SystemExit) as raised:
            main(["--overwrite"])
        self.assertEqual(raised.exception.code, 2)

    def test_an_installed_watcher_runs(self):
        """The end of the line: a copy, started, says what it wants.

        It takes one argument, the folder, and with none it prints the usage
        line. A small claim that covers the mode, the shebang and the copy at
        once -- a 0644 file does not run at all.

        Nonzero rather than a number, and this is the measurement that says
        why: the folder is `${1:?usage ...}`, so the status for leaving it
        out belongs to the shell and not to the script. 1 under bash, which
        is both scripts on macOS, and 2 under dash, which is `/bin/sh` on
        Debian and Ubuntu and so is the inotify watcher on a CI runner. A
        service always passes its folder; this is the person at the terminal,
        and what they need is the sentence.
        """
        self._install()
        for bundled in FILES:
            if not bundled.name.endswith(".sh"):
                continue
            script = self.directory / bundled.name
            interpreter = script.read_text(encoding="utf-8").splitlines()[0]
            interpreter = interpreter.removeprefix("#!").split()[0]
            if not pathlib.Path(interpreter).exists():
                self.skipTest(f"no {interpreter} to run {bundled.name} with")
            with self.subTest(bundled.name):
                done = subprocess.run(
                    [str(script)], capture_output=True, text=True, check=False
                )
                self.assertNotEqual(done.returncode, 0, done.stdout)
                self.assertIn("usage:", done.stderr)


if __name__ == "__main__":
    unittest.main()
