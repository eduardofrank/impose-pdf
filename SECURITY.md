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

## Not vulnerabilities

- **Resource use proportional to the input.** A 20000-page source takes
  20000 pages' worth of memory and time; both documents genuinely have to be
  open at once. A folder exposed to untrusted submitters wants a size limit and
  a `ulimit` in front of it, which is the deployment's job.
- **A refusal.** Being turned away is the design, including the known false
  positive where a complete file with a stale `startxref` is refused as damaged.
  `--damaged recover` is the opt-in.
- **Anything in `tools/`.** Worked examples to adapt, not supported code, and
  not linted. If you adapt a watcher and it is wrong, that is worth an issue —
  but it is the example that is wrong, not a vulnerability in a shipped product.
- **A crash in QPDF reached through pikepdf** — report it upstream, and see
  below.

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
