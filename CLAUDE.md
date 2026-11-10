# Working in this repository

[CONTRIBUTING.md](CONTRIBUTING.md) is the house style and it applies in full —
one dependency, everything in PDF points, unittest and not pytest, pylint
silent rather than merely 10.00/10, measure every figure you quote. Read it
before changing anything. This file holds only what is specific to working
here with an assistant.

## Commit every significant change, as it lands

**One commit per significant addition or change, made when that change is
finished.** Do not carry three changes to the end of a session and commit them
together, and do not leave finished work uncommitted.

The reason is the same one `CONTRIBUTING.md` gives for "one change per commit":
this project's `git log` is where its reasoning lives. A commit body says what
defect it closed, what was measured, and what alternative was rejected — a
commit carrying three unrelated changes cannot say that, and the measurement
that justified one of them becomes unfindable later.

What counts as significant: a behaviour change, a new refusal, a new module, a
new test file, a new top-level document, a rewritten README section. What does
not: fixing a typo in the line you just wrote, or a formatting pass black would
have made anyway — those ride along with the change they belong to.

Before each commit, the gate:

```bash
./.venv/bin/python -m unittest discover -s tests -t .
./.venv/bin/python -m pylint impose tests
./.venv/bin/python -m black --check . && ./.venv/bin/python -m isort --check .
shellcheck tools/*.sh tests/shell/*.sh
bats tests/shell
```

shellcheck has to be silent too, same as pylint, and the scripts in `tools/`
are the ones a shop copies into production. `bats tests/shell` starts a
watcher on a temporary folder and drops files into it; it needs bats and an
installed `impose`, and it takes seven seconds, which is most of the gate.

Subject line a declarative sentence ending in a period; body in prose for the
why. Push when the change is complete, and report CI as pass or fail.

## Not published

Nothing is on PyPI, and publishing is not the current goal — the project is
still being hardened. `pip install impose-pdf` does not work; an install is
from source. Do not add release or publishing steps unasked.
