# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE.

"""What a run comes back as: a status, and a sentence for whoever fixes it.

Every failure becomes a status and a sentence. The statuses are three
different people's problems: 3 is a file to send back, 1 is a job to
describe differently, 4 is a shelf somebody has to clear -- which is the
one worth retrying once it is cleared. They are taken from the exception
class and never from the message, because the messages here get reworded
and something driving this unattended has to keep routing the same way.

A fourth person is whoever maintains impose, and theirs is 70: an
exception nothing here expected, which is a fault in the program and says
nothing about the file or the job.

This is the command line's and not the library's. A library caller gets the
exception, which says more than a number does.
"""

from __future__ import annotations

import sys
import traceback
from collections.abc import Callable

from . import DestinationError, ImposeError, SourceError

#: The status for a fault in impose itself. It is ``EX_SOFTWARE``, "an
#: internal software error", from BSD's sysexits.h, spelt as a number because
#: ``os.EX_SOFTWARE`` is not there on Windows. What matters about it is what
#: it is not: 1 or 3, which a watcher files as the customer's to fix.
FAULT = 70


def answered(run: Callable[[], int]) -> int:
    """Call *run*, and be its status -- or the status for what it raised."""
    try:
        return run()
    # The order is the class hierarchy: the first two are an ImposeError,
    # so the general case has to come last or it would answer for all
    # three.
    except SourceError as error:
        return _failed(error, 3)
    except DestinationError as error:
        return _failed(error, 4)
    # ValueError as well as ImposeError: a schema rejects an impossible
    # request with one, and whichever it is, the person at the terminal
    # asked for something that cannot be done and should be told so in a
    # sentence.
    except (ImposeError, ValueError) as error:
        return _failed(error, 1)
    # Everything that opens a source goes through impose.source, which
    # turns its own OSError into a SourceError, so what reaches here is
    # the other end: a directory that is not there, a volume that is
    # full, a permission on a folder somebody has to fix.
    except OSError as error:
        return _failed(error, 4)
    # What is left is a mistake in impose, or in something under it, and
    # the one thing known about it is that nobody decided it. Left to
    # Python it exits 1, which is the status for a job described wrongly:
    # a watched folder files the artwork in rejected/, to be sent back to
    # a customer who did nothing, with a stack trace beside it for a
    # reason. So it gets a status of its own and the sentence first, and
    # the stack after the sentence, because the stack is the only part of
    # this that whoever fixes it can use. Exception and not BaseException:
    # being stopped is SystemExit, and that one was decided.
    except Exception as error:  # pylint: disable=broad-exception-caught
        return _faulted(error)


def _failed(error: Exception, status: int) -> int:
    """Report *error* as one line, and be the status it exits with."""
    print(f"impose: {error}", file=sys.stderr)
    return status


def _faulted(error: Exception) -> int:
    """Report an exception nobody expected, and be the status for one."""
    print(
        f"impose: this is a fault in impose, and not in the file or in the way "
        f"the job is described: {type(error).__name__}: {error}. Running it "
        f"again unchanged will do the same. What follows is the part to send "
        f"to whoever maintains impose.",
        file=sys.stderr,
    )
    traceback.print_exception(error, file=sys.stderr)
    return FAULT
