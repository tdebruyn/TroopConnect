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

The unit's real name and federation, the federation's four branches with their
ages, and the registration state — all already held by the instance in
`TroopSettings` and `Branch`. No prices, no testimonials, no invented dates.

## Open decision

The desk needs real branch ages, so it cannot be authored content in the
GrapesJS canvas, which is what the public page was previously decided to be.
Proposed resolution, not yet confirmed: the desk becomes a fixed data-driven
band at the top of `/` for anonymous visitors, and everything below it stays the
editable canvas exactly as it is today.

## Direction contract

**THESIS.** The homepage is the enrolment desk: the offer is operated, not
described. It refuses the category's photograph-of-children hero with a row of
equal branch cards beneath it.

**OWN-WORLD.** Charter blue deep on paper, one branch colour spent once as the
4px rule beside the answer. A row of year chips, the chosen one a solid charter
fill. One white result band, one primary action, nothing else coloured.

**STORY.** The visitor sees that this is the unit's enrolment, and believes it is
for their child because the page names their child's branch — then registers.

**FIRST VIEWPORT.** The 110px navbar, then the question "En quelle année votre
enfant est-il né ?" at 48px over two lines, a chip row with one chip filled, and
a white band carrying the named branch with "Inscrire mon enfant" at its right.

**FORM.** Position 3 of 7 grounded structures; the dealt lead.
seed:68206952be1717e3

**FINISH.** unreviewed and undocumented is unfinished; this build ends with the
finish review, the verdict, DESIGN.md, and every shipping raster carrying its
provenance.
