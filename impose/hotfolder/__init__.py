# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

"""The hot-folder files, and the command that hands them over.

Four files that are not Python: two watcher scripts and the service templates
that run them. They are here, inside the package, for one reason -- an install
from a wheel has no checkout to copy them out of, and a shop that pip-installs
impose should not have to find this repository to get the folder half of it.

They are worked examples all the same. :mod:`impose.hotfolder.cli` prints
their paths and makes copies; it never writes them into /usr/local or
/etc/systemd, because what belongs there is the copy you have read and
changed.
"""
