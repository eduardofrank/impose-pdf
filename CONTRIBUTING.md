# Contributing

Thanks for looking. This file is the house style — the things that are
particular to this project and that a reviewer would otherwise have to tell you
one at a time.

Read [README.md](README.md) first, at least `## Design` and `## Development`.
This file does not repeat it.

## Setting up

```bash
git clone https://github.com/eduardofrank/impose-pdf.git
cd impose-pdf
python -m venv .venv && ./.venv/bin/pip install -e ".[dev]"
```

Use `./.venv/bin/python` for everything. A system `python` will not have
pikepdf, and the error it gives is not the one you will expect.

Five commands, and they are the whole gate:

```bash
./.venv/bin/python -m unittest discover -s tests -t .
./.venv/bin/python -m pylint impose tests
./.venv/bin/python -m black --check . && ./.venv/bin/python -m isort --check .
shellcheck impose/hotfolder/*.sh tests/shell/*.sh
bats tests/shell
```

CI runs exactly those, on Python 3.10 through 3.14, in a job per Python and
two more: `lint`, and `watched folder` for the three checks that are about
what a shop copies into production — shellcheck on the watchers,
`systemd-analyze verify` on `impose/hotfolder/impose-folder@.service`, and bats
on a temporary folder with the real `inotifywait` under it. Only the unit
check is CI-only; there is no systemd on a macOS laptop to run it with. It
fails on any line of the report naming the unit, rather than on the exit
status, because systemd reports a misspelled directive and then ignores it —
`Unknown key 'Restat'`, exit 0 — which is precisely the mistake worth
catching in a file nobody here can boot. The lines not naming it belong to
the host: verify reads the runner's own units on the way, and some of those
warn.

**pylint has to be silent, not merely 10.00/10.** The score rounds, so
10.00/10 is quite possible with a message still showing — pylint exits
nonzero for any message at all, which is what CI reads, and a message nobody
acts on is a message nobody reads.
`check-artwork.py` is deliberately outside pylint: it imports a renderer the
package will not depend on.

**shellcheck has to be silent as well**, and for a better reason than symmetry:
the watchers in `impose/hotfolder/` ship in the wheel and are what a shop
copies as the starting point for every hot folder it builds, so a defect in
one of them is a defect in somebody's production folder. It is not a Python package — `brew install shellcheck`, or
`apt install shellcheck` — and like the rest of the dev tools it is unpinned,
so CI may be running a release behind or ahead of yours.

Default severity, and **not** `--enable=all`. The optional checks want `[[ ]]`
over `[ ]`, braces round every variable reference, and a `|| true` on every
command substitution; the first two are a different house style from this one,
and the third contradicts what those scripts do on purpose — `message=$(impose
…) || status=$?` is how a watcher turns a failure into a bucket instead of
dying on it.

At default severity the watchers raised two findings, the same two in each
script, and the two went different ways. `set -- $OPTIONS` keeps its
unquoted expansion and carries a `# shellcheck disable=SC2086` with the reason
beside it, because the splitting is the point of the line and `set -f` is what
makes it safe; a `# shellcheck disable` earns its place exactly the way a
`# pylint: disable` does, narrowest form and a reason. The other was an
unquoted `done` as a bucket name, which shellcheck reads as the end of a loop
— quicker to quote than to explain, and quoted.

## One dependency, and it stays that way

The package imports `pikepdf` and the standard library. Nothing else, and a
change that adds a third-party import will be turned down however convenient
it is — see `## Licence` in the README for why it is pikepdf in particular.

Three consequences worth knowing before you plan a change:

- **No renderer.** The library never rasterises. `tools/check-artwork.py` does,
  which is exactly why it is a tool and not a module.
- **No system libraries.** `pip install` is the whole install, and the test
  suite needs nothing on the machine. Keep it that way.
- **No network, ever**, at import or at run time.

## Everything is PDF points

1 inch is 72 points, as in PDF user space. The origin is the bottom-left of the
sheet and y grows upward. Millimetres exist at the edges only — what an operator
types, and what a sentence prints — and `impose.units` is where they turn into
points. A bare number anywhere inside is points; if you find yourself wondering
which a variable holds, that is a naming bug, not a comment opportunity.

Geometry goes in `Size`, `Rect` and `Insets` from `impose.geometry` rather than
in tuples that happen to have two numbers in them.

## How tests are written here

`unittest`, and **not pytest** — there is no pytest in the project and adding it
is not a small change. Doctests are collected from every module automatically by
`tests/test_doctests.py`, so an example in a docstring is a test and has to run.

Four rules that are not obvious:

**Assert geometry and structure, never pixels.** An imposition is right or wrong
by where the trims land on the sheet. Nothing in the suite renders.

**Expected numbers come from the standard, not from the code.** A4 is written
`210 * MM` or checked against `595.2755905`, not against whatever
`units.paper("A4")` returns — otherwise the test says the code agrees with
itself. Literals from ISO 216 and ISO 217 are the point.

**Where two paths answer one question, assert they agree.** A signature folded
once must come out identical to the ordinary folded sheet; `impose fit` predicts
a grid that imposing then has to reach. Those checks catch what a single-path
test cannot, because the two were written from different starting points.

**For page order, assemble the book and read it.** `tests/booklet.py` turns the
pages of a nested set of sheets and asserts the result reads 1, 2, 3. A
page-order bug is invisible in a rendered sheet and obvious the moment the pages
are turned.

Fixtures live in `tests/support.py` — `make_pdf`, `make_office_pdf`,
`truncated_pdf`, `stale_startxref_pdf`. Build on those rather than writing bytes
in a test, and if you need a new *shape* of document, add a builder there and say
in its docstring which real-world producer emits that shape.

Name a test after the claim it makes, as a sentence:
`test_a_producer_s_rounding_is_not_a_different_size`, not `test_tolerance_2`.

## The shell tests

The watchers are tested in two places, and the split is deliberate.

`tests/test_unattended.py` runs them from Python with an event source that
exits immediately. That reaches every startup refusal and the sweep, costs
nothing, and skips by itself on a machine with no `/bin/bash` or no `impose`.
What it cannot reach is the loop at the bottom of the script, because a source
that exits never reports an event.

`tests/shell/watch-inotify.bats` reaches it, by doing what a shop does: start
the watcher on a folder, hand it a PDF while it is running, and read the
folder back afterwards. A file that arrives lands in `done/`, `rejected/` or
`failed/` by what impose did with it, the status that put it there is in the
log, and impose's sentence is in a `.txt` beside the file. Those are the
claims an operator relies on every morning and none of them were tested
before.

It is in bats rather than in more Python for one reason: driving a service is
most of the work — a process group of its own, a live event source, a signal
that a pipeline will actually notice — and in `subprocess` that plumbing reads
nothing like the shell it is testing. Here the test is the same language as
the thing under test.

**It is not part of the Python suite and does not change what that suite
needs.** `unittest discover` still wants nothing but the install. `bats
tests/shell` wants bats (`brew install bats-core`, or `apt install bats`) and
an `impose` it can run, and it skips the whole file rather than failing when
there is no impose to find. It is also slow by this project's standards — four
to five and a half seconds for seven tests, measured over four runs, because
waiting for an event source is wall-clock time and nothing makes it shorter.
The spread is `prove_watching` re-announcing a file in the tests that start
before their event source does.

Two things to know before adding a test there:

**inotify is a Linux interface, so most of the time the event source is a
stand-in.** `tests/shell/inotifywait-stand-in.sh` polls the inbox and prints
what appears. It copies the one behaviour of inotify the script depends on --
silence about files that were already there, which is the whole reason the
script sweeps at startup -- and it copies nothing else, `close_write` least of
all. The real `inotifywait` runs in CI's `watched folder` job, and that is the
only place it runs.

**Give a file a second chance in `prove_watching` and nowhere else.** Neither
event source says when it has started watching, so the tests hand over one
file of their own first and re-announce it until it comes back; everything
after that is read once, with no retry. Measured the other way round, with the
retry inside the wait that every test uses: deleting the call to `sweep` from
the watcher left every test passing, because the file put in the inbox before
startup was picked up by the retry's event instead. A test that cannot
fail is worse than no test, and that is what a generous retry buys.

## Measure what you claim

The strongest convention in this project. Every figure in the README, in a
docstring, or in a commit message is something that was run and read off —
"measured at every decile", "237 KB and 786 KB of 1.77 MB", "12.8 MB of
temporary files". None of them are estimates.

So: generate every console transcript from the built code and paste it. Do not
retype it from memory and do not tidy it. If you quote a number you did not
measure, that is the kind of thing review will catch and ask you to go and
measure, and it is faster to do it first.

## Failures are a class, a status and a sentence

- `ImposeError` — the job cannot be imposed as described. Exit `1`.
- `SourceError` — the file handed in cannot be trusted. Exit `3`.
- `DestinationError` — where it would be written refuses. Exit `4`.

Both of the latter subclass `ImposeError`, so an existing `except ImposeError`
keeps working. **Status is routed on exception class and never on message
text**, because the messages get reworded whenever a better sentence turns up
and something driving this unattended has to keep routing the same way.

Every failure is one sentence on stderr beginning `impose: `, never a traceback.
Write the sentence for the person who has to fix it: name the measurement, and
say what to do. Do not add a broad `except Exception` to make an unforeseen bug
into a confident sentence — a traceback for a real bug is correct, and the
watcher's `failed/` bucket exists for it.

## Judgements are per-run; policies can be stored

A job file (`--record`, `impose run`) may carry an option that *refuses*, and
may not carry one that *assumes*. `trim_from`, `damaged` and `overwrite` are in
`_PER_RUN` in `impose/ticket.py`: stored, they would mean "assume a size for
every file", "impose whatever survived the copy" and "replace yesterday's press
file without mentioning it" — each the thing its own refusal exists to prevent.
`expect_size` is storable because it refuses rather than assumes.

If you add an option, decide which it is and say why in the commit message. If
it is storable it needs a `_KEYS` entry, an `_options` entry, a `_plain` branch
for any non-JSON type, and a round-trip test. If it is per-run it needs to be
an option of `impose run` as well — a stored job is still run by somebody, and
a judgement nobody can make is not a judgement, it is a refusal.

## Style

Black at 88 columns, isort on the black profile. Both run over the whole tree
and neither is negotiable; let them format and do not fight them by hand.

Every file opens with:

```python
# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.
```

Docstrings say **why**, not what the signature already says. A module docstring
explains what problem the module exists for; a refusal's docstring explains the
failure it prevents and, where one was measured, what it cost. Comments earn
their place the same way — a comment restating the next line will be removed, a
comment recording why a tolerance is 0.25 mm and not 0.01 pt will not.

The dev tools are deliberately unpinned, so CI may be running a newer pylint
than you are, and a new release can count one more local variable in a
function that was passing. `pip install -U pylint` before you trust a clean
local run; the answer when a cap then bites is the next paragraph, not a
higher cap.

When pylint's line or complexity caps bite, **split rather than raise the cap**.
`tests/test_cli.py` became `tests/test_cli.py` plus `tests/test_unattended.py`
for this reason, and `impose/signals.py` came out of `impose/cli.py` for the
same one. The two raised caps in `pyproject.toml` each carry a paragraph saying
why; if you need a third, that paragraph is the hard part.

A `# pylint: disable` needs a reason beside it, and it should be the narrowest
one that works.

## Commits

A subject line that is a declarative sentence, ending in a period, saying what
the change does for whoever uses it:

> Refuse a page count the file did not state.
>
> Move the press file into place instead of growing it there.
>
> Let a folder say what size its work is supposed to be.

Not `fix: xref bug`, not `Add --expect-size`. If you cannot write that sentence,
the change probably does two things.

Then a body, in prose paragraphs, for **why** — the defect it closes, what was
measured, what alternative was rejected and on what grounds, and anything
surprising a future reader would otherwise rediscover. The bodies in
`git log` are long on purpose: they are where this project's reasoning lives.

One change per commit. A revert is its own commit.

## Pull requests

Branch off `main`, make CI green, and say in the description what you measured.
If the change touches the README, regenerate any transcript it affects.

A PR that is a question rather than a change is welcome — open it as an issue
and describe the job you are trying to impose. Several of the refusals in here
exist because a real file behaved badly, and that file is the useful part.

Anything that looks exploitable goes privately through
[SECURITY.md](SECURITY.md) instead, not into a public issue or PR.

## What is likely to be turned down

Not to discourage you — just so you do not spend a weekend on it:

- A new third-party dependency, as above.
- Anything that rasterises inside the library.
- Imposition the code cannot check: a schema whose output no test can assert
  without rendering it.
- An option whose stored form would quietly assume something about a file
  nobody has looked at.
- Catching broad exception types to turn a bug into a tidy sentence.
- Locking, retries or queueing inside `impose`. A watched folder's exclusion
  belongs in the watcher; see `## Running from a watched folder` in the README.

## Licence

By contributing you agree your work ships under the MIT licence in
[LICENSE](LICENSE).
