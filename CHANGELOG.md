# Changelog

What changed between two versions of impose, written for whoever installs it:
the shop running a folder, more than the person reading the code. `impose
--version` says which version an install is. Each version is a git tag, `v`
followed by the number, on the commit that set it. The reasoning behind each
change is in that commit's message; this file says what a user will notice.

A line goes under **Unreleased** in the same commit as the change it
describes. A version is cut by moving those lines under a new heading, setting
the number in `pyproject.toml` and `impose/__init__.py`, and tagging that
commit. `tests/test_changelog.py` checks that the three agree. Nothing is
published to PyPI; an install is still from source.

Version numbers follow [Semantic Versioning](https://semver.org/). Before 1.0
a minor version may change behaviour a folder depends on, so read its section
before you upgrade. The things a folder depends on are the exit statuses, the
refusals, the options, and the watchers' buckets and log lines.

## Unreleased

## 0.3.0 — 2026-11-26

Two changes a folder will see. The watcher's own messages are JSON when the
policy asks for JSON, so a `jq` command copied from RUNNING.md before this
version needs the change described below. And a cover whose output names its
artwork is now refused at exit 4.

### Changed: the watchers

- A PDF the watcher cannot claim gets a log line,
  `book.pdf: cannot be claimed, so it stays in in/`, with the reason after it.
  Before, it stayed in `in/` and nothing was logged. On Linux, this happens
  when the upload belongs to an account the folder's user cannot write as.
- The macOS watcher looks through `in/` again when FSEvents says it dropped
  events, as the Linux one does on an inotify overflow. It logs a line saying
  so. Before, those files waited in `in/` for a restart.
- With `LOG_FORMAT=json`, the watcher's own messages are JSON objects too,
  still on stderr: `timestamp`, `folder`, `file` (or `null`) and `message`,
  with no `bucket` or `exit`. Before, they were prose in the same log, and
  `jq` stopped at the first one. RUNNING.md's morning-check `jq` commands now
  pick the file records out with `has("bucket")`; if you copied the old ones,
  change them the same way. A refusal that comes before the policy is read
  is still text.

### Changed: covers

- A cover whose `-o` or `--proof` names its `--artwork` file is refused at
  exit 4, with or without `--overwrite`, as one naming the text block already
  was. Called as a library, `impose_cover` refuses an output that names either
  file. Before, nothing compared the artwork's path with the output, and the
  library compared neither, so the sheets could be written over a file the
  run was made from.
- `impose cover --overwrite` replaces an existing press file or proof, as it
  does for every other schema. Before, it accepted the option, ignored it, and
  refused at exit 4.

## 0.2.0 — 2026-11-19

The fixes from an audit of the watched folder and the project. Several change
what a folder sees: a file 0.1.0 imposed at exit 0 may now be refused at
exit 3, and there is a new status, 70. Read this section before you upgrade a
folder.

### Changed: files that are now refused

- A page with no MediaBox, or one that is not four numbers, is refused at
  exit 3. 0.1.0 imposed the US Letter page QPDF put in its place, at exit 0.
  No option brings that back.
- A file whose page tree held something that is not a page is refused at
  exit 3, as a rebuilt page count already was. 0.1.0 imposed it a page short,
  at exit 0. `--damaged recover` imposes what can be read, with a note.
- A mark colour other than `registration` or `black` in a job file is refused
  at exit 1. 0.1.0 drew registration marks for any other word, `"blak"`
  included.

### Changed: exit statuses

- `70` is a fault in impose itself, followed by its traceback. 0.1.0 reported
  an unexpected exception as `1`, which a folder files as the customer's
  problem. A watcher files a `70` in `failed/`.
- A malformed file that used to stop impose with a traceback now gets a
  sentence and exit 3.

### Changed: the watchers

- A watcher whose event source ends, or is missing, exits 1 with a sentence,
  or refuses to start at exit 2. 0.1.0 exited 0, which a service manager does
  not restart.
- `systemctl stop` no longer leaves the unit marked failed.
- A resend under a name already filed goes beside the earlier file, with the
  time in its name. 0.1.0 replaced it.
- Any spelling of `.pdf` is taken, and only an ordinary file: a link or a pipe
  under a PDF's name is removed, not imposed. What is not artwork is left in
  `in/` and named once a sweep.
- `TIMEOUT` in `policy.conf` limits one run, so that one file cannot stop a
  folder.
- Under systemd, one file running out of memory no longer stops and restarts
  the whole watcher.
- A leftover whose press file is already there is explained, not just failed.
- On Linux, events the kernel dropped send the watcher back through `in/`.
- The macOS watcher hears a file renamed into the folder.

### Changed: requirements

- pikepdf 10 or later. 0.1.0 said 9, but failed 19 tests on 9.0.0, and on
  10.0.0 could not write to a device such as `/dev/stdout`.
- Type information ships with the package (`py.typed`).

## 0.1.0 — 2026-11-15

The first version given a number. Every install before 0.2.0 reports it, and
`v0.1.0` tags the commit the audit was run against. This is what it does.

### Imposing

- Eight schemas: `saddle`, `perfect`, `nup`, `cutstack`, `steprepeat`,
  `signature`, `gang` and `cover`, plus `fit`, which says how many fit on a
  sheet and what the leftovers cost. `run` imposes a stored job file.
- Everything in PDF points. Sizes accept mm, cm, in, pt and pc.
- Press profiles, or a press of your own given by sheet, border and gripper
  edge.
- Creep per leaf, bindery limits, signature folding, folded sections for
  perfect binding, and several copies of a bound job on one sheet.
- Cut, fold and registration marks, a colour bar, a cutter path on an ISO 19593
  Cutting layer, a control strip, and a slug line set in the bundled typeface,
  subset and embedded.
- PDF/X OutputIntent and conformance keys carried through to the press file.
- `--dry-run` describes the job that would run, without writing it.
- Job files with the same fields as the command. A job file with no source is
  a watched folder's policy.

### Refusing rather than guessing

- Mixed page sizes, orientations and offsets are refused, and the page is
  named.
- A page with no TrimBox is refused. `--trim-from mediabox` opts in to using
  the MediaBox. `--expect-size` refuses work that is not the finished size a
  folder is for.
- If QPDF had to rebuild the page count, the file is refused rather than
  imposed short. `--damaged recover` opts in to imposing it anyway.

### Running unattended

- Exit statuses a watcher can route on: `0` done, `1` the job, `2` the
  arguments, `3` the source, `4` the destination.
- The press file appears whole or not at all, and nothing is overwritten
  unless asked. A run stopped by SIGTERM or Ctrl-C leaves no temporary file
  behind.
- Reference watchers for Linux (inotify) and macOS (fswatch), a systemd
  template and a launchd plist, shipped with the package. `impose-hotfolder`
  hands them out.
- A watched folder's `policy.conf` sets a schema, options and
  `LOG_FORMAT=json`. Each folder has one watcher and one outbox, and both are
  enforced.
- Files are filed in `done/`, `rejected/` or `failed/` by exit status, with
  impose's sentence beside each one.
- A restart sweeps up what is left in `in/` and `work/`.

### Requirements

- Python 3.10 to 3.14, and pikepdf 9 or later, the only runtime dependency.
