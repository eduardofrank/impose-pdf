# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

"""The bundled font, and what a PDF needs to know about it.

PDF/X requires every font embedded, so the slug line carries its own rather
than naming one and hoping the RIP has it. That means reading enough of the
TrueType tables to describe the font to a PDF: the metrics go in a
``/FontDescriptor`` and the file itself goes in a ``/FontFile2`` stream beside
it.

Only what the descriptor needs is read, which is little: the units per em, the
bounding box, the ascent and descent, the cap height, and one advance width.
The last of those is the reason the bundled font is monospaced. A proportional
font would need the whole ``hmtx`` table walked through the ``cmap`` to build a
``/Widths`` array, and every string measured glyph by glyph; a fixed-pitch one
is one number, and measuring text is multiplication.

Nothing here subsets. Embedding the whole file is what PDF/X asks for and is
right first; a subsetter would save about 130 kB a document and is an
optimisation, not a correctness matter.
"""

from __future__ import annotations

import dataclasses
import functools
import pathlib
import struct

from . import ImposeError

#: The font shipped with the package. See ``impose/fonts/README.md``.
BUNDLED = pathlib.Path(__file__).parent / "fonts" / "IBMPlexMono-Regular.ttf"

#: Character used where a string holds something WinAnsi cannot express.
SUBSTITUTE = "?"

#: The first and last codes a simple font's ``/Widths`` array covers.
FIRST_CHAR, LAST_CHAR = 32, 255

#: FixedPitch (1) | Nonsymbolic (32). Nonsymbolic is what says the font is
#: read through a standard encoding rather than its own built-in one, which is
#: what makes ``/WinAnsiEncoding`` mean anything.
FLAGS = 33


@dataclasses.dataclass(frozen=True, slots=True)
class Font:  # pylint: disable=too-many-instance-attributes
    """A TrueType font, measured for PDF.

    Lengths are in PDF glyph space -- thousandths of the text size -- which is
    what a font descriptor wants. The bundled font has 1000 units per em, so
    for it the conversion is the identity, but it is applied anyway rather
    than assumed.
    """

    name: str
    data: bytes
    advance: int
    bbox: tuple[int, int, int, int]
    ascent: int
    descent: int
    cap_height: int
    italic_angle: float
    fixed_pitch: bool

    def width(self, text: str, size: float) -> float:
        """How wide *text* sets, in points.

        >>> load().width("12345", 10)
        30.0
        """
        return len(text) * self.advance * size / 1000.0

    def height(self, size: float) -> float:
        """Ascender to descender, in points -- the room a line of text needs.

        >>> round(load().height(10), 2)
        13.0
        """
        return (self.ascent - self.descent) * size / 1000.0

    @staticmethod
    def encode(text: str) -> bytes:
        """*text* as WinAnsi bytes, with anything unrepresentable replaced.

        A slug carries job names, and a job name can hold anything. Refusing
        the sheet over one character would be the wrong trade, so the character
        is substituted and the sheet still prints.

        >>> load().encode("Catálogo")
        b'Cat\\xe1logo'
        >>> load().encode("→")
        b'?'
        """
        return "".join(
            character if _encodable(character) else SUBSTITUTE for character in text
        ).encode("cp1252", errors="replace")


def embed(pdf, font: Font):
    """Put *font* in *pdf* and return the font dictionary.

    A simple TrueType font: the glyphs are reached through WinAnsiEncoding, so
    one byte is one character and the ``/Widths`` array covers the codes the
    encoding defines. Fixed pitch makes that array one number repeated, which
    is the whole reason the bundled font is monospaced.

    ``/Length1`` is the uncompressed size of the font file, which is how a
    reader knows where the TrueType data ends once the stream is deflated.
    """
    # Imported here rather than at module scope so that measuring text costs
    # nothing but this module: the renderer pulls in pikepdf's compiled
    # extension, and a caller asking how wide a slug sets has no use for it.
    from pikepdf import Array, Dictionary, Name, Stream  # pylint: disable=C0415

    file_stream = Stream(pdf, font.data)
    file_stream["/Length1"] = len(font.data)
    descriptor = pdf.make_indirect(
        Dictionary(
            Type=Name.FontDescriptor,
            FontName=Name("/" + font.name),
            Flags=FLAGS,
            FontBBox=Array(list(font.bbox)),
            ItalicAngle=font.italic_angle,
            Ascent=font.ascent,
            Descent=font.descent,
            CapHeight=font.cap_height or font.ascent,
            StemV=_stem_width(font),
            FontFile2=pdf.make_indirect(file_stream),
        )
    )
    return pdf.make_indirect(
        Dictionary(
            Type=Name.Font,
            Subtype=Name.TrueType,
            BaseFont=Name("/" + font.name),
            FirstChar=FIRST_CHAR,
            LastChar=LAST_CHAR,
            Widths=Array([font.advance] * (LAST_CHAR - FIRST_CHAR + 1)),
            Encoding=Name.WinAnsiEncoding,
            FontDescriptor=descriptor,
        )
    )


def _stem_width(font: Font) -> int:
    """A stem thickness for the descriptor.

    No TrueType table carries one, and every producer estimates it. A reader
    uses it only to synthesise a substitute face, which cannot happen here
    because the font is embedded -- so the estimate has to be present and
    plausible rather than exact.
    """
    return max(1, round(font.advance * 0.14))


def _encodable(character: str) -> bool:
    """Whether WinAnsi has a code for this character."""
    try:
        character.encode("cp1252")
    except UnicodeEncodeError:
        return False
    return True


@functools.lru_cache(maxsize=4)
def load(path: pathlib.Path | str | None = None) -> Font:
    """Read a TrueType font, defaulting to the bundled one.

    >>> load().name
    'IBMPlexMono-Regular'
    >>> load().fixed_pitch
    True
    """
    path = pathlib.Path(path) if path is not None else BUNDLED
    try:
        data = path.read_bytes()
    except OSError as error:
        raise ImposeError(f"Cannot read the font at {path}: {error}") from error
    return _measure(data, path)


def _measure(data: bytes, path: pathlib.Path) -> Font:
    """Pull the descriptor metrics out of the font's tables."""
    tables = _tables(data, path)
    head = tables["head"]
    upem = struct.unpack(">H", data[head + 18 : head + 20])[0]
    if not upem:
        raise ImposeError(f"{path.name} declares no units per em.")
    scale = 1000.0 / upem

    def at(table: str, offset: int, form: str = ">h") -> int:
        start = tables[table] + offset
        return struct.unpack(form, data[start : start + struct.calcsize(form)])[0]

    post = tables["post"]
    italic = struct.unpack(">i", data[post + 4 : post + 8])[0] / 65536.0
    return Font(
        name=_postscript_name(data, tables, path),
        data=data,
        advance=round(at("hmtx", 0, ">H") * scale),
        bbox=tuple(  # type: ignore[arg-type]
            round(value * scale)
            for value in struct.unpack(">hhhh", data[head + 36 : head + 44])
        ),
        ascent=round(at("hhea", 4) * scale),
        descent=round(at("hhea", 6) * scale),
        cap_height=round(at("OS/2", 88) * scale) if at("OS/2", 0, ">H") >= 2 else 0,
        italic_angle=italic,
        fixed_pitch=bool(struct.unpack(">I", data[post + 12 : post + 16])[0]),
    )


def _tables(data: bytes, path: pathlib.Path) -> dict[str, int]:
    """Where each table starts, by tag."""
    if len(data) < 12 or data[:4] == b"OTTO":
        raise ImposeError(
            f"{path.name} is not a TrueType font with glyf outlines. A PDF "
            f"embeds those as /FontFile2; an OpenType-CFF font needs a "
            f"different descriptor and is not supported."
        )
    count = struct.unpack(">H", data[4:6])[0]
    found: dict[str, int] = {}
    for index in range(count):
        record = 12 + 16 * index
        tag, _checksum, offset, _length = struct.unpack(
            ">4sIII", data[record : record + 16]
        )
        found[tag.decode("latin-1").strip()] = offset
    missing = {"head", "hhea", "hmtx", "post", "OS/2", "glyf"} - set(found)
    if missing:
        raise ImposeError(
            f"{path.name} is missing the {', '.join(sorted(missing))} "
            f"table(s), which a PDF font descriptor needs."
        )
    return found


def _postscript_name(data: bytes, tables: dict[str, int], path: pathlib.Path) -> str:
    """Name record 6, which is what ``/BaseFont`` must say."""
    start = tables["name"]
    count, strings = struct.unpack(">HH", data[start + 2 : start + 6])
    for index in range(count):
        record = start + 6 + 12 * index
        platform, _encoding, _language, name_id, length, offset = struct.unpack(
            ">HHHHHH", data[record : record + 12]
        )
        if name_id != 6:
            continue
        at = start + strings + offset
        return data[at : at + length].decode(
            "utf-16-be" if platform == 3 else "latin-1"
        )
    raise ImposeError(f"{path.name} carries no PostScript name.")
