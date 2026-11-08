# How we run impose in this shop

The operating procedure for the folders: what they are called, what goes in a
policy and what is left alone, what a status means at seven in the morning,
and how to add a folder.

This page is what you do. [README.md](README.md) is why — [Running from a
watched folder](README.md#running-from-a-watched-folder) has the measurements
behind every refusal named here, and [A job the shop can
store](README.md#a-job-the-shop-can-store) has the full list of job keys.
Nothing on this page is enforced by impose: it is this shop's convention. The
one part a machine cares about is the folder's name, which the unit file turns
into the service's.

## One folder, one schema, one policy

A folder's options are statements about what arrives in *that* folder.
`--expect-size A4` is one, and a folder that takes two finished sizes cannot
make it. Two sizes is two folders, and folders are cheap: a directory, a
four-line policy, and a `systemctl enable`.

So: nothing is ever imposed by hand into a watched folder's `out/`, and no
folder is ever taught a second schema. If a job does not fit a folder we have,
it gets one — see [Adding a folder](#adding-a-folder).

## What the folders are called

`<finished size>-<schema>`, in lowercase letters, digits and hyphens, with a
third part when we do the same schema two ways:

```
a4-nup   a6-saddle   a5-perfect   card-steprepeat   a5-perfect-uncoated
```

The name is not decoration. It becomes the service, so it is the name in every
start, stop and log line:

| | |
|---|---|
| the folder, on Linux  | `/srv/impose/a4-nup` |
| the folder, on macOS | `/Users/Shared/impose/a4-nup` |
| the unit | `systemctl restart impose-folder@a4-nup` |
| the launchd label | `impose-folder.a4-nup` |
| the journal | `journalctl -fu impose-folder@a4-nup`, tagged `impose-a4-nup` |

Keep to those characters. A systemd instance name takes letters, digits and
hyphens literally; a space or a slash has to go through `systemd-escape`
first, and a name nobody can type is a folder nobody restarts. That part is
from the systemd documentation rather than measured here — see the caveat in
[One folder, one service](README.md#one-folder-one-service).

Inside the folder you write one file. The watcher makes the rest on its first
start:

| directory | what it holds |
|---|---|
| `policy.conf` | what this folder is for. The only file you write |
| `in/` | the inbox. The only directory anything outside this folder writes to |
| `work/` | a claimed file, for exactly as long as impose is reading it |
| `out/` | press files. Outside the watch path, which is the point |
| `proof/` | proofs, if the policy asks for them. Never in `out/` |
| `done/` | the artwork, imposed |
| `rejected/` | the artwork, turned away: the file or the job |
| `failed/` | the artwork, not imposed: the environment |
| `.watcher.lock/` | held by the one watcher working this folder |

No file is ever in two of them, and which of the last three a file is in *is*
the answer to what happened to it. A file lands beside a `book.pdf.txt` holding
what impose said about it, so `rejected/` answers its own question without
anybody opening a log.

## What goes where: policy, ticket, default

Three places a setting can live, and the choice is not a matter of taste.

**`policy.conf`, and nowhere else: the three per-run options.** `--trim-from`,
`--damaged` and `--overwrite` are judgements somebody makes about a file, and
a job file is forbidden to carry them. Put them in `OPTIONS`, which is where
somebody chose them for this folder:

```
SCHEMA=nup
OPTIONS=--up 1x2 --trim-from mediabox --expect-size A4
PROOF=proof
```

A job file that names one is refused, and says which:

```console
$ impose run a4-nup.json minutes.pdf -o out/minutes.pdf
impose: a4-nup.json has 'trim_from', which is not a field of a job.
```

`OPTIONS` reaches impose split on whitespace, so an option whose value has a
space in it wants the ticket instead.

**The job ticket: everything the bindery told us, and anything too long for a
line.** `JOB=` in the policy, a JSON file beside it. What belongs there:

- `expect_size` — **in every folder, one way or the other**: `--expect-size`
  in `OPTIONS` where the policy is a schema and a line, `expect_size` in the
  ticket where it is a file. It is the only check a job carries, and it is what
  makes `--trim-from mediabox` safe to stand: stored,
  `trim_from` would mean *assume a finished size for every file this folder is
  ever handed*, where `expect_size` means *refuse any file that is not this
  size*. One of those stops being checked; the other is the check.
- `press`, `sheet` — only when the folder is not for the house default.
- `paper_caliper`, `section_pages`, `grind`, `lap`, `hinge`, `cover_caliper` —
  bindery figures. They come from the bindery, never from the file.
- `gutters`, `marks` — only where the knife or the cutter wants something the
  default does not give.

**Everything else: left alone.** These are what a run decides when nobody asks
it to decide anything, and a folder that writes them down has frozen them at
today's value for good:

| key | default |
|---|---|
| `press` | `indigo-5000` |
| `bleed` | 2 mm (5.669 pt) |
| `marks` | registration colour, 2 mm offset, 3 mm long, 0.25 pt wide |
| `page` | `imageable` |
| `lay` | `center` |
| `orientation` | `auto` |
| `fold` | `auto` |
| `max_nested_sheets` | 15 |
| `paper_caliper`, `grind`, `lap` | 0 |
| `registration`, `colour_bar`, `cut`, `slug` | off |
| `cut_name` | `CutContour` |
| `slug_size` | 8 pt |

**Write the ticket by hand. Do not `--record` it into a folder.** `--record`
writes the job it just ran *in full*: for the A4 n-up policy above, 24 keys,
defaults and all. That is the right tool for finding out what a run actually
decided, and the wrong file to leave in a folder, because every default it
froze stops following impose. Written by hand the same policy is four keys —

```json
{
  "version": 1,
  "schema": "nup",
  "up": "1x2",
  "expect_size": "210mmx297mm"
}
```

— and imposes the same sheets. Measured on an 8-page A4 export: both give
`n-up: 8 pages onto 2 sheet(s) at 2 up (1 × 2 turned), page 310 × 450 mm on
indigo-5000; finished page 210 × 297 mm`, and the two sheets carry the same
forty operators each, differing only in the generated names of the resources
they place.

`--record` does say what it is leaving out, which is worth reading once:

```console
$ impose nup minutes.pdf -o out/rec.pdf --up 1x2 --trim-from mediabox \
    --expect-size A4 --record a4-nup.json -q
impose: warning: --trim-from mediabox applies to this run only and is not in
a4-nup.json. That job will refuse a page with no TrimBox, as any stored job
does.
```

## What the exit codes mean in practice

The status is the whole of what the watcher knows, and it is what decides the
bucket. There are five, and the split is about who fixes it:

| exit | bucket | whose problem | what you do |
|---|---|---|---|
| `0` | `done/` | nobody's | nothing |
| `1` | `rejected/` | the way the job is described, or artwork for another job | read the `.txt`, send the file back |
| `2` | — | the policy | the watcher refuses to start; see below |
| `3` | `rejected/` | the file: missing, unreadable, still copying, no pages | ask for the file again |
| `4` | `failed/` | a shelf somebody has to clear | clear it, move the file back to `in/` |

Only `4` is worth running again unchanged. Measured, all five, on the same
folder:

```console
$ impose nup minutes.pdf -o out/minutes.pdf --up 1x2 --trim-from mediabox --expect-size A4
impose: warning: No TrimBox on all 8 pages: the finished size 210 × 297 mm was
taken from the MediaBox, as this run asked. Check it is the finished page and
not the sheet the artwork was drawn on, which carries whatever bleed and marks
came with it.
n-up: 8 pages onto 2 sheet(s) at 2 up (1 × 2 turned), page 310 × 450 mm on indigo-5000; finished page 210 × 297 mm
wrote out/minutes.pdf
proof proof/minutes.pdf                                                        # 0

$ impose nup flattened.pdf -o out/flattened.pdf --up 1x2 --trim-from mediabox --expect-size A4
impose: Page 1 is 216 × 303 mm taken from its MediaBox, and this run expects
210 × 297 mm. Either this is not artwork for that job, or the size this run was
told to expect is wrong.                                                       # 1

$ impose nup minutes.pdf -o out/x.pdf --up 1x2 --expect-size A$
impose nup: error: argument --expect-size: Cannot read 'A$' as a paper size.
Use a name such as A4 or SRA3, or WIDTHxHEIGHT such as 320mmx450mm.            # 2

$ impose nup missing.pdf -o out/missing.pdf --up 1x2 --expect-size A4
impose: No such file: missing.pdf                                              # 3

$ impose nup minutes.pdf -o out/minutes.pdf --up 1x2 --trim-from mediabox --expect-size A4
impose: out/minutes.pdf is already there, and that press file is not replaced
without being asked: the file now at that name may be the one already on the
press. Write to another name, or ask for it to be overwritten.                 # 4
```

Three more statuses a folder produces, none of which is impose deciding
anything:

- **`2` never reaches a file.** It is the watcher refusing to start, and the
  only status a refusal uses, which is why the unit carries
  `RestartPreventExitStatus=2`: a policy that is wrong now is wrong in five
  seconds. Read the sentence at the top of `journalctl -u impose-folder@NAME`.
- **`127` is `impose` not being on the service's `PATH`.** This is the
  commonest way a folder fails, because systemd and launchd each hand a job a
  `PATH` of their own, and the folder works perfectly from your terminal.
  The startup check turns it into one sentence at boot instead of a `failed/`
  bucket holding a copy of everything the folder was ever sent.
- **`143` and `130` are a stop**, SIGTERM and Ctrl-C, `128 +` the signal.
  They go to `failed/`, which is right: nothing was wrong with the file.

A warning is not a status. A book too thick to staple, a colour bar left off,
a MediaBox taken as the finished size — all of those go to the journal and the
file still lands in `done/`. `--expect-size` is how a folder turns the ones
that matter into refusals, since there is nobody at the terminal to read a
warning.

## The morning check

```bash
systemctl status 'impose-folder@*'                      # all of them, at once
ls /srv/impose/*/failed /srv/impose/*/rejected          # anything to answer for
journalctl -u impose-folder@a4-nup --since yesterday
```

What each thing you find means:

- **A file in `work/` and the service running.** Normal: that is a file being
  imposed. The same file ten minutes later is not — it was imposed but could
  not be filed, which is a full disk or a bucket somebody chmodded. The
  sentence is in the journal, and the next restart sweeps the file up.
- **A file in `rejected/`.** Read `book.pdf.txt` beside it; that is what
  impose said. Send the file back with that sentence. Do not resend it
  unchanged: a `1` or a `3` is not going to come out differently.
- **A file in `failed/`.** The environment. Clear whatever it names, then
  `mv failed/book.pdf in/` — and `rm failed/book.pdf.txt` with it, or
  yesterday's reason sits in the bucket after the file has gone.
- **Files in `in/` and the service up.** The event source has gone away and
  the loop is reading nothing. `systemctl restart impose-folder@NAME`; the
  sweep takes everything already sitting there, which is exactly what the
  sweep is for.
- **A resend of a name already in `out/`.** Exit `4`, by design. Move the old
  press file aside, or put `--overwrite` in that folder's `OPTIONS` if the
  folder is one where the latest file always wins.

## Adding a folder

Seven steps. Every transcript below was measured on a real folder, bar the
`systemctl` lines in step 7 — there is no systemd on the machine this was
written on. `impose` throughout is the one on the service's `PATH`, not the one
on yours, and `impose-watch` is whichever of the two watcher scripts suits the
platform, installed under that name. One copy of the watcher serves every
folder, and installing it is a thing you do once per machine rather than once
per folder:

```bash
sudo install -m 755 tools/watch-inotify.sh /usr/local/libexec/impose-watch  # Linux
sudo install -m 755 tools/watch-fswatch.sh /usr/local/libexec/impose-watch  # macOS
```

**1. Settle the grid before the folder exists.** `impose fit` answers with
what fits and what the leftovers cost:

```console
$ impose fit 90mmx55mm -n 500
90 × 55 mm on indigo-5000, imageable 310 × 450 mm
  21 up, 3 × 7 upright, form 278 × 409 mm  ->  24 sheet(s), 4 wasted   <- run this
  20 up, 5 × 4 turned, form 291 × 372 mm  ->  25 sheet(s), 0 wasted

  4 surplus piece(s) are imaged on the last sheet and discarded, which is ink spent on nothing. The sheets are already being run, so raising the order to 504 costs no more press time.
```

**2. Impose one real file by hand**, with the exact options the folder will
use, and look at the sheets. This is the only step where somebody checks the
imposition with their eyes, and it is cheaper here than after a folder has
run a week.

**3. Make the directory and start the watcher once.** It writes the policy and
stops, because the alternative is guessing, and a guess here is somebody's
work imposed to a policy nobody chose:

```console
$ mkdir /srv/impose/a6-saddle
$ impose-watch /srv/impose/a6-saddle
impose-watch: wrote /srv/impose/a6-saddle/policy.conf. Say what this folder is
for, then start it again.
```

**4. Say what the folder is for.** The commented file it just wrote lists every
key. Two forms, and both is a mistake rather than a merge:

```
SCHEMA=saddle
OPTIONS=--expect-size A6 --paper-caliper 0.1mm
PROOF=proof
```

```
JOB=a6-saddle.json
OPTIONS=--trim-from mediabox
```

Set `OUT` to the RIP's own hot folder if there is one, and nothing has to copy
anything afterwards. Leave `PROOF` out and the folder makes no proofs.

**5. Start it by hand again and read the refusal, if there is one.** Every
policy problem is caught before a file is touched, and the policy is *tried*
once against a filename that is not there — so what comes back is the sentence
impose itself would have given. Three of them, with the usage block argparse
prints ahead of the first one left out:

```console
$ impose-watch /srv/impose/a6-saddle            # OPTIONS=--expect-size A5x
impose-watch: /srv/impose/a6-saddle/policy.conf does not describe a run this
impose can make (exit 2):
impose saddle: error: argument --expect-size: Cannot read 'A5x' as a paper
size. Use a name such as A4 or SRA3, or WIDTHxHEIGHT such as 320mmx450mm.

$ impose-watch /srv/impose/a6-saddle            # SHEET=SRA3
impose-watch: /srv/impose/a6-saddle/policy.conf: SHEET is not a key of a policy.
Known: SCHEMA, JOB, OPTIONS, OUT, PROOF.

$ impose-watch /srv/impose/a6-saddle            # SCHEMA and JOB both
impose-watch: /srv/impose/a6-saddle/policy.conf says both SCHEMA (saddle) and
JOB (a6-saddle.json). One of them is the policy; pick which.
```

**6. Drop a sample in `in/` and start it one more time.** The sweep runs before
the first event, so a folder can be tested without anything arriving — two
files, one good and one that is artwork for another job:

```console
$ impose-watch /srv/impose/a6-saddle
minutes.pdf: rejected (1)
novel.pdf: done (0)
```

```
a6-saddle/
├── policy.conf
├── in/
├── work/
├── out/novel.pdf
├── proof/novel.pdf
├── done/novel.pdf, novel.pdf.txt
├── rejected/minutes.pdf, minutes.pdf.txt
└── failed/
```

Read `rejected/minutes.pdf.txt`. If it says what you expect it to say about
that file, the folder is right.

**7. Install the service.** One per folder, enabled and stopped without
touching any other:

```bash
sudo install -m 644 tools/systemd/impose-folder@.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now impose-folder@a6-saddle
systemd-analyze verify impose-folder@a6-saddle.service
journalctl -fu impose-folder@a6-saddle
```

If the folder's `OUT` or `PROOF` point outside the folder, add them to
`ReadWritePaths` in the unit first — the service runs with a read-only
filesystem apart from what it is given, so every file would fail at exit `4`
with a permission error naming the output directory, which is the one place
the fix is not.

On macOS it is one plist per folder, copied from
`tools/launchd/impose-folder.plist` with its `Label` and its folder changed:

```bash
cp tools/launchd/impose-folder.plist \
   ~/Library/LaunchAgents/impose-folder.a6-saddle.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/impose-folder.a6-saddle.plist
launchctl bootout gui/$(id -u)/impose-folder.a6-saddle
```

launchd has no `RestartPreventExitStatus`, so a folder whose policy is wrong
restarts every `ThrottleInterval` and writes its sentence to the log each
time. Loud rather than silent, which is the best available there.

## Where the reasoning is

- [Running from a watched folder](README.md#running-from-a-watched-folder) —
  every refusal on this page, with what it was measured against.
- [A job the shop can store](README.md#a-job-the-shop-can-store) — every key a
  ticket may carry.
- [Exit codes](README.md#exit-codes) — the full table, and why the numbers come
  from the kind of failure and never from the message.
- [One folder, one service](README.md#one-folder-one-service) — what is in the
  unit and the plist, and the one caveat about the unit.
- [SECURITY.md](SECURITY.md) — what a folder open to people outside the shop
  needs, which is more than this page asks for.
