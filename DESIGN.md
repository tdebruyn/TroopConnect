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
  white: "#ffffff"
  border: "#dee2e6"
  border-input: "#ced4da"
  muted: "#6c757d"
  muted-on-paper: "#5d666e"
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
in flat charter colour, in bold Muli, and in one ornamental gesture — the flag
silhouette repeated behind a banner — and nowhere else. There is no troop-level
colour, no theme picker, no second accent: the palette is the federation's, and
the unit's identity is carried by its name and the logo it uploads.

**Key Characteristics:**
- Bootstrap's own primitives, used as intended, restyled only where a task needs it
- One typeface (Muli) and one flat charter palette, both inherited, neither configurable
- A sky-blue banner with the federation flag behind it as the recurring page opener
- Thin 1px lines and soft 0.25rem corners; depth by border, not by shadow
- Paper-filled fields on a paper-coloured page, separated by a border and a blue focus halo
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

## Typography

**Display Font:** Muli (with `sans-serif`)
**Body Font:** Muli (with `sans-serif`)
**Available but unused:** Housepaint, CaveatBrush, Mali-Bold, Roboto Mono

**Character:** One geometric humanist sans in nine weights, set entirely without
decoration. The theme ships the real Muli files — ExtraLight through Black, both
upright and oblique — so weight is a free and precise tool, and the design uses
it plainly: 700 for anything that names something, 400 for everything else.

Hierarchy inside a page is carried by size and weight, not by colour or by
shifting typefaces, because every heading shares the body's ink.

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

**The One Voice Rule.** The application sets Muli and only Muli. The theme's
Housepaint (a hand-painted face), CaveatBrush, Mali-Bold and Roboto Mono are
available in the stylesheet and appear nowhere in the product; reaching for one
is a departure from the incumbent system, not a flourish within it.

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
`.container` holding the page. The navbar's height and its background both live
in inline style, and the background reads
`var(--bs-navbar-toggler-border-color)` — a Bootstrap variable for a *toggle
button* used as the navbar's own fill. It resolves today, but it is the kind of
reference a theme upgrade can drop without any local file changing; treat the
navbar's chrome as pinned by markup rather than by CSS. Content is laid out at `col-md-12` by default and
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
accents (`--bs-primary`, `--bs-border-color`), and the enrolment desk marks the
branch its answer is about with a 4px rule in that branch's charter colour. All
three are state, not decoration, and none of them is a pattern to extend to a
card that has no state to state.

Circular forms appear exactly once, in the wizard's progress markers, where the
shape is doing semantic work (done / current / pending) rather than decoration.

The one ornamental geometry in the system is the **topping**: the federation's
flag silhouette, repeated as a background image at 10% opacity behind a coloured
band (`.bg-topping-federation` with `.bg-topping-opacity-10`). It is a watermark,
not a texture — it never carries meaning, never appears at full strength, and
never appears on a white surface.

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
- **The homepage is the exception:** its hero is a photo rather than a flat band,
  and it stays an ordinary block in the flow (not absolutely positioned), because
  the homepage editor drops content directly beneath it.

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
