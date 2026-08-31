# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

# pylint: disable=missing-class-docstring,missing-function-docstring

"""Perfect binding, checked by gathering the sections and reading them."""

import unittest

from impose.schemas import LEFT, RIGHT
from impose.schemas.perfect import impose

from .booklet import read_gathered


class TestReading(unittest.TestCase):
    def test_single_sheet_sections_read_in_order(self):
        plan = impose(8, section_pages=4)
        self.assertEqual(
            read_gathered(list(plan.surfaces), sheets_per_section=1), list(range(8))
        )

    def test_larger_sections_read_in_order(self):
        for section in (4, 8, 16, 32):
            for pages in (32, 64, 96):
                with self.subTest(section=section, pages=pages):
                    plan = impose(pages, section_pages=section)
                    self.assertEqual(
                        read_gathered(
                            list(plan.surfaces), sheets_per_section=section // 4
                        ),
                        list(range(pages)),
                    )

    def test_padded_documents_read_in_order_then_stop(self):
        for pages in (5, 17, 33):
            with self.subTest(pages=pages):
                plan = impose(pages, section_pages=16)
                self.assertEqual(
                    read_gathered(list(plan.surfaces), sheets_per_section=4),
                    list(range(pages)),
                )


class TestSections(unittest.TestCase):
    def test_sections_are_gathered_not_nested(self):
        """Section two starts after section one, rather than wrapping it."""
        plan = impose(8, section_pages=4)
        first, second = plan.surfaces[0], plan.surfaces[2]
        self.assertEqual(first.at(RIGHT, 0).source, 0)
        self.assertEqual(second.at(RIGHT, 0).source, 4)

    def test_pages_nest_within_a_section(self):
        plan = impose(8, section_pages=8)
        self.assertEqual(plan.surfaces[0].at(LEFT, 0).source, 7)

    def test_section_size_sets_the_sheet_count(self):
        self.assertEqual(impose(32, section_pages=4).sheets, 8)
        self.assertEqual(impose(32, section_pages=16).sheets, 8)

    def test_padding_rounds_up_to_a_whole_section(self):
        self.assertEqual(impose(17, section_pages=16).sheets, 8)

    def test_section_must_be_made_of_folded_sheets(self):
        for bad in (0, 2, 6, 10):
            with self.subTest(section_pages=bad), self.assertRaises(ValueError):
                impose(8, section_pages=bad)

    def test_every_page_imposed_exactly_once(self):
        for pages in (4, 17, 64):
            for section in (4, 8, 16):
                with self.subTest(pages=pages, section=section):
                    impose(pages, section_pages=section).validate()
