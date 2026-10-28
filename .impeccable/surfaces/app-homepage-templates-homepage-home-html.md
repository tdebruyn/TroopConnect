---
version: 1
slug: "app-homepage-templates-homepage-home-html"
primary_target: "app/homepage/templates/homepage/home.html"
related_targets: []
---

# Surface: the troop's public homepage (`/`, anonymous)

**Mode:** Persuade.

## Audience and job

A parent in the commune who has never heard of this troop. They arrive from a
search or from a neighbour, on a phone as often as a desktop, and they carry one
question under every other one: is this for my child, and can I sign them up
before I lose the thread.

## Action

Register a child, and it must be *operable* in the first viewport rather than
described. The parent answers one question about their child's age, which names
the branch, and is handed the registration.

## Content and proof

The unit's real name, the federation's four branches with their ages, and the
registration state — all already held by the instance in `TroopSettings` and
`Branch`. The year-line's dates are activities a superuser enters in the
admin (a start date, an optional end date for a multi-day activity); the site
draws the current school year's rows against the band's axis. No prices, no
testimonials, no invented dates.

The desk opens on its question and nothing else. A line naming the scout year
and the federation sat under the heading and was **removed on the user's
instruction**: the question and the years say what the page is for, and the
sentence restated the navbar. The branch legend below the answer stays.

**The registration window is part of the offer.** The troop sets the day and
month registrations open for the next school year — 1 April by default — and
the cutoff repeats each scout year. While it is closed the desk still answers
for the running year, keeps the register button visible but disabled, and
states the opening date between the branch strip and the answer sheet, as a
large statement with the section's rule down its left; once it is open the
rail's years and the answer's sentence move to the intake's school year, the
button is live, and a quiet line in the same place states which year is being
taken. The date is generated from the cutoff (and takes the French `1er`), not
written copy; an optional troop note sits under the date.

**The page is composed from blocks, not authored in a canvas.** The GrapesJS
editor and the CMS tables are gone. A superadmin chooses on `/users/settings`
→ Public page which blocks the visitor sees — introduction (name, description
and the year-line's dates), enrolment desk, where to find us, About and FAQ —
and edits the words and the place's address and map inside the same card. The
two content blocks are plain text and are left out when empty. The desk and the
band remain fixed, data-driven blocks: the desk reads the branches' own ages,
which no canvas could do.

## Open decision

Resolved: the desk is a fixed data-driven band at the top of `/` for anonymous
visitors, and the page around it is composed from switched blocks rather than
from editable canvas content.

## Direction contract

**THESIS.** The homepage is the enrolment desk: the offer is operated, not
described. It refuses the category's photograph-of-children hero with a row of
equal branch cards beneath it.

**OWN-WORLD.** Charter blue deep on paper, one branch colour spent once as the
4px rule beside the answer. A row of year chips, the chosen one a solid charter
fill. One white result band, one primary action, nothing else coloured — and,
while the window is closed, a large serif opening-date statement between the
branch strip and the result band, marked by the section's green rule.

**STORY.** The visitor sees that this is the unit's enrolment, believes it is
for their child because the page names their child's branch, learns when it can
be acted on — then registers.

**FIRST VIEWPORT.** The 84px navbar, then the unit's own photo band with its
description card and its year-line — the troop introducing itself comes first —
then the question "En quelle année votre enfant est-il né ?" at 48px over two
lines, a chip row
with one chip filled, and a white band carrying the named branch with "Inscrire
mon enfant" at its right. While the window is closed, the opening date stands
between the branch strip and the answer band at display size, and the button is
the same pill disabled. (Corrected
by the user after the first build: the desk had been placed above the band.)

**FORM.** Position 3 of 7 grounded structures; the dealt lead.
seed:68206952be1717e3

**FINISH.** unreviewed and undocumented is unfinished; this build ends with the
finish review, the verdict, DESIGN.md, and every shipping raster carrying its
provenance.
