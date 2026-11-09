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
# What the folder is for is written in the folder, in `policy.conf`, and not
# in this script. One copy of the script then serves every folder, and what a
# folder does can be read -- and changed -- without touching the thing that
# runs it. The first start of a folder writes a commented policy.conf and
# stops, because a watcher that guessed would be imposing somebody's work to
# a policy nobody chose.
#
# It needs inotify-tools, which `impose` does not depend on:
#
#     apt install inotify-tools
#
# Deliberately not part of the package. It is a worked example to adapt, not
# a supported product -- read it, put it under systemd, and change what you
# need. tools/systemd/impose-folder@.service is a unit for one folder.
#
# Exit 2 is this script refusing to start, and nothing else is: the folder is
# not set up, and starting it again changes nothing until that is fixed. Any
# other exit is the event source ending, which is worth starting again.

set -eu

root=${1:?usage: watch-inotify.sh FOLDER}
in="$root/in"
work="$root/work"

# Five directories, and each of them is one question answered. `in/` is the
# only one anybody else writes to; `work/` holds what is claimed and is the
# only place a file is while impose reads it; and `done/`, `rejected/` and
# `failed/` say which of the three kinds of thing happened to it. Where the
# press file goes is the policy's to say, so it is made further down.
if ! trouble=$(mkdir -p "$in" "$work" "$root/done" "$root/rejected" \
    "$root/failed" 2>&1); then
    printf '%s: cannot lay out %s:\n%s\n' "$0" "$root" "$trouble" >&2
    exit 2
fi

policy="$root/policy.conf"

# A folder with no policy has not been set up yet, so write the form and
# stop. The alternative is guessing, which means imposing somebody's work to
# a policy nobody chose.
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
    # A policy edited on Windows over a share arrives with carriage returns,
    # which would otherwise end up inside a size or a schema name.
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
        # Named rather than ignored, for the same reason a job file refuses a
        # field it does not know: a misspelled key that is skipped is a
        # policy somebody believes is in force.
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
# parameters; globbing is off across the split so that an option value cannot
# be expanded against whatever happens to be in the directory.
impose_it() {
    claimed=$1
    press_file=$2
    proof_file=$3
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

# Try the policy before trusting it to everything this folder is ever sent. A
# source that is not there is exit 3 -- the file is the problem, and it is --
# so a 3 means the rest of the invocation is one this impose can make. Any
# other status is the options, the job file, or impose not being on the PATH
# this service runs with, and each of those is worth a sentence now rather
# than a `failed/` bucket with a copy of every file in it.
status=0
trouble=$(impose_it "$root/.impose-policy-check.pdf" /dev/null "" 2>&1) || status=$?
if [ "$status" != 3 ]; then
    printf '%s: %s does not describe a run this impose can make (exit %s):\n%s\n' \
        "$0" "$policy" "$status" "$trouble" >&2
    exit 2
fi

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
        exit 2
    fi
    # The holder is gone, so the lock is debris from a kill or a reboot.
    printf '%s: clearing a lock left by pid %s, which is no longer running.\n' \
        "$0" "${held:-unknown}" >&2
fi
printf '%s\n' "$$" >"$lock/pid"

# Two traps and not one. A trap does not run while the shell is waiting on a
# foreground command, and the event pipeline at the bottom of this script
# never returns -- so a signal aimed at this pid alone does nothing at all
# (measured: five seconds later, still watching, lock untouched). What stops
# a watcher is a signal to the whole process group: `systemctl stop` sends
# one to the service's cgroup and Ctrl-C to the foreground job, the pipeline
# then ends, and the EXIT trap below clears the lock. Exit 143 either way.
#
# The one window where a signal trap does fire is startup, between taking the
# lock and reaching the loop. `trap 'rm -rf "$lock"' EXIT HUP INT TERM`,
# which is what this was, deleted the lock there and then carried on into the
# loop: measured with the probe slowed down, a watcher still claiming files
# with nothing left to refuse a second one started on the same folder. So the
# cleanup hangs off EXIT, which runs however this leaves, and each signal's
# only job is to leave -- with the status a shell reports for that signal,
# which is the status `impose` itself now exits with.
#
# The two claims taken below are released the same way. They are empty until
# they are taken, and `${x:+"$x"}` is one word or nothing at all, so a signal
# arriving during startup cannot remove a directory this run does not hold.
out_claim=
proof_claim=
trap 'rm -rf "$lock" ${out_claim:+"$out_claim"} ${proof_claim:+"$proof_claim"}' EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

# Whether this run still holds the folder. The loop at the bottom is a
# pipeline child, so it is a second process, and it survives a SIGKILL -- or
# a crash -- of this one. The lock then names a pid nobody is running, which
# the next watcher to start is entitled to clear and does. Measured without
# this check: the orphaned loop claimed a file out of in/ while the new
# watcher held the lock, which is the two-watchers-one-folder the lock exists
# to prevent. It finds out here instead, before the next file, and stops.
owned() {
    [ "$(cat "$lock/pid" 2>/dev/null || true)" = "$$" ]
}

# One outbox, one folder. The lock above settles two watchers on one folder;
# this settles two folders on one outbox, which is the other way to arrive at
# two runs writing a single press file -- and the one a policy can ask for by
# accident, since `OUT=/srv/rip/in` in two folders is one directory, and any
# filename that arrives in both is one name there. impose refuses that
# sequentially: the press file is already at that name, exit 4, and the file
# lands in `failed/` with the sentence. It cannot refuse the concurrent case,
# because both runs look at a directory where the name is still free, and it
# says so in `impose/destination.py` -- the rename is atomic and nothing
# reserves the name. Measured: two runs, one `-o`, both exit 0, one press
# file, the other run's sheets gone and nothing said about it.
#
# So the directory is claimed once, at startup, with the same `mkdir` that
# claims the folder. Not `flock` around the impose call: that serialises every
# folder sharing an outbox behind whichever one is part way through a
# 3000-page job, which is the opposite of a service per folder, and `flock(1)`
# is util-linux -- there is none on macOS, so watch-fswatch.sh could not carry
# the same guarantee. `mkdir` is atomic on every filesystem, including the SMB
# and NFS mounts a RIP's inbox tends to be, where flock is absent or advisory.
#
# PROOF is claimed too. A proof takes the arriving file's name as well, so two
# folders sharing a proof directory lose a proof the same way.
claim_written() {
    directory=$1
    role=$2
    claim="$directory/.impose-writer.lock"
    if ! trouble=$(mkdir "$claim" 2>&1); then
        # Tell the two failures apart. A name already taken is another
        # folder's claim and wants the sentence below; anything else -- a
        # read-only mount, a directory somebody chmodded -- is this folder's
        # own problem and wants the errno.
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
        # The holder is gone, so the claim is debris, exactly as the folder
        # lock's is.
        printf '%s: clearing a claim on %s left by pid %s, which is no longer running.\n' \
            "$0" "$directory" "${held:-unknown}" >&2
    fi
    # Both, because the pid says whether the claim is live and the folder says
    # which policy to go and fix.
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
# Nearly everything does; some SMB mounts and exFAT do not, and there the
# claim would fail on every file and this script would skip the lot without
# saying why. Find out now instead, in one sentence, while somebody is still
# watching the terminal.
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

# Impose a file already claimed into `work/`, and file it by what happened.
impose_claimed() {
    name=$1
    status=0
    proof_file=""
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
        owned || break
        handle "$name" || true
    done
}
