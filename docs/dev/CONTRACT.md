# TroopConnect configuration contract

Two kinds of configuration, deliberately kept apart:

| Kind | Lives in | Changed by | Examples |
| --- | --- | --- | --- |
| Infrastructure | environment variables (`.env`) | whoever runs the server | domain, mail server, database password |
| Troop content | the database (`TroopSettings`) | the troop's staff, in the web UI | unit name, languages offered, scout-year dates |

Neither requires editing a file shipped in this repository. A troop never
edits files; a hoster never edits the database by hand.

This document is the reference for both. **Update it whenever you add or
change an environment variable, a management command, a service or a
`TroopSettings` field.**

---

## 1. Environment variables

Read by a single settings module (`app/troopconnect/settings.py`) through the
helpers in `app/troopconnect/env.py`. Parsing happens in settings; validation
happens in `app/troopconnect/checks.py`, so `python manage.py check` is the one
place an operator sees what is wrong.

### Required

Missing or malformed values are reported as **errors** and stop the process.
With `DJANGO_DEBUG=1` they are reported as warnings instead, so a developer can
run the app before wiring up mail.

| Variable | Example | Notes |
| --- | --- | --- |
| `SITE_DOMAIN` | `troop.example.org` | Bare hostname. Drives `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, the `django.contrib.sites` row and Caddy's TLS certificate. No scheme, no path, no port. |
| `EMAIL_URL` | `smtp+tls://user:pass@mail.example.org:587` | Schemes: `smtp://`, `smtp+tls://`, `smtp+ssl://`, `console://`. Percent-encode `@`, `:` and `/` in credentials. Optional `?timeout=10`. |
| `DEFAULT_FROM_EMAIL` | `inscriptions@example.org` | Sender on every message the app sends. Must be an address the mail provider permits. |
| `ACME_EMAIL` | `admin@example.org` | Let's Encrypt contact address. Used by the Caddy container; Django reads it only to insist it is set. |

### Optional

| Variable | Default | Notes |
| --- | --- | --- |
| `SECRET_KEY` | generated | An explicit value wins. |
| `SECRET_KEY_FILE` | `/data/secrets/secret_key` | Where the key is read from, and generated into, when `SECRET_KEY` is unset. |
| `DJANGO_DEBUG` | off | `1`/`true`/`yes`/`on` turns debug on. Never set on a public domain; a system check warns if you do. |
| `SITE_ID` | `1` | The `django.contrib.sites` row allauth reads. Only change it for an instance migrated from the old `.settings.json`. |
| `TIME_ZONE` | `Europe/Brussels` | Used for dates and Celery schedules. |
| `POSTGRES_USER` | `troopconnect` | |
| `POSTGRES_DB` | `troopconnect` | |
| `POSTGRES_PASSWORD` | generated | Set it only to choose the password yourself, and only before the first start: the database is initialised with whatever the first run generated. |
| `POSTGRES_PASSWORD_FILE` | unset | Read when `POSTGRES_PASSWORD` is unset. The compose file points it at `/data/db-secrets/postgres_password`; the Postgres image uses the same convention. |
| `POSTGRES_HOST` | `db` | The compose service name. |
| `POSTGRES_PORT` | `5432` | |
| `POSTGRES_CONN_MAX_AGE` | `0` | Seconds to keep connections open. |
| `DATABASE_URL` | unset | `postgres://user:pass@host:5432/db`. Overrides the `POSTGRES_*` variables. |
| `REDIS_URL` | `redis://redis:6379/0` | Celery broker and Django cache. |
| `CELERY_BROKER_URL` | `REDIS_URL` | Override the broker only. |
| `CELERY_WORKER_STATE_DB` | `/tmp/celery-worker-state.db` | |
| `CACHE_URL` | `REDIS_URL` | |
| `SERVE_MEDIA_LOCALLY` | on in debug, off otherwise | `1` makes Django serve `/media/` instead of leaving it to the reverse proxy. |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | unset | Both required. Without them the Google provider is not registered and no Google button appears. |
| `FACEBOOK_APP_ID` / `FACEBOOK_SECRET` | unset | As above, for Facebook. |
| `SENTRY_DSN` | unset | Enables Sentry error reporting. `send_default_pii` is off. |
| `SENTRY_ENVIRONMENT` | `production` | |
| `SENTRY_RELEASE` | unset | |
| `MAILERSEND_API_KEY` | unset | Setting it switches sending to MailerSend's HTTP API and takes precedence over `EMAIL_URL`. |
| `MAIL_SEND_MODE` | `mailersend` if an API key is set, else `EMAIL_URL` | `mailersend` (legacy alias `real`), `dummy`, or anything else to follow `EMAIL_URL`. |
| `UPDATE_CHECK` | off | Reserved. No outbound update check is implemented yet. |
| `UPDATE_CHECK_URL` | GitHub releases API | Reserved, as above. |

### Read by the images, not by Django

| Variable | Default | Read by |
| --- | --- | --- |
| `TC_VERSION` | `0` | `compose.yml`, to choose the image tag: `ghcr.io/tdebruyn/troopconnect:$TC_VERSION`. Versions are `0.Y.Z` until 1.0, so `0` tracks the 0.x line; **this default becomes `1` at the 1.0 release**. See `RELEASING.md`. |
| `TC_APP_VERSION` | `dev` | Baked into the image by the release workflow, so a running container can be asked which build it is. Readable as the `TC_APP_VERSION` Django setting. |
| `SECRET_KEY_FILE` | `/data/secrets/secret_key` | `app/entrypoint.sh`, which generates it when absent, and `troopconnect.env`. |
| `POSTGRES_PASSWORD_FILE` | `/data/db-secrets/postgres_password` | The same, for the database password, plus the Postgres image itself. |
| `RUN_MIGRATIONS` | unset | `app/entrypoint.sh`. Set on the web service only: it makes the entrypoint migrate and collect static files. |
| `SITE_DOMAIN`, `ACME_EMAIL` | required | Also read by Caddy, which substitutes `{$SITE_DOMAIN}` and `{$ACME_EMAIL}` into `caddy/Caddyfile` and refuses to serve an empty site address. |

---

## 2. Troop-editable settings (`TroopSettings`)

A singleton row edited by staff at **`/users/settings`** (and, field by field,
in the Django admin). Defaults are generic, not troop-specific, and migration
`members/0025` creates the row, so a freshly migrated instance has a settings
page to open before anyone has saved anything. Read it through
`TroopSettings.get_settings()`, which serves a cached copy and is invalidated
whenever the row is saved. Save it with `save()`/`delete()` rather than
`queryset.update()`, which the invalidation does not see.

The page shows the four groups below, in this order. Every field is optional to
set: the defaults are what a troop that has configured nothing gets.

### Organisation

| Field | Purpose |
| --- | --- |
| `name` | The unit's name. Shown in the header, and the name outgoing mail speaks for — resolved in the *recipient's* language, not the sender's. |
| `short_name` | Short form for places the full name does not fit. Empty falls back to `name` (`display_short_name()`). |
| `federation` | Free text — the federation this unit belongs to is not something this project can enumerate. |
| `contact_email` | Public contact address, exposed to every template as `contact_email` via `members.context_processors.contact_info`. Empty by default: a placeholder that looks like a real address would have a troop publishing somebody else's. |
| `contact_phone` | Public phone number. |
| `reply_to_email` | Where answers to automated mail should go. Empty means "reply to the sender" (`DEFAULT_FROM_EMAIL`). |
| `footer_address` | Postal address shown in the footer. Formerly `contact_address`. |
| `privacy_policy` | A URL or a block of text, whichever the troop has. `privacy_policy_url()` returns the value when it is a link and `""` otherwise, so a template can test before rendering an `<a href>`. |
| `logo` | The unit's own mark, an upload in the media storage. Shown in the site header and at the top of every HTML email. Read it through `logo_url()`, never `.logo.url`: empty falls back to the mark shipped with the application (`members.constants.DEFAULT_LOGO`, `static/images/troop/mini-logo-moutons.png`), so the header always has something to show. |
| `favicon` | The icon browsers show for the site, also an upload. `favicon_url()` returns `""` when there is none, and the template then renders no `<link rel="icon">` at all — a browser's own behaviour is the honest default for an icon nobody chose. |

### Locale

| Field | Purpose |
| --- | --- |
| `enabled_languages` | A subset of the shipped `LANGUAGES` (`fr`, `nl`, `en`). Drives the language switcher and `AvailableLanguagesMiddleware`. With exactly one entry the site is locked to it and the selector is hidden. Default `["fr"]`. |
| `default_language` | Used when the visitor's language is not enabled. Must be one of `enabled_languages`; enforced in `clean()` and by the settings form. |
| `phone_region` | ISO 3166-1 alpha-2. Decides how a locally-written number ("0475 12 34 56") is read and how it is displayed back. Numbers are stored in E.164 either way, so changing this never rewrites the database. Validated against `phonenumbers.SUPPORTED_REGIONS`. Default `BE`. |
| `currency` | ISO 4217. Every amount in the UI goes through `members.money.format_money`, which writes the symbol for `EUR`/`USD`/`GBP` and the code itself for anything else. Default `EUR`. |

### Calendar

| Field | Purpose |
| --- | --- |
| `year_start_month`, `year_start_day` | First day of the scout year (default 1 August). Used when a `SchoolYear` row is created and when `create_year_task` decides which year "today" belongs to. |
| `age_reference_month`, `age_reference_day` | The day a member's age is measured on (default 31 December). Read through `TroopSettings.age_at_reference`, which the passage task, the member list's branch check and `Person.age_on_dec_31` all share. The `Branch.min_age_dec_31`/`max_age_dec_31` columns keep names that predate this setting; they mean "age at the reference day". |
| `passage_month`, `passage_day` | The day the section passage falls due (default 1 May), i.e. in the *start* calendar year of the school year it prepares. |
| `passage_mode` | `auto` (default) runs `run_passage` on that day; `manual` switches the automatic run off and leaves it to the staff button on `/users/passage`. Either way the button runs the same code, with the guards skipped. |
| `top_branch_graduates_become_leaders` | `true` (default): members who leave the last branch become animators. `false`: they are flagged for review instead, and nothing about them is changed until staff decide. |
| `archive_retention_years` | How long an archived member is kept before `delete_archived_users` may discard them (default 5). `notify_upcoming_deletion` warns a month before. The unit is 365-day years, not calendar years. |

These six fields are read only through the `TroopSettings` calendar helpers —
`school_year_for`, `school_year_bounds`, `age_reference_date`,
`age_at_reference`, `passage_datetime`, `next_passage_datetime` and the
`archive_*` retention trio. Views, tasks and templates must call those rather
than re-deriving a date from the month/day pair, so that changing a calendar
setting moves every calculation with it. The age reference day is pinned to
whichever calendar year places it *inside* the school year, so 31 December means
31 December of a September-starting year, not of the year before it.

### The branch ladder

`Branch` carries the shape of a troop's sections, and the passage follows it
instead of inferring anything from names or ages:

| Field | Purpose |
| --- | --- |
| `promotes_to` | The branch a member moves into when they outgrow this one. `null` means the passage cannot follow it. |
| `is_top` | Marks the last branch of the ladder: members who outgrow it leave it for good. |
| `min_age_dec_31` / `max_age_dec_31` | Only used to decide *when* someone has outgrown their branch. A branch with no maximum age keeps its members. |
| `key` | The branch's identifier in the preset it was created from (`louveteaux`). This is what `manage.py setup` matches on when the preset is applied a second time, so a branch a troop has renamed is recognised rather than added again. Empty on a branch no preset created. Nothing else reads it: the passage walks `promotes_to`, never this. |

A branch added after the ladder migration starts unlinked, so its members are
flagged for review rather than moved somewhere arbitrary. Both fields are
editable on the branch's admin page, which is the only place a troop has to
touch to reshape the ladder.

When the passage cannot place a member — no next branch, no section that suits
them, or the last branch with the graduation toggle off — it sets
`Person.passage_review` with the reason, leaves the member alone, and lists them
on `/users/passage`. Staff answer the question by setting the member's section
for the coming year by hand (the "Section <year>" field on the member's admin
page), which clears the flag, or by fixing the branch and running the passage
again.

### Modules

| Field | Default | Switches off |
| --- | --- | --- |
| `fees_enabled` | `true` | The membership-fees module: `/finance/`, the price grid, recording payments, payment history, reminders, the Treasurer role in the member form, and the fee count on the member purge page. |
| `signing_enabled` | `true` | The attestation (document signing) wizard, every step of it. |
| `public_agenda_enabled` | `true` | The public agenda page. |

A switch means the module is not installed as far as the troop is concerned:
its URLs answer **404**, and the UI that belongs to it disappears from the
navigation and from the member screens. What the module *stores* is never
touched — events, campaigns, payments and enrolments all stay put — so turning
a switch back on restores everything.

One implementation, in `members/modules.py`, reached three ways so a view, a
template and the navigation cannot disagree:

* `@requires_module(FEES)` on a view function (below `@login_required`, so a
  stranger is sent to the login page rather than told which modules the troop
  uses), `ModuleRequiredMixin` with `required_module` on a class-based view;
* `{% module_enabled "fees" as fees_on %}` in a template, from
  `members/templatetags/modules.py`;
* `fees_enabled` / `signing_enabled` / `public_agenda_enabled` as context
  variables, from `members.context_processors.contact_info`.

The settings page and the Django admin are deliberately **not** gated: a troop
that switches a module off has to be able to switch it back on. A role the
module hides (Treasurer) is hidden, not deleted — an existing assignment
survives an unrelated edit of that member.

### Retained site content

| Field | Purpose |
| --- | --- |
| `site_description`, `site_keywords` | Meta description and keywords. |
| `facebook_url`, `instagram_url` | Social links in the footer. |
| `email_signature` | Appended to outgoing mail. |
| `registration_open`, `registration_message` | Whether new registrations are accepted, and what to say when they are not. |
| `photo_consent_text` | Consent wording shown on the child form. |
| `address_placeholder` | Example address shown under the address field. |
| `last_passage_school_year` | Bookkeeping for the yearly section passage; do not edit by hand. |

`ImportantDocument` (title, description, url, file) is likewise admin-managed.

---

## 2b. Branding and the vendored theme

The design is Les Scouts'; the identity is the troop's. Those are kept apart
in the file layout, so that a theme upgrade is a diff against a known commit
rather than a hunt for local edits.

| Path | Whose | Rule |
| --- | --- | --- |
| `app/static/vendor/template-unite/` | Les Scouts asbl | **Never edited.** Byte-identical to the commit recorded in that directory's `README.md`. `css/` + `scss/` + `fonts/` + `images/` are upstream's, in upstream's layout, because `css/base.css` addresses its assets relatively. |
| `app/static/css/troopconnect.css` | ours | Every styling deviation from the theme. Loaded *after* the theme, so ours wins. |
| `app/static/images/troop/` | ours | The mark the header falls back to, and our own illustration. |
| `app/static/js/` | ours | Dialog, toast, homepage editor. |

`templates/base.html` loads `<link>` tags in that order — theme, then override.
Reversing them, or editing anything under `vendor/`, defeats the arrangement.

**Licence.** Upstream `template-unite` is MIT, © 2022 Les Scouts asbl (a copy
travels in `app/static/vendor/template-unite/LICENSE.md`). MIT is permissive
and compatible with this project's AGPL-3.0: the theme may be redistributed
inside an AGPL-3.0 work as long as the MIT notice goes with it, which is why
that file is vendored rather than summarised. The theme's fonts and images are
covered by the same licence. Nothing here is copyleft-incompatible, and nothing
in this project is relicensed by it.

**Updating the theme.** Pick the upstream commit, replace the vendored files
byte for byte, update the table in the vendor `README.md`, then check that
`troopconnect.css` still overrides what it means to — a theme upgrade can
rename the class an override targets. The steps are in the vendor `README.md`.

**Per-branch marks.** The theme ships a mark for each of the five branches and
a "topping" decoration family to match, keyed `f`/`federation`, `b`/`baladins`,
`l`/`louveteaux`, `e`/`eclaireurs`, `p`/`pionniers` (see `scss/_ls-variables.scss`).
They stay in the vendor directory, unrenamed, and **nothing selects them yet**:
`members.Branch` has no field naming one of these keys, and no template renders
a branch mark. Wiring that up — a `Branch` key field, and choosing between the
theme's mark and an uploaded override — is a feature to add, not a
configuration to set. `TroopSettings.logo` deliberately covers only the unit
as a whole and does not stand in for them.

---

## 2a. What a freshly migrated database contains

`migrate` against an empty database leaves the instance able to take its first
registration, with nothing seeded by hand:

| What | Created by | Kept current by |
| --- | --- | --- |
| The `django.contrib.sites` row for `SITE_ID` | Migration `members/0021` | `troopconnect/siteconfig.py`, on every `migrate`: rewrites its `domain` from `SITE_DOMAIN` |
| The email templates, in `fr`, `nl` and `en` | Migration `members/0021`, from `members/email_templates.py` | — |
| The `TroopSettings` row, with generic defaults | Migration `members/0025` | The staff settings page, `/users/settings` |
| The roles (`members/migrations/0002`), and a first pair of school years | Migrations | `manage.py setup`, and the nightly `create_year_task` |

What `migrate` does **not** leave behind is the rest of the list in §3a:
the branches, the administrator, the Celery beat schedule. Those come from
`manage.py setup`, which is what turns a migrated database into an instance a
troop can use. It is deliberately not a migration: a preset is a choice, the
first administrator's address and password cannot be, and both are things a
host may want to answer in a browser rather than at a shell.

Nothing is uploaded, so the row's `logo` and `favicon` stay empty on a fresh
install and the header falls back to the mark shipped with the application.
Migration `members/0029`, which gives an instance already in use a copy of that
mark, deliberately does nothing on a database with no members — see below.

`django.contrib.sites` ships no data of its own, so without that migration
`Site.objects.get_current()` raises `DoesNotExist` and the first registration
fails — every email that links back to the site calls it. The split is
deliberate: the migration guarantees the row exists, and the startup hook keeps
its value current, because `SITE_DOMAIN` can change long after the migration
has run.

The templates name no troop. They say `{{ troop_name }}`, which
`members.mail.send_templated` fills in from `TroopSettings.name` — read in the
language the message is being written in, not whichever one the sender has on
screen. That helper also builds absolute URLs from the Site row, sets
`Reply-To` from `reply_to_email` when the troop has one, and resolves the
language to one templates actually exist in, so a parent whose
`preferred_language` is `nl` or `en` gets an email rather than a lookup failure.

Each HTML body opens with the troop's logo. `send_templated` supplies
`logo_url` as an absolute URL built the same way as every other link, and
`members.email_templates` puts `{{ logo_url }}` at the top of the body (see
`LOGO_HTML`) rather than repeating the markup in fifteen places. An instance
that has uploaded no logo gets the shipped mark, so the tag never renders an
empty `<img>`.

Migration `members/0029` gives an instance that was *already in use* — one
holding at least one member — its own copy of the mark it was already showing,
moved out of the static files and into the media storage, so the troop owns the
file and can replace it. A database with no members is a fresh install: it is
left on the shipped fallback, which is the same image.

Changing or adding copy means editing `members/email_templates.py` and running
`makemigrations` for a new seeding migration that calls
`email_templates.seed(..., force=True)`. The `force` is needed: by default
re-seeding replaces a row only while it still holds text this project seeded
(`email_templates.LEGACY_MARKERS`), which is what protects an administrator's
own wording, but it also means the default cannot recognise copy this module
itself wrote earlier.

Two things to know about post_office here:

* A template is looked up by the exact pair `(name, language)`, with no
  fallback, which is why all three languages are seeded rather than one plus
  translations.
* Its template cache keys on `"{name}:{language}"` but its own `save()` only
  clears `"{name}"`. `troopconnect/postoffice.py` corrects that, so re-seeding
  (or an admin edit) takes effect immediately instead of after the cache entry
  expires.

**A data migration that writes a cached row has to invalidate the cache itself.**
Both of these are cache-backed, and in both cases the app's invalidation is a
`post_save` receiver on the *real* model — which a migration never sends: it
gets its models from `apps.get_model` on the historical registry, and that is a
class rebuilt from the recorded migration state, so the sender differs and the
receiver is skipped. `TroopSettings` is worse than `EmailTemplate`, because its
cache entry is written with **no expiry** into Redis, which outlives the deploy:
without an explicit `cache.delete(TROOP_SETTINGS_CACHE_KEY)` the instance goes on
serving the row it cached *before* the migration, and the change looks like it
never happened. Migrations `0028` and `0029` show both.

This is invisible to a test that calls a migration function with
`django.apps.apps`, because that registry hands back the real model and fires the
receiver the migration does not get. `tests/test_branding.py` disconnects the
receivers to put the condition back; without that a test passes whether or not
the migration invalidates anything.

---

## 3. Management commands

| Command | Notes |
| --- | --- |
| `wait_for_db` | Blocks until the database answers. Used by the entrypoint. |
| `migrate_locked` | `migrate` under a Postgres advisory lock, so only one process migrates. Used by the entrypoint. |
| `setup` | Brings an empty database to a usable state. See §3a. |
| `create_test_data` | Seeds the Playwright end-to-end users described in the README. Development only. |
| `import_legacy` | One-off import of members from the pre-TroopConnect system. |

`migrate` also rewrites the `django.contrib.sites` row's domain from
`SITE_DOMAIN` (`app/troopconnect/siteconfig.py`), so links in outgoing email
point at the right host on a fresh install.

---

## 3a. `manage.py setup`

`migrate` leaves an instance that can take a registration but is not yet a
troop. `setup` is the rest of it, in one command, and it is meant to be run
more than once:

```bash
docker compose exec web python manage.py setup --answers answers.json
```

| Step | What it does | `--no-…` |
| --- | --- | --- |
| `settings` | Fills the `TroopSettings` fields that are still at their default (§2). | — |
| `preset` | Creates the branches and sections of a preset, and links the ladder. | `--no-preset` |
| `school_years` | Creates the school year today falls in, and the next one, from the calendar helpers (§2). | `--no-school-years` |
| `email_templates` | Writes the shipped email copy in every language (§2a). | `--no-email-templates` |
| `site_pages` | Gives the homepage and the FAQ the markup the editor would seed them with, in every enabled language. | `--no-site-pages` |
| `periodic_tasks` | Writes `settings.CELERY_BEAT_SCHEDULE` into the `django_celery_beat` tables, so the schedule is there — and editable — before beat's first start. `DatabaseScheduler` installs the same mapping itself on that first run, so this only moves the work earlier; the two cannot disagree because there is one mapping. | `--no-periodic-tasks` |
| `admin` | Creates the first administrator: an `Account` on a `Person` holding the **Animateur** primary role and the **Admin** secondary one, with its `allauth` address marked verified — `ACCOUNT_EMAIL_VERIFICATION` is `mandatory`, so an unverified administrator could not log in. | `--no-admin` |

**It fills, it never overwrites.** A `TroopSettings` field counts as missing
while it holds its own default (`"Scouts"` for the name, `["fr"]` for the
languages); a branch's ages and ladder link are missing while they are empty,
and a name only where a language has none. A branch the troop has already
stocked with sections keeps them, and `is_top` is written only on a branch the
preset itself created — on an existing one, `False` is what the column holds
and cannot be told apart from a decision. Running `setup` on an instance that
has been in use for a year reports what it kept and writes nothing.

**It is one transaction.** A step that cannot finish — a mistyped currency, a
preset that will not load — rolls the whole run back rather than leaving a
half-provisioned instance. `--dry-run` uses the same transaction and rolls it
back on purpose, so it reports exactly what a real run would have written.

The logic is in `app/members/setup.py`, in one function per step, because the
first-run web wizard calls the same functions. The command is a shell around
them: it reads the answers, prompts for what is missing, and prints the
result.

The beat schedule itself is declared once, as `CELERY_BEAT_SCHEDULE` in
`troopconnect/settings.py`; the `periodic_tasks` step reads it rather than
repeating it, and the test suite asserts that every task it names is one a
worker actually registers.

### Inputs

Flags win over `--answers`, which wins over a prompt. With no terminal and
`--noinput`, a value nobody supplied keeps its default.

| Group | Flags |
| --- | --- |
| Organisation | `--unit-name`, `--short-name`, `--federation`, `--contact-email`, `--reply-to-email`, `--contact-phone`, `--footer-address`, `--privacy-policy` |
| Locale | `--languages fr,nl`, `--default-language`, `--phone-region`, `--currency` |
| Calendar | `--year-start 08-01`, `--age-reference 12-31`, `--passage-date 05-01`, `--passage-mode`, `--archive-retention-years`, `--top-branch-graduates-become-leaders` |
| Administrator | `--admin-email`, `--admin-password`, `--admin-first-name`, `--admin-last-name`, `--no-admin-superuser` |
| Which steps | the `--no-…` column above, plus `--preset` |
| How | `--dry-run`, `--noinput` |

`--answers` takes a JSON file, with every key optional:

```json
{
  "settings": {"name": "Les Scouts de Limal", "enabled_languages": ["fr", "nl"]},
  "preset": "les-scouts",
  "steps": {"preset": true, "admin": false},
  "admin": {"email": "chef@example.org", "password": "…",
            "first_name": "Ada", "last_name": "Chef"}
}
```

`settings` keys are `TroopSettings` field names, and anything else is refused
rather than ignored. A translated field (`name`, `site_description`, …) takes
either one string, written to every language, or an object keyed by language.
`logo`, `favicon` and `last_passage_school_year` are refused: an answers file
cannot carry an upload, and the marker is the passage's own bookkeeping.

### Branch presets

`--preset` takes the name of a preset shipped in `app/members/presets/`, or a
path to a file in the same shape for a federation or a unit to contribute.

| File | What it is |
| --- | --- |
| `les-scouts.json` | Les Scouts' four branches — Baladins (6-8), Louveteaux (8-12), Éclaireurs (12-16), Pionniers (16-18) — with the federation's names in French and Dutch and one section per branch. |
| `preset.schema.json` | The JSON Schema every preset is validated against, shipped file or `--preset` path alike. |

A branch carries `key`, `name` (per language, French required), the two age
bounds, `promotes_to` (a key) and `is_top`; a section carries a name and the
sex it takes (`M`, `F` or `B`). `app/members/presets/__init__.py` validates the
file on load and reports *every* problem at once, naming the path into the
file (`$.branches[2].promotes_to`) — it implements the subset of JSON Schema
the schema uses rather than pulling in a schema library, and adds the checks a
shape cannot express: that every `promotes_to` resolves, that the links do not
loop, and that the ladder ends somewhere.

The shipped preset names the federation's branches, never a unit's sections:
a troop's own section names belong in the database it edits.

---

## 4. Services

`compose.yml`:

| Service | Image | Role |
| --- | --- | --- |
| `init` | app image | One shot. Runs `entrypoint.sh init-secrets` and exits. |
| `web` | app image | Gunicorn on 9000. The only service that migrates and collects static files. |
| `worker` | app image | Celery worker: `send_queued_mail`, `create_year_task`, `run_passage`, cleanup tasks. |
| `beat` | app image | Celery scheduler (`django_celery_beat`, database-backed). |
| `db` | `postgres:17-alpine` | Database. PostgreSQL only — the app uses `ArrayField`. |
| `redis` | `redis:8-alpine` | Celery broker and cache. |
| `caddy` | `caddy:2-alpine` | TLS termination and reverse proxy; serves `/static/` and `/media/` from volumes. |

The four application services run the same image,
`ghcr.io/tdebruyn/troopconnect:${TC_VERSION:-0}`. Only `caddy` publishes ports
(80 and 443); the rest are reachable only from the compose network, by service
name. There are no `container_name` overrides, so the project name keeps two
instances on one host from colliding.

Volumes:

| Volume | Mounted at | Holds |
| --- | --- | --- |
| `db_data` | `db:/var/lib/postgresql/data` | Database files. |
| `app_secrets` | `init`, `web`, `worker`, `beat` | The generated `secret_key`. **Not** mounted into `db`. |
| `db_secrets` | `init` (rw), `db`, `web`, `worker`, `beat` (ro) | The generated `postgres_password`. |
| `media` | `web`, `worker`, `beat`, `caddy` (ro) | User uploads. |
| `static` | `web`, `caddy` (ro) | `collectstatic` output. |
| `caddy_data`, `caddy_config` | caddy | Certificates and Caddy's autosaved config. |

The two secrets are separate volumes so that the database container can read
the password it was initialised with and nothing else. A database process that
can also read the key signing every session has a privilege it has no use for;
`init` and the application services mount both, `db` mounts only `db_secrets`,
read-only, and the smoke workflow asserts it.

Both are shared between `init` and the application on purpose: the database
reads the password the entrypoint generated, so the two can never disagree. The
consequence is that deleting `db_data` without deleting `db_secrets` leaves the
generated password pointing at a database that no longer has it — delete both,
or neither.

`compose.dev.yml` overlays the same file for development: it builds the image
locally as `troopconnect-dev:local` (so it never shadows a release tag), mounts
`app/`, sets `DJANGO_DEBUG=1` with `SITE_DOMAIN=localhost` and
`EMAIL_URL=console://`, publishes the web port and the database ports, and puts
`caddy` behind a profile so it does not start.

The `init` service exists because Postgres reads `POSTGRES_PASSWORD_FILE` once,
when it first initialises an empty data directory. Something has to create that
file before then, and compose can only express that ordering with a one-shot
service and `depends_on: condition: service_completed_successfully`.

---

## 4a. Container entrypoint

`app/entrypoint.sh` runs for every service built from the app image, as the
Dockerfile `ENTRYPOINT` with the service's `command` as arguments.

1. **Secrets.** Creates `SECRET_KEY_FILE` (mode 600) and
   `POSTGRES_PASSWORD_FILE` (mode 644, because Postgres reads it as a different
   user), each in its own volume. An existing file is never overwritten, so
   `SECRET_KEY` or `POSTGRES_PASSWORD` in the environment wins on the first
   start and is ignored afterwards. With the argument `init-secrets` it stops
   here — that is all the `init` service does.
2. **Wait for the database.** `manage.py wait_for_db`, which fails with a
   clear message after `--timeout` (60s) rather than a connection traceback.
3. **Once-per-deploy work**, only when `RUN_MIGRATIONS` is set, which only the
   web service does. `manage.py migrate_locked` takes a Postgres advisory lock
   and gives up with a plain-language message if another process is still
   migrating; then `collectstatic`.
4. `exec "$@"` — the service's command, usually Gunicorn or Celery.

---

## 4b. Health

`GET /healthz` answers `200` while the database and the cache both respond, and
`503` the moment either does not:

```
{"database": "ok", "cache": "error"}
```

It reports *whether* each dependency answered and never the error itself,
because the endpoint is public. Nothing else is checked: an unreachable SMTP
server degrades a feature, and taking a working instance out of rotation for it
would be worse than the degradation.

The web service's Docker healthcheck runs `app/healthcheck.py`, which requests
`/healthz` over HTTP from inside the container — the same path a request takes,
rather than importing the app. It addresses `127.0.0.1` with `SITE_DOMAIN` as
the Host header, because Django would reject that address as a host name in
production. Caddy waits for the web service to be healthy before starting, so
a first boot never serves a certificate before the application can answer.

`worker` and `beat` have no healthcheck: `/healthz` describes the web
application, and there is no equivalent HTTP surface for a Celery process.

---

## 5. Email pipeline

`django-post-office` queues messages (status `queued`) rather than sending on
the request path. Celery flushes them: immediately on the `email_queued` signal,
with the `send_queued_mail` beat task every 5 minutes as a backstop. After
`MAX_RETRIES` (3) failures a message is marked `failed` and staff see a warning
banner linking to the queue page, where they can requeue or purge.

The backend is chosen from `MAIL_SEND_MODE` / `MAILERSEND_API_KEY` / `EMAIL_URL`
(see the table above). `troopconnect/dummy_backend.py` records to
`django.core.mail.outbox` without sending, for tests and dry runs.

---

## 6. Deployment

**Self-hosted (supported):** the installation is two files. Copy `.env.example`
to `.env`, fill in the four required variables, then

```bash
docker compose up -d
```

Nothing in the shipped files is edited, and there is no build step: the images
come from `ghcr.io/tdebruyn/troopconnect`.

**Ansible (community-maintained, unsupported):** `contrib/ansible/`. Non-secret
values go in `config.yml` (from `config.yml-example`), secrets in `vault.yml`
(edited with `create-config.py`). The playbook writes them to
`{{ project_dir }}/.env` as uppercase variables and starts `compose.yml`. See
that directory's README before relying on it.

---

## 7. Continuous integration

`.github/workflows/`, all triggered on `main` pushes and pull requests:

| Workflow | Does |
| --- | --- |
| `test` | The Django suite against Postgres 17 and Redis 8 services, plus `ruff`. The environment it sets is the same set of variables a troop puts in `.env`. |
| `image` | Builds `ghcr.io/tdebruyn/troopconnect` for amd64 and arm64, and publishes it on tags and `main`. Pull requests build amd64 only and do not push. |
| `smoke` | Builds the image locally, writes `.env` from `.env.example`, brings the stack up on empty volumes, waits for `/healthz`, checks the homepage and login page answer, then restarts on the same volumes and checks nothing was regenerated. |
| `security` | `pip-audit` against `requirements.txt`, and Trivy over the built image failing on fixable criticals. Also runs weekly. |

Dependabot (`.github/dependabot.yml`) watches pip, both Docker contexts and
GitHub Actions; minor and patch bumps arrive as one grouped pull request.

Versioning, the tag-to-image-tag mapping, and the one-time step that makes the
GHCR package public are in `RELEASING.md`.
