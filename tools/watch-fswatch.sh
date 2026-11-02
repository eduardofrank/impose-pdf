#!/bin/bash
# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.
#
# bash, not sh: reading fswatch's null-separated output needs `read -d`, and
# a filename is the one thing a hot folder cannot promise is well behaved.
#
# Impose every PDF dropped into a folder, on macOS, with fswatch.
#
#     tools/watch-fswatch.sh ~/impose/a4-nup
#
# The companion to watch-inotify.sh, which carries the commentary on the
# folder layout, the lock, the claim and the invocation. This one differs in
# exactly one place, and it is the important one: fswatch has no close event.
#
#     brew install fswatch
#
# Deliberately not part of the package: a worked example to adapt, not a
# supported product. Put it under launchd.

set -eu

root=${1:?usage: watch-fswatch.sh FOLDER}
in="$root/in"
work="$root/work"
mkdir -p "$in" "$work" "$root/out" "$root/done" "$root/rejected" "$root/failed"

# One watcher per folder: see watch-inotify.sh. The sweep below treats `work/`
# as the debris of a run that died, which is only true for as long as nothing
# else is working this folder.
lock="$root/.watcher.lock"
if ! mkdir "$lock" 2>/dev/null; then
    held=$(cat "$lock/pid" 2>/dev/null || true)
    if [ -n "$held" ] && kill -0 "$held" 2>/dev/null; then
        printf '%s: %s is already being watched by pid %s.\n' "$0" "$root" "$held" >&2
        exit 1
    fi
    printf '%s: clearing a lock left by pid %s, which is no longer running.\n' \
        "$0" "${held:-unknown}" >&2
fi
printf '%s\n' "$$" >"$lock/pid"
trap 'rm -rf "$lock"' EXIT HUP INT TERM

# The claim below is a hard link, so `in/` and `work/` have to support one.
# Most volumes do; some SMB mounts and exFAT do not, and there the claim would
# fail on every file and this script would skip the lot without saying why.
# Find out now instead, in one sentence, while somebody is still watching the
# terminal.
probe="$in/.impose-link-probe.$$"
: >"$probe"
if ln "$probe" "$work/.impose-link-probe.$$" 2>/dev/null; then
    rm -f "$probe" "$work/.impose-link-probe.$$"
else
    rm -f "$probe"
    printf '%s: %s cannot hard-link between in/ and work/, which is how a\n' "$0" "$root" >&2
    printf 'file is claimed before it is imposed. Put the folder on a\n' >&2
    printf 'filesystem that can, or replace the claim with your own.\n' >&2
    exit 1
fi

# The invocation. Everything policy-ish lives here, in one place, so that what
# this folder accepts can be read off four lines:
#
#   --trim-from mediabox   these are office exports; take the page as drawn
#   --expect-size A4       and refuse anything that is not actually A4
#   -o <outside the inbox> or the watcher would fire on its own output
#   no --overwrite         a resend never silently replaces a press file
impose_it() {
    impose nup "$1" -o "$2" --trim-from mediabox --expect-size A4
}

# FSEvents reports that something changed, never that a writer finished, so
# there is no equivalent of inotify's close_write and this has to guess. Wait
# for the size to stop moving: three identical samples a second apart.
#
# It is a heuristic and it can be fooled -- a slow share that stalls for three
# seconds mid-copy looks exactly like a finished file. That is why it is not
# the only defence. `impose` refuses a file whose cross-reference table had to
# be reconstructed, which is what a half-copied PDF always needs, so a file
# this loop hands over too early is turned away rather than imposed short.
settled() {
    local last="" stable=0 size
    while [ "$stable" -lt 3 ]; do
        size=$(stat -f %z "$1" 2>/dev/null) || return 1
        if [ "$size" = "$last" ]; then
            stable=$((stable + 1))
        else
            stable=0
            last="$size"
        fi
        sleep 1
    done
}

# Impose a file already claimed into `work/`, and file it by what happened.
impose_claimed() {
    local name=$1 status=0 message bucket
    message=$(impose_it "$work/$name" "$root/out/$name" 2>&1) || status=$?

    # The status says which bucket; the sentence says why. Both go with the
    # file, because whoever opens that folder wants to know without digging
    # through a log.
    case $status in
    0) bucket=done ;;
    1 | 3) bucket=rejected ;; # the file or the job: do not retry
    *) bucket=failed ;;       # the environment: fix it and run it again
    esac

    # Guarded, and this is not pedantry: `set -eu` makes an unguarded failure
    # here exit the whole script, so one file that cannot be filed -- a full
    # disk, a folder somebody chmodded -- would stop the watcher dead and
    # quietly. Leave it in `work/` instead, say so, and carry on; the next
    # start sweeps it up.
    if ! mv "$work/$name" "$root/$bucket/$name"; then
        printf '%s: imposed with status %s, but cannot be filed into %s/ -- left in work/\n' \
            "$name" "$status" "$bucket" >&2
        return 1
    fi
    [ -n "$message" ] && printf '%s\n' "$message" >"$root/$bucket/$name.txt"
    printf '%s: %s (%s)\n' "$name" "$bucket" "$status"
    return 0
}

# Wait for the file to settle, claim the name, impose it. The settle wait sits
# in here rather than in the event loop so the sweep gets it too: a file
# already in the inbox when this starts may still be arriving.
handle() {
    local name=$1
    case "$name" in
    *.pdf | *.PDF) ;;
    *) return 0 ;;
    esac
    [ -f "$in/$name" ] || return 0
    settled "$in/$name" || return 0

    # `ln`, not `mv -n`: linking fails when the name is already claimed, which
    # is what makes it a claim. `mv -n` skips a taken destination and still
    # exits 0, so a duplicate event, or the ordinary resend of a filename
    # still being worked on, would sail past the check and impose a file this
    # run already holds. Whoever loses the link leaves the file alone.
    ln "$in/$name" "$work/$name" 2>/dev/null || return 0
    rm -f "$in/$name"
    impose_claimed "$name"
}

# What a restart has to pick up, because an FSEvent does not survive one.
# fswatch reports changes from the moment it starts watching and nothing about
# what is already there, so without this every file sitting in the inbox at
# login, after a `launchctl kickstart`, or after this script was killed is
# invisible -- permanently, since the arrival that would have been its event
# is long past.
sweep() {
    local path name
    # `work/` first. We hold the lock, so nothing else is working this folder
    # and anything here was claimed by a run that did not finish. It is still
    # claimed -- the name in `work/` *is* the claim -- so finish the job
    # rather than putting it back, which would risk landing on a resend that
    # arrived in the meantime.
    for path in "$work"/*; do
        [ -f "$path" ] || continue
        name=${path##*/}
        printf '%s: left over from an earlier run; imposing it now\n' "$name" >&2
        impose_claimed "$name" || true
    done
    for path in "$in"/*; do
        [ -f "$path" ] || continue
        handle "${path##*/}" || true
    done
}

# The sweep runs inside the reader, not before the pipeline, so that fswatch
# is already watching while it works: anything arriving during the sweep waits
# in the pipe instead of falling down the gap between listing the folder and
# starting to watch it. An event for a file the sweep already took finds the
# name gone and costs nothing.
fswatch -0 --event Created --event MovedTo --event Updated "$in" | {
    sweep
    while read -r -d "" path; do
        handle "$(basename "$path")" || true
    done
}
