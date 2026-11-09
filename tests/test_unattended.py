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
import io
import os
import pathlib
import shutil
import signal
import subprocess
import sys
import tempfile
import unittest

import pikepdf

from impose import DestinationError
from impose.geometry import Size
from impose.job import impose_document
from impose.signals import STOP_SIGNALS, stop, stopping_cleanly
from impose.units import MM

from .support import make_office_pdf, make_pdf, truncated_pdf
from .test_cli import run, workspace

#: The reference watchers. Both of them, because the claim is written out once
#: per script -- they are copied to a server one file at a time and share no
#: library, so one of the two is exactly the thing that drifts.
_WATCHERS = (
    pathlib.Path(__file__).resolve().parents[1] / "tools" / "watch-inotify.sh",
    pathlib.Path(__file__).resolve().parents[1] / "tools" / "watch-fswatch.sh",
)


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


class TestOpenDocumentIsStillAFile(unittest.TestCase):
    """A document handed over already open still knows where it lives.

    The blind spot pikepdf's own guard has, and the obvious way to drive the
    library: read the boxes, decide what to do, then impose. The path has to
    come from the document, because the caller did not pass one.
    """

    def test_imposing_an_open_document_onto_its_own_file_is_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            source = pathlib.Path(folder) / "catalogue.pdf"
            make_pdf(16).save(source)
            opened = pikepdf.open(source)
            try:
                with self.assertRaises(DestinationError):
                    impose_document(opened, source, schema="nup", overwrite=True)
            finally:
                opened.close()
            with pikepdf.open(source) as after:
                self.assertEqual(len(after.pages), 16)

    def test_a_document_built_in_memory_has_no_file_to_protect(self):
        """`Pdf.new().filename` is a description, not a path, and must not be
        mistaken for one."""
        with tempfile.TemporaryDirectory() as folder:
            output = pathlib.Path(folder) / "out.pdf"
            impose_document(make_pdf(8), output, schema="nup")
            self.assertTrue(output.exists())


class TestExitCodes(unittest.TestCase):
    """The number a watcher routes on.

    0 done, 1 the job cannot be imposed as described, 2 the arguments do not
    parse, 3 the source cannot be used, 4 the destination refuses. The split
    that matters operationally is 3 and 1 against 4: the first two are a file
    or a job somebody has to fix and must not be retried, the last is a shelf
    that will be there again in a minute.
    """

    def test_a_good_run_is_nought(self):
        with workspace(pages=8) as source:
            status, _, _ = run("nup", str(source), "-o", str(source.with_name("o.pdf")))
            self.assertEqual(status, 0)

    def test_a_job_that_cannot_be_imposed_is_one(self):
        """The artwork is fine and the description is not: a form that will
        not go on the press."""
        with workspace(pages=8, trim=Size(900 * MM, 900 * MM)) as source:
            status, _, err = run(
                "nup", str(source), "-o", str(source.with_name("o.pdf"))
            )
            self.assertEqual(status, 1)
            self.assertNotIn("Traceback", err)

    def test_arguments_that_do_not_parse_are_two(self):
        with workspace(pages=8) as source:
            status, _, _ = run("nup", str(source), "--up", "4by2")
            self.assertEqual(status, 2)

    def test_a_source_that_cannot_be_used_is_three(self):
        for name, make in (
            ("missing", lambda d: d / "absent.pdf"),
            ("not a pdf", _write(b"certainly not a pdf")),
            ("empty", _write(b"")),
            ("truncated", _write(truncated_pdf(make_pdf(16), 0.4))),
        ):
            with self.subTest(source=name), tempfile.TemporaryDirectory() as folder:
                path = make(pathlib.Path(folder))
                status, _, err = run(
                    "nup", str(path), "-o", str(pathlib.Path(folder) / "o.pdf")
                )
                self.assertEqual(status, 3)
                self.assertNotIn("Traceback", err)
                self.assertTrue(err.startswith("impose: "))

    def test_a_destination_that_refuses_is_four(self):
        with workspace(pages=8) as source:
            existing = source.with_name("there.pdf")
            existing.write_bytes(b"already here")
            cases = {
                "already there": str(existing),
                "directory missing": str(source.with_name("nope") / "o.pdf"),
                "is the input": str(source),
            }
            for name, output in cases.items():
                with self.subTest(destination=name):
                    status, _, err = run("nup", str(source), "-o", output)
                    self.assertEqual(status, 4)
                    self.assertNotIn("Traceback", err)
                    self.assertTrue(err.startswith("impose: "))

    def test_a_zero_page_document_is_three_and_not_an_indexerror(self):
        with tempfile.TemporaryDirectory() as folder:
            path = pathlib.Path(folder) / "empty.pdf"
            pikepdf.Pdf.new().save(path)
            status, _, err = run(
                "nup", str(path), "-o", str(pathlib.Path(folder) / "o.pdf")
            )
            self.assertEqual(status, 3)
            self.assertIn("no pages", err)
            self.assertNotIn("Traceback", err)


#: A run that is provably inside the write when the signal arrives: it prints
#: once the temporary exists and then waits, so the parent never has to guess
#: at a moment. `impose.signals` is asked for the handler rather than the test
#: inventing one, because the handler is what is under test.
_HELD_WRITE = """
import pathlib
import signal
import sys
import time

from impose.signals import STOP_SIGNALS, stop
from impose.destination import writing

for number in STOP_SIGNALS:
    signal.signal(number, stop)
with writing(pathlib.Path(sys.argv[1])) as temporary:
    pathlib.Path(temporary).write_bytes(b"half a press file")
    print("writing", flush=True)
    time.sleep(30)
"""


class TestStoppedFromOutside(unittest.TestCase):
    """A run ended by a signal leaves nothing half written behind it.

    `systemctl stop` and `launchctl` end a service with SIGTERM, and Python
    does nothing with it unasked: the interpreter stops where it stands and no
    ``finally`` anywhere runs. So the temporary the press file is written to
    stayed in the output directory -- a dotfile that a watcher matching
    `*.pdf` cannot see and nothing ever comes back for. Measured before this,
    on a 20000-page run killed mid-write: 12.8 MB of pikepdf's own temporary
    and a zero-byte one of ours, and not a word on stderr.
    """

    def test_the_handler_leaves_with_the_status_a_shell_would_report(self):
        with contextlib.redirect_stderr(io.StringIO()) as said:
            with self.assertRaises(SystemExit) as stopped:
                stop(int(signal.SIGTERM), None)
        self.assertEqual(stopped.exception.code, 128 + int(signal.SIGTERM))
        self.assertIn("SIGTERM", said.getvalue())
        self.assertNotIn("Traceback", said.getvalue())

    def test_a_library_caller_s_signal_policy_is_borrowed_not_taken(self):
        before = {number: signal.getsignal(number) for number in STOP_SIGNALS}
        with stopping_cleanly():
            self.assertEqual(
                [signal.getsignal(number) for number in STOP_SIGNALS],
                [stop] * len(STOP_SIGNALS),
            )
        after = {number: signal.getsignal(number) for number in STOP_SIGNALS}
        self.assertEqual(after, before)

    @unittest.skipIf(
        sys.platform == "win32",
        "Windows terminates a process rather than delivering a signal to it",
    )
    def test_sigterm_during_a_write_takes_the_temporary_with_it(self):
        with tempfile.TemporaryDirectory() as folder:
            out = pathlib.Path(folder)
            with subprocess.Popen(
                [sys.executable, "-c", _HELD_WRITE, str(out / "sheet.pdf")],
                cwd=pathlib.Path(__file__).resolve().parents[1],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            ) as running:
                try:
                    self.assertEqual(running.stdout.readline().strip(), "writing")
                    temporaries = list(out.glob(".sheet.pdf.impose-*.tmp"))
                    self.assertEqual(len(temporaries), 1, "nothing was being written")
                    running.send_signal(signal.SIGTERM)
                    status = running.wait(timeout=30)
                finally:
                    # So a failed assertion above cannot leave the parent
                    # waiting out the child's sleep.
                    running.kill()
                self.assertEqual(status, 128 + int(signal.SIGTERM))
                self.assertIn("stopped on SIGTERM", running.stderr.read())
            # Neither the temporary nor the destination: the press file never
            # appeared, which is the point of writing beside it.
            self.assertEqual(sorted(path.name for path in out.iterdir()), [])


def _write(data):
    """A factory that drops *data* into a temporary directory as a PDF."""

    def make(folder):
        path = folder / "book.pdf"
        path.write_bytes(data)
        return path

    return make


class TestOneOutboxOneFolder(unittest.TestCase):
    """Two folders writing one directory, answered where it can still be seen.

    Measured before the watchers claimed the directory they write into: two
    runs with one `-o`, started together, both exit 0 and leave one press
    file, so a whole imposition is gone with nothing said about it. impose
    cannot refuse that -- :func:`impose.destination.reserve` is looking at a
    directory where the name is still free, and the rename that follows is
    atomic but reserves nothing -- and the mistake is made in a policy, so the
    folder's watcher is where it has to be answered.

    The event source is stubbed out rather than relied on. A stub that exits
    at once ends the pipeline, so the script runs every check, sweeps, and
    leaves: deterministic on a machine that has inotify-tools or fswatch and
    on one that has neither.
    """

    def setUp(self):
        self.watchers = _runnable_watchers()
        if not self.watchers:
            self.skipTest("no interpreter for either reference watcher")
        self.root = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, True)
        self.shared = self.root / "rip-in"
        self.shared.mkdir()
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

    def folder(self, name, out=None):
        """A watched folder whose policy writes into *out*, or its own out/."""
        root = self.root / name
        root.mkdir()
        policy = "SCHEMA=nup\nOPTIONS=--up 1x2 --expect-size A4\n"
        if out is not None:
            policy += f"OUT={out}\n"
        (root / "policy.conf").write_text(policy, encoding="utf-8")
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
                root = self.folder(f"second-{watcher.stem}", out=self.shared)
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
                root = self.folder(f"proofs-{watcher.stem}")
                (root / "policy.conf").write_text(
                    f"SCHEMA=nup\nOPTIONS=--up 1x2 --expect-size A4\n"
                    f"PROOF={self.shared}\n",
                    encoding="utf-8",
                )
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
                root = self.folder(f"heir-{watcher.stem}", out=shared)
                finished = self.start(watcher, root)
                self.assertEqual(finished.returncode, 0, finished.stderr)
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
                self.assertEqual(finished.returncode, 0, finished.stderr)
                self.assertEqual(finished.stderr, "")
                self.assertEqual(
                    sorted(path.name for path in (root / "out").iterdir()), []
                )
                self.assertFalse((root / ".watcher.lock").exists())
