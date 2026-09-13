# Fonts

`IBMPlexMono-Regular.ttf` — IBM Plex Mono, Regular weight, static TrueType.
Copyright IBM Corp., licensed under the SIL Open Font License 1.1; the licence
is beside it in `LICENSE-OFL.txt` and travels with the file.

It is here so the slug line can be embedded, which PDF/X requires of every
font. The choices behind it are all about making the PDF simple and the sheet
legible:

- **TrueType, not OpenType-CFF.** `glyf` outlines embed as `/FontFile2`, the
  better-supported path for PDF/X-1a. No `fvar` table, so it is a static
  instance rather than a variable font, which a RIP need not interpolate.
- **1000 units per em.** That is PDF glyph space exactly, so nothing is scaled
  anywhere between the font and the page.
- **Fixed pitch, 600/1000 for every glyph.** Checked across the whole WinAnsi
  range rather than trusted: `/Widths` is one number repeated, and text
  positioning needs no per-glyph metrics.
- **Complete Latin-1.** A job called `Catálogo.pdf` sets correctly rather than
  dropping to notdef boxes.
- **`fsType` 0.** Installable embedding, no restriction.

Only the Regular weight is here. A slug line has one voice, and shipping eight
weights would be 1 MB of wheel for nothing.
