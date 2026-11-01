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

# close_write fires when the writer closes the file, not when it appears, so
# a file still being copied is never handed over. moved_to catches the other
# arrival pattern: uploaded under a temporary name, then renamed into place.
# `impose` refuses a half-copied file anyway -- it will not impose a page
# count QPDF had to reconstruct -- and that refusal is the net under this.
inotifywait -m -q -e close_write -e moved_to --format '%f' "$in" | while read -r name; do
    case "$name" in
    *.pdf | *.PDF) ;;
    *) continue ;;
    esac

    # Move it out of the inbox before touching it. One rename, within one
    # filesystem, settles three things at once: the folder cannot fire on it
    # again, a duplicate event finds nothing to move, and nothing can still
    # be writing to a name we now hold. If the rename fails, another run of
    # this script won the race, and that is its file.
    mv -n "$in/$name" "$work/$name" 2>/dev/null || continue
    [ -f "$work/$name" ] || continue

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
    mv "$work/$name" "$root/$bucket/$name"
    [ -n "$message" ] && printf '%s\n' "$message" >"$root/$bucket/$name.txt"
    printf '%s: %s (%s)\n' "$name" "$bucket" "$status"
done
