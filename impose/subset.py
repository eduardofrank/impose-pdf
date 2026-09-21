# Copyright (c) 2026 Eduardo Frank. MIT licensed; see LICENSE-MIT.

"""Cutting a font down to the glyphs a slug line actually uses.

The bundled face is 134 kB and 82 per cent of that is ``glyf``, the outlines
of 1028 glyphs. A slug line uses perhaps forty. PDF/X requires the font
embedded, so that weight is carried by every sheet unless the outlines nobody
asked for are dropped.

**Glyph numbers are kept.** The obvious subset renumbers glyphs densely, which
then forces ``cmap`` to be rewritten, ``hmtx`` rebuilt, and every composite
glyph's component references renumbered inside its own outline data. Keeping
the numbering leaves all three correct without being touched -- the only
tables rebuilt are ``glyf`` and the ``loca`` index into it, and a glyph nobody
needs simply becomes a zero-length entry. It costs a few kilobytes of sparse
index against a large amount of machinery that could be subtly wrong.

Three more tables go because a simple TrueType font in a PDF never consults
them: ``GSUB``, ``GPOS`` and ``GDEF`` describe OpenType layout, which happens
long before anything reaches a page. ``post`` is rewritten from version 2.0,
which carries a name for every glyph, to version 3.0, which carries none; a
PDF reaches glyphs through the encoding and the cmap, never by name.
"""

from __future__ import annotations

import hashlib
import struct

from . import ImposeError

#: Tables a PDF's simple TrueType font never reads.
DISCARD = frozenset({"GSUB", "GPOS", "GDEF", "DSIG", "meta", "gasp"})

#: The glyph every font has and every subset keeps.
NOTDEF = 0

#: Length of the tag PDF requires on a subsetted font's name.
TAG_LENGTH = 6


def subset(data: bytes, glyphs: set[int]) -> bytes:
    """*data* carrying only *glyphs*, their components, and ``.notdef``.

    The result is a valid TrueType font with the same glyph numbering, so
    anything already referring to a glyph by number still reaches it.
    """
    tables = _directory(data)
    keep = _with_components(data, tables, glyphs | {NOTDEF})
    glyf, loca, long_loca = _rebuild(data, tables, keep)

    built = {
        tag: data[offset : offset + length]
        for tag, (offset, length) in tables.items()
        if tag not in DISCARD
    }
    built["glyf"] = glyf
    built["loca"] = loca
    built["post"] = _post_without_names(data, tables)
    built["head"] = _head(built["head"], long_loca)
    return _assemble(built)


def tag_for(glyphs: set[int]) -> str:
    """The six-letter tag PDF requires on a subsetted font's name.

    Derived from the glyph set, so the same subset always gets the same tag
    and two different subsets in one file get different ones.

    >>> tag_for({3, 4, 5})
    'SSKWEJ'
    """
    digest = hashlib.sha256(repr(sorted(glyphs)).encode()).digest()
    return "".join(chr(ord("A") + byte % 26) for byte in digest[:TAG_LENGTH])


def _directory(data: bytes) -> dict[str, tuple[int, int]]:
    """Where each table lives, by tag."""
    if len(data) < 12:
        raise ImposeError("That is not a font: the file has no table directory.")
    count = struct.unpack(">H", data[4:6])[0]
    found: dict[str, tuple[int, int]] = {}
    for index in range(count):
        record = 12 + 16 * index
        tag, _checksum, offset, length = struct.unpack(
            ">4sIII", data[record : record + 16]
        )
        found[tag.decode("latin-1").strip()] = (offset, length)
    missing = {"head", "maxp", "loca", "glyf"} - set(found)
    if missing:
        raise ImposeError(
            f"Cannot subset a font without its {', '.join(sorted(missing))} "
            f"table(s)."
        )
    return found


def _offsets(data: bytes, tables: dict[str, tuple[int, int]]) -> list[int]:
    """Where each glyph's outline starts and ends, from ``loca``."""
    head, _ = tables["head"]
    maxp, _ = tables["maxp"]
    loca, _ = tables["loca"]
    long_format = struct.unpack(">h", data[head + 50 : head + 52])[0]
    count = struct.unpack(">H", data[maxp + 4 : maxp + 6])[0]
    if long_format:
        return list(
            struct.unpack(f">{count + 1}I", data[loca : loca + 4 * (count + 1)])
        )
    return [
        value * 2
        for value in struct.unpack(
            f">{count + 1}H", data[loca : loca + 2 * (count + 1)]
        )
    ]


def _with_components(
    data: bytes, tables: dict[str, tuple[int, int]], wanted: set[int]
) -> set[int]:
    """*wanted*, plus every glyph any of them is built out of.

    An accented letter is usually a composite: an outline that says "draw
    glyph 68 here and glyph 941 there". Dropping a component would leave the
    accent off the letter, which on a Spanish job name is exactly the failure
    this font was chosen to avoid.
    """
    offsets = _offsets(data, tables)
    glyf, _ = tables["glyf"]
    keep = set(wanted)
    pending = list(wanted)
    while pending:
        glyph = pending.pop()
        if glyph + 1 >= len(offsets):
            continue
        start, end = glyf + offsets[glyph], glyf + offsets[glyph + 1]
        if end - start < 10:
            continue
        contours = struct.unpack(">h", data[start : start + 2])[0]
        if contours >= 0:
            continue  # simple outline, nothing referenced
        for component in _components(data, start + 10, end):
            if component not in keep:
                keep.add(component)
                pending.append(component)
    return keep


def _components(data: bytes, at: int, end: int):
    """The glyph numbers a composite outline refers to."""
    while at + 4 <= end:
        flags, index = struct.unpack(">HH", data[at : at + 4])
        yield index
        at += 4
        at += 4 if flags & 0x0001 else 2  # ARG_1_AND_2_ARE_WORDS
        if flags & 0x0008:  # WE_HAVE_A_SCALE
            at += 2
        elif flags & 0x0040:  # X_AND_Y_SCALE
            at += 4
        elif flags & 0x0080:  # TWO_BY_TWO
            at += 8
        if not flags & 0x0020:  # MORE_COMPONENTS
            return


def _rebuild(
    data: bytes, tables: dict[str, tuple[int, int]], keep: set[int]
) -> tuple[bytes, bytes, bool]:
    """A ``glyf`` of only the kept outlines, and the ``loca`` indexing it."""
    offsets = _offsets(data, tables)
    glyf, _ = tables["glyf"]
    outlines: list[bytes] = []
    index = [0]
    for glyph in range(len(offsets) - 1):
        if glyph in keep:
            start, end = glyf + offsets[glyph], glyf + offsets[glyph + 1]
            outline = data[start:end]
            if len(outline) % 2:  # a short loca counts in pairs of bytes
                outline += b"\0"
            outlines.append(outline)
        index.append(index[-1] + (len(outlines[-1]) if glyph in keep else 0))
    body = b"".join(outlines)
    long_format = index[-1] > 0x1FFFE
    if long_format:
        return body, struct.pack(f">{len(index)}I", *index), True
    return body, struct.pack(f">{len(index)}H", *(v // 2 for v in index)), False


def _head(head: bytes, long_loca: bool) -> bytes:
    """``head`` with the loca format it now needs, and no stale checksum."""
    patched = bytearray(head)
    struct.pack_into(">I", patched, 8, 0)  # checkSumAdjustment, set at the end
    struct.pack_into(">h", patched, 50, 1 if long_loca else 0)
    return bytes(patched)


def _post_without_names(data: bytes, tables: dict[str, tuple[int, int]]) -> bytes:
    """``post`` as version 3.0: the same metrics, none of the glyph names."""
    offset, _ = tables["post"]
    header = bytearray(data[offset : offset + 32])
    struct.pack_into(">I", header, 0, 0x00030000)
    return bytes(header)


def _assemble(tables: dict[str, bytes]) -> bytes:
    """A font file from its tables, with the directory and checksums right."""
    names = sorted(tables)
    count = len(names)
    search = 1
    while search * 2 <= count:
        search *= 2
    entry = max(0, search.bit_length() - 1)
    header = struct.pack(
        ">IHHHH", 0x00010000, count, search * 16, entry, count * 16 - search * 16
    )

    offset = len(header) + 16 * count
    records, body = [], []
    for name in names:
        payload = tables[name] + b"\0" * (-len(tables[name]) % 4)
        records.append(
            struct.pack(
                ">4sIII",
                name.ljust(4).encode("latin-1"),
                _checksum(payload),
                offset,
                len(tables[name]),
            )
        )
        body.append(payload)
        offset += len(payload)

    font = bytearray(header + b"".join(records) + b"".join(body))
    head_at = next(
        struct.unpack(">I", font[12 + 16 * i + 8 : 12 + 16 * i + 12])[0]
        for i, name in enumerate(names)
        if name == "head"
    )
    struct.pack_into(
        ">I", font, head_at + 8, (0xB1B0AFBA - _checksum(font)) & 0xFFFFFFFF
    )
    return bytes(font)


def _checksum(data: bytes) -> int:
    """The sum of a table's 32-bit words, as the format defines it."""
    padded = data + b"\0" * (-len(data) % 4)
    return sum(struct.unpack(f">{len(padded) // 4}I", padded)) & 0xFFFFFFFF
