---
version: 1
slug: "app-homepage-templates-homepage-member-html"
primary_target: "app/homepage/templates/homepage/member.html"
related_targets: []
---

# Surface: the member homepage (`/`, signed in)

**Mode:** Operate.

## Audience and job

Someone who already belongs: a parent first, then a section leader, then unit
staff. They open the site to check something about their own people and to act
on it — confirm an absence, read a section message, settle what the household
owes. They are not reading; they are doing.

## Task

See the state of the people this reader is responsible for, and act on each one
without leaving the page. The page reorders per role: a parent's children, a
leader's section members, the unit's members for staff.

## Content and proof

Next activity per section, absence state, the household's balance and its
billing rule, the member's file state. All already held by the instance:
`Enrollment`, `SectionEvent`, `Absence`, the finance models, `TroopSettings`.

## The page is the menu

Decided by the user after the first build. The reader's tools live on this page,
grouped by what they answer for, and the header carries **no menu** for anyone
signed in — the brand (which returns here), the account and the language are all
that remain. A link kept in both places is two things to keep honest, and two of
this session's dead links were exactly that: a destination whose gate had moved.

Two rules follow, and they are the reason the code looks the way it does:

- **A link appears only where its view would answer.** `_member_tools` gates
  every entry on the same predicate its view enforces, and a test fetches each
  one for each role rather than trusting the list.
- **A panel is a thing the reader answers for, not a thing they may read.** The
  unit's staff can read every agenda and lead none, so they get no section
  panels at all — their page is their tools. Whether the header carries the
  menu is not a matter of taste: it is the same rule applied to the header.

## Constraints

Fees are billed per **household**, not per child — the eldest pays full and
siblings are discounted — so a per-child balance would be a lie and the balance
is stated once, above the panels. A troop can switch the fees module off, so the
balance band is absent when it is.

## Direction contract

**THESIS.** The page is a board of the reader's year, not a form report: one
tile per person and one per action, sized by what the reader actually answers
for. It refuses the equal-width card grid — no two tiles carry the same weight,
and the first row is deliberately 7/5 rather than 6/6.

**OWN-WORLD.** A full-bleed gradient in the two branch colours this unit's
homepage already speaks — Baladins blue (#00a0de) into Louveteaux green
(#296f52) over paper. White tiles with 1.25rem corners and a soft charter-blue
shadow; tinted tiles at 6–8% of one branch colour; one dark tile per page
(green→deep-blue) carrying either the household balance or, when there is no
money, the reader's lead action. Activity types keep the charter's three
colours; crimson appears only where money or an absence is overdue.

**STORY.** The reader sees each person's next commitment at a glance, settles
the household's one balance, and reaches every tool they answer for from a tile
rather than a menu. Nothing needs hover to be understood.

**FIRST VIEWPORT.** The 84px bar, then "Vos enfants" / "Votre unité" in the
display serif at 44px over a greeting and household line. Immediately below, the
dark balance tile (4-5 columns) beside the first child's tile; the next child
wraps at 5 columns and the third at 7, so the board runs asymmetrically. Each
person tile carries a date leaf, the activity title, its type chip and absence
state, then its actions.

**FORM.** Position 3 of 7 grounded structures; the tile board is the brief's own
world. seed:5ce6a7fc8487a175

**FINISH.** unreviewed and undocumented is unfinished; this build ends with the
finish review, the verdict, DESIGN.md, and every shipping raster carrying its
provenance.

## Finished build

Recorded from the shipped source after the finish review. The contract above
remains the brief; these are the values and behaviours the build settled on.

- **Board.** `.member-board` is a flex row at a 26rem basis with a 1rem gap,
  not a Bootstrap column grid. Grow weights: household balance `1.75`, first
  person tile `1.25`, second `0.9`. Two tiles read about 7/5; three read about
  45/32/23. Below `md` every tile takes its own row and the weights are dropped.
  The brief's column language ("4–5 columns", "third at 7") is shorthand for
  these weights, not for `col-*` classes.
- **Ground.** `paper` plus two radial blooms mixed with `transparent` — Baladins
  blue at 22% upper right, Louveteaux green at 20% lower left — over a 168°
  wash (#e3eff8 → #f0f6f2 → #e3efe7). Tiles carry a 1.25rem radius and one
  `0 0.5rem 1.5rem rgba(10, 66, 117, .07)` shadow, never a border.
- **One dark tile.** The household balance uses a 145° gradient from Louveteaux
  green (82% with #0b1a12) to charter blue (76% with #0b1a12) with one 32%
  charter-sky bloom. When `_household_dues` returns no amount — settled, or fees
  off — the balance tile is absent and the featured tool group's first tile
  takes the same dark gradient. Staff and leaders with no balance get the dark
  note in the tools.
- **Tools.** Groups are a flex row at a 17rem basis; the most-populated group
  takes `1.5` grow and a 24rem basis, its list is two columns, and its first
  tile spans both. Other lists are `auto-fill` at a 9rem minimum. Children tiles
  are tinted 7% Baladins blue, sections and unit 6% Louveteaux green, account
  and site white.
- **Section tile.** At `lg` (992px) and up it becomes a three-area grid:
  identity and attendance in the left column, the next event in the right behind
  a 1px divider, the actions across both feet. Below `lg` it is the stacked
  person tile.
- **One section.** An animateur leads exactly one section, so `_member_context`
  takes the first section the reader can edit and the page renders one section
  panel; the tools group is titled "Your section" in the singular, and the
  head's summary line carries no section count — the tile below already says
  which. The child count stays, because a family's number is not obvious from
  the board. A second enrolment is data a real troop cannot have and must not
  grow a second panel. The agenda tools still reach every section the reader may
  read.
- **Bar and account chip.** `.page-member` restates the navbar's two variables:
  a 110° fill from Louveteaux green through a slate midpoint to charter blue
  (all stops at 94%), dimmed at `brightness(0.82)`, so the bar reads as the
  board's own glass. The account chip drops the theme's teal for a pale
  green-to-blue paper (`#e9f4ee` → `#e7f0f8`, hover `#dceee4` → `#dae9f5`) with
  charter ink at 700; its dropdown is white with ink items, and the collapsed
  menu keeps the bar's gradient. The public page's `.page-home` bar is
  untouched.
- **Type.** The surface title uses `clamp(2rem, 3.4vw, 2.75rem)` in Source Serif
  4; panel names 1.75rem; the balance `clamp(2.5rem, 4.6vw, 3.25rem)`; a
  section's member count 2rem; a date leaf's day 1.875rem. Board numerals use
  tabular figures. Labels, meta, absence lines and notes stay Muli.
- **Absence and lateness.** A reported absence uses #b30d31 ink with a
  charter-crimson dot; the overdue note on the dark tile uses #ffd1db. No other
  state spends crimson.
- **No hover dependency.** The whole tool tile is the link; its label, icon and
  corner arrow are visible at rest. Hover lifts 2px and removes the arrow's 40%
  opacity. Focus is a 2px solid ink outline offset 2 (white on the dark tile).
