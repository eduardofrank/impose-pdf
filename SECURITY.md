# Security

## Reporting a vulnerability

**Report privately, through GitHub:** [open a draft
advisory](https://github.com/eduardofrank/impose-pdf/security/advisories/new).
Reports there are visible only to you and the maintainer until an advisory is
published.

Please do not open a public issue for anything that looks exploitable. Everything
else — a crash on a file that ought to be refused, a confusing refusal, a wrong
measurement — is an ordinary [issue](https://github.com/eduardofrank/impose-pdf/issues)
and is more useful in the open.

Useful in a report, roughly in order:

1. What an attacker gets, and what they have to be able to do first.
2. The file, or a script that builds it. A PDF that reproduces it is the most
   useful thing you can attach, and a builder script is better still.
3. The command, or the library call, and the version — `impose --version`, plus
   `python -c "import pikepdf; print(pikepdf.__version__, pikepdf.__libqpdf_version__)"`.
4. Whether it reproduces with a current pikepdf, since most PDF parsing is not
   this project's code (see [Upstream](#upstream)).

One maintainer, so: an acknowledgement within about a week, and progress reported
as there is any. No bounty programme. Credit in the advisory unless you would
rather not be named.

## Supported versions

| version | supported |
|---|---|
| `main` | yes |
| 0.1.0 | unreleased — nothing published to PyPI yet |

There are no releases, so there is nothing to backport to. Fixes land on `main`.
Once there is a release this table will say which ones get fixes.

## What impose does, in security terms

It **parses PDFs it did not write** — which in a watched folder means files from
whoever can put a file in the folder — and it **writes files where it is told
to**. That is the surface. Everything else it deliberately does not do:

- **No network**, at import or at run time. Nothing in the package imports
  `socket`, `urllib` or anything like them.
- **No subprocesses, no shell.** No `subprocess`, `os.system`, `eval`, `exec`,
  `pickle` or `marshal` anywhere in `impose/`.
- **No rasterising.** The library never decodes an image or runs a content
  stream; it reads page boxes and copies page objects. `tools/check-artwork.py`
  does render, which is why it is a tool and not a module.
- **No environment, no config file, no cache.** Nothing read from `os.environ`,
  no dotfile, no state between runs. What a run does is what the arguments say.
- **No temporary directory.** Nothing is written to `/tmp`.
- **One font, and it ships in the wheel.** No system font lookup.

## What is meant to hold

If you can break one of these, it is a bug worth reporting even without a
demonstrated exploit:

**It writes only where it was told.** The output, the proof and `--record`, and
beside each of those one temporary in the same directory, which is how the file
arrives whole. For the two PDFs, pikepdf makes a second temporary of its own
there as well. Nothing else, nowhere else.

**A symlink at the destination is replaced, not followed.** The press file is
written to a temporary and moved on with `os.replace`, which replaces the link
itself. Verified: with `out/sheet.pdf` a symlink to another file, the other file
was untouched and `out/sheet.pdf` became a regular PDF.

**The destination is never seen half written**, and a run that fails or is
killed leaves whatever was there before untouched, and no temporary behind. See
`## Running from a watched folder` in the README.

**The input is never the output.** A run that would impose a file over the
artwork it was made from is refused, including when the document was handed in
already open.

**Nothing from a PDF becomes code or a path.** Page boxes are numbers,
`/OutputIntent` keys are copied as objects. No name, string or stream out of a
source file is used to build a filename or a command.

**A malformed PDF is a status and a sentence, never a traceback.** Exit `3` for
a file that cannot be used, `1` for a job that cannot be imposed; see the
exit-code table in the README. Spot-checked on empty, truncated, null-stuffed
and garbage files: all exit `3` or `1`, none print a stack trace.

That was a spot check, and a search then found what it had missed. A valid
six-page file damaged 676 ways — cut short, a piece taken out, bytes changed
in place — left as a stack trace 38 times, from two places: a page box whose
entries were not numbers, and a content stream that would not decode when its
page was copied onto a sheet. Both are exit `3` and a sentence naming the
page now, and the search is kept in `tests/test_malformed.py` with a fixed
seed, so the next such place is a failing test. What holds is that sentence
and no more than it: 6000 further mutations found nothing, which is not the
same as there being nothing.

## Not vulnerabilities

- **Resource use proportional to the input.** A 20000-page source takes
  20000 pages' worth of memory and time; both documents genuinely have to be
  open at once. A folder exposed to untrusted submitters wants a size limit
  and a ceiling in front of it, which is the deployment's job — see [a folder
  anybody can drop into](#a-folder-anybody-can-drop-into) for the measured
  figures to pick one from.
- **A refusal.** Being turned away is the design, including the known false
  positive where a complete file with a stale `startxref` is refused as damaged.
  `--damaged recover` is the opt-in.
- **The hot-folder files in `impose/hotfolder/`, and anything in `tools/`.**
  Worked examples to adapt, not supported code. The watchers ship with the
  package so that an install has them, and they are linted — shellcheck in the
  gate, `systemd-analyze verify` on the unit in CI — but a folder you build
  from one of them is yours. If an example is wrong, that is worth an issue;
  it is the example that is wrong, not a vulnerability in a shipped product.
- **A crash in QPDF reached through pikepdf** — report it upstream, and see
  below.

## A folder anybody can drop into

FTP, WebDAV, a share a customer mounts: an inbox whose submitters you do not
know is a different folder from one your own prepress fills, and four things
have to change. Everything in the section above still applies — this is what
it does not cover.

**A user per folder, rather than one user for all of them.** The shipped unit
says `User=impose` for every instance, which is right while folders differ
only in what they impose. It is wrong the moment one of them takes files from
outside, because that user can read every other folder's inbox, write every
other folder's `out/`, and read every `policy.conf` on the machine: a
submitter who finds a way out of one folder is in all of them. Give each
exposed folder a user of its own, which the instance name already gives a
spelling for:

```ini
User=impose-%i
Group=impose-%i
```

with a `useradd --system impose-a4-nup` per folder — or set it per instance in
a drop-in, which leaves the shipped template alone and is also where the two
ceilings below belong:

```ini
# /etc/systemd/system/impose-folder@a4-nup.service.d/exposed.conf
[Service]
User=impose-a4-nup
Group=impose-a4-nup
MemoryMax=2G
TasksMax=32
```

Both forms pass `systemd-analyze verify`, measured, and verify reads a
drop-in as well as the unit — a misspelled directive in one is reported with
the drop-in's own path, so the check CI runs over the template works over
your overrides too. `ReadWritePaths=/srv/impose/%i` then means what it looks
like it means, which it does not while one user owns every folder.

What the submitting service needs is write access to `in/` and nothing else.
The policy, `work/`, `out/`, `proof/` and the three buckets belong to the
folder's own user. `DynamicUser=yes` hands out a per-instance user without the
`useradd` and is the wrong tool here: the uid changes between starts, and
something outside the service has to keep being able to write into `in/`
across one.

**A memory ceiling, picked from the largest job the folder is meant to take.**
Both documents are open at once, so what it costs tracks the page count:

| pages | peak RSS | wall clock |
|---|---|---|
| 100 | 43 MB | 0.1 s |
| 1000 | 59 MB | 0.3 s |
| 4000 | 114 MB | 1.3 s |
| 20000 | 412 MB | 19 s |

Measured with `/usr/bin/time` on Ubuntu 26.10, Python 3.14.8, pikepdf 10.18.1
over QPDF 12.4.2, imposing a synthetic book of text-only pages at `--up 2x2`.
The same book on macOS 15.8 (pikepdf 10.12.0, QPDF 12.3.2) peaked at 352 MB
for the 20000-page case, some 15% lower, so take a ceiling with headroom
rather than one platform's number. A source whose pages carry large images
costs more again: page objects are copied whole, without being decoded.

The commented `MemoryMax=2G` in the template is generous against that table,
which is the point — the ceiling is not for the jobs you expect. What happens
when it is reached, measured at 160 MiB with swap off and a 20000-page source:
`SIGKILL`, exit `137`, no press file. `137` is not `0`, `1` or `3`, so the
reference watchers file the artwork in `failed/`, the bucket that means fix
the environment and send it again, which is the right answer. One honest
caveat: that run was killed while the pages were being copied and left no
temporary, but `SIGKILL` cannot be caught, so a kill during the write *can*
leave a `.book.pdf.impose-1234.tmp` in the output directory. It is a dotfile,
so a `*.pdf` watcher downstream will not pick it up, and nothing sweeps it.

**A task ceiling, which is a fork bomb's ceiling and nothing else.** Measured
on a folder while it imposed a file: three tasks idle — the watcher's shell,
`inotifywait`, and the shell reading the pipe — and five at the busiest
sample, adding a command-substitution subshell and `impose` itself, every one
of them single-threaded. `TasksMax=32` is therefore room to spare rather than
a tuning knob. It counts threads rather than processes, and anything under
about six stops the folder working, so it is a number to set and leave: what
it is there for is something in the chain starting to fork, which nothing in
impose does.

**A policy with no `--damaged recover` in it.** That option tells impose to go
ahead with a file whose cross-reference table had to be rebuilt to read at
all — and that table is what states the page count, so a file that is still
arriving reads short. `refuse` is the default and is what an exposed folder
keeps.

Measured, the same file both ways: a 16-page book truncated to 3002 bytes, as
an upload cut off part way through leaves it. With the default policy the
journal says `book.pdf: rejected (3)` and the artwork is in `rejected/` with
the refusal beside it. With `OPTIONS=--up 2x2 --damaged recover` the same file
was imposed as **11 pages**, the press file was written, the artwork was filed
in `done/`, and the journal line was `book.pdf: done (0)` — the warning that
the count was rebuilt is in the sidecar and in the journal message, not in the
status, so a monitor that reads statuses sees a clean run.

For a folder your own prepress fills that trade is reasonable: `recover` is
the answer to a producer that writes a stale `startxref`, and somebody who
knows the job checks the count. For external drop-off it hands the page count
to whoever cut the upload off. FTP and WebDAV make it worse than a copy over
SMB, because both ordinarily write in place: the inbox sees it while still
growing, the watcher's own guard is the first line of defence — inotify's
`close_write`, fswatch's settle — the damaged-file refusal is the second, and
`recover` is how you remove the second.

In a policy it can only arrive through `OPTIONS`, since `--damaged` is one of
the three options a job file may not carry, so the audit is one line:

```bash
grep -l damaged /srv/impose/*/policy.conf   # nothing, on an exposed folder
```

**None of this is impose's to enforce.** The unit and the policy are the
operator's files; the watchers check that a policy parses and that the run it
describes is one impose can make, not that a folder is safely exposed. The
`grep` above, `systemd-analyze verify` on the drop-in, and `systemctl show -p
User -p MemoryMax -p TasksMax impose-folder@a4-nup` are what say whether a
folder got what this section asks for.

**Only an ordinary file is taken, and this one the watchers do for you.** A
submitter who can make a symbolic link — SFTP can — used to be able to have
the folder impose whatever the link pointed at: any PDF the service user can
read, in any folder on the machine, written into this folder's `out/`. A
per-folder user narrows what that reaches; it does not close it. The
reference watchers now refuse a link or a pipe under a PDF's name, before
the claim and again after it. If you write your own watcher, write that
check, and write it on what you claimed rather than on what you saw.

## A soft spot worth naming

`impose.font.load()` takes an optional path, and parsing a TrueType file is
this project's own code rather than a library's. It is **not hardened against a
hostile font**: a malformed file raises `struct.error` rather than the usual
`ImposeError`, and a font truncated to a third of its bytes is accepted rather
than refused.

Nothing reachable from the command line goes there — there is no font option,
and every call inside the package is `load()` with no argument, which reads the
bundled face. But a library caller can pass a path, and should not point it at a
font from somewhere it does not trust. Hardening this is on the list.

## Upstream

Reading and writing PDF is [pikepdf](https://github.com/pikepdf/pikepdf) over
[QPDF](https://github.com/qpdf/qpdf), which is C++. A memory-safety bug reached
by handing impose a crafted PDF is almost certainly theirs, and they are the
people who can fix it:

- pikepdf — https://github.com/pikepdf/pikepdf/security
- QPDF — https://github.com/qpdf/qpdf/security

Tell us as well, though, especially if it is *how impose uses them* that exposes
it — the damaged-file refusal exists because of what QPDF's recovery does to a
page count, and that class of thing is ours to get right.

Keeping pikepdf current is the single most useful thing a deployment does. The
floor is `pikepdf>=9`; there is no upper pin, so `pip install -U pikepdf` is
always available to you.

## Running a watched folder with some care

The folder is the real attack surface, because it accepts a file from whoever
can write to its inbox. The reference scripts are written to be read, so read
them; and:

- Give the inbox the narrowest write access that lets work arrive, and do not
  make it world-writable.
- `policy.conf` is the command the folder runs on everything it is sent, so
  only the operator writes it. The reference watchers refuse to start on one
  that is world-writable, and they parse it themselves rather than letting a
  shell source it, so a value in it cannot become a command. Keep the folder
  root as closed as the policy: `in/` is the only part that wants to be open.
- Run the watcher as a user with nothing else to lose — it needs to read the
  inbox and write the output directory, and that is all. Not root.
- Put the output directory somewhere only that user writes. The temporary is
  created `0644`, so a shared output directory means a readable temporary. Two
  *folders* sharing one is worse than readable: the same filename arriving in
  both is one press file, and two runs racing for that name both report
  success with one imposition left. The reference watchers claim `OUT` and
  `PROOF` at startup and refuse a directory another folder already holds, so
  give each folder its own — a directory under the shared one if a RIP reads
  that. Nothing claims it against a writer that is not one of these scripts.
- Cap the input size before impose sees it, and put `ulimit`, `systemd`'s
  `MemoryMax`, or both in front of a folder exposed to anybody you do not know.
- Keep `--overwrite` out of the invocation, which is the default. A resend then
  cannot replace a press file that may already be on the press.
