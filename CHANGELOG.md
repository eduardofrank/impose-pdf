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

Nothing yet.

## 0.1.0 — 2026-11-19

The first version given a number and a tag. Everything before it is one
version, and this is what it does.

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
- If QPDF had to rebuild the page count, or drop something from the page
  tree, the file is refused rather than imposed short. `--damaged recover`
  opts in to imposing it anyway.
- A page with no MediaBox, or one that is not four numbers, is refused. It is
  never imposed as the US Letter page QPDF puts in its place.
- A mark colour other than `registration` or `black` is refused, in a job
  file as on the command line.

### Running unattended

- Exit statuses a watcher can route on: `0` done, `1` the job, `2` the
  arguments, `3` the source, `4` the destination, `70` a fault in impose
  itself, with its traceback.
- The press file appears whole or not at all, and nothing is overwritten
  unless asked. A run stopped by SIGTERM or Ctrl-C leaves no temporary file
  behind.
- Reference watchers for Linux (inotify) and macOS (fswatch), a systemd
  template and a launchd plist, shipped with the package. `impose-hotfolder`
  hands them out.
- A watched folder's `policy.conf` sets a schema, options, a `TIMEOUT` and
  `LOG_FORMAT=json`. Each folder has one watcher and one outbox, and both are
  enforced.
- Files are filed in `done/`, `rejected/` or `failed/` by exit status, with
  impose's sentence beside each one. A resend goes beside the earlier file,
  never over it.
- A restart sweeps up what is left in `in/` and `work/`. On Linux, events the
  kernel dropped send the watcher back through `in/`.

### Requirements

- Python 3.10 to 3.14, and pikepdf 10 or later, the only runtime dependency.
- Type information ships with the package (`py.typed`).
