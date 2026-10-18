---
name: TroopConnect
description: A scout unit's year, run on the federation's own design.
colors:
  charter-blue-deep: "#0a4275"
  charter-green-bright: "#95c11f"
  charter-green-deep: "#304a3c"
  charter-plum: "#4e1d4f"
  charter-teal: "#2b99a4"
  charter-orange: "#ef7b00"
  charter-crimson: "#d60f3c"
  charter-slate: "#809aaf"
  charter-sky: "#15adea"
  paper: "#f2f5f8"
  home-ground: "#dde5ec"
  white: "#ffffff"
  border: "#dee2e6"
  border-input: "#ced4da"
  muted: "#6c757d"
  muted-on-paper: "#5d666e"
  muted-on-field: "#515a63"
  member-tint-blue: "color-mix(in srgb, #00a0de 7%, #ffffff)"
  member-tint-green: "color-mix(in srgb, #296f52 6%, #ffffff)"
  member-date-tint: "color-mix(in srgb, #296f52 9%, #ffffff)"
  member-action-veil: "color-mix(in srgb, #00a0de 12%, #ffffff)"
  member-dark-green: "color-mix(in srgb, #296f52 82%, #0b1a12)"
  member-dark-blue: "color-mix(in srgb, #0a4275 76%, #0b1a12)"
  member-absence: "#b30d31"
  member-late-on-dark: "#ffd1db"
  tile-divider: "#eceff2"
typography:
  display:
    fontFamily: "Muli, sans-serif"
    fontSize: "calc(1.375rem + 1.5vw)"
    fontWeight: 700
    lineHeight: 1.2
  display-serif:
    fontFamily: "\"Source Serif 4\", Georgia, serif"
    fontSize: "clamp(2rem, 3.4vw, 2.75rem)"
    fontWeight: 700
    lineHeight: 1.08
  headline:
    fontFamily: "Muli, sans-serif"
    fontSize: "calc(1.325rem + 0.9vw)"
    fontWeight: 700
    lineHeight: 1.2
  title:
    fontFamily: "Muli, sans-serif"
    fontSize: "1.25rem"
    fontWeight: 700
    lineHeight: 1.2
  body:
    fontFamily: "Muli, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "Muli, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.5
rounded:
  chip: "0.2rem"
  md: "0.25rem"
  lg: "0.5rem"
  leaf: "0.875rem"
  tile-inner: "1rem"
  tile: "1.25rem"
  pill: "999px"
spacing:
  xs: "0.25rem"
  sm: "0.5rem"
  md: "1rem"
  lg: "1.5rem"
  xl: "3rem"
motion:
  settle: "cubic-bezier(0.16, 1, 0.3, 1)"
  feedback: "150ms ease-in-out"
  ground: "300ms"
  sheet: "340ms, 90ms delay"
  draw: "500ms, 80ms a segment"
components:
  button-primary:
    backgroundColor: "{colors.charter-blue-deep}"
    textColor: "{colors.white}"
    typography: "{typography.body}"
    rounded: "{rounded.md}"
    padding: "0.375rem 0.75rem"
  button-primary-hover:
    backgroundColor: "#093863"
  button-sm:
    typography: "{typography.label}"
    rounded: "{rounded.chip}"
    padding: "0.25rem 0.5rem"
  button-outline-primary:
    backgroundColor: "transparent"
    textColor: "{colors.charter-blue-deep}"
    rounded: "{rounded.md}"
    padding: "0.375rem 0.75rem"
  button-outline-danger:
    backgroundColor: "transparent"
    textColor: "{colors.charter-crimson}"
    rounded: "{rounded.md}"
    padding: "0.375rem 0.75rem"
  field:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.charter-blue-deep}"
    typography: "{typography.body}"
    rounded: "{rounded.md}"
    padding: "0.375rem 0.75rem"
  card:
    backgroundColor: "{colors.white}"
    rounded: "{rounded.md}"
    padding: "1rem"
  alert-danger:
    backgroundColor: "#f7cfd8"
    textColor: "#800924"
    rounded: "{rounded.md}"
    padding: "1rem"
  page-head:
    backgroundColor: "transparent"
    textColor: "{colors.charter-blue-deep}"
    padding: "2.5rem 0 0"
  member-tile:
    backgroundColor: "{colors.white}"
    textColor: "{colors.charter-blue-deep}"
    rounded: "{rounded.tile}"
    padding: "1rem 1.5rem"
  member-house:
    backgroundColor: "{colors.member-dark-blue}"
    textColor: "{colors.white}"
    rounded: "{rounded.tile}"
    padding: "1.5rem"
  member-house-action:
    backgroundColor: "{colors.white}"
    textColor: "{colors.charter-blue-deep}"
    typography: "{typography.body}"
    rounded: "{rounded.pill}"
    padding: "0.5rem 0.95rem"
  member-tool:
    backgroundColor: "{colors.white}"
    textColor: "{colors.charter-blue-deep}"
    rounded: "{rounded.tile-inner}"
    padding: "1rem"
  member-tool-children:
    backgroundColor: "{colors.member-tint-blue}"
  member-tool-sections:
    backgroundColor: "{colors.member-tint-green}"
  member-tool-anchor:
    backgroundColor: "{colors.member-dark-green}"
    textColor: "{colors.white}"
  member-action:
    backgroundColor: "{colors.member-action-veil}"
    textColor: "{colors.charter-blue-deep}"
    rounded: "{rounded.pill}"
    padding: "0.25rem 0.5rem"
  member-action-hover:
    backgroundColor: "color-mix(in srgb, #00a0de 20%, #ffffff)"
  member-account-chip:
    backgroundColor: "#eaf4ef"
    textColor: "{colors.charter-blue-deep}"
    rounded: "{rounded.md}"
    padding: "0.375rem 0.75rem"
---

# Design System: TroopConnect

## Overview

**Creative North Star: "The Unit Handbook"**

This is a practical printed document that a family keeps to hand — a handbook the
federation printed and the unit filled in. It is not trying to be distinctive. It
is trying to be legible, familiar, and recognisably the federation's, so that a
parent who has never seen this particular software still knows how to read it:
every page opens the same way, every action is a button in the place buttons go,
and nothing on screen is competing with the thing they came to do.

Structurally the system is two layers that never mix. A vendored theme — Les
Scouts' own `template-unite`, a Bootstrap build carrying the federation's
graphical charter — supplies every shape, colour and typeface. On top sits a
single small override file, `static/css/troopconnect.css`, holding only the
deviations: a hero band, the public page's enrolment desk, the member homepage's
tile board, a first-run wizard, an agenda grid, one table column with a ceiling.
The rule that makes this work is that the override file stays small; a rule that
merely restates one the theme already makes is a liability, because the theme can
move under it and the local copy would win.

The result is deliberately unglamorous and consistently so. Density follows the
task rather than the brand: a settings page is a stack of cards, a member list is
a striped table, a form is one labelled field per block. The federation shows up
in flat charter colour and in bold Muli — and, in four places, at field scale
rather than as an accent: the green-to-blue bar that opens every page, the
ground the enrolment desk stands on, which is the four branches drawn as four
columns, the desk's answer, which takes the matched branch's own colour as its
ground, and the member ground every signed-in page stands on, which lifts the
two branch colours the unit's public page already speaks into a wash behind
white tiles. There is no troop-level colour, no theme picker, no second accent: the
palette is the federation's, and the unit's identity is carried by its name and
the logo it uploads.

The member page is the one surface that composes rather than lists. Its board
refuses the equal card grid: tiles carry unequal grow weights, the household's
one dark tile sits beside a person's white one, and the tool mosaic repeats the
same asymmetry for actions. The exception is a family with more than one child:
there the balance takes the first row alone and the children stand under it in
equal columns, because siblings are peers. The composition is still the
handbook's — same paper, same inks, same serif — but it is laid out for scanning
a family rather than for reading a page.

**Key Characteristics:**
- Bootstrap's own primitives, used as intended, restyled only where a task needs it
- One typeface (Muli) and one flat charter palette, both inherited, neither configurable
- One green-to-blue bar and a serif page head on the member ground as the recurring opener
- Thin 1px lines and 0.25rem corners on the product; the member board's 1.25rem tiles trade the border for one soft charter-blue shadow
- Paper-filled fields on a paper-coloured page, separated by a border and a blue focus halo
- The homepage's desk standing on the four branches' colours, at the one place the page spends them
- A member board of unequal tiles: one dark anchor (balance or lead tool), white person tiles, and branch-tinted tool clusters
- Two shells: the site (fixed 84px navbar) and the first-run wizard (its own page, same theme)

## Colors

Flat charter inks on a pale blue-grey paper — saturated and confident in small
areas, nearly monochrome over most of the screen. Every colour here is the
federation's; none was chosen by this project.

### Primary
- **Charter Blue Deep** (#0a4275): The ink. Body text, every heading, links, the
  primary button, the navbar gradient, and the focus halo. It is also the page's
  *only* text colour — there is no separate near-black; headings and body differ
  by size and weight, not by colour.
- **Charter Sky** (#15adea): The theme's light blue. It survives in the member
  dark tile's corner bloom; it is no longer a page band. See Components → Page
  head.

### Secondary
- **Charter Green Deep** (#304a3c): The quiet second voice — the navbar's
  secondary surface and the "day activity" chip. Dark enough to read as a
  neutral, green enough to be a charter colour.

### Tertiary
- **Charter Teal** (#2b99a4): Bootstrap's `info`, and the one place the system
  puts black text on a saturated fill (the navbar's user chip on every page
  except the member board, which restates it as paper). A deliberate oddity,
  not a pattern to extend.
- **Charter Green Bright** (#95c11f): `success`. Confirmation only — a saved
  settings group, a successful toast.
- **Charter Orange** (#ef7b00): `warning`. The "detach" action, the
  staff-facing failed-mail banner, and the new-members alert tile — the one
  tool that reports work waiting rather than offering a destination.
- **Charter Crimson** (#d60f3c): `danger`. Destructive actions and every form
  error. On the member board it is narrowed to a reported absence and an overdue
  balance — see The Crimson-Only-For-Overdue Rule.
- **Charter Plum** (#4e1d4f): The "weekend" chip. The deepest colour in the
  system, and the only one that reads as dark rather than bright.

### Neutral
- **Paper** (#f2f5f8): The page background *and* the fill of every text field.
  Fields are not white — they sit on the page as slightly darker wells defined by
  their border. This is the single most distinctive thing about the form layer.
- **Home Ground** (#dde5ec, `color-mix(in srgb, #0a4275 9%, #f2f5f8)`): The
  ground the desk's section and the "where to find us" band are laid on, so the
  visitor's half of the public page reads as one field rather than two sections
  cut in different colours. It is *derived* rather than picked, so it moves with
  the ink it is mixed from, and it exists only on `/` — no members page ever sees
  it. It is also the base the four branch rooms are mixed into, which makes
  those rooms darker than they would be on bare `paper`; the `muted-on-field`
  rung was re-measured against that and moved a step down, and every ink in
  `BRANCH_INKS` is measured against it.
- **Home Green** (#2c4936, `color-mix(in srgb, #304a3c 84%, #0b1a12)`): The
  federation's own green taken down until it can hold white type over any
  photograph, and the colour the public page's band is read under. Charter-green-
  deep is `--bs-secondary` in the theme; this is that colour darkened rather than
  replaced, and it is the page's only large surface of colour that belongs to no
  branch.
- **Section Green** (#304a3c): Charter-green-deep itself, at label size for a
  section's eyebrow, for the rule the page draws down the left of a statement it
  wants read as a statement, and as the ground of both doors on the page.
- **White** (#ffffff): Cards, dropdowns, modals, the navbar's overlay surfaces,
  and every person and tool tile on the member board. Nothing else is white.
- **Border** (#dee2e6): Structural lines — wizard branches, the agenda grid,
  section dividers. Card outlines are black at 12.5%.
- **Input Border** (#ced4da): The one darker line, used only where a border has
  to define an editable field against paper.
- **Muted** (#6c757d): Help text, empty states, elapsed and out-of-month labels
  *on a white surface*.
- **Muted on Paper** (#5d666e): The same voice on the page's own ground. The
  theme's muted is drawn for white cards and measures 4.29:1 on `paper`, which
  fails AA by a margin thin enough that it would pass unnoticed — so text on the
  paper ground uses this instead, one step darker.
- **Muted on Field** (#515a63): The third rung, for the same voice on the desk
  field's tints. `muted-on-paper` clears AA on `paper` with room to spare, and a
  branch tint under it spends most of that room: on the three darker branch
  colours it measures 4.16–4.35:1, which is a failure thin enough to pass
  unnoticed for the same reason the theme's muted did. One step darker again, and
  it clears AA on every tint the desk field can lay down (worst case 4.68:1) as
  well as on `paper` (5.95:1), and on `home-ground` itself. On the member board
  it is the quiet voice on both the white tiles and the 6–9% tints, where it
  keeps the same role under a lighter ground than the desk's.
  The rung is a *measurement*, not a choice, and it is re-measured whenever the
  ground under the tints moves: the tints are read through `home-ground` now
  rather than through `paper`, and the value that cleared the old ground (4.63:1
  worst) came out at 4.35:1 on the new one — a failure thin enough to pass
  unnoticed again. Any further change to `home-ground` or to the field's
  strength has to bring this rung back with it.

### The member board

Every signed-in page stands on this ground edge to edge, and the homepage is
where the board's tiles fill it. It is still paper and branch colour, but mixed
rather than laid on, so the tiles keep their own edges without a line.

- **Member Ground**: `paper` with two radial blooms — Baladins blue at 22% in the
  upper right, Louveteaux green at 20% in the lower left — over a 168° wash from
  #e3eff8 through #f0f6f2 to #e3efe7. The blooms are mixed with `transparent`,
  not with paper, so the colours stay the federation's rather than becoming two
  new tints. The ground is full-bleed because a board that stopped at the
  container's edge would read as a card.
- **Tile tints**: white tiles carry the page; the tools carry a branch at 6–8%
  over white — children at 7% Baladins blue, sections and the unit at 6%
  Louveteaux green, account and site none. The date leaf is 9% Louveteaux green
  and is the only *tint* inside a white person tile; the activity chip is still
  one of the charter's three state colours.
- **The dark note**: a 145° gradient from Louveteaux green mixed 82% with
  #0b1a12 (`member-dark-green`) into charter blue mixed 76% with the same shade
  (`member-dark-blue`), plus one 32% charter-sky bloom in the bottom-right
  corner. It is a *darkened* mix, not a branch field, which is what lets white
  type sit on it — see The Never-On-The-Field Rule.
- **Absence and lateness**: a reported absence uses `member-absence` (#b30d31,
  charter crimson taken down until it clears AA on white) and a charter-crimson
  dot (#d60f3c). The overdue note on the dark tile uses `member-late-on-dark`
  (#ffd1db), the same warning at the contrast that ground allows.
- **Tile divider** (#eceff2): the 1px rule between a tile's head and its event,
  and between the event and its foot. It is lighter than the product's structural
  border because it sits inside a white tile rather than between page regions.
- **Selection**: the board's own text selection is a 24% Baladins wash with the
  charter ink on it, so even the browser's surface belongs to this ground.

### Branches

The federation draws a colour for each branch, and they are a fourth family
apart from the charter inks above: `BRANCH_COLOURS` in `homepage/views.py` maps
`Branch.key` — the preset slug, not the name a troop gives it — to the theme's
own branch colour.

- **Baladins** #00a0de, **Louveteaux** #296f52, **Éclaireurs** #004f9f,
  **Pionniers** #d51317.

The federation also ships a mark per branch, `logo_<Branch>.png` (mapped by
`BRANCH_LOGOS` in `homepage/views.py`). It is spent beside the branch's name
wherever that name is a title — the desk's four rooms, the answer sheet and a
section tile — and only where `Branch.key` matches a preset. A branch no preset
made has no mark, exactly as it has no colour and no topping.

They are spent on the homepage, where the branches are the subject, and in five
strengths of one idea: the desk field's columns at 15%, the rail's 4px rules at
full, the year chips' rings and fills at full and 32%, and the answer band's
ground at full. The answer sheet also carries the branch's coloured topping,
from the theme's vendored 100px tiles, at 12% as texture behind the sentence.
A branch no preset made has no colour and gets none: a made-up one would claim a
meaning it does not carry, so its rule is the structural line, its column is
nothing, its answer band is the plain outlined one, and it has no topping to
wear.

The member board spends the same two branch colours at the two ends of its
ground — Baladins blue and Louveteaux green — and asks nothing of the other two.
That is not a claim about the unit's sections: it is the pair the page already
speaks, mixed into one light. The tiles never take a branch's full strength as a
field; the strongest they go is a 9% tint or the darkened dark note.

The field's 15% is a *veil over the home ground*, not a colour in its own right —
the tints are mixed with `transparent` and never with `paper` — and that is the
whole of how four branches of four different temperatures end up in one light.
Nothing levels them: Baladins stays the loud one and Louveteaux the quiet one,
because the relative weight of the four is the federation's own and not this
project's to editorialise. The ground supplies the shared light; the hues stay
the federation's.

### Named Rules

**The Federation's Ink Rule.** The palette belongs to Les Scouts and a troop
never configures it. A troop owns its name, its logo, its favicon, its branches
and its content — it does not own colour. A "match my logo" or theme-picker
feature is a departure from this system, not a refinement of it.

**The Charter-Only Rule.** A new state gets a colour from this list or it gets
no colour. Charter hues may carry meaning only through an explicit mapping —
today that is the agenda's and the member tiles' three activity types
(`charter-blue-deep` reunion, `charter-green-deep` day, `charter-plum` weekend) —
and never by inventing a hue or reaching for a Bootstrap default that the theme
did not override.

**The Shared Ground Rule.** The hero band and the desk are two elements of one
field. The band's settle ends on `home-ground` and the desk *begins* on it, with
no gap between them, and that is what makes the join invisible. Changing one
without the other puts a seam across the top of the public page — and it lands
at exactly the height where the photograph stops, which is the most visible
line the page could have. Both read it from the one `--home-ground` in `:root`
because the two elements are siblings and neither owns it.

**The One Dark Tile Rule.** A member page spends exactly one dark surface. It
carries the household balance when the reader owes money for a child, and
otherwise the first action of the featured tool group. It is never a second
decorative note: one dark tile is what makes the rest of the board read as
paper. When the household is settled or fees are off, the dark note moves to the
tools — the page still has one, and the balance tile is simply absent rather
than rendered as a zero. A staff reader's new-members alert is the one
exception: when it holds the featured group's first slot the alert takes the
page's loud note as a warning tint, and the dark gradient is not stacked under
it. The page still spends one loud surface, and it is the one that says there is
work to do.

**The Branch-Tint Rule.** A tool cluster takes a 6–8% tint of one branch colour
over white — children 7% Baladins blue, sections and the unit 6% Louveteaux
green, account and site none. The tint names the group; it never becomes the
label's colour, and it is mixed over white so the tile stays a tile on the
gradient ground.

**The Crimson-Only-For-Overdue Rule.** Crimson is spent on money and absence,
and only when something is overdue or reported: the late note on the dark tile
and the absence line on a person tile. The dark tile takes the same warning as a
light rose (#ffd1db) because crimson ink fails on it. No other state borrows the
colour.

## Typography

**Display Font:** Source Serif 4 (with `Georgia, serif`)
**Body Font:** Muli (with `sans-serif`)
**Available but unused:** Housepaint, CaveatBrush, Mali-Bold, Roboto Mono

**Character:** A humanist sans for everything the product says, and a serif for
the things it *names*. Muli runs in nine weights and carries every label, table
cell, button and paragraph; Source Serif 4 carries the unit's own name, a
section's heading, a branch's name and the desk's closing sentence — the words
that are titles rather than prose. On the member board the serif also carries the
facts a reader scans: a child's or section's name, the day on a date leaf, a
section's member count and the household balance. The serif names; it also
counts.

The serif is vendored (`static/fonts`, OFL, one variable file per subset) and it
is the only typeface this project has ever added. The theme's four decorative
faces — Housepaint, CaveatBrush, Mali-Bold, Roboto Mono — are still not used and
still should not be: they are costumes. A serif is not a costume on a title; it
is the difference between a title and a large label.

Hierarchy inside a page is carried by size and weight, and now by *face* at one
boundary only: display type is the serif, everything else is the sans, and no
third case exists. Colour is still not a hierarchy tool —
see the Weight-Not-Colour Rule.

### Hierarchy
- **Surface display** (700, `clamp(2rem, 3.4vw, 2.75rem)`, 1.08): Every page's
  `h1` in its page head — "Vos enfants", "Historique des messages" — and the
  desktop's question. It opens the page without a band, so it carries the page's
  name at the largest step on the surface.
- **Headline** (700, `calc(1.325rem + 0.9vw)` → 2rem, 1.2): Section headings —
  the h2s the theme's `.h5` and card titles do not cover.
- **Title** (700, 1.25rem, 1.2): Card titles, wizard step titles, settings group
  names. Set with `.h5` on a real `h2` so the outline stays correct while the
  size stays small.
- **Body** (400, 1rem, 1.5): Everything — labels, values, table cells, prose.
- **Label** (400, 0.875rem, 1.5): Help text under a field, month grid headers,
  progress labels. Muted (#6c757d), never bold.

### The Override Scale

The homepage's two surfaces set their own steps on top of the theme's ramp,
because Bootstrap's five sizes cannot express both a 48px question and a 13px
fact label:

| Step | Size | Where |
| --- | --- | --- |
| Unit name | clamp(2rem, 3.2vw, 2.75rem) | The public page's band |
| Question | clamp(2rem, 3.4vw, 2.75rem) | The enrolment desk's heading |
| Surface title | clamp(2rem, 3.4vw, 2.75rem) | "Vos enfants", "Votre unité" |
| Section title | 1.75rem | "Nos locaux" / the troop's own name for its hall; "Your tools" |
| Panel name | 1.75rem | A child's or a section's name |
| Balance amount | clamp(2.5rem, 4.6vw, 3.25rem) | The household balance |
| Section count | 2rem | A section tile's member numeral |
| Date day | 1.875rem | The date leaf's day |
| Answer | 1.625rem | The branch a birth year lands in |
| Room name | 1.25rem | A branch's name on the desk's strip; the dark tool's label |
| Note | 1.3125rem | The desk's closing statement |
| Lede | 1.0625rem | Desk lede, CTAs, the household summary, an event title |
| Body note | 0.9375rem | Federation line, branch legend, panel meta, absence line, house notes |
| Fact label | 0.8125rem | Panel row labels, branch ages |
| Eyebrow | 0.75rem | The label over a section's heading |
| Chip / group label | 0.75rem | Activity chips, tool-group headings, count and balance labels |
| Date month | 0.6875rem | The month under a date leaf's day |

The steps above `Lede` are the ones the public page sets; the member board adds
`Surface title`, `Panel name`, `Balance amount`, `Section count` and `Date day`
to that upper half, and shares everything from `Lede` down. The **unit name**,
the **question**, the **surface title**, the **section title**, the **panel
name**, the **balance amount**, the **section count** and the **date day** are
the steps that take the display serif — see the Two-Voice Rule — and everything
from `Room name` down is Muli.

It is a second scale and is documented as one rather than folded into the
theme's, because the two answer different questions: the theme's ramp sizes
*page structure*, the override scale sizes *one working block*. They do not
collide — Bootstrap caps `h1` at 2.5rem above 1200px, so the desk's question and
the member page's surface title stay the largest type on their pages at every
width.

### Named Rules

**The Two-Voice Rule.** The application speaks Muli and *names* in Source Serif
4. The boundary is display versus everything else — a unit's name, a section
heading, a branch's name, a child's or section's name, a date leaf's day, a
member count, the household balance, the desk's closing statement are display; a
button, a table cell, a help line, a form label are not, however emphatic. A
third face is a departure from this system rather than a flourish within it, and
the theme's four decorative faces (Housepaint, CaveatBrush, Mali-Bold, Roboto
Mono) are still not it: they are costume, and a title is not a costume.

**The Two-Scale Rule.** A new block sizes itself from the override scale above
and never from an ad-hoc value; a page's structure keeps to the theme's ramp.
Adding a step to either without recording it here is how a system stops being
one.

**The Weight-Not-Colour Rule.** Emphasis is 700, not a hue. Never colour text to
make it louder — the palette has no text colours to spend, and every heading
already shares the body's ink.

**The Board-Numeral Rule.** A number the reader scans for — the household
balance, a section's member count, the day on a date leaf — is set in the display
serif with tabular figures. A number inside a sentence stays Muli. The face is
the signal that the number is a fact, not prose.

## Layout

A single Bootstrap 12-column grid inside a `.container`, with two page shells
sharing it.

**The site shell** is fixed: an 84px navbar (set inline in `base.html`, and
mirrored as `--site-navbar-height` in CSS in **px, not rem**, because the navbar
itself does not follow the root font size), then the page head — or, on the
public page, the troop's photo band — then a `.container` holding the page.

It is a **full-height column** — `body` is `display: flex; flex-direction:
column; min-height: 100vh` — so that a page shorter than the window still ends
at the window's edge rather than at whatever its content stopped on. The footer
sits in a `.site-footer-slot` whose auto margin spends the height a short page
does not use. The slot exists so the *footer* keeps its own 3rem gap: an auto
margin on the footer itself would eat that gap on every long page, and on a page
that already fills the screen the whole mechanism is inert.

**The navbar is one green-to-blue band on every page.** Its height and the two
properties that make it what it is live in inline style on the element, because
`.bg-primary` carries the navbar's fill with `!important` and only an inline
`!important` out-ranks it. The two properties are named once in `:root` and
*applied* by `base.html` (`--site-navbar-fill`, `--site-navbar-backdrop`).

- **The bar is shallow enough to be chrome rather than a header.** 84px with a
  66px mark leaves the unit's name and the two doors on one line and gives the
  photograph the rest of the first viewport; the height is stated once inline
  and once in `--site-navbar-height`, and the band's pull reads the variable so
  the two can never disagree.
- **The two doors do not share a jamb.** The filled invitation and its outlined
  peer are separated by one system step (0.5rem) from `md` up, and by the same
  step vertically when the menu stacks them on a phone.
- **The collapsed menu is a panel, not the glass.** Below `md` the menu floats
  over the page rather than over the bar's backdrop, so it takes an opaque
  charter fill and rounded bottom corners; white links over a photograph are a
  contrast accident, not a design.
- **What is behind the glass is what you see.** A `backdrop-filter` blurs and
  dims the backdrop — the ground the page opens with — and the fill is the
  gradient laid over the result. The bar reads as the site's own chrome on every
  page, rather than as a different colour per surface.
- **The dimming is the guarantee, the alpha is the look.** White nav links are
  legible only while their ground stays dark, and a troop's photograph may be
  bright anywhere in it. The fill's alpha can never promise that; the
  `brightness()` in the backdrop filter can, and it is what lets the one bar work
  over paper, over the member ground and over the public page's photograph.
- **The glass only sees what is painted before it.** `z-index: 2` on `.navbar`
  is load-bearing rather than tidy: the hero band is a positioned sibling that
  comes later in the document, and without the order stated the band paints over
  the bar and swallows the logo and the menu.
- **No page restates the bar.** The gradient is a default in `:root`; a page
  supplies the ground beneath it — the public page's photograph, the member
  ground — and the `page-member` class carries only that ground now. Below `md`
  the collapsed menu keeps the gradient instead of base.html's navy panel, so the
  account never opens onto a third ground.

Content is laid out at `col-md-12` by default and
split into halves or thirds only where two things genuinely sit side by side; a
form is one full-width field per block.

**The member board.** A signed-in reader gets the same shell without a band:
the 84px bar, then a `.container` whose `.member-page` sets 2.5rem above the
head and 3.5rem below (1.75rem on a phone). The head is a surface display title
over one summary line; the board follows it at 1.75rem, and the tools at 2.75rem
(0.5rem when the reader's page is tools alone).

- **The board is a flex row, not a grid.** Each tile has a 26rem basis and a grow
  weight that differs on purpose: the household balance 1.75, the first person
  tile 1.25, the second 0.9. Two tiles read about 7/5; three read about
  45/32/23, so the second row's wide tile lands on the right and the board never
  settles into the equal-card symmetry it is refusing. A fixed grid left a hole
  whenever a family had an odd number of children.
- **Siblings are peers.** A family with more than one child is the one place the
  asymmetric weights are dropped: the balance takes the first row alone and the
  children stand under it in equal columns — two from `lg`, three from `xl`,
  one per row below `lg`. The column count is explicit rather than auto-fit,
  because the balance spans every column and an auto-fit track it spans never
  collapses. A leader's section tile keeps a full row of its own.
- **Every count fills its row.** One, two or four tiles each wrap into a filled
  line; below `md` every tile takes its own row and the unequal weights are
  dropped with the columns.
- **A one-section leader gets a wide tile.** At `lg` (992px) and up the section
  tile becomes a three-area grid — identity and attendance in the left column,
  the next event in the right, the actions across both feet — so one section
  reads as a row rather than as a lonely card in a half-empty board. Below
  `lg` it is the stacked tile again.
- **The tools repeat the rhythm at a smaller scale.** Groups are a flex row with
  a 17rem basis; the group with the most entries takes `1.5` grow and a 24rem
  basis, its list is two columns and its first tile spans both. Every other
  group's list is `auto-fill` at a 9rem minimum, so a narrow group never breaks
  a label mid-word.
- **The board's rhythm is 1rem.** The gap between tiles, between tool groups and
  between tools in a list is the same step; tile padding runs 1.25–1.5rem. The
  page does not invent a second spacing scale for the surface.

**The wizard shell** deliberately does not extend `base.html` — its header and
navigation would point at pages that do not exist yet. It keeps only the
stylesheets, centres a `col-lg-9 col-xl-8` column on a `setup-page` background,
and swaps a single `#wizard-pane` element over HTMX.

Breakpoints are Bootstrap's. `md` (768px) is the load-bearing one: the navbar
collapses, the grid halves, and the member board stacks there. `lg` (992px) is
the one the section tile changes composition at. `xxl` is used once, to inline
the Sections dropdown in the navbar. Single-column stacking holds all the way
down; nothing in the system depends on hover.

The spacing rhythm is Bootstrap's spacer scale — `mb-3` between fields, `mb-4`
between cards, `mt-5` above page content, `p-4` inside a wizard card. The system
does not invent spacing steps.

### Named Rules

**The Asymmetric Board Rule.** The member board is a flex row with deliberately
unequal grow weights, never an equal-width grid: the balance tile is the widest,
the first person tile next, the second narrower again, so a row of two reads
about 7/5 and a row of three about 45/32/23. The weights wrap; below 768px every
tile takes the row. A fixed grid is a hole whenever a family has an odd number of
children. The one exception is a family with more than one child: siblings are
peers, so the balance stands alone on the first row and the children share equal
columns under it — an equal group, not an equal page.

**The Page-Is-The-Menu Rule.** A signed-in reader's tools live on the member
page, gated one by one on the same predicate their view enforces; the header
carries no menu for them. A link kept in two places is two things to keep honest,
and a link whose gate has moved is a dead end. The page is the menu. The one
exception is the way back: a member page names the board above its title,
because the rule only holds for a reader who can reach the page the menu is on.

## Elevation & Depth

**Depth is a border, and a shadow is what replaces it — never both at once.**
The default surface is a card outlined in 1px black-at-12.5% with no shadow at
all. A card that is its own functional unit — a settings group that posts its own
form, the first-run wizard's card — drops the outline and takes a soft
charter-blue shadow instead. That swap is the whole elevation vocabulary; there
is no ladder of raised surfaces to climb.

The member board is the one place a whole page of surfaces floats. Each tile
drops its border for a blue-tinted shadow, because a 1px line on a full-bleed
gradient reads as a seam rather than as an edge. The shadow is the
functional-card lift at a lighter alpha (7%) — a dozen tiles share one ground,
and the settings card's shadow repeated a dozen times would be a storm. The dark
tile takes the same geometry at 18%, deepening with its weight rather than
changing its shape.

Outlines are also 1px and 12.5% black, and 1px `#dee2e6` for structure, so a
"filled" surface is never distinguished from a flat one by weight of line. The
only element that genuinely floats is the toast, which keeps the theme's own
shadow because it is positioned over the page rather than in it.

### Shadow Vocabulary
- **Functional card** (`box-shadow: 0 0.5rem 1.5rem rgba(10, 66, 117, 0.08)`): A
  card that is a unit of work — the wizard pane, a settings section. Comes with
  `border: 0`. It is tinted with the charter blue rather than black, so it reads
  as a soft lift rather than a drop.
- **Member tile** (`box-shadow: 0 0.5rem 1.5rem rgba(10, 66, 117, 0.07)`): A
  white person tile or the empty state on the gradient board. No border.
- **Member dark tile** (`box-shadow: 0 0.5rem 1.5rem rgba(10, 66, 117, 0.18)`):
  The household balance, and the tool tile that carries the dark note when there
  is no balance. The deeper alpha is what makes the one dark object sit above
  the white ones.
- **Member tool** (`box-shadow: 0 0.4rem 1.25rem rgba(10, 66, 117, 0.06)`): The
  resting action tile in the tools mosaic. Its hover lifts it to
  `0 0.75rem 1.75rem rgba(10, 66, 117, 0.12)`.
- **Floating overlay** (`box-shadow: 0 .5rem 1rem rgba(0, 0, 0, .15)`): Toasts
  only, inherited from the theme. Nothing else over the page uses a shadow.

### Named Rules

**The Border-or-Shadow Rule.** Never both on the same surface. If a card needs a
shadow, its border goes; if it needs a border, it gets no shadow. The two are the
same signal, and using them together makes a surface look like two. On the member
board the trade is explicit: the tiles have no border at all, because a 1px line
on the gradient ground reads as a seam.

**The Flat-Page Rule.** The page itself is flat. No section, band or container
lifts off the background — depth is spent only on cards that behave as separate
units, and never as decoration. The member board's tiles are those units at page
scale; the ground between them is still one flat light.

## Shapes

Squares with a shaved corner. The default radius is 0.25rem on cards, buttons,
inputs, badges and dropdowns — enough to read as soft, not enough to read as a
shape. Smaller controls step down to 0.2rem (`.btn-sm`, agenda chips) and larger
containers step up to 0.5rem (the wizard's branch blocks), so radius tracks the
size of the thing rather than a fixed scale.

The member board changes the scale without changing the language: page tiles
take 1.25rem, tool tiles and the monogram 1rem, the date leaf and the quiet-event
icon 0.875rem, and the tool icon 0.75rem. Chips, tile actions and the balance
door are the system's pill (999px). The one step up from the product's 0.25rem is
deliberate — these are objects on a board rather than rows in a document — and it
still tracks size: the outermost tile is the roundest, the marks inside it step
down. Tiles use `overflow: clip` so a divider or the dark tile's corner bloom
cannot paint outside its own corner.

Almost every line is 1px, at three values: `#ced4da` for input borders, 12.5%
black for card and dropdown outlines, `#dee2e6` for structural borders and the
agenda grid. Inside a member tile the line is lighter still (#eceff2) because it
divides two parts of one object rather than two objects. A thicker rule is
reserved for stating *which* thing you are looking at, and there are exactly
three in the codebase: the first-run wizard marks a step's summary and a
structure block's nesting with 3px `border-left` accents (`--bs-primary`,
`--bs-border-color`), and the branch rail heads each segment with a 4px rule in
that branch's own charter colour. All three are state, not decoration, and none
is a pattern to extend to a card that has no state to state.

The rail's 4px rule is where the desk's colour scale starts: 4px at full
strength saying which branch, the column behind it at 15% filling the room the
branch occupies, the year chip ringed at full over a 32% fill once it is chosen,
and the answer band's ground at full. One colour, five strengths, and the
strength tracks how close the visitor is to it.

Circular forms appear in three places, each time where the shape does semantic
work rather than decoration: the wizard's progress markers (done / current /
pending), the band's year-line dots, which mark a one-day activity on the axis,
and the member board's absence dot, which marks a reported absence beside its
count. A multi-day activity is the axis itself made 3px thick for its span; it
is the same mark at the strength a span asks for, not a second kind of badge. The
dark tile's corner bloom is a radial gradient, not a shape: it is light, and it
has no edge.

The one ornamental geometry in the system is the **topping**: the federation's
flag silhouette, repeated as a background image at 10% opacity behind a coloured
band (`.bg-topping-federation` with `.bg-topping-opacity-10`). There it is a
watermark, not a texture — it carries no meaning and never appears at full
strength. The branch's own topping on the answer sheet is the one that *does*
carry meaning, so it is spent differently: the coloured 100px tile at 12% on
paper, behind the sentence rather than in a frame beside it.

## Motion

**An entrance says where a thing came from, and there is one of them.** The
system moves to explain — a line drawn in the order it is read, a ground laid
down under the sheet that lands on it — and then it stops. A reader who is
working is never made to wait for the page to finish introducing itself.

The desk is the only surface with an authored entrance, and the reason is the
one the whole page rests on: it is the only thing the visitor operates before
they have any reason to believe the page is for them. Everywhere else the
system is quiet — a transition on hover or focus, a chip acknowledging the
touch — and that is all of it. There is no second entrance, no scroll reveal,
and no animation on a surface the reader is not already looking at.

The member board is quiet in exactly that way. A tool tile acknowledges the
pointer by lifting 2px and deepening its shadow over 150ms, and its corner arrow
comes from 40% to full while moving 2px; a tile action deepens its veil. Nothing
it says arrives on hover — the label, the icon and the arrow are visible at rest.
Under `prefers-reduced-motion: reduce` the lift and the arrow's travel are
removed and the state still registers as a shadow/opacity change.

### The two beats

- **The rail draws left to right.** One segment per branch, laid down in the
  order they are read — youngest branch first. The row is a twelve-year journey,
  so it draws in the order a journey runs, and the 80ms step between segments is
  what makes four bars read as one line rather than four things appearing at
  once. Stacked, the same step moves down the column, which is the direction the
  rail is read in there.
- **The band lays its ground down, then lands its sheet.** The branch's colour
  grows out of the band's top edge — out of the rail above it — and the paper
  carrying the answer settles onto it. Ground first, then paper, because that is
  what the band *is*: a sheet of paper lying on a branch's colour, and the one
  place the palette is spent at field scale.

On first paint the two run together as one sequence, the rail drawing while the
answer's sheet lands. On a swap — a year picked — only the band's beat replays,
because only the band changed; the rail is not rebuilt, so it is not redrawn.

### Named Rules

**The One-Entrance Rule.** One surface gets an authored entrance, and it is the
one the visitor operates. Everything else acknowledges a state change and stops.
A page of staggered section reveals is not this system.

**The Finish-Without-It Rule.** Every keyframe states only where the thing comes
*from*; the resting state is always the element's own rule, never the
animation's end frame. An animation that never runs — a browser without them, or
a reader who has asked for less motion — therefore delivers the finished design
rather than half of it. Nothing is ever hidden waiting for script.

**The Reduced-Motion Rule.** `prefers-reduced-motion: reduce` removes the
distance and keeps the arrival. The rail is simply already drawn, and the band
appears as one object, colour and sheet together, in a 200ms fade — the state
change still registers, and nothing moves. The chip and the segment a parent
touched were already confirmed in their own colour by then, so no choice is ever
answered with silence.

## Components

### Buttons

**Familiar and conventional** — Bootstrap's own four-part anatomy, unchanged:
1px transparent border, 0.25rem radius, `0.375rem 0.75rem` padding, 1rem type.
Nothing about a button is custom.

- **Primary:** Charter blue fill, white text. One per view — the action the page
  exists for ("Save", "Edit", "Next", "Add an activity").
- **Outline primary:** Blue text on transparent. The neutral peers of a primary
  action — section tabs, month arrows, "Today".
- **Outline danger / warning / secondary:** How every *removing* action is
  drawn — Deregister, Remove, Detach. Destructive actions are never filled.
- **Small (`btn-sm`):** 0.875rem type, `0.25rem 0.5rem` padding, 0.2rem radius.
  The default size for anything inside a table row or a toolbar.
- **The teal exception:** `.btn-info` — charter teal with *black* text — is the
  theme's default for the signed-in user's chip, and stays the teal one
  everywhere except the member page. There (`.page-member .navbar .btn-info`)
  the chip is pale green-to-blue paper — a 110° `#e9f4ee` → `#e7f0f8` gradient
  with the charter ink at 700 and a 2px white focus outline; hover steps the
  paper down to `#dceee4` → `#dae9f5`. Its `.bg-info` dropdown is white with
  ink items, so the account does not flash a third colour over the board. The
  theme's teal chip remains the only saturated fill in the system that takes
  dark text.
- **The account menu holds one door.** The signed-in reader's tools are on the
  page at `/`, so the chip opens a menu with only "Log out": profile, documents
  and staff destinations are tiles on the board, and a second copy in the header
  is a link to keep honest twice.
- **Hover / Focus:** Hover darkens the fill (primary → #093863) or floods an
  outline button with its own colour and flips the text to white. Focus is
  Bootstrap's ring, tinted with the charter blue — `0 0 0 .25rem rgba(10, 66, 117, .25)`.
- **On the member board:** the tile actions are the product's small outline
  button in a pill. The tile's first action is not filled; it takes a 12%
  Baladins veil with the charter ink on it, and hover deepens the veil to 20%
  rather than flipping the button. The whole-tile tool link takes a solid 2px ink
  outline offset 2 for focus, because a 25%-alpha halo on white is only about
  1.5:1 and a keyboard reader can lose it; on the dark tile the outline is white.

### Page head

Every signed-in page opens with its name in the display serif on the member
ground, with an optional one-line lede under it. There is no coloured band
between the bar and the content: the head and the page are one surface, and the
white tiles and cards carry the separation.

- **Markup:** `members/base.html` renders `hat_title` / `hat_text` inside
  `.page-head`; the title is the page's `h1` and the lede is `.page-lede`.
- **Type:** The title takes the surface-display step in Source Serif 4; the lede
  takes the Lede step in `muted-on-field`.
- **The way back is named.** A signed-in page carries "My space" (`Mon espace`,
  `Mijn ruimte`) as a white pill above its title: the board's own object at its
  smallest, no border, the member tile's soft shadow, a 2px ink focus outline,
  and a 2px leftward nudge of its arrow on hover. It is not a header menu: it
  names the one destination the bar no longer does, and it is visible on a phone
  without opening the collapsed menu. The head trims its top padding to 1.25rem
  so the pill does not push the title a full step down, and the board itself
  does not carry it.
- **No ground of its own.** A head that laid a second ground above the board's
  ground made the site open on a colour the signed-in homepage never used. The
  head is the identifier; the bar above and the tiles below are the chrome.
- **The public band is the exception:** its band is a photo rather than a flat band,
  and it stays an ordinary block in the flow (not absolutely positioned), so the
  desk under it sits directly beneath it. It is also the one band a troop writes
  itself: the unit's own name and description fill it, while the photograph is
  the one shipped with the application.
- **The band is the federation's green, over the photograph.**
  `--home-green` is charter-green-deep taken down until it can hold white type
  over any picture, laid over the image at 62–74%. It is the page's
  only large surface of colour that is not a branch's, and it is deliberately
  green: a scout unit's header rule that is not green is a header rule that has
  forgotten who it is for.
- **One colour doing the work of three.** It states the movement, it keeps the
  photograph *visible* instead of burying it under a grey of its own, and because
  it is a known colour at every height the contrast of the words on it is
  arithmetic rather than luck — 6.0:1 worst case for the description and 7.6:1
  for the name, measured over the brightest thing a photograph can be. It
  replaced a wash *and* a pool of blurred shade behind the words, and it is why
  the band needs neither.
- **Deeper at the top, lightest through the middle, deeper at the foot.** The bar
  sits on the deepest part and the words on the lightest, so the picture keeps
  the most of itself exactly where it is being looked at. The band ends on a hard
  edge, like a band and not like a fade.
- **It is shallower than the reference it was drawn from.** A hero is a way in,
  not a room.
- **Painted as a pseudo-element and never as a background layer**, so the green
  wash can sit between the photograph and the words. `backdrop-filter` and not `filter`,
  which is the load-bearing choice: a `filter` would dim the band and every word
  in it, while a backdrop filter acts on what is *behind* the layer and leaves
  the type sharp.
- **The band's words are one centred column of left-aligned type.** A unit's
  description runs to whatever length its troop wrote; past two lines a centred
  block stops being read as one statement and starts being read as a shape. The
  column is centred so the band stays symmetrical under the bar — the words
  inside it are not.
- **The signed-in pages have no band.** Their page head is the identifier; a band
  that repeated "your unit" above a page whose subject is the reader's own people
  would be a second title. The 84px bar, then the surface display title on the
  member ground.

### The band's year-line

The unit's year, drawn as one thin axis under its introduction: September to
July, a tick for every month, and the year's activities at the dates a
superuser entered for them. The hero carries an empty `data-home-timeline`
slot; the view fills it for the current school year, so the page and the
activity list cannot hold two versions of the same dates.

- **The axis is the calendar; the activity is the marker.** A 1px white rule
  runs across the eleven months, each with a 1px × 6px tick on its first day
  and a lowercase name at the Fact label step, so an activity reads against the
  month it falls in. A one-day activity is a filled 7px dot at its start date's
  day fraction; a multi-day activity is the same line made 3px thick, from its
  first day to its last inclusive. Both are placed by `--at`, a percentage of
  the real date span, and the bar's `--w` is its inclusive width.
- **No day is ever named in the text.** The label names the activity and, to a
  screen reader, its month; the exact day is read from the marker's position.
  This is the one place the system states a time by placing it rather than
  spelling it out, and "Dates indicatives" is the one qualification.
- **Labels take whichever side has room.** The server estimates each label's
  width from its name, alternates above/below, and moves a label to the other
  side when its span would touch the last one there. The September pair
  splits; a label that would leave the card runs back from the marker; a name
  longer than the single-line box asks the chart for its tall step, which
  gives the wrapped second line room.
- **The axis compresses; it does not stack.** Below `md` the event names step
  down to 0.875rem, and below `sm` every other month keeps its name while all
  eleven keep their ticks — the graphic survives at phone width instead of
  turning into a list.
- **It speaks in the band's own white**, at the Body note step for the event
  names, the Fact label step for the dates and the Eyebrow step for the note.
  The line lives inside the unit's card, so it has no colour of its own.
- **The window is fixed; the dates are not.** The axis is September 1 to
  August 1, and the superuser's activity dates are validated inside it. The
  homepage shows the current school year only, so next year's dates can be
  prepared without appearing early.

### The desk's rooms

The first thing the public page says before it says anything in words: the four
branches as one strip of four rooms, each as wide as its branch is long and in
that branch's own colour, laid across the width of the container at 14% over the
home ground. It is not a field the desk stands on — it *is* the desk's subject,
and the question sits above it rather than on it, because a question asked from
inside one of the four answers would be asked twice.

- **It is the rail's drawing, and the rail is not a second drawing.** The room
  and the branch's name stand in one box; there is no field behind a rail, and
  there is no gap between the rooms. They are one surface divided rather than
  four objects in a row, and a gap let the page show through every boundary as a
  bright hairline — which is what made four rooms read as four panels.
- **The rooms are drawn from the data, not from CSS.** Four fixed stops could not
  do this: a troop that renames, re-ages or drops a branch reshapes the whole
  strip from the same source, and the widths stay the branches' own age ranges,
  so the four read as one twelve-year journey rather than as four equal blocks.
- **A branch's rule is its colour at full strength; its words are its ink.** The
  rule only has to be seen and the name has to be read, and they are not the same
  value for two of the four branches — see `BRANCH_INKS`. A branch no preset made
  has neither: its room is the page's own ground and its rule is the section's.
- **The branch's own mark sits beside its name.** The federation's
  `logo_<Branch>.png` is spent at 4.59375rem beside the room's name. The name
  and its ages form one wrapping column next to the mark, so when a narrow room
  cannot hold both on one line the ages fall under the name rather than under
  the logo. A branch no preset made has no mark and keeps its words alone — the
  same rule as its colour and its topping.
- **The years sit on one line across the strip.** The rooms share their height
  and each year row takes the spare height, so a head that wrapped its ages to a
  second line does not push its own years below its neighbours'. Stacked, the
  room has no spare height and the row follows its head at the normal step.
- **The question sits above the strip, not on it**, in the display face and at
  the largest size on the page. The section is what a parent came for; it is not
  allowed to whisper, and it is not allowed to ask from inside an answer.
- **The chosen year is a solid chip in its branch's ink.** Not the branch's
  colour at full strength: at full strength Baladins carries white at 2.9:1, so
  the fill and the white on it are measured together — which is the only reason
  a filled chip is possible here at all rather than a chip with a ring around it.
- **Stacked, the rooms become cards.** They keep their own colour, take a corner,
  and the strip stops being a strip — the same statement said in the direction
  the page is now laid out.

### The answer sheet

A sheet of paper on the section's ground, and the one place in the band where a
branch's *full-strength* colour is spent. It is stated twice, and never in words
alone:

- **A slim rule down the sheet's left edge, in the branch's colour**, and **the
  branch's own topping as the sheet's paper**: the tile starts at that edge, runs
  behind the sentence and fades out before the action. The rule is 3px and inset
  from the corners: a frame as thick as the branch's colour deserves reads as a
  plate the sheet is mounted in rather than as the sheet's own edge, and the
  branch is already stated by the name in the sentence and by the chip the
  visitor chose.
- **The mark is stated again at the sheet's scale.** The branch's
  `logo_<Branch>.png` stands at 3.5rem above the answer's label, so the mark a
  parent scanned in the rail is the one naming the branch in words.
- **The topping is the coloured 100px tile the federation ships**, repeated at
  12% behind the words and masked to nothing across the right half of the sheet.
  The theme's own `.bg-topping-*` classes only reach the white cut, so the
  coloured tile is loaded from the vendored
  `template-unite/images/toppings/…_100.png` files, keyed by the same
  `Branch.key` as `BRANCH_COLOURS`. It is paper, not a picture: a texture behind
  the sentence rather than a stamp beside it, and a branch no preset made still
  gets no mark.
- **Faded is not unread.** White paper under a 12% tint leaves the sheet's inks
  well past AA, and the mask is what keeps the pattern from ending on a
  rectangle behind the text.
- **The branch's name is written in its ink and the sentence around it is not.**
  It is the one place on the page where the colour is the point of the sentence:
  a parent who has never heard of this troop reads one word of it.
- **The action is the second door on the page** — the same green and the same
  pill as the bar's own, because both are ways in and a way in is not a button
  inside the product.
- **With nothing chosen it is the same sheet**, with its edge in the section's
  rule rather than in a colour, because no branch has been named.

**The Never-On-The-Field Rule.** Copy is never set *on* a charter field. White
type fails AA on the Baladins blue and dark type fails on the other three, so
the paper goes between them every time. The field may carry meaning; it may not
carry words.

A **tint** of a branch colour is not that field. At the 14% a room lays down,
the page's own ink and every value in `BRANCH_INKS` clear AA, which is what lets
the question and the branch names stand on it. The line is where the ground stops
being paper with a colour in it and starts being the colour: past that, the paper
has to come back between the two — which, once a year has been chosen, is exactly
what the answer sheet does. The member board stays on the paper side of that
line: its strongest branch tint is 13%, and its one dark surface is a *darkened
mix* of two branch colours, not either one at full strength, which is why white
type can stand on it.

**The Ink-Not-The-Colour Rule.** A branch's colour is stated twice on the page
and written once. The room, the rule and the mark take the colour at the strength
their ground allows; the branch's *name* — in the rail, on the chosen year, in
the sentence that names it — takes `BRANCH_INKS`, which is the same hue darkened
until it can be read. These are not two colours. They are one colour used for two
jobs that do not have the same requirement, and no branch is ever renamed by it:
Baladins' room is still #00a0de.

### Place

Where the unit meets, under the desk and the other half of the same answer: one
raised surface holding the hall, the address, a directions link and — when the
troop uploaded one — its own picture of a map.

- **It is a full-bleed band on the desk's own ground.** The desk and the place
  are the visitor's half of the page — the question and the place to turn up —
  so they share one light rather than telling the eye the page changed hands in
  the middle of one answer. The white card is what separates the address from
  the branch strip. The band runs edge to edge so the card sits on a field
  rather than in a box.
- **It carries an eyebrow and the troop's own name for its hall.** The label says
  what the section is; the heading is whatever the troop called the place, which
  is the whole point of the setting, at display size. A unit that has not named it
  gets the label alone — the same sentence twice is not a heading.
- **It has a measure, not a fit.** `width: min(100%, 60rem)`. It was
  `fit-content`, which reads better as an intention than it works as a rule: on
  a flex row allowed to wrap, a fit-content container takes the width of its
  *widest single item* rather than of the line they would make, so the card
  stopped at half the page and left the address floating in a dead half beside
  it — and at any wider map it gave up and wrapped the map under the words.
- **The two columns divide the measure.** The words take a column of their own
  and never stretch — which is what keeps the address beside its own map rather
  than an arm's length from it, the fault a stretched grid cell had — and the
  map takes everything else up to 36rem.
- **The words are centred against the picture.** An address is three lines
  beside a picture a hundred tall; pinned to the top it reads as having fallen
  off the top of its own card.
- **The map is content, not a control.** It wears the radius a container wears
  and no border, and the anchor around it is what draws the focus halo — without
  that radius the halo would be a rectangle around a rounded picture.

### The closing notes

The public page's last two blocks are the troop's own words, and the only plain
text on the page: a longer introduction and the questions a parent asks before
registering. Each is a white sheet on the home ground, under the place, with
the address card's soft shadow and the page's own eyebrow-then-title opening.

- **One sheet per block, one measure.** About and the FAQ share the 60rem
  column the place card occupies; the words inside stop at 68ch. The sheet is
  the object and the measure is the reading; neither pretends to be the other.
- **The FAQ is a definition list.** A question in the display serif at the
  Title step, its answer in Muli, and one structural 1px rule between entries.
  The rule runs the sheet's full width while the answer keeps its measure, so
  a long list scans as questions rather than as a column of prose.
- **Plain text, parsed once.** The troop writes one paragraph per block for
  About; for the FAQ, one question per block separated by an empty line, the
  first line the question and the rest the answer. The template tag that splits
  it is the same rule the help text promises, so a volunteer never learns
  markup to answer a parent.
- **A block with nothing written in it is left out.** A content module carries
  its switch and its words together in the settings card; the page tests both,
  and an empty sheet is never rendered.
- **The band is the page's `h1`.** Switching it off leaves a visually hidden
  `h1` carrying the unit's name, so the outline stays correct and the visible
  blocks keep their own levels rather than one of them being promoted.

The page is composed on the settings card rather than in a template: the
introduction (with the year-line's dates), the desk, the place, About and the
FAQ each carry their switch and the fields that configure them. The year-line
is the one list, saved as a formset with the rest of the card, so a page
composed and a date added cannot half-apply.

### The member board

The signed-in homepage is a board of the reader's year, not a form report. Its
subject follows the role — a parent's children, a leader's single section, the
unit's tools for staff — but every item keeps the tile shape, so the page is
predictable whatever the reader answers for. An animateur leads exactly one
section; the page renders one section panel from the first section the reader
can edit, even if bad data holds a second. The head is the surface display title over one
summary line: the reader's name in the ink at 700, then the counts that explain
the page ("3 children linked to your account"). The greeting is part of the
summary because the page is a tool that knows who is holding it, and the line
already has room. A leader's summary carries no section count: an animateur
leads exactly one, and the tile below already says which.

- **One subject, one tile shape.** A child and a section share the head, the
  date leaf, the event block, the presence line and the foot. Only the monogram
  and the count change. A page that changed its card shape with the role would
  make a parent and a leader learn two objects.
- **The board is the first thing under the head.** There is no band and no
  toolbar between them. The balance tile (when it exists) and the first person
  tile are the first viewport's content — except in a multi-child family, where
  the balance takes the row alone and the children follow in an equal row; the
  tools follow the board.
- **Only one group is loud.** The dark note is either the balance or the
  featured tool, never both, and the featured group is the reader's own work:
  staff lead with the unit, a leader with sections, a parent with children.
  Account and site are always last and always the smallest.

### Person tiles

The tile a parent or leader actually reads. It states the next commitment first,
the attendance second, and the two or three things the reader can do about it
last.

- **The head.** A child gets a 3.5rem rounded-square monogram, two initials in
  the display serif, tinted 13% Baladins blue — a piece of the board, not a
  profile avatar — and the branch's own mark at 3.5rem on the right, the height
  of the name and section lines together. A section gets the same mark at
  2.5rem beside its name, and its member count as a numeral at 2rem in the
  display serif with tabular figures at the right edge, over an uppercase label
  at 0.75rem. A branch no preset made has no mark, and a section with no branch
  gets none. The name is 1.75rem display serif; the line under it is 0.9375rem
  muted. A section named after its branch drops the branch line rather than
  stuttering it.
- **The date leaf.** The next commitment is a 3.75rem leaf: the day at 1.875rem
  display serif with tabular figures, the month at 0.6875rem uppercase, on a 9%
  Louveteaux-green tint with a 0.875rem radius. It is the only tint inside a
  white tile (the activity chip keeps its charter state colour), and it is the
  first thing a parent checks. The full date still
  lives in the `<time>` value and a visually hidden phrase, so the leaf is a
  shorthand, never the only version.
- **The event.** The activity title is 1.0625rem at 700 on the ink. The line
  under it carries the type chip, the weekday and the time. The chip is a pill
  (999px), 0.75rem white at 700, filled by the charter's activity mapping:
  blue-deep reunion, green-deep day, plum weekend. The type is always written —
  colour never carries it alone.
- **The presence line.** "No absences" is a green check and the muted voice.
  A reported absence is a charter-crimson dot and the count in the absence ink
  (#b30d31) at 700. It is the one line in the tile that leaves the muted voice,
  because it is the one state the reader has to notice. Nothing scheduled is not
  an error: the leaf's slot becomes a paper-filled icon square and the tile says
  so in the muted voice.
- **The foot.** A 1px divider (#eceff2) and the actions, pushed to the tile's
  floor with `margin-top: auto` so a row of tiles with different middle lengths
  still lines its buttons up. Every action is the product's small outline button
  in a pill. The first action takes a 12% Baladins veil with the ink on it — a
  filled button in every tile would be a wall of navy — and hover deepens the
  veil to 20%. Report an absence, Messages, Edit details; Add an activity,
  Messages, Send a message. The link exists only when the view behind it would
  answer.
- **Agenda off means the block is gone.** The activity, the leaf, the chip and
  the presence line all disappear together; a tile with an empty leaf is worse
  than a tile without one. The head and the actions that do not need the agenda
  survive.
- **A section tile goes wide.** At `lg` the tile becomes a grid: identity and
  attendance left, the next event right behind a 1px vertical divider, the
  actions across both feet. It is the same tile for a one-section leader, laid
  out across the row it owns.

### The household balance tile

The board's one dark note and the only place the reader's money is stated. Fees
are billed per household, not per child — the eldest pays in full and siblings
are discounted — so a per-child balance would be a lie. The tile is above the
person tiles, and there is exactly one.

- **The ground.** A 145° gradient from `member-dark-green` to `member-dark-blue`
  — the two branch colours the page ground is mixed from, taken down with
  #0b1a12 until white type is comfortable — plus one 32% charter-sky radial
  bloom in the bottom-right corner. The bloom is light, not a second colour; it
  keeps the flat gradient from reading as a printed swatch.
- **The contents.** "Household balance" at 0.75rem uppercase, 700, 72% white;
  the amount at `clamp(2.5rem, 4.6vw, 3.25rem)` in the display serif with
  tabular figures; then the notes at 0.9375rem, 82% white, and the quiet ones at
  68%. The discount sentence is printed only when the troop's own fee table
  discounts; a balance with no deadline prints no date.
- **Overdue is rose.** The deadline note becomes `member-late-on-dark` (#ffd1db)
  at 700. Crimson itself fails on this ground; the rose is the same warning at
  the contrast the tile allows, and it is the only colour in the tile.
- **The door only exists where it opens.** A reader with finance access gets
  "Open the ledger" as the one light surface on the dark tile — a white pill with
  the ink on it, hover to #eaf5fb, focus a 2px white outline. A parent gets the
  sentence "Payments are recorded by the unit's treasurer" instead, because the
  finance views 404 for them and the product has no parent-facing payment step.
- **No money, no tile.** When the household owes nothing, or fees are off, the
  tile is absent rather than rendered at zero; the dark note moves to the
  featured tool's first action. A settled household's page is the board of its
  people and the tool mosaic.

### The tool mosaic

The reader's other tools, and the only navigation a signed-in reader has. It is
tiles, not a link list: a menu whose entries all have the same weight is a menu
nobody scans.

- **The page is the menu.** Every entry is gated in `_member_tools` on the same
  predicate its view enforces; a link whose gate has moved is a dead end. The
  header carries no menu for a signed-in reader — the brand, the account and the
  language remain.
- **Groups, not a flat run.** Groups are sorted by role: the reader's own group
  first, account and site last. The group with the most entries takes the wide
  tiles (`1.5` grow, 24rem basis); its first tile spans both columns and, when no
  balance has spent the dark note, becomes the dark tile. Its label is 1.25rem
  instead of 1rem.
- **The tint names the group.** Children at 7% Baladins blue, sections and the
  unit at 6% Louveteaux green, account and site white. The tints are mixed over
  white, not over the page ground, so a tile stays a tile wherever it lands.
- **The whole tile is the link.** A 2.25rem icon square (0.75rem radius, 7% ink
  veil), a 1rem bold label, and a corner arrow at 40% opacity. The label and the
  arrow are visible at rest; hover lifts the tile 2px and brings the arrow to
  full, but nothing has to be hovered to be understood.
- **A wrapped label does not make its tile taller.** The list is a grid and its
  items are flex containers, so the anchor fills the row's height; two tiles
  side by side stay one object even when one label runs to a second line.
- **Focus is an outline, not a halo.** A whole-tile link needs a mark that
  survives the white and tinted grounds: a 2px solid ink outline offset 2, white
  on the dark tile. A 25%-alpha halo measures about 1.5:1 over white and is a
  state a keyboard reader can lose.
- **The lead tile is larger, not louder.** The size difference and the first-tile
  span say which action leads; the dark gradient is spent only when the tile is
  the page's one dark note, so the page never has two competing anchors.
- **A tile says what is behind it.** Under the label sit up to two facts — the
  next activities, the newest documents — at the Fact label step. The first
  carries the full ink and the lines under it a step lighter; nothing is faded
  out, because a fade reads as disabled text and, with exactly two items,
  promises a third that is not there.
- **One tile reports instead of leading.** The unit's new-members tile states
  work waiting: a 14% charter-orange tint, a 45% ring, a 28% icon square and the
  count as its one detail line. It takes the loud note in the featured group's
  first slot instead of the dark gradient, so a staff page does not spend two
  anchors.
- **On a phone the children group takes the full width.** Its labels and detail
  lines are the longest in the mosaic, and two columns leave "Add an already
  registered child" four lines deep; below `md` its list is one column and the
  first and third spans are dropped.
- **A childless parent leads with the way in.** With no child on the page the
  calendar has nobody on it, so the lead group's first row is the two ways to
  add one — "Add a child" (the dark note) and "Add an already registered
  child" — and the agenda takes the full row under them. The first-tile span
  is turned off there: the pair is the lead, not one tile above the rest.

### The reader's lists

The pages reached from the board — a section's message history, the sent
messages, the documents page — are lists of the unit's own things, so they use
the board's objects rather than the theme's striped table. Each entry is a
white tile at 1rem radius with the same soft charter-blue shadow as the tools: a
date leaf at 9% Louveteaux green for a message (the thing a parent scans first),
the subject in the display serif at the Title step, and the sender and time in
the muted-on-field voice. A document swaps the leaf for a 2.25rem icon square.

The tiles are plain list items, not rows: a message the reader may open is a
whole-tile link with the board's 2px ink focus outline, and one they may not is
a div, so no row pretends to be clickable. The empty state is the same white
tile with an icon and one sentence, never an empty striped row.

The message detail turns the list inside out: one sheet carries the sender, the
body at a 68ch reading measure and its attachments; a second carries the
recipient table. A confirmation page is one sheet holding the decision and its
actions, and a destructive action stays an outline — Deregister, Detach and
Remove are never filled.

### Cards / Containers
- **Corner Style:** 0.25rem, outlined in 12.5% black, no shadow.
- **Background:** White, or `bg-white` on a header that would otherwise inherit
  the theme's 3% black tint.
- **Shadow Strategy:** See Elevation — a functional card trades its border for
  the charter-blue shadow. The member board's tiles are the page-scale version of
  that trade: 1.25rem corners, no border, one soft blue shadow.
- **Internal Padding:** 1rem (`card-body`), 1.5rem where a card is a page of
  its own (the wizard's `p-4`).
- **Headers:** Carried in the card itself, not as a separate bar — the settings
  page sets `.card-header bg-white` so the group's name is a title, not a chrome.

### Inputs / Fields
- **Style:** Paper fill (#f2f5f8) — the same colour as the page — with a 1px
  `#ced4da` border and a 0.25rem radius. A field is a well in the page, not a
  white box on it. Text is charter blue.
- **Focus:** Border shifts to `#85a1ba` and a 4px `rgba(10, 66, 117, .25)` halo
  appears. The halo is the primary focus affordance; the border change alone is
  too quiet to rely on.
- **Selects:** Same treatment with the theme's own chevron. Checkboxes are
  labelled to the right of the control, never above it.
- **Field markup:** Label, then control, then `.form-text` help — in that order,
  every time. Multi-selects and file fields render bare under a `.form-label`
  div, because their native widget resists the class.
- **Help text:** Muted (#6c757d) at 0.875rem, directly under the control.
- **Error:** The message, not the field, turns red — an inline
  `.alert-danger.small.mt-1` under the control, plus `role="alert"`. The control
  itself keeps its normal border; there is no red-field treatment in this system.

### Feedback
- **Form-level errors:** `.alert .alert-danger` with `role="alert"`.
- **Confirmations:** `.alert .alert-success` with `role="status"` — a saved
  settings group says so in place, at `py-2`.
- **Toasts:** Fixed top-right, `aria-live="assertive"`, and deliberately
  non-autohiding (`data-bs-autohide="false"`) so a message that matters cannot
  disappear before it is read. Coloured by message tag.
- **Dialogs:** A single `#modal` / `#dialog` pair is the HTMX swap target for
  every modal in the application. There is one, and it is reused.

### Tables
- **Style:** `.table`, with `.table-sm` and `.table-striped` for lists and
  `.table-bordered` for the agenda grid. Always wrapped in `.table-responsive`.
- **Density:** `0.25rem` cell padding at the small size; the header row carries
  the meaning and the rows carry the data.
- **Alignment:** `.text-end` for action and numeric cells; names read left.
- **Ceilings:** A free-text column that would otherwise wrap gets an explicit
  `max-width` (the household column is 16rem) rather than a truncation rule.

### Agenda Grid
The other bespoke component: a month as a real `<table>`, one row per week, one
cell per day.
- Each day is a single full-cell `<button>`, so the entire cell is the target
  rather than the chips inside it.
- Events are chips coloured by activity type from the charter palette, with the
  time inside the chip at 85% opacity.
- Out-of-month days are tinted with the secondary colour at 5% and their date
  number dropped to 45% — quieter, still readable on purpose.
- The grid never depends on hover: every control carries a plain `href` as well
  as its HTMX attributes.
- Below `md` the grid keeps a readable width (44rem) and scrolls sideways inside
  a labelled, keyboard-focusable region. The wrapper carries a soft ink shade at
  its right edge so the days beyond the fold — usually the weekend — are visible
  rather than simply absent.

## Do's and Don'ts

### Do:
- **Do** load the vendored theme first and `troopconnect.css` second — the order
  is what makes the override layer work, and reversing it silently disables every
  deviation.
- **Do** keep `troopconnect.css` small. Only put a rule there that the theme does
  not already state; a restated rule is a copy that can win after a theme upgrade.
- **Do** pair a `.btn-primary` with `.btn-outline-primary` on the same row, and
  give a destructive action an outline button — Deregister, Remove and Detach are
  all outline, never filled.
- **Do** give every field a `<label class="form-label" for="...">`, then the
  control, then `.form-text` for help — in that order.
- **Do** use `role="alert"` on errors and `role="status"` on confirmations, and
  keep errors as text under the control rather than as a red field.
- **Do** wrap every `.table` in `.table-responsive`, and put a `max-width` on a
  free-text cell instead of letting the row grow.
- **Do** open every members page with the page head (`hat_title` + `hat_text`):
  the title in the display serif on the member ground, never a coloured band.
- **Do** ship a plain `href` or `action` alongside every HTMX attribute, so the
  page still works when the swap does not.
- **Do** set the navbar's 84px height in px and keep `--site-navbar-height` in
  px to match; the navbar does not scale with the root font size.
- **Do** state the household balance once, above the person tiles, and never per
  child — the household is the billing unit, and the eldest child pays in full.
- **Do** build the member board as a flex row with unequal grow weights, so one,
  two or four tiles each fill their row without the equal-card symmetry — except
  a multi-child family's children, which are equal peers under the balance tile.
- **Do** spend exactly one dark tile per member page: the balance when there is
  money owed, otherwise the featured group's first action.
- **Do** give each person tile a date leaf, a type chip and an absence state when
  the agenda is on; when it is off, remove the whole block rather than leaving an
  empty leaf.
- **Do** mix tool-cluster tints at 6–8% over white, and keep the label in the
  page ink rather than in the tint.
- **Do** set board numerals in the display serif with tabular figures, and keep
  numbers inside sentences in Muli.
- **Do** use the solid ink focus outline on a whole-tile link, and white on the
  dark tile.

### Don't:
- **Don't** edit anything under `app/static/vendor/template-unite/`. It is
  byte-identical to a known upstream commit, and a local edit is lost at the next
  theme refresh and invisible in the diff that would have caught it.
- **Don't** introduce a colour. The palette is the federation's — if a new state
  needs a colour it takes one from the list above or it takes none.
- **Don't** set Housepaint, CaveatBrush, Mali or Roboto Mono. The application
  speaks Muli; those faces exist in the theme for pages this project does not
  build.
- **Don't** put a border and a shadow on the same card — that is two signals for
  one surface.
- **Don't** colour body or heading text to add emphasis. Weight is the tool.
- **Don't** style the site header with a bare `header` selector. The public
  page's hero band is a `<header>` too, and a bare selector reaches into it.
- **Don't** use `window.alert()` for feedback. Toasts and inline alerts exist,
  and a browser alert cannot be translated or styled.
- **Don't** build a second modal. `#modal` / `#dialog` is the dialog, and every
  HTMX view targets it.
- **Don't** add a page that has to be read on hover to be understood — nothing in
  this system depends on pointer state to be legible.
- **Don't** put a mask or a clip on a container whose children are meant to paint
  outside it. Both clip to the element's own border box, so a fade that lives one
  level too deep cuts off exactly the overflow it was placed to soften — the desk
  field's mask sits on the field's full-width box, never on the container its
  bleeds are supposed to cross.
- **Don't** put a balance or a Pay button on a child's tile. Fees are per
  household and the finance views 404 for anyone without access; the treasurer
  sentence is the honest version for a parent.
- **Don't** replace the member board with an equal-width card grid. The unequal
  grow weights are the composition, and a fixed grid leaves a hole on an odd
  number of children. Equal columns belong only to siblings under a balance
  tile, never to the board as a whole.
- **Don't** add a header menu for signed-in readers. The page is the menu, and a
  link kept in two places is two things to keep honest.
- **Don't** use a branch's full-strength colour as a tile ground. Tints stay at
  6–13% over white, and the one dark tile is a darkened mix of two branch
  colours, not a charter field.
- **Don't** let a long name or activity title truncate inside a tile. Names run
  to 150 characters and titles to 200; they wrap with `overflow-wrap: anywhere`
  and a `min-width: 0` on the flex/grid child.
- **Don't** give the member page a second dark surface or a second primary
  action. One dark note, one lead tile, and the rest of the board is paper.
