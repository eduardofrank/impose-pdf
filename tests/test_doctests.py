# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

"""Run every doctest in the package."""

import doctest
import importlib
import pkgutil

import impose


def load_tests(_loader, tests, _pattern):
    """Collect doctests from `impose` and each of its submodules."""
    tests.addTests(doctest.DocTestSuite(impose))
    for _finder, name, _ispkg in pkgutil.walk_packages(
        impose.__path__, prefix="impose."
    ):
        module = importlib.import_module(name)
        if module.__doc__ or vars(module):
            suite = doctest.DocTestSuite(module)
            if suite.countTestCases():
                tests.addTests(suite)
    return tests
