# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

"""Run the command line with ``python -m impose``.

The guard matters: `python -m impose` imports this module *as* ``__main__``, so
the command still runs, while anything that merely imports the package -- a
doctest collector walking the modules, say -- does not find itself running the
command line against its own argv.
"""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
