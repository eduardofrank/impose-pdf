# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

"""The `impose-hotfolder` command.

It hands over the four files in this directory and does nothing else. No
folder is created, no service is installed, nothing is written outside the
directory asked for: what belongs in /usr/local/libexec or /etc/systemd is a
copy somebody has read, and a command that put one there unread would be
making the decision this package deliberately leaves to the shop.

So there are three things it does. It says what ships and which of it suits
this machine; it prints one file's path, for the `install -m 755 "$(...)"`
line that is the whole reason an entry point is better than a URL; and it
copies the lot into a directory you name, which is what you want when you are
about to change them.
"""

from __future__ import annotations

import argparse
import dataclasses
import pathlib
import sys
from collections.abc import Sequence

from .. import DestinationError, __version__

#: Where the files are: beside this module, inside the installed package.
HERE = pathlib.Path(__file__).resolve().parent


@dataclasses.dataclass(frozen=True)
class Bundled:
    """One file that ships with the package.

    *platform* is :data:`sys.platform` for the machine it is for, because the
    pair a shop needs is decided by the kernel's event interface -- inotify or
    FSEvents -- and not by taste.
    """

    name: str
    what: str
    platform: str

    @property
    def path(self) -> pathlib.Path:
        """The file inside this install."""
        return HERE / self.name

    @property
    def mode(self) -> int:
        """The mode a copy is written with.

        Taken from the name, not from the file it is copied from, so that it
        does not depend on how that file arrived. A wheel does carry the
        executable bit -- measured: built from this tree, pip-installed into
        a fresh virtual environment, both scripts land 0755 -- but a checkout
        on a filesystem with no mode bits does not, and a watcher that
        reaches /usr/local/libexec at 0644 is an `ExecStart=` systemd cannot
        start.
        """
        return 0o755 if self.name.endswith(".sh") else 0o644


#: What ships, in the order a folder is built: the watcher first, then the
#: thing that keeps it running.
FILES = (
    Bundled(
        "watch-inotify.sh",
        "the watcher, for Linux; needs inotify-tools",
        "linux",
    ),
    Bundled(
        "watch-fswatch.sh",
        "the watcher, for macOS; needs fswatch",
        "darwin",
    ),
    Bundled(
        "impose-folder@.service",
        "a systemd unit, one instance per folder",
        "linux",
    ),
    Bundled(
        "impose-folder.plist",
        "a launchd agent, one copy per folder",
        "darwin",
    ),
)

NAMES = tuple(bundled.name for bundled in FILES)


def find(name: str) -> Bundled:
    """The bundled file called *name*."""
    for bundled in FILES:
        if bundled.name == name:
            return bundled
    raise KeyError(name)


def require(bundled: Bundled) -> pathlib.Path:
    """The file, or a sentence naming the install that has not got it.

    Nothing here reaches a shop with a file missing -- the tests check the
    catalogue against the directory -- but a repackager can, and a `--path`
    that answered with a path to nothing would be found out by `install`
    saying `cannot stat`, three steps further on and about the wrong thing.
    """
    if not bundled.path.is_file():
        raise FileNotFoundError(
            f"{bundled.name} is not in this install: {bundled.path} is not "
            f"there. These four ship as package data, so an install without "
            f"one of them was built without it."
        )
    return bundled.path


def build_parser() -> argparse.ArgumentParser:
    """The whole command line."""
    parser = argparse.ArgumentParser(
        prog="impose-hotfolder",
        description=(
            "The watcher scripts and service templates that ship with "
            "impose. Run it with no arguments to see what there is."
        ),
        epilog=(
            "They are worked examples to adapt, not supported code. "
            "RUNNING.md in the project is the procedure they belong to."
        ),
    )
    parser.add_argument("--version", action="version", version=f"impose {__version__}")
    one_thing = parser.add_mutually_exclusive_group()
    one_thing.add_argument(
        "--path",
        metavar="NAME",
        choices=NAMES,
        help=(
            "Print where one of them is in this install, and nothing else, "
            "so that it can be the argument to install(1): sudo install -m "
            '755 "$(impose-hotfolder --path watch-inotify.sh)" '
            "/usr/local/libexec/impose-watch."
        ),
    )
    one_thing.add_argument(
        "--install",
        metavar="DIRECTORY",
        type=pathlib.Path,
        help=(
            "Copy all four into DIRECTORY, which is made if it is not there. "
            "The scripts are written 0755 and the templates 0644. A file "
            "already at one of those names is a refusal, not a decision to "
            "make quietly -- say --overwrite if replacing it is what you "
            "mean."
        ),
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace files --install would otherwise refuse to write over.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command line. Returns the process exit status.

    The statuses are the ones the `impose` command uses, because something
    driving both unattended should route them the same way: 4 is a
    destination to clear, 2 is this command refusing to do anything.
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.overwrite and args.install is None:
        # Not silently ignored: --overwrite on its own is somebody expecting
        # files to be written, and nothing here would write any.
        parser.error(
            "--overwrite is about the copies --install makes, and there is no --install here"
        )
    try:
        if args.path is not None:
            print(require(find(args.path)))
            return 0
        if args.install is not None:
            return _install(args.install, sys.stdout, overwrite=args.overwrite)
        return _list(sys.stdout, platform=sys.platform)
    except DestinationError as error:
        return _failed(error, 4)
    # Everything the destination can do to a copy: a directory that cannot be
    # made, a volume that is full, a permission somebody has to fix.
    except OSError as error:
        return _failed(error, 4)


def _failed(error: Exception, status: int) -> int:
    """Report *error* as one line, and be the status it exits with."""
    print(f"impose-hotfolder: {error}", file=sys.stderr)
    return status


def _install(directory: pathlib.Path, out, *, overwrite: bool) -> int:
    """Copy every bundled file into *directory*."""
    directory.mkdir(parents=True, exist_ok=True)
    copies = [(bundled, directory / bundled.name) for bundled in FILES]
    # Every name checked before any is written. Refusing part way through
    # would leave the directory holding two files of four, and the operator
    # reading one sentence about one of them.
    #
    # Not impose.destination.reserve, which is the same refusal at the same
    # exit status: its sentence is about a press file that may be the one on
    # the press, and read over a watcher script somebody has edited that is
    # a non sequitur. The refusal is the shared part; the reason is not.
    for bundled, destination in copies:
        require(bundled)
        if destination.exists() and not overwrite:
            raise DestinationError(
                f"{destination} is already there, and the copy is not "
                f"written over it without being asked: what is at that name "
                f"may be the one you have already changed. Say --overwrite, "
                f"or name a directory of its own."
            )
    for bundled, destination in copies:
        destination.write_bytes(bundled.path.read_bytes())
        destination.chmod(bundled.mode)
        print(f"wrote {destination}", file=out)
    return 0


def _list(out, *, platform: str) -> int:
    """Say what ships, where it is, and what to do with it."""
    print(f"The hot-folder files are in this install, in\n{HERE}:\n", file=out)
    name_width = max(len(bundled.name) for bundled in FILES)
    # The marker is a column of its own, so that `what suits this machine` is
    # read down the right-hand side rather than hunted for.
    what_width = max(len(bundled.what) for bundled in FILES)
    for bundled in FILES:
        here = "  <- this machine" if bundled.platform == platform else ""
        name = f"{bundled.name:<{name_width}}"
        what = f"{bundled.what:<{what_width}}" if here else bundled.what
        print(f"  {name}  {what}{here}", file=out)
    print(
        "\nThey are worked examples, not supported code: what a folder is for\n"
        "is yours to say, and these are the shape to start from. Read one\n"
        "before you run it.",
        file=out,
    )
    watcher = next(
        (
            bundled
            for bundled in FILES
            if bundled.platform == platform and bundled.name.endswith(".sh")
        ),
        None,
    )
    if watcher is None:
        print(
            f"\nNeither watcher is for this machine ({platform}). They are an\n"
            "inotify script and an FSEvents script, so a folder here wants a\n"
            "third one -- the exit statuses it has to route are in RUNNING.md.",
            file=out,
        )
    else:
        print(
            "\nPut the watcher where both templates expect it:\n\n"
            f'    sudo install -m 755 "$(impose-hotfolder --path {watcher.name})" \\\n'
            "        /usr/local/libexec/impose-watch",
            file=out,
        )
    print(
        "\nOr take a copy of all four, to read and change:\n\n"
        "    impose-hotfolder --install ~/impose-hotfolder",
        file=out,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
