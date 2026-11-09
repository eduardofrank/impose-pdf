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
# What the folder is for is written in the folder, in `policy.conf`, and not
# in this script; the first start of a folder writes a commented one and
# stops. See watch-inotify.sh.
#
# Deliberately not part of the package: a worked example to adapt, not a
# supported product. Put it under launchd --
# tools/launchd/impose-folder.plist is an agent for one folder.
#
# Exit 2 is this script refusing to start, and nothing else is: the folder is
# not set up, and starting it again changes nothing until that is fixed.

set -eu

root=${1:?usage: watch-fswatch.sh FOLDER}
in="$root/in"
work="$root/work"

# Five directories, each of them one question answered: see watch-inotify.sh.
# Where the press file goes is the policy's to say, so it is made further
# down.
if ! trouble=$(mkdir -p "$in" "$work" "$root/done" "$root/rejected" \
    "$root/failed" 2>&1); then
    printf '%s: cannot lay out %s:\n%s\n' "$0" "$root" "$trouble" >&2
    exit 2
fi

policy="$root/policy.conf"

# A folder with no policy has not been set up yet, so write the form and
# stop rather than guess: see watch-inotify.sh, which carries the commentary
# on the policy, the keys and the check at the end of this block.
if [ ! -f "$policy" ]; then
    cat >"$policy" <<'FORM'
# What this folder is for. One folder, one schema, one policy.
#
# Lines are KEY=value. The watcher reads them itself rather than sourcing
# this file, so there is no quoting and no substitution: a value is the rest
# of its line as it stands, and a line starting with # is a comment.
#
# Say either SCHEMA, with the options that go with it, or JOB, naming a job
# file beside this one -- a job file can carry a press, gutters and marks,
# which is more than fits on a line. Both is a mistake rather than a merge.

# SCHEMA=nup
# OPTIONS=--up 2x2 --expect-size A4

# JOB=a4-nup.json
# OPTIONS=--trim-from mediabox

# OPTIONS reaches impose as it stands, split on whitespace, so an option
# whose value has a space in it needs a job file instead. --trim-from,
# --damaged and --overwrite are the three options a job file may not carry:
# they belong here, where somebody chose them for this folder.

# Where the press files go. Default out, beside this file; an absolute path
# for a RIP's own hot folder somewhere else. Anywhere but inside in/.
# OUT=/srv/rip/in

# Where the proofs go, if this folder makes them. Empty means it does not.
# Keep them out of OUT: a RIP watching that folder would print them.
# PROOF=proof
FORM
    printf '%s: wrote %s. Say what this folder is for, then start it again.\n' \
        "$0" "$policy" >&2
    exit 2
fi

# A policy anybody can rewrite is a command anybody can choose. The inbox is
# the only part of a hot folder that wants to be open to all comers.
if [ -n "$(find "$policy" -perm -0002 2>/dev/null)" ]; then
    printf '%s: %s is writable by anybody, and it is the command this folder\n' \
        "$0" "$policy" >&2
    printf 'runs on everything it is sent. Only in/ should be that open.\n' >&2
    exit 2
fi

SCHEMA=
JOB=
OPTIONS=
OUT=
PROOF=
cr=$(printf '\r')
while IFS= read -r line || [ -n "$line" ]; do
    # A share edited from Windows leaves carriage returns behind.
    line=${line%"$cr"}
    case "$line" in
    '' | '#'*) continue ;;
    *=*) ;;
    *)
        printf '%s: %s: this is not KEY=value: %s\n' "$0" "$policy" "$line" >&2
        exit 2
        ;;
    esac
    value=${line#*=}
    case "${line%%=*}" in
    SCHEMA) SCHEMA=$value ;;
    JOB) JOB=$value ;;
    OPTIONS) OPTIONS=$value ;;
    OUT) OUT=$value ;;
    PROOF) PROOF=$value ;;
    *)
        printf '%s: %s: %s is not a key of a policy.\n' \
            "$0" "$policy" "${line%%=*}" >&2
        printf 'Known: SCHEMA, JOB, OPTIONS, OUT, PROOF.\n' >&2
        exit 2
        ;;
    esac
done <"$policy"

if [ -n "$SCHEMA" ] && [ -n "$JOB" ]; then
    printf '%s: %s says both SCHEMA (%s) and JOB (%s). One of them is the\n' \
        "$0" "$policy" "$SCHEMA" "$JOB" >&2
    printf 'policy; pick which.\n' >&2
    exit 2
fi
if [ -z "$SCHEMA" ] && [ -z "$JOB" ]; then
    printf '%s: %s says neither SCHEMA nor JOB, so nobody has said what this\n' \
        "$0" "$policy" >&2
    printf 'folder is for yet.\n' >&2
    exit 2
fi

# A job file is named beside the policy that names it, so a folder moves in
# one piece. An absolute path is taken as given, here and for the two
# directories below.
case $JOB in
'' | /*) job=$JOB ;;
*) job=$root/$JOB ;;
esac
case ${OUT:=out} in
/*) out=$OUT ;;
*) out=$root/$OUT ;;
esac
case $PROOF in
'' | /*) proofs=$PROOF ;;
*) proofs=$root/$PROOF ;;
esac

# Neither of them inside the inbox, or the folder would fire on its own
# output: a press file written into `in/` matches *.pdf, gets claimed, and is
# imposed again as though it were artwork.
for written in "$out" "$proofs"; do
    case ${written:-/dev/null} in
    "$in" | "$in"/*)
        printf '%s: %s writes to %s, which is the inbox or inside it. The\n' \
            "$0" "$policy" "$written" >&2
        printf 'folder would impose its own press files as artwork.\n' >&2
        exit 2
        ;;
    esac
done

# And not the same directory as each other: the proof and the press file take
# the arriving file's name, so one directory for both is one name for both.
if [ -n "$proofs" ] && [ "$proofs" = "$out" ]; then
    printf '%s: %s writes the proofs and the press files both to %s, where\n' \
        "$0" "$policy" "$out" >&2
    printf 'they would be one name. A proof wants a directory of its own --\n' >&2
    printf 'and out of the way of whatever is watching for press files.\n' >&2
    exit 2
fi

# Made, not assumed: a proof directory exists only for a folder that asked
# for proofs, and a press file is not written into a directory nobody made.
if ! trouble=$(mkdir -p "$out" ${proofs:+"$proofs"} 2>&1); then
    printf '%s: cannot make somewhere to write in %s:\n%s\n' "$0" "$root" "$trouble" >&2
    exit 2
fi


# The invocation, assembled from the policy. OPTIONS is split on whitespace
# by `set --`, which inside a function sets that function's own positional
# parameters, with globbing off across the split.
impose_it() {
    local claimed=$1 press_file=$2 proof_file=$3
    set -f
    set -- $OPTIONS
    set +f
    if [ -n "$proof_file" ]; then
        set -- "$@" --proof "$proof_file"
    fi
    if [ -n "$job" ]; then
        impose run "$job" "$claimed" -o "$press_file" "$@"
    else
        impose "$SCHEMA" "$claimed" -o "$press_file" "$@"
    fi
}

# Try the policy before trusting it to everything this folder is ever sent:
# a source that is not there is exit 3, so anything else is the options, the
# job file, or impose not being on this service's PATH. One sentence now
# rather than a `failed/` bucket with a copy of every file in it. launchd in
# particular hands a job a PATH of its own, which is how a watcher that works
# in a terminal files everything into failed/ as a service.
status=0
trouble=$(impose_it "$root/.impose-policy-check.pdf" /dev/null "" 2>&1) || status=$?
if [ "$status" != 3 ]; then
    printf '%s: %s does not describe a run this impose can make (exit %s):\n%s\n' \
        "$0" "$policy" "$status" "$trouble" >&2
    exit 2
fi

# One watcher per folder: see watch-inotify.sh. The sweep below treats `work/`
# as the debris of a run that died, which is only true for as long as nothing
# else is working this folder.
lock="$root/.watcher.lock"
if ! mkdir "$lock" 2>/dev/null; then
    held=$(cat "$lock/pid" 2>/dev/null || true)
    if [ -n "$held" ] && kill -0 "$held" 2>/dev/null; then
        printf '%s: %s is already being watched by pid %s.\n' "$0" "$root" "$held" >&2
        exit 2
    fi
    printf '%s: clearing a lock left by pid %s, which is no longer running.\n' \
        "$0" "${held:-unknown}" >&2
fi
printf '%s\n' "$$" >"$lock/pid"

# Cleanup on EXIT, and each signal's only job is to leave. A trap does not run
# while the shell waits on the pipeline at the bottom, so what stops this is a
# signal to the process group -- `launchctl bootout`, or Ctrl-C. The one that
# used to cover all four here deleted the lock during startup and carried on
# watching without it. See watch-inotify.sh.
# The two claims below are released the same way, and are empty until taken,
# so a signal during startup cannot remove a directory this run does not hold.
out_claim=
proof_claim=
trap 'rm -rf "$lock" ${out_claim:+"$out_claim"} ${proof_claim:+"$proof_claim"}' EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

# Whether this run still holds the folder: see watch-inotify.sh. The loop
# below is a pipeline child and survives a SIGKILL of this script, after which
# the lock names a dead pid and the next watcher clears it; this is how the
# orphan finds out, instead of working a folder somebody else now holds.
owned() {
    [ "$(cat "$lock/pid" 2>/dev/null || true)" = "$$" ]
}

# One outbox, one folder. The lock above settles two watchers on one folder;
# this settles two folders on one outbox -- `OUT=/srv/rip/in` in two policies
# is one directory, and a filename arriving in both is one press file there.
# impose refuses that sequentially (exit 4, already at that name) and cannot
# refuse it concurrently: measured, two runs with one `-o` both exit 0 and one
# of the two impositions is gone. `mkdir` rather than `flock` around the
# impose call, which there is no `flock(1)` for on macOS anyway. See
# watch-inotify.sh for the whole of the reasoning. PROOF is claimed too: a
# proof takes the arriving name as well.
claim_written() {
    local directory=$1 role=$2 claim held holder trouble
    claim="$directory/.impose-writer.lock"
    if ! trouble=$(mkdir "$claim" 2>&1); then
        # A name already taken is another folder; anything else -- a read-only
        # mount, a directory somebody chmodded -- wants its errno instead.
        if [ ! -d "$claim" ]; then
            printf '%s: cannot claim %s as this folder'"'"'s %s:\n%s\n' \
                "$0" "$directory" "$role" "$trouble" >&2
            exit 2
        fi
        held=$(cat "$claim/pid" 2>/dev/null || true)
        holder=$(cat "$claim/folder" 2>/dev/null || true)
        if [ -n "$held" ] && kill -0 "$held" 2>/dev/null; then
            printf '%s: %s is already the %s of %s (pid %s).\n' \
                "$0" "$directory" "$role" "${holder:-another folder}" "$held" >&2
            printf 'One %s, one folder: two folders writing one directory\n' "$role" >&2
            printf 'write one file for every name that arrives in both, and two runs\n' >&2
            printf 'racing for that name both report success. Give this folder a\n' >&2
            printf 'directory of its own -- under that one, if a RIP reads it.\n' >&2
            exit 2
        fi
        printf '%s: clearing a claim on %s left by pid %s, which is no longer running.\n' \
            "$0" "$directory" "${held:-unknown}" >&2
    fi
    printf '%s\n' "$$" >"$claim/pid"
    printf '%s\n' "$root" >"$claim/folder"
}

claim_written "$out" outbox
out_claim="$out/.impose-writer.lock"
if [ -n "$proofs" ]; then
    claim_written "$proofs" "proof directory"
    proof_claim="$proofs/.impose-writer.lock"
fi

# The claim below is a hard link, so `in/` and `work/` have to support one.
# Most volumes do; some SMB mounts and exFAT do not, and there the claim would
# fail on every file and this script would skip the lot without saying why.
# Find out now instead, in one sentence, while somebody is still watching the
# terminal.
probe="$in/.impose-link-probe.$$"
: >"$probe"
if trouble=$(ln "$probe" "$work/.impose-link-probe.$$" 2>&1); then
    rm -f "$probe" "$work/.impose-link-probe.$$"
else
    rm -f "$probe"
    # Say what actually went wrong before explaining what it was for. The
    # likely causes are a filesystem with no hard links and a work/ somebody
    # cannot write to, and they want different fixes.
    printf '%s: cannot claim a file in %s:\n%s\n' "$0" "$root" "$trouble" >&2
    printf 'A file is claimed by hard-linking its name from in/ into work/,\n' >&2
    printf 'so linking has to work. Some SMB mounts and exFAT cannot link at\n' >&2
    printf 'all. Put the folder on a filesystem that can, or replace the\n' >&2
    printf 'claim with your own.\n' >&2
    exit 2
fi

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
    local name=$1 status=0 message bucket proof_file=""
    if [ -n "$proofs" ]; then
        proof_file="$proofs/$name"
    fi
    message=$(impose_it "$work/$name" "$out/$name" "$proof_file" 2>&1) || status=$?

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
        owned || break
        handle "$(basename "$path")" || true
    done
}
