# The vendored display serif

**Source Serif 4**, by Adobe, under the SIL Open Font License 1.1 (`OFL.txt`,
copied verbatim from the upstream repository).

- Upstream: <https://github.com/adobe-fonts/source-serif>
- Taken from: the Google Fonts CSS API, subset **by Google**, on 2026-10-16 —
  `https://fonts.googleapis.com/css2?family=Source+Serif+4:opsz,wght@8..60,400;8..60,600;8..60,700`

Two files and not six. Source Serif 4 is a **variable** font, and the CSS API
serves the whole 400–700 range as one file per subset, repeating the same URL
for every weight it is asked for. `troopconnect.css` declares `font-weight:
400 700` once per subset, which is what the file actually contains.

The two subsets are Google's own split. `latin` is dropped on its own at the
peril of French: it carries é, è, à, ç, ô and û, but *not* œ (U+0153) or Œ, so a
troop with a `cœur` or an `Œuvre` in a heading would get two faces in one word.
Which is why both are here.

**Replace, never edit.** These are upstream binaries; a hand-tweaked woff2 is a
diff nobody can read and a file that is no longer the font it claims to be. To
move to another face, drop in its files, rewrite the `@font-face` block at the
top of `troopconnect.css`, and update this file — the rest of the system reads
`--font-display` and does not care which face answers it.
