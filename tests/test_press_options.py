# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

# pylint: disable=missing-function-docstring

"""The press given at the command line, when no profile describes it.

The page written is the imageable area, so a border given in words is
measurable in the file: these check the figures arrive, not that the command
accepted them.
"""

import unittest

import pikepdf

from impose.press import margins_spec
from impose.units import to_mm

from .test_cli import run, workspace


class TestCustomPress(unittest.TestCase):
    """The machine in the room, when no profile describes it."""

    @staticmethod
    def _page(path):
        """The size of the first page written, in millimetres."""
        with pikepdf.open(path) as pdf:
            box = [float(value) for value in pdf.pages[0].mediabox]
        return (
            round(to_mm(box[2] - box[0]), 3),
            round(to_mm(box[3] - box[1]), 3),
        )

    def _impose(self, source, *extra):
        output = source.with_name("out.pdf")
        status, _, err = run(
            "nup", str(source), "-o", str(output), "--up", "2x1", *extra
        )
        self.assertEqual(status, 0, err)
        return self._page(output)

    def test_a_size_names_a_press_whose_whole_sheet_images(self):
        with workspace(pages=4) as source:
            self.assertEqual(
                self._impose(source, "--press", "320mmx450mm"), (320.0, 450.0)
            )

    def test_margins_come_off_the_sheet(self):
        with workspace(pages=4) as source:
            page = self._impose(
                source, "--press", "320mmx450mm", "--margins", "bottom=12mm,top=5mm"
            )
            self.assertEqual(page, (320.0, 433.0))

    def test_a_uniform_margin_is_every_edge(self):
        with workspace(pages=4) as source:
            page = self._impose(source, "--press", "320mmx450mm", "--margins", "5mm")
            self.assertEqual(page, (310.0, 440.0))

    def test_an_imageable_area_is_centred_in_the_sheet(self):
        with workspace(pages=4) as source:
            page = self._impose(
                source, "--press", "320mmx450mm", "--imageable", "310mmx440mm"
            )
            self.assertEqual(page, (310.0, 440.0))

    def test_margins_override_the_profile_they_are_given_with(self):
        with workspace(pages=4) as source:
            page = self._impose(source, "--press", "sra3", "--margins", "10mm")
            self.assertEqual(page, (300.0, 430.0))

    def test_the_gripper_edge_can_be_moved(self):
        with workspace(pages=4) as source:
            page = self._impose(
                source,
                "--press",
                "320mmx450mm",
                "--margins",
                "left=20mm",
                "--gripper",
                "left",
            )
            self.assertEqual(page, (300.0, 450.0))

    def test_fit_answers_for_the_same_press(self):
        status, text, err = run(
            "fit", "A6", "--press", "320mmx450mm", "--margins", "bottom=12mm"
        )
        self.assertEqual(status, 0, err)
        self.assertIn("320 × 438 mm", text)

    def test_an_edge_no_sheet_has_is_a_sentence(self):
        with workspace(pages=4) as source:
            status, _, err = run(
                "nup", str(source), "--up", "2x1", "--margins", "side=5mm"
            )
            self.assertEqual(status, 1)
            self.assertIn("not an edge of a sheet", err)
            self.assertNotIn("Traceback", err)

    def test_an_unknown_gripper_edge_is_rejected_by_the_parser(self):
        with workspace(pages=4) as source:
            status, _, err = run(
                "nup", str(source), "--up", "2x1", "--gripper", "north"
            )
            self.assertEqual(status, 2)
            self.assertIn("north", err)

    def test_an_imageable_area_and_margins_together_is_a_sentence(self):
        with workspace(pages=4) as source:
            status, _, err = run(
                "nup",
                str(source),
                "--up",
                "2x1",
                "--imageable",
                "A3",
                "--margins",
                "5mm",
            )
            self.assertEqual(status, 1)
            self.assertIn("not both", err)

    def test_a_border_leaving_nothing_names_the_sheet(self):
        with workspace(pages=4) as source:
            status, _, err = run(
                "nup",
                str(source),
                "--up",
                "2x1",
                "--press",
                "100mmx100mm",
                "--margins",
                "60mm",
            )
            self.assertEqual(status, 1)
            self.assertIn("100 × 100 mm", err)

    def test_the_cover_command_takes_the_same_press(self):
        with workspace(pages=8) as source:
            output = source.with_name("cover.pdf")
            status, _, err = run(
                "cover",
                str(source),
                "--paper-caliper",
                "0.1mm",
                "-o",
                str(output),
                "--press",
                "320mmx450mm",
                "--margins",
                "bottom=12mm,top=5mm",
            )
            self.assertEqual(status, 0, err)
            self.assertEqual(self._page(output), (320.0, 433.0))

    def test_margins_parser(self):
        self.assertEqual(margins_spec("5mm"), "5mm")
        self.assertEqual(
            margins_spec("bottom=12mm, top=5mm"), {"bottom": "12mm", "top": "5mm"}
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
