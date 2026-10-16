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

**THESIS.** The page is the children themselves: a panel each, under the
household's single balance. It refuses the row of equal metric cards that every
app dashboard opens with.

**OWN-WORLD.** Paper ground, white 1px-bordered panels, one panel per person.
The activity type in the charter's three colours and nothing else coloured,
except one crimson line where money is overdue.

**STORY.** The reader sees each person's next commitment and what is outstanding,
and acts on a row of that panel without leaving the page.

**FIRST VIEWPORT.** The 110px navbar, "Vos enfants" at 34px over a one-line
household summary, a bordered band stating the 45,00 € balance with its Payer
action, then two panels of labelled fact rows each ending in its own actions.

**FORM.** Position 6 of 7 grounded structures, second hand; the re-roll carried
the steer that money stays visible. seed:5ce6a7fc8487a175

**FINISH.** unreviewed and undocumented is unfinished; this build ends with the
finish review, the verdict, DESIGN.md, and every shipping raster carrying its
provenance.
