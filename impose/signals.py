# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

"""Being stopped from outside without leaving a mess.

Python does nothing at all with SIGTERM unasked: the interpreter stops where
it stands and no ``finally`` anywhere runs. That is how a service is ended --
``systemctl stop`` and ``launchctl`` both send it -- so an imposition killed
that way left the temporary it was writing to behind in the output directory,
a dotfile that a watcher matching ``*.pdf`` cannot see and that nothing ever
comes back for. Measured on a 20000-page run killed mid-write: 12.8 MB of
temporary files, and not a word on stderr.

Unwinding instead costs nothing and settles it, because
:func:`impose.destination.writing` already removes its temporary on the way
past anything that propagates.

This is the command line's business and not the library's. A library caller
owns its own signal policy, and a library that quietly took it over would be
doing something it has no right to do -- so nothing here runs unless it is
asked for. :func:`stopping_cleanly` is asked for by :mod:`impose.cli`, around
one run, and puts back what it found.
"""

from __future__ import annotations

import contextlib
import signal
import sys

#: What it means for somebody outside this process to stop a run. SIGHUP is a
#: terminal going away, and does not exist on Windows, so it is only asked for
#: where it is there.
STOP_SIGNALS = tuple(
    number
    for number in (
        getattr(signal, "SIGHUP", None),
        signal.SIGINT,
        signal.SIGTERM,
    )
    if number is not None
)


def stop(signum: int, _frame) -> None:
    """Leave on a stop signal, by unwinding rather than by stopping dead."""
    print(f"impose: stopped on {signal.Signals(signum).name}.", file=sys.stderr)
    # SystemExit, not a bare exit: it is raised in the main thread and travels
    # back up through everything that was running, which is the whole point.
    # 128 + n is the status a shell reports for a process killed by signal n,
    # so a watcher reads the same number whether it polls the status or
    # watches the process.
    sys.exit(128 + signum)


@contextlib.contextmanager
def stopping_cleanly():
    """Answer for the stop signals while a run is in progress, then stand down.

    Restores whatever was there before, so a caller that drives the command
    line in-process -- a test, an embedding application -- gets its own
    handling back. ``signal.signal`` works only in the main thread, so a
    caller driving it from another one keeps the behaviour it already had
    instead of being handed an error.
    """
    previous = []
    try:
        for number in STOP_SIGNALS:
            previous.append((number, signal.signal(number, stop)))
    except ValueError:
        pass
    try:
        yield
    finally:
        for number, handler in previous:
            signal.signal(number, handler)
