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

import argparse
import dataclasses
from typing import Literal

from . import ImposeError
from .geometry import Insets, Rect, Size
from .units import MM, format_mm, length, paper, to_mm

Edge = Literal["bottom", "top", "left", "right"]


#: A --sheet value meaning "make the sheet exactly the size of the form".
#: The first pass of a two-stage job, whose output is imposed again rather
#: than run.
FIT_SHEET = "fit"

#: The four edges a sheet can be gripped by, for naming one.
EDGES: tuple[Edge, ...] = ("bottom", "top", "left", "right")

#: Keys a press spec may carry. A spec is how a command line or a job file
#: names a press: a profile to start from, a sheet, and the border.
SPEC_KEYS = frozenset({"name", "sheet", "imageable", "margins", "gripper"})


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
        # Measured rather than built: a border wider than the sheet makes a
        # rectangle that cannot exist, and the person who typed the figure
        # should be told about the figure, not about the rectangle.
        if (
            self.margins.horizontal >= self.sheet.width
            or self.margins.vertical >= self.sheet.height
        ):
            raise ValueError(
                f"{self.name}: margins leave no imageable area on a "
                f"{format_mm(self.sheet)} sheet."
            )

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
    margins: Insets | dict | float | str | None = None,
    gripper: Edge = "bottom",
) -> Press:
    """A press defined at the command line or in a job file.

    Give either *imageable* -- centred, the simple case -- or *margins* for the
    asymmetric border a real machine has. *margins* takes whatever
    :func:`insets` reads: one length, or the edges named one at a time.
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
    else:
        resolved = insets(margins)
    return Press(
        name=name, sheet=sheet_size, margins=resolved, gripper=check_edge(gripper)
    )


def insets(spec: Insets | dict | float | str) -> Insets:
    """Margins from one length, or from the edges that differ.

    A single length is the same border all round. A mapping names only the
    edges that are not zero, which is how a real machine is written down: a
    gripper margin and a tail margin, and whatever is left at the sides.

    >>> insets("5mm").left == insets({"left": "5mm"}).left
    True
    """
    if isinstance(spec, Insets):
        return spec
    if isinstance(spec, dict):
        check_edges(spec)
        return Insets(**{edge: length(spec[edge]) for edge in spec})
    return Insets.uniform(length(spec))


def check_edges(named) -> None:
    """Refuse a border that names an edge a sheet does not have."""
    unknown = sorted(set(named) - set(EDGES))
    if unknown:
        raise ImposeError(
            f"{unknown[0]!r} is not an edge of a sheet. "
            f"Margins are named by edge: {', '.join(EDGES)}."
        )


def check_edge(edge: str) -> Edge:
    """*edge* if a sheet has one by that name, or an error naming the four."""
    if edge not in EDGES:
        raise ImposeError(
            f"{edge!r} is not an edge of a sheet. The gripper edge is one "
            f"of: {', '.join(EDGES)}."
        )
    return edge  # type: ignore[return-value]


def resolve(spec: Press | str | dict) -> Press:
    """The press a command line or a job file describes.

    A :class:`Press` is already the answer. A string is a profile name, or a
    size -- a press whose sheet is that and whose whole sheet images, which is
    what a device fed cut sheets does. A mapping is a profile, a sheet, or
    both, with the border given as *imageable* or as *margins*. With a sheet
    of its own, *name* is only a label, so a shop can write down its own
    machine:

    >>> resolve("indigo-5000").name
    'indigo-5000'
    >>> press = resolve({"name": "indigo-5000", "margins": {"bottom": "15mm"}})
    >>> to_mm(press.gripper_margin)
    15.0
    >>> round(to_mm(press.margins.top), 6)  # the profile's tail, not nothing
    8.0
    """
    if isinstance(spec, Press):
        return spec
    if isinstance(spec, str):
        return _from_name(spec)
    if not isinstance(spec, dict):
        raise ImposeError(
            f"A press is a profile name, a sheet size, or an object "
            f"describing one; got {spec!r}."
        )
    unknown = sorted(set(spec) - SPEC_KEYS)
    if unknown:
        raise ImposeError(
            f"{unknown[0]!r} is not a field of a press. A press takes: "
            f"{', '.join(sorted(SPEC_KEYS))}."
        )
    name = spec.get("name")
    if spec.get("sheet"):
        # A sheet of its own settles what the press is, so an unrecognised
        # name is a label for the shop's own machine rather than a mistake.
        base = lookup(name) if name else None
        sheet = paper(spec["sheet"])
    elif name:
        base = _from_name(name)
        sheet = base.sheet
    else:
        raise ImposeError("A press needs a sheet, or the name of a profile.")
    gripper = check_edge(spec.get("gripper") or (base.gripper if base else "bottom"))
    border = spec.get("margins")
    if isinstance(border, dict) and base is not None:
        # Edges the figure does not name keep the profile's. A shop that
        # measured its own gripper strip said nothing about the other three,
        # and reading that as nothing would widen the imageable area past
        # what the press can print -- artwork into the border, quietly.
        check_edges(border)
        border = {edge: border.get(edge, getattr(base.margins, edge)) for edge in EDGES}
    if spec.get("imageable") is not None or border is not None:
        return custom(
            name or (base.name if base is not None else "custom"),
            sheet=sheet,
            imageable=spec.get("imageable"),
            margins=border,
            gripper=gripper,
        )
    if base is not None:
        # The margins stay as the profile has them, measured from the sheet
        # edges: a smaller sheet keeps its gripper strip and loses the
        # difference at the tail, which is what the machine does.
        return dataclasses.replace(base, sheet=sheet, gripper=gripper)
    return Press(name=name or "custom", sheet=sheet, margins=Insets(), gripper=gripper)


def _from_name(text: str) -> Press:
    """A profile by name, or a press whose sheet is the size given."""
    press = lookup(text)
    if press is not None:
        return press
    try:
        sheet = paper(text)
    except ValueError as error:
        raise ImposeError(
            f"Unknown press {text!r}. Known presses: {', '.join(press_names())}. "
            f"A size such as 320mmx450mm defines one whose whole sheet images."
        ) from error
    return Press(name=text, sheet=sheet, margins=Insets())


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


def margins_spec(text: str) -> str | dict:
    """A border from one length, or from the edges that differ.

    ``5mm`` is every edge. ``bottom=12mm,top=5mm`` is a gripper strip and a
    tail, with the sides left at nothing -- the form of a figure an operator
    reads off the machine, one edge at a time.

    >>> margins_spec("5mm")
    '5mm'
    >>> margins_spec("bottom=12mm,top=5mm")
    {'bottom': '12mm', 'top': '5mm'}
    """
    if "=" not in text:
        return text
    spec: dict[str, str] = {}
    for part in text.split(","):
        edge, _, value = part.partition("=")
        spec[edge.strip().lower()] = value.strip()
    return spec


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Options describing the machine, shared by imposing and by `fit`.

    A profile answers for the presses this tool knows. These answer for the
    one in the room: the border a machine cannot image is the border no
    artwork gets, and a figure half a millimetre out is a job reprinted.
    """
    parser.add_argument(
        "--imageable",
        metavar="SIZE",
        help="The part of the sheet that can carry ink, centred in it. A "
        "name such as A3, or WIDTHxHEIGHT such as 310mmx450mm. Centring "
        "splits the unimageable border equally, which no real machine does: "
        "give --margins where the gripper edge differs from the tail.",
    )
    parser.add_argument(
        "--margins",
        type=margins_spec,
        metavar="SPEC",
        help="The border the press cannot image, measured in from the sheet "
        "edges. A length such as 5mm for all four, or edges that differ, "
        "such as bottom=12mm,top=5mm,left=4mm,right=4mm. An edge not named "
        "keeps the profile's figure, or is nothing where there is no "
        "profile to keep.",
    )
    parser.add_argument(
        "--gripper",
        choices=EDGES,
        default=None,
        metavar="EDGE",
        help=f"Which edge the grippers hold, and so which goes into the "
        f"machine first. One of: {', '.join(EDGES)}. It is fixed with "
        f"respect to the sheet, so turning a form to make it fit never "
        f"moves it. Default: the profile's, or bottom.",
    )


def from_arguments(args: argparse.Namespace) -> str | Press:
    """The press the parsed options describe.

    A name with nothing overriding it stays a name, so a recorded job keeps
    saying `indigo-5000` where nothing about the machine was changed, and
    reads the profile of the day it is imposed rather than a frozen copy.
    Anything else is resolved here: a recorded job then carries the sheet and
    all four margins, which is what a machine nothing else describes needs
    written down.
    """
    overrides = {
        key: value
        for key, value in (
            ("imageable", getattr(args, "imageable", None)),
            ("margins", getattr(args, "margins", None)),
            ("gripper", getattr(args, "gripper", None)),
        )
        if value is not None
    }
    if not overrides:
        return args.press
    return resolve({"name": args.press, **overrides})
