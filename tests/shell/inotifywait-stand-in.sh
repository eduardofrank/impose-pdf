#!/bin/sh
# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.
#
# A stand-in for inotifywait(1), so that the shell tests can drive
# watch-inotify.sh on a machine that has no inotify. That is every machine
# that is not Linux: inotify is a kernel interface, inotify-tools builds
# nowhere else, and the watcher under test is the one a shop runs on its
# Linux print server -- which is not the laptop it gets written on.
#
#     inotifywait-stand-in.sh -m -q -e close_write --format '%f' DIRECTORY
#
# Every argument but the last is ignored; the last one is the directory. It
# prints the name of each file that appears there, one per line, as the real
# one does with `--format '%f'`, and keeps going until the directory is gone.
#
# What it copies, because the script under test depends on it: a name that is
# already there when this starts is *not* reported. inotify says nothing about
# what it did not see arrive, which is the whole reason watch-inotify.sh
# sweeps the inbox at startup, and a stand-in that reported the backlog would
# make that sweep untestable by hiding its absence.
#
# What it cannot copy: close_write. It sees an arrival, not the end of a
# write, so it can hand over a file that is still being copied -- which is why
# the tests put files in place with a rename rather than a copy. A name with a
# newline in it would confuse it too. Both are fine for a test double and
# neither is fine for a hot folder: this is not a fallback for the watcher,
# and watch-inotify.sh does not know it exists.

set -eu

# The real one takes its options first and the directories last, and this is
# only ever called with one directory, so the last argument is it.
for directory; do :; done

seen=$(mktemp)
present=$(mktemp)
trap 'rm -f "$seen" "$present"' EXIT

# Seeded before the first report, which is what makes the backlog silent.
ls -A "$directory" >"$seen" 2>/dev/null || :

while [ -d "$directory" ]; do
    ls -A "$directory" >"$present" 2>/dev/null || :
    # Whatever is there now and was not there last time. grep exits 1 when
    # that is nothing, which is the ordinary case and not an error. It writes
    # and exits once per poll, so a name reaches the reader's pipe at once
    # rather than sitting in a block of buffer.
    grep -Fxv -f "$seen" "$present" || :
    cat "$present" >"$seen"
    sleep 0.1
done
