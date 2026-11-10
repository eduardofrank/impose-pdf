#!/usr/bin/env bats
# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.
#
# tools/watch-inotify.sh, driven the way a shop drives it: started on a
# folder, handed a PDF while it is running, and read back afterwards by what
# is in the folder. The claim under test is the one an operator makes every
# morning -- a file that arrives lands in `done/`, `rejected/` or `failed/`
# by what impose did with it, and the status that put it there is in the log.
#
# This is deliberately not the same test as tests/test_unattended.py, which
# runs the watchers with an event source that exits at once: that reaches
# every startup refusal and the sweep, and nothing else, because the loop at
# the bottom of the script never reads an event. Here the event source is
# live, so the path a running folder actually spends its life in -- event,
# claim, impose, bucket, log line -- is the path being measured. The two
# overlap in one test (a folder with no policy) and that one is cheap.
#
# It wants bats and an `impose` it can run:
#
#     brew install bats-core          # or apt install bats
#     bats tests/shell
#
# A missing impose is a skip, the same way the Python suite skips a watcher
# whose interpreter is not there. A missing bats is not something a bats file
# can say anything about; `bats tests/shell` is in the gate in CONTRIBUTING.md
# and in CI, which is where it gets noticed.
#
# Only the inotify watcher. watch-fswatch.sh differs in one place, and it is
# `settled()`, which waits for a file's size to hold still for three polls a
# second apart: a live test of it costs three seconds a file before impose
# starts, and fswatch is not on a Linux CI runner anyway. Its startup is
# covered in tests/test_unattended.py alongside this one's.

setup_file() {
    repo=$(cd "$BATS_TEST_DIRNAME/../.." && pwd)
    export WATCHER="$repo/tools/watch-inotify.sh"

    # The project's own venv first, because that is the install the rest of
    # the gate runs against; a system-wide impose otherwise.
    if [ -x "$repo/.venv/bin/impose" ]; then
        export IMPOSE="$repo/.venv/bin/impose"
        python=$repo/.venv/bin/python
    elif command -v impose >/dev/null 2>&1; then
        export IMPOSE="$(command -v impose)"
        python=$(command -v python3 || true)
        [ -n "$python" ] || skip "no python3 to build a fixture with"
    else
        skip "no impose: install the project, or put one on the PATH"
    fi

    # One fixture for the whole file, from the builders every other test here
    # uses: eight print-ready A6 pages with a TrimBox, bleed and a slug area.
    export ARTWORK="$BATS_FILE_TMPDIR/artwork.pdf"
    ( cd "$repo" && "$python" -c '
import sys
from tests.support import make_pdf
make_pdf(8).save(sys.argv[1])
' "$ARTWORK" )

    # inotify is a Linux interface, so on anything else the event source is
    # the stand-in beside this file. Said out loud, because which one ran is
    # the first thing to know about a failure here.
    if command -v inotifywait >/dev/null 2>&1; then
        export STAND_IN=
        echo "# event source: $(command -v inotifywait)" >&3
    else
        export STAND_IN="$BATS_TEST_DIRNAME/inotifywait-stand-in.sh"
        echo "# event source: the stand-in, as this machine has no inotify" >&3
    fi
}

setup() {
    root=$BATS_TEST_TMPDIR/folder
    log=$BATS_TEST_TMPDIR/log
    err=$BATS_TEST_TMPDIR/err
    mkdir -p "$root"

    # impose reaches the watcher the way it reaches a service: on the PATH,
    # and by the name the script calls it by.
    bin=$BATS_TEST_TMPDIR/bin
    mkdir -p "$bin"
    ln -s "$IMPOSE" "$bin/impose"
    if [ -n "${STAND_IN:-}" ]; then
        ln -s "$STAND_IN" "$bin/inotifywait"
    fi
    PATH=$bin:$PATH
}

teardown() {
    stop_watcher 2>/dev/null || :
}

# What this folder is for: 4-up on a sheet, and nothing a test has to think
# about. A test whose subject is the policy writes its own.
policy() {
    printf '%s\n' 'SCHEMA=nup' 'OPTIONS=--up 2x2' >"$root/policy.conf"
}

# Start the watcher on the folder and wait until it is past its checks.
#
# `set -m` is not decoration. The script is a pipeline, and it says in its own
# comments that a signal to its pid alone does nothing while it waits on one:
# what stops a watcher is a signal to the process group, which is what
# `systemctl stop` sends. Job control is how a non-interactive shell gives a
# background job a group of its own, so that the test can send that signal.
#
# fd 3 is closed for the child. It is bats' own output pipe, and a background
# process holding it open makes bats wait for the watcher at the end of the
# run instead of finishing the test.
start_watcher() {
    set -m
    "$WATCHER" "$root" >"$log" 2>"$err" 3>&- &
    watcher=$!
    set +m

    # The outbox claim is the last thing taken before the event source
    # starts, so it is the folder saying every check passed.
    local waited=0
    while [ ! -d "$root/out/.impose-writer.lock" ]; do
        if [ "$waited" -ge 100 ]; then
            echo "the watcher did not finish starting:" >&2
            cat "$err" >&2
            return 1
        fi
        sleep 0.1
        waited=$((waited + 1))
    done

    prove_watching
}

# Wait until the event source really is watching, by handing the folder a
# file of this function's own and seeing it come out the other end.
#
# Neither inotifywait nor the stand-in says when it has started, and the gap
# between the folder passing its checks and its event source being up is
# real: measured here with nothing in between, a file dropped into that gap
# was reported by nobody -- the startup sweep had already listed an empty
# inbox, and the stand-in seeded its own list of names to ignore after the
# drop. A folder that has been running since Tuesday never meets that window.
# A test that drops a file 50 ms after starting meets it whenever the machine
# is busy.
#
# So this is the only place that gives a file a second chance: a name still
# sitting in the inbox after a second is taken out and put back, which is a
# fresh arrival to either event source. Once one event has been through,
# the source is watching, and every drop a test makes afterwards is read back
# with no retry at all -- which is what keeps "it landed in done/" a claim
# about the watcher instead of a claim about this loop. It cost a test to
# learn that: while `filed` did the re-announcing, deleting the call to
# `sweep` from the script left all six tests passing, because the file put in
# the inbox before startup was picked up by the retry's event instead.
prove_watching() {
    local name=warm-up.pdf waited=0
    drop "$name"
    while [ ! -e "$root/done/$name" ]; do
        if [ "$waited" -ge 300 ]; then
            echo "the event source never reported anything. stderr:" >&2
            cat "$err" >&2
            return 1
        fi
        # Guarded, because the watcher may claim the file between the test
        # seeing it and moving it -- and a bare `mv` failing there would fail
        # the test for the one reason that means everything is working.
        if [ "$((waited % 10))" -eq 9 ] && [ -e "$root/in/$name" ]; then
            if mv "$root/in/$name" "$BATS_TEST_TMPDIR/again" 2>/dev/null; then
                sleep 0.3
                mv "$BATS_TEST_TMPDIR/again" "$root/in/$name"
            fi
        fi
        sleep 0.1
        waited=$((waited + 1))
    done
}

# Stop it the way a service manager does, and leave the status it went out
# with in `$watcher_status`.
#
# Not printed, because a caller would have to read it in `$(...)`: a command
# substitution is a subshell, the watcher is not its child, and `wait` there
# fails with 127 without waiting for anything (measured -- it is how this
# test first passed a 127 off as the watcher's own status).
stop_watcher() {
    watcher_status=0
    [ -n "${watcher:-}" ] || return 0
    kill -TERM -"$watcher" 2>/dev/null || :
    wait "$watcher" || watcher_status=$?
    watcher=
}

# Put a file in the inbox under *name*, by rename. A rename is atomic and is
# `moved_to`, one of the two events the watcher asks for; a copy would be the
# other one and would also put a file in the inbox at a partial size, which
# is a different test than this one.
drop() {
    local name=$1 source=${2:-$ARTWORK}
    cp "$source" "$BATS_TEST_TMPDIR/$name"
    mv "$BATS_TEST_TMPDIR/$name" "$root/in/$name"
}

# Wait for the watcher to file *name*, and print which bucket it chose. No
# second chances here: see prove_watching.
filed() {
    local name=$1 waited=0 bucket
    while [ "$waited" -lt 600 ]; do
        for bucket in done rejected failed; do
            if [ -e "$root/$bucket/$name" ]; then
                printf '%s\n' "$bucket"
                return 0
            fi
        done
        sleep 0.1
        waited=$((waited + 1))
    done
    echo "nothing was filed as $name in a minute. stderr:" >&2
    cat "$err" >&2
    return 1
}

@test "a PDF handed to a running folder is imposed and filed in done" {
    policy
    start_watcher
    drop book.pdf

    [ "$(filed book.pdf)" = done ]

    # The press file, written where the policy said and under the arriving
    # name, because that is what the next step downstream is watching for.
    [ -f "$root/out/book.pdf" ]
    # The status, as the watcher reported it. `(0)` is the whole claim: this
    # file was imposed, and nothing about it needs looking at.
    grep -Fqx 'book.pdf: done (0)' "$log"
    # And impose's own sentence, beside the file, for whoever opens the
    # folder rather than the log.
    grep -Fq 'n-up: 8 pages onto 1 sheet(s) at 4 up' "$root/done/book.pdf.txt"
    [ ! -e "$root/in/book.pdf" ]
    [ -z "$(ls -A "$root/work")" ]
}

@test "a PDF already in the inbox at startup is swept up by the next start" {
    policy
    mkdir -p "$root/in"
    drop waiting.pdf
    # Nothing is watching yet, so the arrival has no event and never will:
    # the sweep is the only thing that can find this file. It is the restart
    # case, and the boot case, and what a shop sees after a crash.
    start_watcher

    [ "$(filed waiting.pdf)" = done ]
    [ -f "$root/out/waiting.pdf" ]
    grep -Fqx 'waiting.pdf: done (0)' "$log"
}

@test "a file that is not a PDF is rejected, not failed" {
    policy
    start_watcher
    printf 'This is a quotation, not artwork.\n' >"$BATS_TEST_TMPDIR/note.pdf"
    drop quote.pdf "$BATS_TEST_TMPDIR/note.pdf"

    # Exit 3 is the source, and a source nobody can read will not read any
    # better on a second run -- so `rejected/`, which is the bucket the
    # morning check does not retry.
    [ "$(filed quote.pdf)" = rejected ]
    grep -Fqx 'quote.pdf: rejected (3)' "$log"
    # impose's own words, not QPDF's: what follows the colon is whatever the
    # library said about the file, and it is not this test's business.
    grep -Fq 'impose: Cannot open' "$root/rejected/quote.pdf.txt"
    [ ! -e "$root/out/quote.pdf" ]
}

@test "a press file already at that name sends the job to failed" {
    policy
    mkdir -p "$root/out"
    # Yesterday's press file, under the name today's resend arrives with.
    cp "$ARTWORK" "$root/out/book.pdf"
    start_watcher
    drop book.pdf

    # Exit 4 is the destination refusing, and that is the environment: the
    # file in out/ may be the one already on the press, so somebody moves it
    # or asks for an overwrite and runs it again. `failed/` is where the
    # folder puts a job that is worth running again once that is done.
    [ "$(filed book.pdf)" = failed ]
    grep -Fqx 'book.pdf: failed (4)' "$log"
    grep -Fq 'is already there' "$root/failed/book.pdf.txt"
    # And the press file is the one that was there, untouched.
    cmp -s "$ARTWORK" "$root/out/book.pdf"
}

@test "a watcher stopped the way systemd stops it exits 143 and lets go" {
    policy
    start_watcher
    stop_watcher
    [ "$watcher_status" -eq 143 ]

    # Both claims released, because the next start has to be able to take
    # them: a lock left behind by a clean stop is a folder that needs a
    # person before it will run again.
    [ ! -e "$root/.watcher.lock" ]
    [ ! -e "$root/out/.impose-writer.lock" ]
}

@test "a folder with no policy writes the form and refuses to start" {
    run "$WATCHER" "$root"

    # Exit 2 is this script refusing to start, and nothing else is -- the
    # distinction a service manager reads to decide whether starting it again
    # is worth anything.
    [ "$status" -eq 2 ]
    [ -f "$root/policy.conf" ]
    grep -Fq 'One folder, one schema, one policy.' "$root/policy.conf"
    grep -Fq 'Say what this folder is for, then start it again.' <<<"$output"
}
