# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE.

# pylint: disable=missing-class-docstring,missing-function-docstring

"""The reference watchers, run from Python on a folder of their own.

`tests/test_unattended.py` is the command run by something other than a
person. This is the two scripts that do the running: what they refuse at
startup, what they take out of an inbox and what they leave, where a file is
filed and under which name, and what they say about it. It was one module
with that one until the watchers' half passed six hundred lines.

The event source is stubbed with one that exits at once, so every run here
gets through its checks, sweeps, and leaves. The live event loop is
`tests/shell/watch-inotify.bats`.
"""

import datetime
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

from impose.hotfolder.cli import FILES as BUNDLED

from .support import make_pdf

#: The reference watchers, taken from what the package ships rather than from
#: a path spelled again here: these tests and `impose-hotfolder` have to be
#: talking about the same two files. Both of them, because the claim is
#: written out once per script -- they are copied to a server one file at a
#: time and share no library, so one of the two is exactly the thing that
#: drifts.
_WATCHERS = tuple(bundled.path for bundled in BUNDLED if bundled.name.endswith(".sh"))


def _runnable_watchers():
    """The watchers this machine can run, by the shebang each one carries.

    `/bin/bash` is not a given -- a minimal container has `/bin/sh` and
    nothing else -- and running a script whose interpreter is missing raises
    `FileNotFoundError` naming the *script*, which reads like the script is
    the thing that is absent. Skipping the one that cannot run says what is
    really going on, and still tests the other.
    """
    runnable = []
    for watcher in _WATCHERS:
        shebang = watcher.read_text(encoding="utf-8").splitlines()[0]
        interpreter = shebang.removeprefix("#!").split()[0]
        if pathlib.Path(interpreter).exists():
            runnable.append(watcher)
    return tuple(runnable)


class WatchedFolder(unittest.TestCase):
    """A folder for a reference watcher to run on, and a way to run it.

    The event source is stubbed out rather than relied on. A stub that exits
    at once ends the pipeline, so the script runs every check, sweeps, and
    leaves: deterministic on a machine that has inotify-tools or fswatch and
    on one that has neither. What that reaches is startup and the sweep. The
    live event loop is `tests/shell/watch-inotify.bats`, which needs bats and
    is not part of this suite.

    An event source that ends is a failure, and the watcher says so: exit 1
    and one sentence, which is therefore how every run here that got past
    its checks finishes. It used to be 0 and silence, which a service
    manager reads as a folder with nothing left to do.
    """

    #: What a watcher says when its event source goes away under it.
    ENDED = "the event source ended, so nothing is watching"

    def setUp(self):
        self.watchers = _runnable_watchers()
        if not self.watchers:
            self.skipTest("no interpreter for either reference watcher")
        self.root = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, True)
        impose = pathlib.Path(sys.executable).parent / "impose"
        if not impose.exists():
            self.skipTest(f"no impose beside {sys.executable}")
        self.bin = self.root / "bin"
        self.bin.mkdir()
        (self.bin / "impose").symlink_to(impose)
        for stub in ("inotifywait", "fswatch"):
            path = self.bin / stub
            path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            path.chmod(0o755)

    #: What the scripts call before they reach the check, and nothing else:
    #: a PATH built from these has no event source on it whatever the machine
    #: has installed, which `PATH=...:/usr/bin` could not promise on Linux.
    TOOLS = ("mkdir", "find", "cat", "date", "rm", "ln", "mv", "awk", "sleep")

    def bare_path(self):
        """A directory holding impose and the tools, and no event source."""
        bare = self.root / "bare"
        bare.mkdir()
        (bare / "impose").symlink_to(self.bin / "impose")
        for tool in self.TOOLS:
            found = shutil.which(tool)
            if found:
                (bare / tool).symlink_to(found)
        return bare

    def folder(self, name, **policy):
        """A watched folder, with *policy* over the top of the house one.

        The keywords are policy keys, spelled the way `policy.conf` spells
        them, because that file is the thing under test.
        """
        root = self.root / name
        root.mkdir()
        keys = {"SCHEMA": "nup", "OPTIONS": "--up 1x2 --expect-size A4", **policy}
        (root / "policy.conf").write_text(
            "".join(f"{key}={value}\n" for key, value in keys.items()),
            encoding="utf-8",
        )
        return root

    def start(self, watcher, root):
        """Run *watcher* on *root*, with the stubs ahead of anything real."""
        return subprocess.run(
            [str(watcher), str(root)],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
            env={**os.environ, "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}"},
        )


class TestOneOutboxOneFolder(WatchedFolder):
    """Two folders writing one directory, answered where it can still be seen.

    Measured before the watchers claimed the directory they write into: two
    runs with one `-o`, started together, both exit 0 and leave one press
    file, so a whole imposition is gone with nothing said about it. impose
    cannot refuse that -- :func:`impose.destination.reserve` is looking at a
    directory where the name is still free, and the rename that follows is
    atomic but reserves nothing -- and the mistake is made in a policy, so the
    folder's watcher is where it has to be answered.
    """

    def setUp(self):
        super().setUp()
        self.shared = self.root / "rip-in"
        self.shared.mkdir()

    @staticmethod
    def hold(directory, pid, folder):
        """Put a claim on *directory* in the name of *pid* and *folder*."""
        claim = directory / ".impose-writer.lock"
        claim.mkdir()
        (claim / "pid").write_text(f"{pid}\n", encoding="utf-8")
        (claim / "folder").write_text(f"{folder}\n", encoding="utf-8")
        return claim

    @staticmethod
    def reaped_pid():
        """A pid that is certainly not running: one started and waited for."""
        with subprocess.Popen([sys.executable, "-c", ""]) as child:
            child.wait()
        return child.pid

    def test_a_second_folder_on_one_outbox_is_refused_by_name(self):
        claim = self.hold(self.shared, os.getpid(), "/srv/impose/a4-nup")
        for watcher in self.watchers:
            with self.subTest(watcher.name):
                root = self.folder(f"second-{watcher.stem}", OUT=self.shared)
                finished = self.start(watcher, root)
                self.assertEqual(finished.returncode, 2, finished.stderr)
                self.assertIn(
                    f"{self.shared} is already the outbox of /srv/impose/a4-nup "
                    f"(pid {os.getpid()})",
                    finished.stderr,
                )
                self.assertIn("One outbox, one folder", finished.stderr)
                # And it leaves the holder's claim alone on the way out, which
                # is what the trap's `${x:+"$x"}` is for: a refusal that
                # cleaned up after itself would hand the folder to the next
                # one to start.
                self.assertEqual(
                    (claim / "pid").read_text(encoding="utf-8").strip(),
                    str(os.getpid()),
                )

    def test_a_shared_proof_directory_is_refused_the_same_way(self):
        self.hold(self.shared, os.getpid(), "/srv/impose/a4-nup")
        for watcher in self.watchers:
            with self.subTest(watcher.name):
                root = self.folder(f"proofs-{watcher.stem}", PROOF=self.shared)
                finished = self.start(watcher, root)
                self.assertEqual(finished.returncode, 2, finished.stderr)
                self.assertIn(
                    f"{self.shared} is already the proof directory of", finished.stderr
                )
                self.assertIn("One proof directory, one folder", finished.stderr)

    def test_a_claim_whose_holder_is_gone_is_cleared_and_taken(self):
        dead = self.reaped_pid()
        for watcher in self.watchers:
            with self.subTest(watcher.name):
                shared = self.root / f"debris-{watcher.stem}"
                shared.mkdir()
                self.hold(shared, dead, "/srv/impose/whoever")
                root = self.folder(f"heir-{watcher.stem}", OUT=shared)
                finished = self.start(watcher, root)
                self.assertEqual(finished.returncode, 1, finished.stderr)
                self.assertIn(f"clearing a claim on {shared}", finished.stderr)
                self.assertIn(f"left by pid {dead}", finished.stderr)

    def test_a_folder_writing_its_own_out_claims_and_releases_it(self):
        # The default layout cannot collide -- one out/ per folder -- so the
        # claim must be invisible there: taken, and gone again afterwards, or
        # every restart would meet its own debris.
        for watcher in self.watchers:
            with self.subTest(watcher.name):
                root = self.folder(f"own-{watcher.stem}")
                finished = self.start(watcher, root)
                # One line on stderr and it is the stub's doing: the checks
                # themselves had nothing to say.
                self.assertEqual(finished.returncode, 1, finished.stderr)
                self.assertEqual(
                    finished.stderr,
                    f"{watcher}: {self.ENDED} {root}.\n",
                )
                self.assertEqual(
                    sorted(path.name for path in (root / "out").iterdir()), []
                )
                self.assertFalse((root / ".watcher.lock").exists())


class TestTheEventSource(WatchedFolder):
    """A folder with nothing to tell it a file arrived is not a running folder.

    Both ways of having no event source used to end the same way: exit 0 and
    nothing said. Measured under systemd 255 with `inotifywait` killed
    beneath a running unit -- "Deactivated successfully", `NRestarts=0`, and
    the next file left in the inbox. `Restart=on-failure` and launchd's
    `SuccessfulExit=false` are both told that 0 needs no restart, so 0 is the
    one status a watcher must never leave with.
    """

    def test_a_machine_without_one_is_refused_before_anything_is_claimed(self):
        bare = self.bare_path()
        for watcher in self.watchers:
            with self.subTest(watcher.name):
                root = self.folder(f"bare-{watcher.stem}")
                finished = subprocess.run(
                    [str(watcher), str(root)],
                    capture_output=True,
                    text=True,
                    timeout=120,
                    check=False,
                    env={**os.environ, "PATH": str(bare)},
                )
                self.assertEqual(finished.returncode, 2, finished.stderr)
                self.assertIn("on the PATH this runs with", finished.stderr)
                # Refused before the lock and before the outbox claim, so
                # there is nothing for the next start to clear.
                self.assertFalse((root / ".watcher.lock").exists())
                self.assertFalse((root / "out" / ".impose-writer.lock").exists())

    def test_one_that_ends_is_a_failure_and_a_sentence(self):
        # The stub is an event source that starts and stops at once, which is
        # what a crash looks like from the reader's end of the pipe.
        for watcher in self.watchers:
            with self.subTest(watcher.name):
                root = self.folder(f"ended-{watcher.stem}")
                finished = self.start(watcher, root)
                self.assertEqual(finished.returncode, 1, finished.stderr)
                self.assertIn(f"{self.ENDED} {root}.", finished.stderr)
                # It still lets go on the way out, or the restart this status
                # asks for would meet its own lock.
                self.assertFalse((root / ".watcher.lock").exists())

    def test_no_folder_given_is_a_refusal_to_start(self):
        for watcher in self.watchers:
            with self.subTest(watcher.name):
                finished = subprocess.run(
                    [str(watcher)], capture_output=True, text=True, check=False
                )
                self.assertEqual(finished.returncode, 2, finished.stderr)
                self.assertIn("usage:", finished.stderr)


class TestFiling(WatchedFolder):
    """What is filed under a name stays there, and says only what is its own.

    The artwork in `done/` is the shop's record of what was printed. Measured
    while the buckets were filled with `mv`: `book.pdf` sent, its press file
    collected, a corrected `book.pdf` sent after it -- two lines saying
    `done (0)`, one file in `done/`, and the first artwork gone with nothing
    said. A resend under the same name is the ordinary case, not the odd one.

    The files go into `work/`, as in :class:`TestJsonLog`, so both watchers
    are measured without the fswatch script's wait for a file to settle.
    """

    def run_over(self, watcher, name, pages, tag, **policy):
        """A folder with a *pages*-page file already claimed as *name*."""
        policy = {"OPTIONS": "--up 2x2", **policy}
        root = self.folder(f"{tag}-{watcher.stem}", **policy)
        (root / "work").mkdir()
        make_pdf(pages).save(root / "work" / name)
        return root

    def test_a_name_already_filed_is_kept_and_the_new_one_goes_beside_it(self):
        for watcher in self.watchers:
            with self.subTest(watcher.name):
                root = self.run_over(watcher, "book.pdf", 4, "resend")
                (root / "done").mkdir()
                first = root / "done" / "book.pdf"
                first.write_bytes(b"the artwork that was printed")
                (root / "done" / "book.pdf.txt").write_text("its sentence\n")
                finished = self.start(watcher, root)

                self.assertEqual(first.read_bytes(), b"the artwork that was printed")
                self.assertEqual(
                    (root / "done" / "book.pdf.txt").read_text(), "its sentence\n"
                )
                beside = sorted(
                    path.name
                    for path in (root / "done").iterdir()
                    if path.name not in {"book.pdf", "book.pdf.txt"}
                )
                # One more file and its own sentence, the name carrying when
                # its run started: book.20261116T101502Z.pdf.
                self.assertEqual(len(beside), 2, beside)
                self.assertRegex(beside[0], r"^book\.\d{8}T\d{6}Z\.pdf$")
                self.assertEqual(beside[1], beside[0] + ".txt")
                self.assertIn(
                    f"book.pdf: done/ already holds a file of that name, so this "
                    f"one is filed as {beside[0]}",
                    finished.stderr,
                )
                self.assertIn("book.pdf: done (0)", finished.stdout)
                self.assertEqual(list((root / "work").iterdir()), [])

    def test_a_second_resend_in_the_same_second_still_has_a_name(self):
        # The stamp is to the second, so the suffix alone is not a promise.
        # Every name the stamp could give for a minute either side is taken
        # here, which leaves only the counter.
        for watcher in self.watchers:
            with self.subTest(watcher.name):
                root = self.run_over(watcher, "book.pdf", 4, "twice")
                (root / "done").mkdir()
                (root / "done" / "book.pdf").write_bytes(b"first")
                now = datetime.datetime.now(datetime.timezone.utc)
                for offset in range(-60, 61):
                    moment = now + datetime.timedelta(seconds=offset)
                    taken = f"book.{moment:%Y%m%dT%H%M%SZ}.pdf"
                    (root / "done" / taken).write_bytes(b"second")
                self.start(watcher, root)
                counted = [
                    path.name
                    for path in (root / "done").iterdir()
                    if path.name.endswith("-2.pdf")
                ]
                self.assertEqual(len(counted), 1, counted)

    def test_a_run_that_said_nothing_leaves_nobody_else_s_sentence(self):
        # `-q` in the policy and a clean run: impose says nothing, so there is
        # nothing to put beside the file -- and a sentence already at that
        # name, left when somebody took an earlier file and not its `.txt`,
        # must not be read as this file's.
        for watcher in self.watchers:
            with self.subTest(watcher.name):
                root = self.run_over(
                    watcher, "book.pdf", 4, "quiet", OPTIONS="--up 2x2 -q"
                )
                (root / "done").mkdir()
                stale = root / "done" / "book.pdf.txt"
                stale.write_text("what impose said about another file\n")
                self.start(watcher, root)
                self.assertTrue((root / "done" / "book.pdf").exists())
                self.assertFalse(stale.exists())


class TestWhatTheInboxTakes(WatchedFolder):
    """Which names are artwork, and what becomes of the ones that are not.

    Measured on the watcher as it was: `Mixed.Pdf` sat in the inbox for good,
    because only `.pdf` and `.PDF` matched, and so did a text file, an
    archive and a directory -- each of them with no line anywhere to say it
    had been seen and passed over.
    """

    #: The test of a name, as both scripts spell it.
    ARTWORK = (
        '    case "$name" in\n'
        "    .*) return 0 ;;\n"
        "    *.[Pp][Dd][Ff]) ;;\n"
        "    *) return 0 ;;\n"
        "    esac\n"
    )

    def test_any_spelling_of_the_extension_is_a_pdf(self):
        # Through `in/`, because the test of a name is in what handles an
        # arrival. Only the inotify script is run: the fswatch one waits four
        # seconds for a file's size to hold still before it will touch it,
        # with a BSD `stat` that a Linux runner does not have -- so it is held
        # to the same words instead, below.
        for watcher in self.watchers:
            if watcher.name != "watch-inotify.sh":
                continue
            root = self.folder("spelling", OPTIONS="--up 2x2")
            (root / "in").mkdir()
            make_pdf(2).save(root / "in" / "Mixed.Pdf")
            finished = self.start(watcher, root)
            self.assertIn("Mixed.Pdf: done (0)", finished.stdout)
            self.assertTrue((root / "done" / "Mixed.Pdf").exists())

    def test_both_scripts_ask_the_same_thing_of_a_name(self):
        for watcher in _WATCHERS:
            with self.subTest(watcher.name):
                self.assertIn(self.ARTWORK, watcher.read_text(encoding="utf-8"))

    def test_what_is_not_artwork_is_left_alone_and_named(self):
        for watcher in self.watchers:
            with self.subTest(watcher.name):
                root = self.folder(f"strays-{watcher.stem}", OPTIONS="--up 2x2")
                inbox = root / "in"
                inbox.mkdir()
                (inbox / "notes.txt").write_text("a quotation\n", encoding="utf-8")
                (inbox / "book.pdf.part").write_bytes(b"%PDF-1.7 half of an upload")
                (inbox / "job1").mkdir()
                (inbox / "folder.pdf").mkdir()
                (inbox / ".DS_Store").write_bytes(b"")
                (inbox / "._book.pdf").write_bytes(b"what a Mac leaves on a share")
                finished = self.start(watcher, root)

                # Nothing moved: an upload under its temporary name is about
                # to be renamed by the client that is writing it.
                self.assertEqual(
                    sorted(path.name for path in inbox.iterdir()),
                    [
                        ".DS_Store",
                        "._book.pdf",
                        "book.pdf.part",
                        "folder.pdf",
                        "job1",
                        "notes.txt",
                    ],
                )
                for bucket in ("done", "rejected", "failed"):
                    self.assertEqual(list((root / bucket).iterdir()), [], bucket)
                # And each one that can be seen is said, once.
                for name in ("notes.txt", "book.pdf.part", "job1", "folder.pdf"):
                    self.assertIn(f"{name}: left in in/", finished.stderr)
                self.assertNotIn(".DS_Store", finished.stderr)
                self.assertNotIn("._book.pdf", finished.stderr)

    def test_a_link_or_a_pipe_under_a_pdf_s_name_is_not_a_file(self):
        # Measured on the watcher as it was: a symbolic link in the inbox was
        # imposed as the file it points at -- `done (0)`, for a file that was
        # never sent here and is read with the service's permissions -- and a
        # pipe was opened and waited on for good, with every later file
        # behind it. Neither is opened now, and what a link points at is not
        # touched.
        outside = self.root / "somebody-else.pdf"
        make_pdf(2).save(outside)
        before = outside.read_bytes()
        for watcher in self.watchers:
            with self.subTest(watcher.name):
                root = self.folder(f"odd-{watcher.stem}", OPTIONS="--up 2x2")
                inbox = root / "in"
                inbox.mkdir()
                (inbox / "link.pdf").symlink_to(outside)
                os.mkfifo(inbox / "pipe.pdf")
                finished = self.start(watcher, root)

                self.assertTrue((inbox / "link.pdf").is_symlink())
                self.assertTrue((inbox / "pipe.pdf").is_fifo())
                for bucket in ("done", "rejected", "failed", "out"):
                    self.assertEqual(list((root / bucket).iterdir()), [], bucket)
                for name in ("link.pdf", "pipe.pdf"):
                    self.assertIn(f"{name}: left in in/", finished.stderr)
                self.assertEqual(outside.read_bytes(), before)

    def test_one_that_reached_work_is_removed_and_never_opened(self):
        # The look and the claim are two steps, so what is in `work/` is
        # looked at again. A link there is taken away; its target is not.
        outside = self.root / "target.pdf"
        make_pdf(2).save(outside)
        for watcher in self.watchers:
            with self.subTest(watcher.name):
                root = self.folder(f"swapped-{watcher.stem}", OPTIONS="--up 2x2")
                (root / "work").mkdir()
                (root / "work" / "link.pdf").symlink_to(outside)
                os.mkfifo(root / "work" / "pipe.pdf")
                finished = self.start(watcher, root)

                self.assertEqual(list((root / "work").iterdir()), [])
                self.assertEqual(list((root / "done").iterdir()), [])
                self.assertTrue(outside.exists())
                self.assertIn("link.pdf: not an ordinary file", finished.stderr)
                self.assertIn("pipe.pdf: not an ordinary file", finished.stderr)

    def test_an_empty_inbox_has_nothing_to_say(self):
        # The pattern itself must not be reported as a file called `*`.
        for watcher in self.watchers:
            with self.subTest(watcher.name):
                root = self.folder(f"empty-{watcher.stem}")
                finished = self.start(watcher, root)
                self.assertNotIn("left in in/", finished.stderr)


class TestALimitOnOneRun(WatchedFolder):
    """`TIMEOUT`: how long one file may take before its run is stopped.

    A folder works one file at a time, so a run that never ends is the whole
    folder stopped behind a service that looks idle. The one known cause, a
    pipe under a PDF's name, is refused; this is the bound on the next one.
    """

    SLOW = (
        "#!/bin/sh\n"
        "# The policy is tried against a file that is not there: answer that\n"
        "# as impose does, and take for ever over anything else.\n"
        'case "$*" in *.impose-policy-check.pdf*) exit 3 ;; esac\n'
        "exec sleep 60\n"
    )

    def needs_gnu_timeout(self):
        """Skip where there is nothing to enforce a limit with."""
        if not (shutil.which("timeout") or shutil.which("gtimeout")):
            self.skipTest("no GNU timeout on this machine to enforce one with")

    def claimed(self, watcher, tag, **policy):
        """A folder holding one two-page file, already claimed."""
        root = self.folder(f"{tag}-{watcher.stem}", OPTIONS="--up 2x2", **policy)
        (root / "work").mkdir()
        make_pdf(2).save(root / "work" / "book.pdf")
        return root

    def test_a_run_past_it_is_stopped_and_filed_as_failed(self):
        self.needs_gnu_timeout()
        (self.bin / "impose").unlink()
        (self.bin / "impose").write_text(self.SLOW, encoding="utf-8")
        (self.bin / "impose").chmod(0o755)
        for watcher in self.watchers:
            with self.subTest(watcher.name):
                root = self.claimed(watcher, "slow", TIMEOUT=1)
                finished = self.start(watcher, root)
                # 124 is timeout saying it stopped the run, which is neither
                # the file nor the job: `failed/`, where somebody looks.
                self.assertIn("book.pdf: failed (124)", finished.stdout)
                self.assertTrue((root / "failed" / "book.pdf").exists())
                self.assertEqual(list((root / "work").iterdir()), [])

    def test_a_run_inside_it_is_none_the_wiser(self):
        self.needs_gnu_timeout()
        for watcher in self.watchers:
            with self.subTest(watcher.name):
                root = self.claimed(watcher, "quick", TIMEOUT=60)
                finished = self.start(watcher, root)
                self.assertIn("book.pdf: done (0)", finished.stdout)

    def test_a_limit_that_is_not_seconds_is_refused(self):
        for value in ("5m", "0", "-3", "1.5", "soon"):
            for watcher in self.watchers:
                with self.subTest(watcher.name, value=value):
                    root = self.folder(f"n{value}-{watcher.stem}", TIMEOUT=value)
                    finished = self.start(watcher, root)
                    self.assertEqual(finished.returncode, 2, finished.stderr)
                    self.assertIn(
                        f"TIMEOUT={value} is not a whole number of seconds",
                        finished.stderr,
                    )

    def test_a_limit_nothing_can_enforce_is_refused_at_startup(self):
        # Refused, rather than run without it: a folder whose policy says ten
        # minutes and whose runs are unbounded is a policy somebody believes
        # is in force.
        bare = self.bare_path()
        for watcher in self.watchers:
            with self.subTest(watcher.name):
                root = self.folder(f"unenforced-{watcher.stem}", TIMEOUT=600)
                finished = subprocess.run(
                    [str(watcher), str(root)],
                    capture_output=True,
                    text=True,
                    timeout=120,
                    check=False,
                    env={**os.environ, "PATH": str(bare)},
                )
                self.assertEqual(finished.returncode, 2, finished.stderr)
                self.assertIn("there is no GNU timeout on the PATH", finished.stderr)


class TestStoppedBetweenWritingAndFiling(WatchedFolder):
    """A run killed after its press file was written and before it was filed.

    impose moves the press file into place whole, and the watcher files the
    artwork afterwards. Between the two there is a finished press file in
    `out/` and a claim in `work/`, and a kill there is what the next start
    finds. It imposes the claim again, impose refuses to replace the press
    file -- exit 4, correctly -- and the artwork is filed as failed for a job
    that succeeded. The watcher cannot tell that from a real conflict, so it
    says what to look at.
    """

    def test_the_leftover_is_failed_and_the_reason_is_said_first(self):
        for watcher in self.watchers:
            with self.subTest(watcher.name):
                root = self.folder(f"midway-{watcher.stem}", OPTIONS="--up 2x2")
                (root / "work").mkdir()
                (root / "out").mkdir()
                make_pdf(2).save(root / "work" / "book.pdf")
                (root / "out" / "book.pdf").write_bytes(b"the press file, whole")
                finished = self.start(watcher, root)

                self.assertIn("book.pdf: failed (4)", finished.stdout)
                self.assertIn(
                    f"book.pdf: {root / 'out'} already holds a press file of that name",
                    finished.stderr,
                )
                self.assertEqual(
                    (root / "out" / "book.pdf").read_bytes(), b"the press file, whole"
                )

    def test_an_ordinary_leftover_gets_no_such_sentence(self):
        for watcher in self.watchers:
            with self.subTest(watcher.name):
                root = self.folder(f"plain-{watcher.stem}", OPTIONS="--up 2x2")
                (root / "work").mkdir()
                make_pdf(2).save(root / "work" / "book.pdf")
                finished = self.start(watcher, root)
                self.assertIn("book.pdf: done (0)", finished.stdout)
                self.assertNotIn("already holds a press file", finished.stderr)


class TestJsonLog(WatchedFolder):
    """`LOG_FORMAT=json`: the same record, for a reader that is not a person.

    What a watcher says about a file -- `book.pdf: done (0)` -- was written
    for whoever is tailing the journal, and it is three facts in a sentence.
    A shop that wants to count this morning's jobs, find the slow ones, or
    raise something when a bucket fills has to parse them back out of prose
    that nothing here promised to keep. So a folder may ask for one object a
    file instead, and two facts the sentence never carried come with it: when
    the run started, and how long impose took.

    The files go into `work/` rather than `in/`, which is the
    left-over-from-an-earlier-run path. It reaches `impose_claimed` without
    the fswatch script's three-second wait for a file to settle, so both
    watchers cost the same here. The live event path is
    `tests/shell/watch-inotify.bats`.
    """

    def sweep(self, watcher, files, **policy):
        """Run *watcher* over *files*, already claimed, and give back its run.

        A name whose value is `None` is a print-ready PDF; anything else is
        the bytes to write under that name.
        """
        root = self.folder(f"log-{watcher.stem}", OPTIONS="--up 2x2", **policy)
        work = root / "work"
        work.mkdir()
        for name, data in files.items():
            if data is None:
                make_pdf(2).save(work / name)
            else:
                (work / name).write_bytes(data)
        finished = self.start(watcher, root)
        self.assertEqual(finished.returncode, 1, finished.stderr)
        self.assertIn(self.ENDED, finished.stderr)
        return root, finished

    def test_one_object_a_file_saying_what_happened_to_it(self):
        # A name with a quote, a backslash and a tab in it, because a hot
        # folder's filenames come from strangers and these are the three that
        # would otherwise write a line nothing can parse.
        odd = 'odd "name"\tand a \\ copy.pdf'
        for watcher in self.watchers:
            with self.subTest(watcher.name):
                root, finished = self.sweep(
                    watcher,
                    {"book.pdf": None, odd: None, "quote.pdf": b"not artwork\n"},
                    LOG_FORMAT="json",
                )
                lines = finished.stdout.splitlines()
                self.assertEqual(len(lines), 3, finished.stdout)
                # Escaped, not sent raw: a tab in a filename reaching the
                # line as a tab is a second field to whatever reads it.
                self.assertNotIn("\t", finished.stdout)

                logged = {}
                for line in lines:
                    entry = json.loads(line)
                    logged[entry["file"]] = entry
                self.assertEqual(sorted(logged), sorted(["book.pdf", odd, "quote.pdf"]))

                imposed = logged["book.pdf"]
                self.assertEqual(
                    sorted(imposed),
                    [
                        "bucket",
                        "duration",
                        "exit",
                        "file",
                        "folder",
                        "message",
                        "timestamp",
                    ],
                )
                self.assertEqual(imposed["folder"], str(root))
                self.assertEqual(imposed["bucket"], "done")
                self.assertEqual(imposed["exit"], 0)
                self.assertIn("n-up: 2 pages onto 1 sheet", imposed["message"])

                # The two facts the text line never carried. The duration is
                # whatever impose took and nothing else -- not the claim, not
                # the filing -- so it is small, and it is not negative.
                started = datetime.datetime.strptime(
                    imposed["timestamp"], "%Y-%m-%dT%H:%M:%SZ"
                ).replace(tzinfo=datetime.timezone.utc)
                self.assertLess(
                    abs(datetime.datetime.now(datetime.timezone.utc) - started),
                    datetime.timedelta(minutes=5),
                )
                self.assertGreaterEqual(imposed["duration"], 0)
                self.assertLess(imposed["duration"], 60)

                # The status and the bucket are the same decision the text
                # line reports, which is the whole point of the field.
                turned_away = logged["quote.pdf"]
                self.assertEqual(turned_away["exit"], 3)
                self.assertEqual(turned_away["bucket"], "rejected")
                self.assertTrue(
                    turned_away["message"].startswith("impose: "),
                    turned_away["message"],
                )

    def test_a_format_nobody_implements_is_refused_before_anything_is_imposed(self):
        for watcher in self.watchers:
            with self.subTest(watcher.name):
                root = self.folder(f"xml-{watcher.stem}", LOG_FORMAT="xml")
                finished = self.start(watcher, root)
                self.assertEqual(finished.returncode, 2, finished.stderr)
                self.assertIn(
                    "LOG_FORMAT=xml is not a format this writes", finished.stderr
                )
                # Before anything: no outbox, so no file was ever at risk of
                # being imposed and logged in a format nobody asked for.
                self.assertFalse((root / "out").exists())

    def test_the_default_is_still_the_line_a_person_reads(self):
        for watcher in self.watchers:
            with self.subTest(watcher.name):
                _, finished = self.sweep(watcher, {"book.pdf": None})
                self.assertEqual(finished.stdout, "book.pdf: done (0)\n")
