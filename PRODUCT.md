# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

**Parents are the primary audience.** They register a child once a year and then
touch the site a handful of times: correcting details, reporting an absence,
reading a section message, paying a fee. They are numerous, uninvested, and
arrive mid-task — often on a phone, often unsure whether the registration went
through. A screen that fails here costs the troop a registration.

**Section leaders (animators)** are the second audience and the most frequent
users: they write agenda entries, send messages to their section, and track who
is coming. The same few people, week after week, on desktop and phone.

**Unit staff** — trésorier, responsable inscriptions, admin — are the third.
They work in bursts at enrollment and billing: fee rules, payments, reminders,
imports, documents, unit settings. They tolerate density; they are the audience
that can absorb a dense table.

## Product Purpose

TroopConnect runs a scout unit's year: member registration (children, parents,
animators), enrollment per section and school year, email communication, a
section agenda, household fee billing, attestations, and the administration that
holds it together.

Success means a troop runs its year without a developer and without a
spreadsheet — parents register their child online and reliably hear from the
unit, and the volunteers running it are not doing data entry to keep the system
true.

## Positioning

**Self-hosted, no-code, one instance per troop.** A troop deploys the published
images with a filled-in `.env` and changes no code. It gets its own domain, its
own database, and its own release cadence. There is no SaaS account, no shared
tenancy, and no vendor holding the children's data — a claim a hosted
competitor cannot make without abandoning its own architecture.

## Operating Context

- **The unit is run by volunteers, and so is the deployment.** The person who
  installs it is usually not an IT professional; the README asks that they be
  able to read a container log, run `docker compose` commands, and get a shell
  into the web container. Every operational ceremony is a place a unit can get
  stuck.
- **Setup is a first-run wizard.** An instance with no administrator serves
  `/setup` and nothing else, gated by a one-time code printed in the web
  container's log. Same functions as `manage.py setup` at a shell.
- **The year is a scout year, not a calendar year.** It runs from a configurable
  start (default 1 August) to the next one, ages are taken on a configurable
  reference day (default 31 December), and members change sections on a
  configurable passage date (default 1 May).
- **Three usage rhythms, not one.** Parents a few times a year, leaders weekly,
  staff in intense bursts. A design that serves one rhythm well can starve the
  others.
- **Three languages on one instance**, French by default; a troop enables any
  subset, and a single enabled language locks the site to it.
- **Belgian scouting by default**, federation-neutral by construction: phone
  region `BE`, currency `EUR`, and Les Scouts' four branches shipped as an
  editable starting preset.

## Capabilities and Constraints

- **Membership.** Person (the real-world entity) is separate from Account (the
  login). Primary roles: Nouveau, Animateur, Parent, Animé. Secondary roles
  include Admin, Trésorier, Responsable inscriptions, Parent actif, Animateur
  responsable.
- **Parent–child linking** happens through a 6-character secret key a child's
  profile generates; several parents may link to the same child. Children aged
  12+ can sign in themselves but cannot change their address, which belongs to
  the household.
- **Messaging.** Rich-text messages targeted at a section or a role, with a
  recipient preview before sending and per-person exclusion. Attachments are
  sent as unique UUID links rather than as files. Delivery is queued, not
  synchronous, and logged.
- **Agenda.** Per section, with absence reports from families. Events older than
  30 days are purged automatically; recent past events are shown muted.
- **Public year-line.** The homepage's timeline is configured by a superuser as
  named activities with a start date and an optional end date. The current
  school year's activities are drawn against a September–July axis: a dot for a
  one-day activity, a short thicker bar for a multi-day one.
- **Fees.** The household is the child's address. The eldest child pays in full,
  siblings get a discount, leaders pay a flat rate and are outside the sibling
  rule. An optional late penalty applies after a deadline. The trésorier
  records payments by hand.
- **Attestations** (the `signing` module) produce the unit's documents for a
  signing campaign.
- **Module switches.** Fees, signing and agenda can each be turned off; off
  means the module's URLs 404 and its UI disappears, while its stored data is
  left alone so switching it back on restores it.
- **Email** goes through a queue (`django-post_office`) flushed by Celery, over
  SMTP or the MailerSend API. Failed sends surface as a staff banner linking to
  the queue, where they can be requeued or purged.
- **Stack.** Django 6.0, PostgreSQL only, Redis for cache and broker, Celery for
  background work, Caddy for TLS, `docker compose` for the whole installation.
  Interface languages: French, Dutch, English — English is the source language
  for strings.
- **Pre-1.0.** Versions are `0.Y.Z`, and until 1.0 a *minor* bump signals a
  breaking change: an upgrade may rewrite the schema, change a configuration
  variable, or alter what a screen does. Troops are told to pin `TC_VERSION` and
  back up before upgrading.
- **Licence.** AGPL-3.0.

## Brand Commitments

- **The design is Les Scouts'; the identity is the troop's.** This is the line
  the project draws everywhere, and it is structural rather than aspirational:
  the federation's theme is vendored, unmodified, and every deviation lives in a
  file loaded after it.
- **`app/static/vendor/template-unite/` is never edited.** It is byte-identical
  to the upstream commit recorded in its own `README.md`, upstream is MIT © 2022
  Les Scouts asbl, and a theme upgrade is a byte-for-byte replacement followed
  by a check that the overriding stylesheet still targets what it means to.
- **No Les Scouts endorsement is implied anywhere.** The project is run by its
  authors, not by the federation. That most units are Les Scouts members and
  that the shipped design is the federation's are facts; an official
  relationship is not.
- **Federation-neutral by design.** Nothing may hard-depend on Les Scouts. The
  branches and sections it ships are a preset the unit renames, edits and
  extends; the project cannot enumerate the federations its users belong to.
- **The troop's identity always beats the federation's.** Unit name, short name,
  logo, favicon, branches, sections, languages, contact details and privacy
  policy come from the troop's own settings in the database — never from the
  environment and never from the shipped design. An instance that configures
  nothing still has the default Les Scouts mark, by design.

## Evidence on Hand

- `GETTING-STARTED.md` — the full install walkthrough, with a screenshot of
  every screen of the setup wizard under `docs/images/getting-started/`. These
  are real captures of the running application and are the honest source for how
  its screens actually look.
- `README.md` — the project's own voice: candid about being early-stage,
  explicit about what a volunteer is taking on, and directed at a troop that can
  look after itself.
- `UserFlows.md` — the intended flows for authentication, roles, messaging,
  the agenda, and billing.
- `docs/dev/CONTRACT.md` — the configuration contract and the file-by-file
  branding split.
- Real demo content exists in the repository (a unit mark under
  `app/static/images/troop/`, uploaded logos under `app/media/homepage_images/`),
  but it belongs to a specific unit and is not product content.

**Absences that later work must not paper over.** The default landing-page and
FAQ copy shipped in the repository is placeholder text, not real copy. There are
no testimonials, no case studies, no customer list, no benchmarks and no
pricing. None of these exist and none may be invented.

## Product Principles

1. **The troop owns the instance and the data.** Nothing routes member data
   through a service the troop does not run.
2. **Never bake a specific troop — or a specific federation — into the
   product.** What ships is a preset; what the unit sets wins.
3. **Model the unit's real year, not generic membership CRUD.** Passage, school
   years, households and sections are the domain, and the software should think
   in them.
4. **Assume the operator is a volunteer, not an IT department.** Reduce
   ceremony, and say plainly what went wrong when something does.
5. **A parent's screen has to work the first time**, on a phone, for someone
   who is unsure and in a hurry.

## Accessibility & Inclusion

**WCAG 2.1 AA is the target** for member- and parent-facing screens: contrast,
focus order and visibility, full keyboard operation, labelled form controls, and
errors that identify themselves. This was confirmed as binding, not aspirational.

The interface is genuinely multilingual — French, Dutch and English share one
instance, so no layout may assume a language's string lengths, and no user-facing
text ships unextracted.
