#!/bin/sh
# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.
#
# Impose every PDF dropped into a folder, on Linux, with inotify.
#
#     tools/watch-inotify.sh /srv/impose/a4-nup
#
# The folder is one schema and one policy: that is the whole design. A folder
# that takes two finished sizes is two folders, because `--expect-size` is
# per-folder and so is everyone's idea of what the folder is for.
#
# It needs inotify-tools, which `impose` does not depend on:
#
#     apt install inotify-tools
#
# Deliberately not part of the package. It is a worked example to adapt, not
# a supported product -- read it, change the invocation to your schema, and
# put it under systemd.

set -eu

root=${1:?usage: watch-inotify.sh FOLDER}
in="$root/in"
work="$root/work"
mkdir -p "$in" "$work" "$root/out" "$root/done" "$root/rejected" "$root/failed"

# One watcher per folder, enforced rather than hoped for. The sweep below
# treats everything in `work/` as left over from a run that died, which is
# only true if no other run is holding a file right now -- and starting the
# same folder twice, from two terminals or two unit files, is the easiest
# mistake to make here. `mkdir` is the lock because it either creates the
# directory or fails, on every filesystem.
lock="$root/.watcher.lock"
if ! mkdir "$lock" 2>/dev/null; then
    held=$(cat "$lock/pid" 2>/dev/null || true)
    if [ -n "$held" ] && kill -0 "$held" 2>/dev/null; then
        printf '%s: %s is already being watched by pid %s.\n' "$0" "$root" "$held" >&2
        exit 1
    fi
    # The holder is gone, so the lock is debris from a kill or a reboot.
    printf '%s: clearing a lock left by pid %s, which is no longer running.\n' \
        "$0" "${held:-unknown}" >&2
fi
printf '%s\n' "$$" >"$lock/pid"
trap 'rm -rf "$lock"' EXIT HUP INT TERM

# The claim below is a hard link, so `in/` and `work/` have to support one.
# Nearly everything does; some SMB mounts and exFAT do not, and there the
# claim would fail on every file and this script would skip the lot without
# saying why. Find out now instead, in one sentence, while somebody is still
# watching the terminal.
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

# The invocation. Everything policy-ish lives here, in one place, so that
# what this folder accepts can be read off four lines:
#
#   --trim-from mediabox   these are office exports; take the page as drawn
#   --expect-size A4       and refuse anything that is not actually A4
#   -o <outside the inbox> or the watcher would fire on its own output
#   no --overwrite         a resend never silently replaces a press file
impose_it() {
    impose nup "$1" -o "$2" --trim-from mediabox --expect-size A4
}

# Impose a file already claimed into `work/`, and file it by what happened.
impose_claimed() {
    name=$1
    status=0
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

# Claim one name out of the inbox, then impose it.
handle() {
    name=$1
    case "$name" in
    *.pdf | *.PDF) ;;
    *) return 0 ;;
    esac

    # Claim it before touching it, and claim it with `ln`. Linking the name
    # into the work folder fails, loudly, when that name is already taken --
    # which is what makes it a claim. `mv -n` looks like it would do the same
    # and does not: given an existing destination it skips the move and still
    # exits 0, so a duplicate event, or the ordinary resend of a filename
    # still being worked on, would sail past the check and impose a file this
    # run already holds. Whoever loses the link leaves the file alone.
    #
    # With the inbox name gone, the folder cannot fire on it again. It does
    # not stop a writer that still has the file open -- a link shares the
    # inode, and so did the rename this replaces -- which is why `impose`
    # refusing a reconstructed page count is the net under this and not a
    # belt-and-braces extra.
    ln "$in/$name" "$work/$name" 2>/dev/null || return 0
    rm -f "$in/$name"
    impose_claimed "$name"
}

# What a restart has to pick up, because an event does not survive one.
# inotify reports what happens from the moment it starts watching and nothing
# about what is already there, so without this every file sitting in the inbox
# at boot, after `systemctl restart`, or after this script was killed is
# invisible -- permanently, since the arrival that would have been its event
# is long past.
sweep() {
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

# close_write fires when the writer closes the file, not when it appears, so
# a file still being copied is never handed over. moved_to catches the other
# arrival pattern: uploaded under a temporary name, then renamed into place.
# `impose` refuses a half-copied file anyway -- it will not impose a page
# count QPDF had to reconstruct -- and that refusal is the net under this.
#
# The sweep runs inside the reader, not before the pipeline, so that
# inotifywait is already running while it works: anything arriving during the
# sweep waits in the pipe instead of falling down the gap between listing the
# folder and starting to watch it. An event for a file the sweep already took
# finds the name gone and costs nothing.
inotifywait -m -q -e close_write -e moved_to --format '%f' "$in" | {
    sweep
    while read -r name; do
        handle "$name" || true
    done
}
