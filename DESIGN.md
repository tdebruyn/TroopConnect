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
typography:
  display:
    fontFamily: "Muli, sans-serif"
    fontSize: "calc(1.375rem + 1.5vw)"
    fontWeight: 700
    lineHeight: 1.2
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
  banner:
    backgroundColor: "{colors.charter-sky}"
    textColor: "{colors.white}"
    padding: "3.625rem 0.75rem 0.5rem"
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
deviations: a hero band, a first-run wizard, an agenda grid, one table column
with a ceiling. The rule that makes this work is that the override file stays
small; a rule that merely restates one the theme already makes is a liability,
because the theme can move under it and the local copy would win.

The result is deliberately unglamorous and consistently so. Density follows the
task rather than the brand: a settings page is a stack of cards, a member list is
a striped table, a form is one labelled field per block. The federation shows up
in flat charter colour and in bold Muli — and, in three places, at field scale
rather than as an accent: the banner's flag silhouette behind a page title, the
ground the enrolment desk stands on, which is the four branches drawn as four
columns, and the desk's answer, which takes the matched branch's own colour as
its ground. There is no troop-level colour, no theme picker, no second accent:
the palette is the federation's, and the unit's identity is carried by its name
and the logo it uploads.

**Key Characteristics:**
- Bootstrap's own primitives, used as intended, restyled only where a task needs it
- One typeface (Muli) and one flat charter palette, both inherited, neither configurable
- A sky-blue banner with the federation flag behind it as the recurring page opener
- Thin 1px lines and soft 0.25rem corners; depth by border, not by shadow
- Paper-filled fields on a paper-coloured page, separated by a border and a blue focus halo
- The homepage's desk standing on the four branches' colours, at the one place the page spends them
- Two shells: the site (fixed 110px navbar) and the first-run wizard (its own page, same theme)

## Colors

Flat charter inks on a pale blue-grey paper — saturated and confident in small
areas, nearly monochrome over most of the screen. Every colour here is the
federation's; none was chosen by this project.

### Primary
- **Charter Blue Deep** (#0a4275): The ink. Body text, every heading, links, the
  primary button, the navbar gradient, and the focus halo. It is also the page's
  *only* text colour — there is no separate near-black; headings and body differ
  by size and weight, not by colour.
- **Charter Sky** (#15adea): The banner band. Used behind the page title on every
  members page, and nowhere else. See Components → Banner.

### Secondary
- **Charter Green Deep** (#304a3c): The quiet second voice — the navbar's
  secondary surface and the "day activity" chip. Dark enough to read as a
  neutral, green enough to be a charter colour.

### Tertiary
- **Charter Teal** (#2b99a4): Bootstrap's `info`, and the one place the system
  puts black text on a saturated fill (the navbar's user chip). A deliberate
  oddity, not a pattern to extend.
- **Charter Green Bright** (#95c11f): `success`. Confirmation only — a saved
  settings group, a successful toast.
- **Charter Orange** (#ef7b00): `warning`. The "detach" action and the
  staff-facing failed-mail banner.
- **Charter Crimson** (#d60f3c): `danger`. Destructive actions and every form
  error.
- **Charter Plum** (#4e1d4f): The "weekend" chip. The deepest colour in the
  system, and the only one that reads as dark rather than bright.

### Neutral
- **Paper** (#f2f5f8): The page background *and* the fill of every text field.
  Fields are not white — they sit on the page as slightly darker wells defined by
  their border. This is the single most distinctive thing about the form layer.
- **Home Ground** (#dde5ec, `color-mix(in srgb, #0a4275 9%, #f2f5f8)`): The
  ground the desk's section is laid on, so the section reads as a band of the
  page rather than as the page. It is *derived* rather than picked, so it moves
  with the ink it is mixed from, and it exists only on `/` — no members page ever
  sees it. It is also the base the four branch rooms are mixed into, which makes
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
- **Warm Paper** (`color-mix(in srgb, #ef7b00 6%, #f2f5f8)`): The page's own
  paper warmed with the charter's ochre, and the ground of the "where to find us"
  band. A second *section* colour and not a second brand colour: the page changes
  ground between sections so the eye is told one ended, and it changes it inside
  the federation's palette.
- **White** (#ffffff): Cards, dropdowns, modals, the navbar's overlay surfaces.
  Nothing else is white.
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
  well as on `paper` (5.95:1), and on `home-ground` itself.
  The rung is a *measurement*, not a choice, and it is re-measured whenever the
  ground under the tints moves: the tints are read through `home-ground` now
  rather than through `paper`, and the value that cleared the old ground (4.63:1
  worst) came out at 4.35:1 on the new one — a failure thin enough to pass
  unnoticed again. Any further change to `home-ground` or to the field's
  strength has to bring this rung back with it.

### Branches

The federation draws a colour for each branch, and they are a fourth family
apart from the charter inks above: `BRANCH_COLOURS` in `homepage/views.py` maps
`Branch.key` — the preset slug, not the name a troop gives it — to the theme's
own branch colour.

- **Baladins** #00a0de, **Louveteaux** #296f52, **Éclaireurs** #004f9f,
  **Pionniers** #d51317.

They are spent on the homepage, where the branches are the subject, and in five
strengths of one idea: the desk field's columns at 15%, the rail's 4px rules at
full, the year chips' rings and fills at full and 32%, and the answer band's
ground at full. A branch no preset made has no colour and gets none: a made-up
one would claim a meaning it does not carry, so its rule is the structural line,
its column is nothing, and its answer band is the plain outlined one.

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
today that is the agenda's three activity types (`charter-blue-deep` reunion,
`charter-green-deep` day, `charter-plum` weekend) — and never by inventing a hue
or reaching for a Bootstrap default that the theme did not override.

**The Shared Ground Rule.** The hero band and the desk are two elements of one
field. The band's settle ends on `home-ground` and the desk *begins* on it, with
no gap between them, and that is what makes the join invisible. Changing one
without the other puts a seam across the top of the public page — and it lands
at exactly the height where the photograph stops, which is the most visible
line the page could have. Both read it from the one `--home-ground` in `:root`
because the two elements are siblings and neither owns it.

## Typography

**Display Font:** Source Serif 4 (with `Georgia, serif`)
**Body Font:** Muli (with `sans-serif`)
**Available but unused:** Housepaint, CaveatBrush, Mali-Bold, Roboto Mono

**Character:** A humanist sans for everything the product says, and a serif for
the things it *names*. Muli runs in nine weights and carries every label, table
cell, button and paragraph; Source Serif 4 carries the unit's own name, a
section's heading, a branch's name and the desk's closing sentence — the words
that are titles rather than prose.

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
- **Display** (700, `calc(1.375rem + 1.5vw)` → 2.5rem, 1.2): The page title
  inside the banner. Fluid between roughly 1.6rem and 2.5rem. One per page.
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
| Question | 3rem (2.125rem under 768px) | The enrolment desk's `h1` |
| Surface title | 2.125rem | "Vos enfants", "Votre unité" |
| Panel name | 1.375rem | A child's or a section's name |
| Answer | 1.75rem | The branch a birth year lands in |
| Lede | 1.0625rem | Desk lede, CTAs, the household summary |
| Note | 0.9375rem | Federation line, branch legend, household notes |
| Fact label | 0.8125rem | Panel row labels, activity chips |

It is a second scale and is documented as one rather than folded into the
theme's, because the two answer different questions: the theme's ramp sizes
*page structure*, the override scale sizes *one working block*. They do not
collide — Bootstrap caps `h1` at 2.5rem above 1200px, so the desk's question
stays the largest type on the page at every width.

### Named Rules

**The Two-Voice Rule.** The application speaks Muli and *names* in Source Serif
4. The boundary is display versus everything else — a unit's name, a section
heading, a branch's name, the desk's closing statement are display; a button,
a table cell, a help line, a form label are not, however emphatic. A third face
is a departure from this system rather than a flourish within it, and the
theme's four decorative faces (Housepaint, CaveatBrush, Mali-Bold, Roboto Mono)
are still not it: they are costume, and a title is not a costume.

**The Two-Scale Rule.** A new block sizes itself from the override scale above
and never from an ad-hoc value; a page's structure keeps to the theme's ramp.
Adding a step to either without recording it here is how a system stops being
one.

**The Weight-Not-Colour Rule.** Emphasis is 700, not a hue. Never colour text to
make it louder — the palette has no text colours to spend, and every heading
already shares the body's ink.

## Layout

A single Bootstrap 12-column grid inside a `.container`, with two page shells
sharing it.

**The site shell** is fixed: a 110px navbar (set inline in `base.html`, and
mirrored as `--site-navbar-height` in CSS in **px, not rem**, because the navbar
itself does not follow the root font size), then an optional banner, then a
`.container` holding the page.

It is a **full-height column** — `body` is `display: flex; flex-direction:
column; min-height: 100vh` — so that a page shorter than the window still ends
at the window's edge rather than at whatever its content stopped on. The footer
sits in a `.site-footer-slot` whose auto margin spends the height a short page
does not use. The slot exists so the *footer* keeps its own 3rem gap: an auto
margin on the footer itself would eat that gap on every long page, and on a page
that already fills the screen the whole mechanism is inert.

**The navbar is a pane of glass.** Its height and the two properties that make
it what it is live in inline style on the element, because `.bg-primary` carries
the navbar's fill with `!important` and only an inline `!important` out-ranks
it. The two properties are named in `:root` and *applied* by `base.html`
(`--site-navbar-fill`, `--site-navbar-backdrop`), which is what lets a page
restate them without a style attribute of its own.

- **What is behind the glass is what you see.** A `backdrop-filter` blurs and
  dims the backdrop — the band the page opens with — and the fill is only a tint
  laid over the result. That is why the bar reads as the band seen through
  glass rather than as a bar of its own colour.
- **The dimming is the guarantee, the alpha is the look.** White nav links are
  legible only while their ground stays dark, and a troop's photograph may be
  bright anywhere in it. The fill's alpha can never promise that; the
  `brightness()` in the backdrop filter can, and it is what lets the default bar
  work over paper and the homepage's over a photograph.
- **The glass only sees what is painted before it.** `z-index: 2` on `.navbar`
  is load-bearing rather than tidy: the hero band is a positioned sibling that
  comes later in the document, and without the order stated the band paints over
  the bar and swallows the logo and the menu.
- **The homepage restates both values** (`.page-home`, read off the `body_class`
  block). Its band is dark underneath, so it can drop the fill to 30% and let the
  photograph through; every other page has paper behind the bar, where the same
  alpha washes it out to a pale slate and the two stop looking like one site.

Content is laid out at `col-md-12` by default and
split into halves or thirds only where two things genuinely sit side by side; a
form is one full-width field per block.

**The wizard shell** deliberately does not extend `base.html` — its header and
navigation would point at pages that do not exist yet. It keeps only the
stylesheets, centres a `col-lg-9 col-xl-8` column on a `setup-page` background,
and swaps a single `#wizard-pane` element over HTMX.

Breakpoints are Bootstrap's. `md` (768px) is the load-bearing one: the navbar
collapses and the grid halves there. `xxl` is used once, to inline the Sections
dropdown in the navbar. Single-column stacking holds all the way down; nothing in
the system depends on hover.

The spacing rhythm is Bootstrap's spacer scale — `mb-3` between fields, `mb-4`
between cards, `mt-5` above page content, `p-4` inside a wizard card. The system
does not invent spacing steps.

## Elevation & Depth

**Depth is a border, and a shadow is what replaces it — never both at once.**
The default surface is a card outlined in 1px black-at-12.5% with no shadow at
all. A card that is its own functional unit — a settings group that posts its own
form, the first-run wizard's card — drops the outline and takes a soft
charter-blue shadow instead. That swap is the whole elevation vocabulary; there
is no ladder of raised surfaces to climb.

Outlines are also 1px and 12.5% black, and 1px `#dee2e6` for structure, so a
"filled" surface is never distinguished from a flat one by weight of line. The
only element that genuinely floats is the toast, which keeps the theme's own
shadow because it is positioned over the page rather than in it.

### Shadow Vocabulary
- **Functional card** (`box-shadow: 0 0.5rem 1.5rem rgba(10, 66, 117, 0.08)`): A
  card that is a unit of work — the wizard pane, a settings section. Comes with
  `border: 0`. It is tinted with the charter blue rather than black, so it reads
  as a soft lift rather than a drop.
- **Floating overlay** (`box-shadow: 0 .5rem 1rem rgba(0, 0, 0, .15)`): Toasts
  only, inherited from the theme. Nothing else over the page uses a shadow.

### Named Rules

**The Border-or-Shadow Rule.** Never both on the same surface. If a card needs a
shadow, its border goes; if it needs a border, it gets no shadow. The two are the
same signal, and using them together makes a surface look like two.

**The Flat-Page Rule.** The page itself is flat. No section, band or container
lifts off the background — depth is spent only on cards that behave as separate
units, and never as decoration.

## Shapes

Squares with a shaved corner. The default radius is 0.25rem on cards, buttons,
inputs, badges and dropdowns — enough to read as soft, not enough to read as a
shape. Smaller controls step down to 0.2rem (`.btn-sm`, agenda chips) and larger
containers step up to 0.5rem (the wizard's branch blocks), so radius tracks the
size of the thing rather than a fixed scale.

Almost every line is 1px, at three values: `#ced4da` for input borders, 12.5%
black for card and dropdown outlines, `#dee2e6` for structural borders and the
agenda grid. A thicker rule is reserved for stating *which* thing you are
looking at, and there are exactly three in the codebase: the first-run wizard
marks a step's summary and a structure block's nesting with 3px `border-left`
accents (`--bs-primary`, `--bs-border-color`), and the branch rail heads each
segment with a 4px rule in that branch's own charter colour. All three are
state, not decoration, and none is a pattern to extend to a card that has no
state to state.

The rail's 4px rule is where the desk's colour scale starts: 4px at full
strength saying which branch, the column behind it at 15% filling the room the
branch occupies, the year chip ringed at full over a 32% fill once it is chosen,
and the answer band's ground at full. One colour, five strengths, and the
strength tracks how close the visitor is to it.

Circular forms appear exactly once, in the wizard's progress markers, where the
shape is doing semantic work (done / current / pending) rather than decoration.

The one ornamental geometry in the system is the **topping**: the federation's
flag silhouette, repeated as a background image at 10% opacity behind a coloured
band (`.bg-topping-federation` with `.bg-topping-opacity-10`). It is a watermark,
not a texture — it never carries meaning, never appears at full strength, and
never appears on a white surface.

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
- **The teal exception:** `.btn-info` — charter teal with *black* text — is used
  for the signed-in user's chip in the navbar and should stay there. It is the
  only saturated fill in the system that takes dark text.
- **Hover / Focus:** Hover darkens the fill (primary → #093863) or floods an
  outline button with its own colour and flips the text to white. Focus is
  Bootstrap's ring, tinted with the charter blue — `0 0 0 .25rem rgba(10, 66, 117, .25)`.

### Banner

The signature component, and the only page chrome this project owns. Every
members page opens with it: a charter sky band carrying the federation flag at
10% opacity, holding the page's `h1` and a one-line lede.

- **Markup:** `bg-ls-bleu-clair bg-topping-federation topping-white bg-topping-opacity-10`,
  with the title and lede supplied through the `hat_title` and `hat_text` blocks.
- **Type:** White display type on the band, the `h1` first and the lede directly
  under it, indented one column from the left on `md` and up.
- **Behaviour:** It is the page's *identifier*, not its content. It always says
  what page you are on, it is the same on every page, and it never carries
  actions — the buttons live in the content below it.
- **The homepage is the exception:** its band is a photo rather than a flat band,
  and it stays an ordinary block in the flow (not absolutely positioned), because
  the homepage editor drops content directly beneath it. It is also the one band
  a troop writes itself: the unit's own name and description seed it, its text
  and contents are editable in the editor, and its background image is a
  property set there rather than a rule in a stylesheet nobody can reach. The
  editor holds it in place as the anchor it repairs the rest of the canvas
  around, so it may not be dragged, removed or copied — only edited into.
- **The band is the federation's green, over the troop's own photograph.**
  `--home-green` is charter-green-deep taken down until it can hold white type
  over any picture, laid over the troop's own image at 62–74%. It is the page's
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
- **Painted as a pseudo-element and never as a background layer**, because a
  troop's own picture arrives as an inline `background-image` and an inline style
  beats anything a stylesheet says about it. `backdrop-filter` and not `filter`,
  which is the load-bearing choice: a `filter` would dim the band and every word
  in it, while a backdrop filter acts on what is *behind* the layer and leaves
  the type sharp.
- **The band's words are one centred column of left-aligned type.** A unit's
  description runs to whatever length its troop wrote; past two lines a centred
  block stops being read as one statement and starts being read as a shape. The
  column is centred so the band stays symmetrical under the bar — the words
  inside it are not.
- **The editor's canvas drops only the last of it.** The canvas has the same
  photograph and the same green, so the words read there exactly as they do on
  the site; what it does not have is the hard edge into the desk, so its band
  ends on the page colour the blocks are dropped onto.

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

- **A slim rule down the sheet's left edge, in the branch's colour**, and **a
  square in the corner carrying the federation's mark for that branch** at the
  10% a watermark is allowed. The rule is 3px and inset from the corners: a frame
  as thick as the branch's colour deserves reads as a plate the sheet is mounted
  in rather than as the sheet's own edge, and the branch is already stated by the
  name in the sentence and by the chip the visitor chose.
- **The mark is a square, not a run of pattern.** The theme draws a topping as an
  absolutely positioned pseudo-element that fills whatever it is put on; across a
  whole sheet a pattern stops being a mark and becomes wallpaper.
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
what the answer sheet does.

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

- **It is a full-bleed band, in the page's warm step.** The ground changes edge
  to edge between the desk and the footer, so the eye is told a section ended; a
  band that changed colour and stopped at the container's edge would read as a
  box rather than as a section.
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

### Cards / Containers
- **Corner Style:** 0.25rem, outlined in 12.5% black, no shadow.
- **Background:** White, or `bg-white` on a header that would otherwise inherit
  the theme's 3% black tint.
- **Shadow Strategy:** See Elevation — a functional card trades its border for
  the charter-blue shadow.
- **Internal Padding:** 1rem (`card-body`), 1.5rem where a card is a page of its
  own (the wizard's `p-4`).
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
- **Do** open every members page with the banner (`hat_title` + `hat_text`).
- **Do** ship a plain `href` or `action` alongside every HTMX attribute, so the
  page still works when the swap does not.
- **Do** set the navbar's 110px height in px and keep `--site-navbar-height` in
  px to match; the navbar does not scale with the root font size.

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
- **Don't** style the site header with a bare `header` selector. The homepage
  editor exports content that can carry its own `<header>`, and a bare selector
  reaches into authored content.
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
