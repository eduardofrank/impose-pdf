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
# The companion to watch-inotify.sh, which has the commentary on the folder
# layout and the invocation. This one differs in exactly one place, and it is
# the important one: fswatch has no close event.
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
    last=""
    stable=0
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

fswatch -0 --event Created --event MovedTo --event Updated "$in" | while read -r -d "" path; do
    name=$(basename "$path")
    case "$name" in
    *.pdf | *.PDF) ;;
    *) continue ;;
    esac
    [ -f "$path" ] || continue
    settled "$path" || continue

    mv -n "$in/$name" "$work/$name" 2>/dev/null || continue
    [ -f "$work/$name" ] || continue

    status=0
    message=$(impose_it "$work/$name" "$root/out/$name" 2>&1) || status=$?

    case $status in
    0) bucket=done ;;
    1 | 3) bucket=rejected ;;
    *) bucket=failed ;;
    esac
    mv "$work/$name" "$root/$bucket/$name"
    [ -n "$message" ] && printf '%s\n' "$message" >"$root/$bucket/$name.txt"
    printf '%s: %s (%s)\n' "$name" "$bucket" "$status"
done
