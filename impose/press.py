# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

"""Presses: the sheet a machine takes, and the part of it that can carry ink.

Two facts decide whether a form can be run. The press takes a sheet up to some
size, and it cannot image the whole of it: the grippers hold the lead edge, and
that strip stays blank. The blank border is not the same on all four edges, and
a model that centres an imageable area inside the sheet quietly misplaces every
job by half the difference.

The gripper edge is also the edge that goes into the machine first, so it is
fixed with respect to the sheet, not to the artwork. Turning a form to make it
fit turns the form, never the gripper.

Nominal figures are given for the models below, but a press is a physical
machine with its own history. Confirm against yours before committing a job,
and override with an explicit sheet and margins where they differ.
"""

from __future__ import annotations

import dataclasses
from typing import Literal

from . import ImposeError
from .geometry import Insets, Rect, Size
from .units import MM, format_mm, length, paper, to_mm

Edge = Literal["bottom", "top", "left", "right"]


@dataclasses.dataclass(frozen=True, slots=True)
class Press:
    """A press: the largest sheet it takes and the border it cannot image."""

    name: str
    sheet: Size
    margins: Insets
    gripper: Edge = "bottom"
    description: str = ""
    min_sheet: Size | None = None

    def __post_init__(self) -> None:
        area = self.imageable_area(self.sheet)
        if area.width <= 0 or area.height <= 0:
            raise ValueError(f"{self.name}: margins leave no imageable area.")

    def imageable_area(self, sheet: Size | None = None) -> Rect:
        """The part of *sheet* that can carry ink, in sheet coordinates.

        The margins are measured from the sheet edges, so a sheet smaller than
        the press maximum keeps the same gripper strip, and loses the
        difference at the far edge -- which is what actually happens.
        """
        sheet = sheet or self.sheet
        self.check_sheet(sheet)
        return Rect.from_size(sheet).shrunk(self.margins)

    def check_sheet(self, sheet: Size) -> None:
        """Refuse a sheet the press cannot take."""
        if (
            sheet.width > self.sheet.width + 1e-6
            or sheet.height > self.sheet.height + 1e-6
        ):
            raise ImposeError(
                f"{self.name} takes at most {format_mm(self.sheet)}; "
                f"asked for {format_mm(sheet)}."
            )
        if self.min_sheet is not None and (
            sheet.width < self.min_sheet.width - 1e-6
            or sheet.height < self.min_sheet.height - 1e-6
        ):
            raise ImposeError(
                f"{self.name} takes at least {format_mm(self.min_sheet)}; "
                f"asked for {format_mm(sheet)}."
            )

    @property
    def gripper_margin(self) -> float:
        """The blank strip at the lead edge."""
        return getattr(self.margins, self.gripper)

    def describe(self) -> str:
        """A line an operator can check against the machine."""
        area = self.imageable_area()
        gripper = to_mm(self.gripper_margin)
        return (
            f"{self.name}: sheet {format_mm(self.sheet)}, "
            f"imageable {format_mm(area.size)}, "
            f"{gripper:g} mm gripper at {self.gripper}"
        )


def custom(
    name: str = "custom",
    *,
    sheet: Size | str | tuple[float, float],
    imageable: Size | str | tuple[float, float] | None = None,
    margins: Insets | float | str | None = None,
    gripper: Edge = "bottom",
) -> Press:
    """A press defined at the command line or in a job file.

    Give either *imageable* -- centred, the simple case -- or *margins* for the
    asymmetric border a real machine has.
    """
    sheet_size = paper(sheet)
    if margins is not None and imageable is not None:
        raise ValueError("Give imageable or margins, not both.")
    if margins is None:
        if imageable is None:
            resolved = Insets()
        else:
            area = paper(imageable)
            if area.width > sheet_size.width or area.height > sheet_size.height:
                raise ImposeError(
                    f"Imageable area {format_mm(area)} is larger than the "
                    f"sheet {format_mm(sheet_size)}."
                )
            dx = (sheet_size.width - area.width) / 2
            dy = (sheet_size.height - area.height) / 2
            resolved = Insets(left=dx, right=dx, bottom=dy, top=dy)
    elif isinstance(margins, Insets):
        resolved = margins
    else:
        resolved = Insets.uniform(length(margins))
    return Press(name=name, sheet=sheet_size, margins=resolved, gripper=gripper)


def _mm(value: float) -> float:
    """Millimetres to points, for the tables below."""
    return value * MM


def _press(
    name: str,
    sheet_mm: tuple[float, float],
    imageable_mm: tuple[float, float],
    *,
    gripper_mm: float,
    description: str,
) -> Press:
    """A press whose imageable area is centred across the width.

    Sheets feed short edge first on these machines, so the lead-edge gripper
    strip is taken off the height and the remainder goes to the tail.
    """
    sheet = Size(_mm(sheet_mm[0]), _mm(sheet_mm[1]))
    image = Size(_mm(imageable_mm[0]), _mm(imageable_mm[1]))
    side = (sheet.width - image.width) / 2
    gripper = _mm(gripper_mm)
    tail = sheet.height - image.height - gripper
    if tail < -1e-6:
        raise ValueError(f"{name}: gripper margin exceeds the unimageable height.")
    return Press(
        name=name,
        sheet=sheet,
        margins=Insets(left=side, right=side, bottom=gripper, top=max(0.0, tail)),
        gripper="bottom",
        description=description,
    )


# Nominal figures. Confirm against your machine before committing a job.
INDIGO_5000 = _press(
    "indigo-5000",
    (320, 470),
    (310, 450),
    gripper_mm=12,
    description="HP Indigo 5000/5500/5600, short edge to the grippers.",
)

INDIGO_7000 = _press(
    "indigo-7000",
    (330, 482),
    (317, 464),
    gripper_mm=12,
    description="HP Indigo 7000 series, short edge to the grippers.",
)

INDIGO_12000 = _press(
    "indigo-12000",
    (750, 530),
    (740, 510),
    gripper_mm=12,
    description="HP Indigo 12000, B2 format.",
)

SRA3_DIGITAL = _press(
    "sra3",
    (320, 450),
    (310, 440),
    gripper_mm=5,
    description="Generic SRA3 digital press.",
)

_REGISTRY: dict[str, Press] = {}


def _register(press: Press, *aliases: str) -> None:
    for key in (press.name, *aliases):
        _REGISTRY[key.lower().replace("_", "-").replace(" ", "-")] = press


_register(
    INDIGO_5000, "indigo", "indigo5000", "hp-indigo-5000", "indigo-5500", "indigo-5600"
)
_register(
    INDIGO_7000,
    "indigo7000",
    "hp-indigo-7000",
    "indigo-7500",
    "indigo-7600",
    "indigo-7800",
)
_register(INDIGO_12000, "indigo12000", "hp-indigo-12000")
_register(SRA3_DIGITAL, "sra3-digital", "generic-sra3")


def lookup(name: str) -> Press | None:
    """The press registered under *name*, or ``None``."""
    return _REGISTRY.get(name.strip().lower().replace("_", "-").replace(" ", "-"))


def get(name: str) -> Press:
    """The press registered under *name*, or an error naming the alternatives."""
    press = lookup(name)
    if press is None:
        raise ImposeError(
            f"Unknown press {name!r}. Known presses: {', '.join(press_names())}."
        )
    return press


def press_names() -> tuple[str, ...]:
    """Every canonical press name, sorted."""
    return tuple(sorted({press.name for press in _REGISTRY.values()}))
