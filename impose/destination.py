# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

"""Where the work gets written.

A press file appears under its final name the moment writing starts, and it
grows there for as long as the write takes. Anything watching that folder --
a RIP hot folder, a queue, the next step of a shop's own plumbing -- can
pick it up half written, and a half-written PDF is a file that opens and is
wrong, which is the expensive kind.

So a document is written beside its destination under a temporary name and
moved onto it when it is whole. The move is a rename within one directory,
which is the one filesystem operation that either happened or did not.

A stream is passed through untouched: a caller who handed over a buffer owns
the timing already. So is a device, because ``os.replace`` onto ``/dev/null``
would replace the device.
"""

from __future__ import annotations

import contextlib
import os
import pathlib
import shutil

from . import DestinationError


def is_pass_through(destination) -> bool:
    """Whether *destination* is written directly rather than moved into place.

    A stream -- anything with ``write`` -- and an existing character device,
    fifo or block device. Everything else is a path this module will write
    beside and rename onto.
    """
    if hasattr(destination, "write"):
        return True
    path = pathlib.Path(destination)
    try:
        return path.is_char_device() or path.is_fifo() or path.is_block_device()
    except OSError:
        # A path we cannot stat is not a device we need to protect; let the
        # write itself produce the error, with its own errno in it.
        return False


@contextlib.contextmanager
def writing(destination):
    """Yield what to write to, leaving *destination* whole or untouched.

    For a path: a temporary file beside it, renamed onto the destination when
    the block completes, and removed if the block raises. Nothing ever
    observes the destination at a partial size.

    The temporary is a dotfile ending ``.tmp`` in the destination's own
    directory -- it has to share the filesystem for the rename to be atomic
    -- so a watcher on that directory should match the extension it wants
    rather than everything that appears.

    Note what this does *not* do: it does not reserve the name. Two runs
    writing one destination still race, and the last rename wins. One watched
    folder writing into its own output directory does not have that problem,
    and :func:`reserve` refuses the overwrite that would make it one.
    """
    if is_pass_through(destination):
        yield destination
        return
    final = pathlib.Path(destination)
    temporary = final.parent / f".{final.name}.impose-{os.getpid()}.tmp"
    try:
        # Exclusive creation: two runs of ours in one directory get distinct
        # names from the pid, and anything already at this name is a leftover
        # we should not silently write over.
        os.close(os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644))
    except OSError as error:
        raise DestinationError(
            f"Cannot write beside {final}: {error}. The press file is written "
            f"to a temporary name in its own directory and moved into place, "
            f"so that directory has to be writable."
        ) from error
    try:
        yield temporary
        if final.exists():
            # Keep the mode and times of the file being replaced: a shop that
            # has set permissions on an output folder means them.
            shutil.copystat(final, temporary)
        os.replace(temporary, final)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


#: How each path of a run is named in a refusal, by the keyword it arrives as.
_ROLES = {
    "source": "file being imposed",
    "output": "press file",
    "proof": "proof",
    "record": "job file",
}


def reserve(destination, *, what: str = "press file", overwrite: bool = False) -> None:
    """Refuse *destination* if something is already there.

    A shop resends a job under the name it sent it under the first time, and
    the second arrival is usually a correction -- but sometimes the first one
    is already on the press, and replacing it silently loses the only record
    of what was printed. So an existing file is a refusal, not a decision to
    make quietly.

    A stream and a device are never a clobber, and pass.
    """
    if overwrite or destination is None or is_pass_through(destination):
        return
    path = pathlib.Path(destination)
    if not path.exists():
        return
    raise DestinationError(
        f"{path} is already there, and that {what} is not replaced without "
        f"being asked: the file now at that name may be the one already on "
        f"the press. Write to another name, or ask for it to be overwritten."
    )


def check_distinct(**paths) -> None:
    """Refuse a run that names one file for two jobs.

    Chiefly ``-o`` pointing at the input, which imposed the artwork over the
    top of itself and reported success -- the renderer builds a fresh
    document, so nothing underneath noticed that the file it had read was the
    file it was writing.
    """
    # Only things that name a place on disk. A source may be an open
    # document and an output may be a buffer; neither can collide with a
    # path, and neither is a path to compare.
    named = [
        (role, pathlib.Path(value))
        for role, value in paths.items()
        if isinstance(value, (str, os.PathLike))
    ]
    for index, (role, path) in enumerate(named):
        for other_role, other in named[index + 1 :]:
            if not _same_file(path, other):
                continue
            if "source" in (role, other_role):
                raise DestinationError(
                    f"{path} is both the {_ROLES[role]} and the "
                    f"{_ROLES[other_role]}. Imposing it would write the "
                    f"sheets over the artwork they are made from, and there "
                    f"is no undo."
                )
            raise DestinationError(
                f"{path} is named as both the {_ROLES[role]} and the "
                f"{_ROLES[other_role]}. One of them would survive the run."
            )


def _same_file(path: pathlib.Path, other: pathlib.Path) -> bool:
    """Whether two paths are one file.

    ``samefile`` when both exist, because that follows links and mount
    points; the resolved names otherwise, since a file not yet written
    cannot be compared by inode.
    """
    try:
        if path.exists() and other.exists():
            return path.samefile(other)
    except OSError:
        return False
    return path.resolve() == other.resolve()
