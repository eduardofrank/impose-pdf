#!/bin/bash
# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE.
#
# bash, not sh: reading fswatch's null-separated output needs `read -d`, and
# a filename is the one thing a hot folder cannot promise is well behaved.
#
# Impose every PDF dropped into a folder, on macOS, with fswatch.
#
#     impose-watch ~/impose/a4-nup
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
# It ships inside the package, which `impose-hotfolder` is the way into, and
# is a worked example to adapt rather than a supported product. Put it under
# launchd -- `impose-folder.plist`, beside it, is an agent for one folder.
#
# Exit 2 is this script refusing to start, and nothing else is: the folder is
# not set up, and starting it again changes nothing until that is fixed. Exit
# 1 is the event source ending under a folder that was running. It never
# leaves with 0, which launchd is told means there is nothing to restart.

set -eu

# Asked rather than left to `${1:?}`, whose status is the shell's and is 1
# under bash: see watch-inotify.sh.
if [ -z "${1:-}" ]; then
    printf 'usage: %s FOLDER\n' "$0" >&2
    exit 2
fi
root=$1
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

# How this folder says what it did, one line per file either way. The
# default, text, is `book.pdf: done (0)`, written for whoever is reading the
# log. json is one object per file -- when it ran, which folder, which file,
# which bucket, impose's exit status, how long impose took, and what it said
# -- for when something other than a person is reading. The watcher's own
# sentences become objects too, with no bucket.
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
    LOG_FORMAT) LOG_FORMAT=$value ;;
    TIMEOUT) TIMEOUT=$value ;;
    *)
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

# A format nobody implements is named rather than ignored, and the clock is
# settled once rather than per file: see watch-inotify.sh for both.
case $LOG_FORMAT in
'' | text) log_json= ;;
json) log_json=yes ;;
*)
    printf '%s: %s: LOG_FORMAT=%s is not a format this writes.\n' \
        "$0" "$policy" "$LOG_FORMAT" >&2
    printf 'Say text, the default, which is one line a file for a person; or\n' >&2
    printf 'json, which is one object a file for whatever reads the log.\n' >&2
    exit 2
    ;;
esac

# One string as a JSON string, quotes and all, and what the watcher says on its
# own account, in the format the policy asked for: see watch-inotify.sh, which
# carries the commentary on escaping, on why the value reaches awk through the
# environment, and on what a json line from `say` holds.
json_string() {
    IMPOSE_JSON_RAW=$1 awk '
    BEGIN {
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
        raw = ENVIRON["IMPOSE_JSON_RAW"]
        out = ""
        for (i = 1; i <= length(raw); i++) {
            c = substr(raw, i, 1)
            out = out ((c in escaped) ? escaped[c] : c)
        }
        printf "\"%s\"", out
    }'
}

say() {
    local file=$1 format=$2 text
    shift 2
    if [ -n "$log_json" ]; then
        format=$(printf '%s' "$format" | sed 's/\\n/ /g')
    fi
    # The format is this script's own, never a filename or anything sent.
    # shellcheck disable=SC2059
    text=$(printf "$format" "$@")
    if [ -z "$log_json" ]; then
        printf '%s: %s\n' "${file:-$0}" "$text" >&2
        return 0
    fi
    if [ -n "$file" ]; then
        file=$(json_string "$file")
    else
        file=null
    fi
    printf '{"timestamp":"%s","folder":%s,"file":%s,"message":%s}\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$(json_string "$root")" \
        "$file" "$(json_string "$text")" >&2
}

# A limit on one run, enforced by GNU timeout: see watch-inotify.sh for why
# that and not a watchdog written here. On macOS it is `gtimeout`, from
# Homebrew's coreutils.
limiter=
case $TIMEOUT in
'') ;;
*[!0-9]* | 0*)
    say "" '%s: TIMEOUT=%s is not a whole number of seconds.' \
        "$policy" "$TIMEOUT"
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
        say "" '%s sets TIMEOUT, and there is no GNU timeout on the PATH this\nruns with to enforce it. Install coreutils -- gtimeout, from Homebrew,\nis the same thing -- or take the line out.' \
            "$policy"
        exit 2
    fi
    ;;
esac

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
        say "" '%s writes to %s, which is the inbox or inside it. The\nfolder would impose its own press files as artwork.' \
            "$policy" "$written"
        exit 2
        ;;
    esac
done

# And not the same directory as each other: the proof and the press file take
# the arriving file's name, so one directory for both is one name for both.
if [ -n "$proofs" ] && [ "$proofs" = "$out" ]; then
    say "" '%s writes the proofs and the press files both to %s, where\nthey would be one name. A proof wants a directory of its own --\nand out of the way of whatever is watching for press files.' \
        "$policy" "$out"
    exit 2
fi

# Made, not assumed: a proof directory exists only for a folder that asked
# for proofs, and a press file is not written into a directory nobody made.
if ! trouble=$(mkdir -p "$out" ${proofs:+"$proofs"} 2>&1); then
    say "" 'cannot make somewhere to write in %s:\n%s' "$root" "$trouble"
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
# parameters, with globbing off across the split.
impose_it() {
    local claimed=$1 press_file=$2 proof_file=$3
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

# Try the policy before trusting it to everything this folder is ever sent:
# a source that is not there is exit 3, so anything else is the options, the
# job file, or impose not being on this service's PATH. One sentence now
# rather than a `failed/` bucket with a copy of every file in it. launchd in
# particular hands a job a PATH of its own, which is how a watcher that works
# in a terminal files everything into failed/ as a service.
status=0
trouble=$(impose_it "$root/.impose-policy-check.pdf" /dev/null "" 2>&1) || status=$?
if [ "$status" != 3 ]; then
    say "" '%s does not describe a run this impose can make (exit %s):\n%s' \
        "$policy" "$status" "$trouble"
    exit 2
fi

# The event source, looked for before anything is claimed: see
# watch-inotify.sh. Without it the pipeline at the bottom sweeps once and
# stops, and the folder is never watched.
if ! command -v fswatch >/dev/null 2>&1; then
    say "" 'there is no fswatch on the PATH this runs with, and it is\nwhat says a file has arrived. brew install fswatch.'
    exit 2
fi

# One watcher per folder: see watch-inotify.sh. The sweep below treats `work/`
# as the debris of a run that died, which is only true for as long as nothing
# else is working this folder.
lock="$root/.watcher.lock"
if ! mkdir "$lock" 2>/dev/null; then
    held=$(cat "$lock/pid" 2>/dev/null || true)
    if [ -n "$held" ] && kill -0 "$held" 2>/dev/null; then
        say "" '%s is already being watched by pid %s.' "$root" "$held"
        exit 2
    fi
    say "" 'clearing a lock left by pid %s, which is no longer running.' \
        "${held:-unknown}"
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
            say "" 'cannot claim %s as this folder'"'"'s %s:\n%s' \
                "$directory" "$role" "$trouble"
            exit 2
        fi
        held=$(cat "$claim/pid" 2>/dev/null || true)
        holder=$(cat "$claim/folder" 2>/dev/null || true)
        if [ -n "$held" ] && kill -0 "$held" 2>/dev/null; then
            say "" '%s is already the %s of %s (pid %s).\nOne %s, one folder: two folders writing one directory\nwrite one file for every name that arrives in both, and two runs\nracing for that name both report success. Give this folder a\ndirectory of its own -- under that one, if a RIP reads it.' \
                "$directory" "$role" "${holder:-another folder}" "$held" "$role"
            exit 2
        fi
        say "" 'clearing a claim on %s left by pid %s, which is no longer running.' \
            "$directory" "${held:-unknown}"
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
    say "" 'cannot claim a file in %s:\n%s\nA file is claimed by hard-linking its name from in/ into work/,\nso linking has to work. Some SMB mounts and exFAT cannot link at\nall. Put the folder on a filesystem that can, or replace the\nclaim with your own.' \
        "$root" "$trouble"
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

# How long the run took, and what this folder says about one file: see
# watch-inotify.sh, which carries the commentary on the clock.
elapsed() {
    awk -v from="$1" -v to="$2" -v places="$places" \
        'BEGIN { printf "%." places "f", to - from }'
}

log_line() {
    local name=$1 bucket=$2 status=$3 stamp=$4 duration=$5 message=$6

    if [ -z "$log_json" ]; then
        printf '%s: %s (%s)\n' "$name" "$bucket" "$status"
        return 0
    fi

    printf '{"timestamp":"%s","folder":%s,"file":%s,"bucket":"%s","exit":%s,"duration":%s,"message":%s}\n' \
        "$stamp" "$(json_string "$root")" "$(json_string "$name")" \
        "$bucket" "$status" "$duration" "$(json_string "$message")"
}

# Impose a file already claimed into `work/`, and file it by what happened.
impose_claimed() {
    local name=$1 status=0 message bucket proof_file="" clocked stamp started
    local duration filed tries suffix
    if [ -n "$proofs" ]; then
        proof_file="$proofs/$name"
    fi

    # The pair brackets the impose run and nothing else -- not the wait for
    # the file to settle, which happens in `handle` before this is called,
    # because what a shop asks of this number is how long the job took.
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
    # whatever already has the name and says nothing. See watch-inotify.sh for
    # what that cost. So a name that is taken is left alone and this file goes
    # in beside it, with the moment its run started in its name.
    filed=$name
    tries=1
    while ! ln "$work/$name" "$root/$bucket/$filed" 2>/dev/null; do
        if { [ ! -e "$root/$bucket/$filed" ] && [ ! -L "$root/$bucket/$filed" ]; } ||
            [ "$tries" -gt 99 ]; then
            say "$name" 'imposed with status %s, but cannot be filed into %s/ -- left in work/' \
                "$status" "$bucket"
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
        say "$name" '%s/ already holds a file of that name, so this one is filed as %s' \
            "$bucket" "$filed"
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

# Whether a path is an ordinary file, and what becomes of a claimed one that
# is not: see watch-inotify.sh for what a link and a pipe each did here.
ordinary() {
    [ -f "$1" ] && [ ! -L "$1" ]
}

discard() {
    rm -f "$work/$1"
    say "$1" 'not an ordinary file once claimed -- a link or a pipe under a PDF'"'"'s name. Removed, not imposed.'
}

# Wait for the file to settle, claim the name, impose it. The settle wait sits
# in here rather than in the event loop so the sweep gets it too: a file
# already in the inbox when this starts may still be arriving.
handle() {
    local name=$1
    # Which names are artwork, and why the rest are left where they are: see
    # watch-inotify.sh.
    case "$name" in
    .*) return 0 ;;
    *.[Pp][Dd][Ff]) ;;
    *) return 0 ;;
    esac
    ordinary "$in/$name" || return 0
    settled "$in/$name" || return 0

    # `ln`, not `mv -n`: linking fails when the name is already claimed, which
    # is what makes it a claim. `mv -n` skips a taken destination and still
    # exits 0, so a duplicate event, or the ordinary resend of a filename
    # still being worked on, would sail past the check and impose a file this
    # run already holds. Whoever loses the link leaves the file alone.
    #
    # `-P`, because this `ln` follows a symbolic link unless told not to, and
    # a link swapped in after the look above would otherwise be claimed as the
    # file it points at. Then looked at again where nobody else can write.
    ln -P "$in/$name" "$work/$name" 2>/dev/null || return 0
    rm -f "$in/$name"
    ordinary "$work/$name" || {
        discard "$name"
        return 0
    }
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
        [ -e "$path" ] || [ -L "$path" ] || continue
        name=${path##*/}
        ordinary "$path" || {
            discard "$name"
            continue
        }
        say "$name" 'left over from an earlier run; imposing it now'
        # A run killed after writing its press file and before filing the
        # artwork: see watch-inotify.sh.
        if [ -e "$out/$name" ]; then
            say "$name" '%s already holds a press file of that name. If the earlier run was stopped\nafter writing it, that press file is whole and this will be failed (4): check it,\nand move the artwork from failed/ to done/ yourself.' \
                "$out"
        fi
        impose_claimed "$name" || true
    done
    sweep_inbox
}

# Every file in the inbox, handled as if its event had just come. Run at each
# start, and again whenever FSEvents asks for the inbox to be looked at
# rather than naming a file in it: see the loop at the bottom.
sweep_inbox() {
    local path
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
        # Said once a sweep rather than once an event: an upload passing
        # through under its temporary name is not worth a line, and something
        # that is still here at the next start is.
        say "${path##*/}" 'left in in/, which takes an ordinary file whose name ends in .pdf and nothing else'
    done
}

# The sweep runs inside the reader, not before the pipeline, so that fswatch
# is already watching while it works: anything arriving during the sweep waits
# in the pipe instead of falling down the gap between listing the folder and
# starting to watch it. An event for a file the sweep already took finds the
# name gone and costs nothing.
#
# Four event names, and `Renamed` is the one that matters most. FSEvents has
# no "moved to": a file renamed into the folder is reported as `Renamed` and
# nothing else, measured with `fswatch -x` on macOS --
#
#     seen/copied.pdf Created IsFile Updated
#     seen/renamed.pdf IsFile Renamed
#
# -- and a rename is how a finished upload arrives from anything careful: a
# temporary name while it is written, then its own. This asked for `MovedTo`,
# which is inotify's word, and so never heard of one; every such file waited
# for the next restart to sweep it up. `MovedTo` stays for a monitor that
# does say it. A rename out of the folder is `Renamed` too, and costs a look
# at a name that is no longer there.
#
# `PlatformSpecific` is the fifth, and it is how a dropped event is heard.
# When FSEvents loses events -- its own queue or the kernel's filled -- it
# sends one event flagged MustScanSubDirs, with UserDropped or KernelDropped,
# naming a directory to look through rather than a file. fswatch 1.22.0 maps
# all three flags to `PlatformSpecific` (fsevents_monitor.cpp, read rather
# than measured: no drop could be caused here to watch one arrive), so
# without asking for it the notice is filtered out and the files it was
# about wait for a restart, as they did on Linux before `q_overflow`.
#
# So each event comes with its flags (`-x`, comma-separated, after the last
# space), and its path is sorted rather than cut down to its last part. A file
# directly in the inbox is handled. Something deeper is inside a directory
# somebody dropped there, which is never artwork. Anything else -- the inbox
# itself, with or without a trailing slash, or a directory above it -- is
# looked through again if it carries `PlatformSpecific`, and left alone if it
# does not. A path in a spelling of the inbox not matched here is treated as
# every path was before: its last part is taken as a name. The flag is what matters: a file taken out of the inbox makes
# FSEvents report the inbox too, as `Created,AttributeModified,IsDir`
# (measured in CI), and a rescan for every file would be a journal line for
# every file. FSEvents reports real paths, so a folder under /var is heard as
# /private/var, and both spellings are matched.
inbox=$(cd "$in" && pwd)
inbox_real=$(cd "$in" && pwd -P)
fswatch -0 -x --event-flag-separator=, \
    --event Created --event MovedTo --event Renamed --event Updated \
    --event PlatformSpecific "$in" | {
    sweep
    # `IFS=`, or `read` trims the record even with `-d`: see watch-inotify.sh.
    while IFS= read -r -d "" record; do
        owned || break
        path=${record% *}
        case $path in
        "$inbox"/*/* | "$inbox_real"/*/*) continue ;;
        "$inbox"/?* | "$inbox_real"/?*)
            handle "${path##*/}" || true
            continue
            ;;
        esac
        case ,${record##* }, in
        *,PlatformSpecific,*)
            say "" 'FSEvents asked for %s to be looked through again, as it does after dropping events; doing so' \
                "$in"
            sweep_inbox
            ;;
        *)
            # The inbox itself, which is nothing to do; or a spelling of
            # its path neither `pwd` gave, which is what this loop did with
            # every event before it sorted them: take the last part as a
            # name, which costs a look if it is not one.
            case $path in
            "$inbox" | "$inbox/" | "$inbox_real" | "$inbox_real/") ;;
            *) handle "${path##*/}" || true ;;
            esac
            ;;
        esac
    done
}

# Reached only when the event source has gone away, and said with a status
# that is not 0: see watch-inotify.sh, where falling off this end was
# measured as a folder that stopped and reported success.
if owned; then
    say "" 'the event source ended, so nothing is watching %s.' "$root"
else
    say "" '%s is held by another watcher now, so this one is leaving.' "$root"
fi
exit 1
