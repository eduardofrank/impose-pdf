#!/bin/sh
# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE.
#
# Impose every PDF dropped into a folder, on Linux, with inotify.
#
#     impose-watch /srv/impose/a4-nup
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
# It ships inside the package so that an install has it -- `impose-hotfolder`
# prints its path and hands out copies -- but it is a worked example to adapt
# rather than a supported product: read it, put it under systemd, and change
# what you need. `impose-folder@.service`, beside it, is a unit for one
# folder.
#
# Exit 2 is this script refusing to start, and nothing else is: the folder is
# not set up, and starting it again changes nothing until that is fixed. Exit
# 1 is the event source ending under a folder that was running, which is
# worth starting again. It never leaves with 0: a watcher has no way to be
# finished, so 0 would be a folder that stopped and called it success.

set -eu

# Asked rather than left to `${1:?}`, whose status is the shell's own: 1 from
# bash and 2 from dash, measured, and 2 is the one this script promises.
if [ -z "${1:-}" ]; then
    printf 'usage: %s FOLDER\n' "$0" >&2
    exit 2
fi
root=$1
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

# How this folder says what it did, one line per file either way. The
# default, text, is `book.pdf: done (0)`, written for whoever is reading the
# journal. json is one object per file -- when it ran, which folder, which
# file, which bucket, impose's exit status, how long impose took, and what it
# said -- for when something other than a person is reading.
# LOG_FORMAT=json

# How long one file may take, in whole seconds, before its run is stopped and
# the file goes to failed/ at status 124. Unset is no limit. Pick it from the
# largest job this folder is meant to take, not from a typical one: 20000
# pages is about twenty seconds. Needs GNU timeout, which is coreutils.
# TIMEOUT=600
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
LOG_FORMAT=
TIMEOUT=
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
    LOG_FORMAT) LOG_FORMAT=$value ;;
    TIMEOUT) TIMEOUT=$value ;;
    *)
        # Named rather than ignored, for the same reason a job file refuses a
        # field it does not know: a misspelled key that is skipped is a
        # policy somebody believes is in force.
        printf '%s: %s: %s is not a key of a policy.\n' \
            "$0" "$policy" "${line%%=*}" >&2
        printf 'Known: SCHEMA, JOB, OPTIONS, OUT, PROOF, LOG_FORMAT, TIMEOUT.\n' >&2
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

# Named rather than ignored, like a key nobody knows: a folder whose policy
# asks for a format this does not write would otherwise log in the other one
# and look as though it had been asked to.
case $LOG_FORMAT in
'' | text) log_json= ;;
json) log_json=yes ;;
*)
    printf '%s: %s: LOG_FORMAT=%s is not a format this writes.\n' \
        "$0" "$policy" "$LOG_FORMAT" >&2
    printf 'Say text, the default, which is one line a file for a person; or\n' >&2
    printf 'json, which is one object a file for whatever reads the journal.\n' >&2
    exit 2
    ;;
esac

# A limit on one run, for the hang nobody has found yet. A folder works one
# file at a time, so a run that never ends is the folder stopped, behind a
# service that looks idle: measured with a pipe under a PDF's name, before
# that was refused. Whatever the next cause is, this is what bounds it.
#
# GNU timeout rather than a watchdog written here. The shell version is a
# background `sleep` per file, and either it is waited for, which costs every
# file a second, or it is left behind, which is a process a file against a
# `TasksMax` that counts them. `--foreground` keeps impose in this script's
# process group, so that the signal which stops a watcher still reaches it;
# without it timeout makes a group of its own and a stop leaves the run going.
# The probe is the flag, because a `timeout` that is not GNU's has no such
# option, and finding that out on the first file is finding it out too late.
limiter=
case $TIMEOUT in
'') ;;
*[!0-9]* | 0*)
    printf '%s: %s: TIMEOUT=%s is not a whole number of seconds.\n' \
        "$0" "$policy" "$TIMEOUT" >&2
    exit 2
    ;;
*)
    for candidate in timeout gtimeout; do
        if "$candidate" --foreground 5 true 2>/dev/null; then
            limiter=$candidate
            break
        fi
    done
    if [ -z "$limiter" ]; then
        printf '%s: %s sets TIMEOUT, and there is no GNU timeout on the PATH this\n' \
            "$0" "$policy" >&2
        printf 'runs with to enforce it. Install coreutils -- gtimeout, from Homebrew,\n' >&2
        printf 'is the same thing -- or take the line out.\n' >&2
        exit 2
    fi
    ;;
esac

# How precisely this machine can time a run, settled once rather than per
# file. `date +%N` is nanoseconds wherever it exists at all -- measured on GNU
# coreutils and on macOS 15.8, nine digits from both -- and a `date` without
# it answers with something that has no digits in it, which is the test. The
# precision travels with the clock so that a duration is never printed to
# three places by something that cannot measure them.
case $(date +%N 2>/dev/null) in
*[0-9]*)
    clock='%s.%N'
    places=3
    ;;
*)
    clock='%s'
    places=0
    ;;
esac

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

# The run, under the limit if the policy set one. 124 is timeout's own status
# for a run it stopped; `-k` is for one that ignored being asked.
limited() {
    if [ -n "$limiter" ]; then
        "$limiter" --foreground -k 10 "$TIMEOUT" "$@"
    else
        "$@"
    fi
}

# The invocation, assembled from the policy. OPTIONS is split on whitespace
# by `set --`, which inside a function sets that function's own positional
# parameters; globbing is off across the split so that an option value cannot
# be expanded against whatever happens to be in the directory.
impose_it() {
    claimed=$1
    press_file=$2
    proof_file=$3
    set -f
    # The splitting is the point of this line, and `set -f` is what makes it
    # safe, so the quotes shellcheck asks for here would break it.
    # shellcheck disable=SC2086
    set -- $OPTIONS
    set +f
    if [ -n "$proof_file" ]; then
        set -- "$@" --proof "$proof_file"
    fi
    if [ -n "$job" ]; then
        limited impose run "$job" "$claimed" -o "$press_file" "$@"
    else
        limited impose "$SCHEMA" "$claimed" -o "$press_file" "$@"
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

# The event source, looked for before anything is claimed. A pipeline whose
# first command is not there still runs its second: the shell says `not
# found`, the reader sweeps, reads end of file and stops, and the folder is
# never watched at all. That is a machine nobody finished setting up, so it
# is a refusal to start like the rest of them.
if ! command -v inotifywait >/dev/null 2>&1; then
    printf '%s: there is no inotifywait on the PATH this runs with, and it is\n' \
        "$0" >&2
    printf 'what says a file has arrived. Install inotify-tools.\n' >&2
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

# How long the run took, to whatever precision the clock above has. Wall
# clock, so a clock stepped backwards mid-run reports a negative duration --
# nothing a shell can do about that, and better in the line than hidden.
elapsed() {
    awk -v from="$1" -v to="$2" -v places="$places" \
        'BEGIN { printf "%." places "f", to - from }'
}

# What this folder says about one file, in the format its policy asked for.
# On stdout, because stdout is the journal under both service managers; the
# sentences on stderr are the watcher's own troubles rather than a record of
# a file.
log_line() {
    log_name=$1
    log_bucket=$2
    log_status=$3
    log_stamp=$4
    log_duration=$5
    log_message=$6

    if [ -z "$log_json" ]; then
        printf '%s: %s (%s)\n' "$log_name" "$log_bucket" "$log_status"
        return 0
    fi

    # One object, one line, with every string escaped. A hot folder takes its
    # filenames from strangers and impose's sentence carries whatever QPDF
    # said, so a quote, a backslash or a tab in either would otherwise write
    # a line nothing downstream can parse.
    #
    # The values travel through the environment and not through `awk -v`,
    # which expands backslash escapes in what it is handed: a file called
    # `a\nb.pdf` would come out of -v with a real newline in the middle of
    # it. ENVIRON is the one way in that passes bytes through untouched.
    #
    # POSIX awk and nothing more, because which awk a folder gets is not up
    # to it: measured with one-true-awk 20200816, mawk 1.3.4 and gawk 5.4.1,
    # the same line out of all three. An Ubuntu service gets mawk.
    IMPOSE_LOG_STAMP=$log_stamp \
        IMPOSE_LOG_FOLDER=$root \
        IMPOSE_LOG_FILE=$log_name \
        IMPOSE_LOG_BUCKET=$log_bucket \
        IMPOSE_LOG_EXIT=$log_status \
        IMPOSE_LOG_DURATION=$log_duration \
        IMPOSE_LOG_MESSAGE=$log_message \
        awk '
        function escape(raw,    out, i, c) {
            out = ""
            for (i = 1; i <= length(raw); i++) {
                c = substr(raw, i, 1)
                out = out ((c in escaped) ? escaped[c] : c)
            }
            return out
        }
        BEGIN {
            # Every C0 control first, since JSON allows none of them raw in a
            # string, then the five with a shorter spelling and the two that
            # have to be escaped whatever they are.
            for (i = 1; i < 32; i++) {
                escaped[sprintf("%c", i)] = sprintf("\\u%04x", i)
            }
            escaped["\b"] = "\\b"
            escaped["\t"] = "\\t"
            escaped["\n"] = "\\n"
            escaped["\f"] = "\\f"
            escaped["\r"] = "\\r"
            escaped["\""] = "\\\""
            escaped["\\"] = "\\\\"

            # The timestamp, the bucket and the status are written by this
            # script and cannot need escaping. The other three are not.
            printf "{\"timestamp\":\"%s\",\"folder\":\"%s\",\"file\":\"%s\"," \
                "\"bucket\":\"%s\",\"exit\":%s,\"duration\":%s," \
                "\"message\":\"%s\"}\n", \
                ENVIRON["IMPOSE_LOG_STAMP"], \
                escape(ENVIRON["IMPOSE_LOG_FOLDER"]), \
                escape(ENVIRON["IMPOSE_LOG_FILE"]), \
                ENVIRON["IMPOSE_LOG_BUCKET"], \
                ENVIRON["IMPOSE_LOG_EXIT"], \
                ENVIRON["IMPOSE_LOG_DURATION"], \
                escape(ENVIRON["IMPOSE_LOG_MESSAGE"])
        }'
}

# Impose a file already claimed into `work/`, and file it by what happened.
impose_claimed() {
    name=$1
    status=0
    proof_file=""
    if [ -n "$proofs" ]; then
        proof_file="$proofs/$name"
    fi

    # One call, two readings of the same instant: the wall clock for the line
    # and the same moment as a number to subtract. The pair brackets the
    # impose run and nothing else -- not the claim, not the filing, and in
    # the fswatch script not the wait for the file to settle either, because
    # what a shop asks of this number is how long the job took.
    clocked=$(date -u +"%Y-%m-%dT%H:%M:%SZ $clock")
    stamp=${clocked% *}
    started=${clocked#* }
    message=$(impose_it "$work/$name" "$out/$name" "$proof_file" 2>&1) || status=$?
    duration=$(elapsed "$started" "$(date -u +"$clock")")

    # The status says which bucket; the sentence says why. Both go with the
    # file, because whoever opens that folder wants to know without digging
    # through a log.
    #
    # Quoted, all three, because an unquoted `done` reads to shellcheck as
    # the end of a loop (SC1010) and the three are one set.
    case $status in
    0) bucket="done" ;;
    1 | 3) bucket="rejected" ;; # the file or the job: do not retry
    *) bucket="failed" ;;       # the environment: fix it and run it again
    esac

    # Guarded, and this is not pedantry: `set -eu` makes an unguarded failure
    # here exit the whole script, so one file that cannot be filed -- a full
    # disk, a folder somebody chmodded -- would stop the watcher dead and
    # quietly. Leave it in `work/` instead, say so, and carry on; the next
    # start sweeps it up.
    #
    # Filed with `ln` and not `mv`, for the reason the claim is: `mv` replaces
    # whatever already has the name and says nothing. Measured before this:
    # `book.pdf` sent, its press file collected, and a corrected `book.pdf`
    # sent after it -- two lines saying `done (0)`, one file in `done/`, and
    # the artwork that was actually printed gone. So a name that is taken is
    # left alone and this file goes in beside it, with the moment its run
    # started in its name.
    filed=$name
    tries=1
    while ! ln "$work/$name" "$root/$bucket/$filed" 2>/dev/null; do
        if { [ ! -e "$root/$bucket/$filed" ] && [ ! -L "$root/$bucket/$filed" ]; } ||
            [ "$tries" -gt 99 ]; then
            printf '%s: imposed with status %s, but cannot be filed into %s/ -- left in work/\n' \
                "$name" "$status" "$bucket" >&2
            return 1
        fi
        suffix=$(printf '%s' "$stamp" | tr -d ':-')
        [ "$tries" -gt 1 ] && suffix="$suffix-$tries"
        case $name in
        *.*) filed="${name%.*}.$suffix.${name##*.}" ;;
        *) filed="$name.$suffix" ;;
        esac
        tries=$((tries + 1))
    done
    rm -f "$work/$name" || true
    if [ "$filed" != "$name" ]; then
        printf '%s: %s/ already holds a file of that name, so this one is filed as %s\n' \
            "$name" "$bucket" "$filed" >&2
    fi

    # What impose said, beside the file -- and nothing beside it when impose
    # said nothing, which is `-q` in the policy. A sentence left there by an
    # earlier file of the same name would otherwise read as this one's.
    if [ -n "$message" ]; then
        printf '%s\n' "$message" >"$root/$bucket/$filed.txt"
    else
        rm -f "$root/$bucket/$filed.txt"
    fi
    log_line "$name" "$bucket" "$status" "$stamp" "$duration" "$message"
    return 0
}

# Whether a path is an ordinary file: not a directory, not a pipe or a device,
# and not a link to anything. `-f` alone follows a link, which is how a
# symbolic link dropped into the inbox was imposed as though the file it
# points at had been sent -- measured, `done (0)`, for a file that was never
# in this folder. An SFTP client can make one, and what it points at is then
# read with this service's permissions. A pipe is the other half: nothing
# reads a page out of one, impose waits on it for good, and every file behind
# it waits too (measured: eight seconds, nothing logged, the next file still
# in the inbox).
ordinary() {
    [ -f "$1" ] && [ ! -L "$1" ]
}

# Take something that is not an ordinary file back out of `work/`. It got
# there by changing between being looked at and being claimed, which no
# upload does by accident, or it was put there by hand. Removing it removes
# the link or the pipe and never what a link points at.
discard() {
    rm -f "$work/$1"
    printf '%s: not an ordinary file once claimed -- a link or a pipe under a PDF'"'"'s name. Removed, not imposed.\n' \
        "$1" >&2
}

# Claim one name out of the inbox, then impose it.
handle() {
    name=$1
    # Which names are artwork. Any spelling of the extension, because a file
    # saved as `Cover.Pdf` on Windows is a PDF to whoever sent it, and one
    # that matched nothing here sat in the inbox for good with no line
    # anywhere saying why (measured). And nothing that starts with a dot:
    # those are what a Mac leaves beside a file on a share (`._book.pdf`) and
    # what an upload is called while it is still arriving.
    #
    # A name that is not artwork is left exactly where it is, and that is
    # deliberate. Most of them are an upload under its temporary name --
    # `book.pdf.part`, `book.pdf.filepart` -- which the client is about to
    # rename, and a watcher that moved it away would break the upload it was
    # waiting for. What does not belong is named by the sweep at each start.
    case "$name" in
    .*) return 0 ;;
    *.[Pp][Dd][Ff]) ;;
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
    #
    # Looked at before and after. Before, so that a link or a pipe is left
    # where it is like anything else that is not artwork. After, because the
    # look and the link are two steps and the inbox is open to whoever sends
    # work: what is in `work/` is what was claimed, and nobody else can write
    # there.
    ordinary "$in/$name" || return 0
    ln "$in/$name" "$work/$name" 2>/dev/null || return 0
    rm -f "$in/$name"
    ordinary "$work/$name" || {
        discard "$name"
        return 0
    }
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
        [ -e "$path" ] || [ -L "$path" ] || continue
        name=${path##*/}
        ordinary "$path" || {
            discard "$name"
            continue
        }
        printf '%s: left over from an earlier run; imposing it now\n' "$name" >&2
        impose_claimed "$name" || true
    done
    for path in "$in"/*; do
        # The pattern itself, when the inbox is empty.
        [ -e "$path" ] || [ -L "$path" ] || continue
        case ${path##*/} in
        *.[Pp][Dd][Ff])
            if ordinary "$path"; then
                handle "${path##*/}" || true
                continue
            fi
            ;;
        esac
        # Said once a start rather than once an event: an upload passing
        # through under its temporary name is not worth a line, and something
        # that is still here at the next start is.
        printf '%s: left in in/, which takes an ordinary file whose name ends in .pdf and nothing else\n' \
            "${path##*/}" >&2
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
    # `IFS=`, or `read` trims the name: ` cover.pdf`, with the space a
    # careless rename leaves, was looked for as `cover.pdf`, not found,
    # and left in the inbox until the next restart swept it (measured).
    while IFS= read -r name; do
        owned || break
        handle "$name" || true
    done
}

# Reached only when the pipeline has ended, and the only way it ends is the
# event source going away: killed, crashed, or its watch torn down with the
# mount under it. A stop signal does not get here -- its trap leaves first,
# with the signal's own status.
#
# This has to be said, and with a status that is not 0. Without it the script
# fell off its own end: measured under systemd 255 with inotifywait killed,
# "Deactivated successfully", no restart, and the next file left sitting in
# the inbox with nothing wrong anywhere a person would look. A status of 0 is
# the one `Restart=on-failure` is told not to restart on.
if owned; then
    printf '%s: the event source ended, so nothing is watching %s.\n' \
        "$0" "$root" >&2
else
    printf '%s: %s is held by another watcher now, so this one is leaving.\n' \
        "$0" "$root" >&2
fi
exit 1
