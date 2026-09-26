# Legacy import (one-off)

The importer that reads the old site's database — the djangoCMS-era SQLite dump
— and rebuilds it as TroopConnect members. It exists for one migration, for one
unit, and belongs with the rest of the unsupported, run-by-hand automation in
`contrib/`. The supported way to bring members in is the **import page in the
application itself** (`/users/import`), which takes a CSV or an XLSX and is
documented in [`docs/dev/CONTRACT.md`](../../docs/dev/CONTRACT.md).

Like `contrib/ansible/`, this folder is community-maintained and unsupported:
it is here because it was needed once and is worth keeping, not because anyone
promises it still fits a database it has not seen.

**It no longer runs, and nothing has ported it.** It imports
`homepage.models.Event`, which the per-section agenda replaced with
`members.SectionEvent`, so it raises `ImportError` before it reads anything —
and `test_import_legacy.py` with it. Porting the event import is work for
whoever next needs this tool on a real dump; nothing else in the project
depends on it, which is exactly why it lives here.

`import_legacy.py` is deliberately **not part of the Docker image**. It lives
outside `app/`, so it is never installed as a `manage.py` command and can never
be triggered by accident from a running container. You run it by hand, mounted
into a throwaway container, as described below.

---

## Why this file is not in `app/`

Both Dockerfiles (`app/Dockerfile.dev`, `app/Dockerfile.prod`) build from the
repository root but only copy the app directory:

```dockerfile
COPY app/ .
```

Anything outside `app/` is therefore absent from the image — and
`.dockerignore` names `contrib/` explicitly, so it stays that way even if the
build context ever changes. That is the whole trick: **outside `app/` means
outside the image**, with no `Dockerfile` edit needed.

Two consequences worth knowing:

- The importer cannot be a Django management command anymore (Django only
  discovers commands inside installed apps). It bootstraps Django itself — see
  the `Bootstrap Django` block at the top of `import_legacy.py`.
- It is invisible to the container unless you mount it in. That is
  intentional: in production there is no way to run it by mistake.

Because the script lives outside `app/`, the ruff check that runs as part of
`manage.py test` (`app/tests/test_lint.py`) does not cover it. Lint it
explicitly — see [Linting](#linting).

---

## Running the tool

A one-off `web` container, with this folder bind-mounted inside it.

```bash
# from the repository root
docker compose -f compose.yml -f compose.dev.yml run --rm \
  -v "$PWD/contrib/legacy-import:/app/legacy_import" \
  web uv run python /app/legacy_import/<tool>.py <args>
```

Notes:

- Run it from the **repository root**, where the compose project name
  (`troopconnect`) matches the running stack so this reuses the existing
  `postgres` container. From elsewhere — a worktree, say — add
  `-p troopconnect` so it does not try to start a second database.
- `web` is the service whose environment has the database credentials, so run
  it there, not in `worker`/`beat`.
- The script never writes next to itself, so the mount can be `:ro` — it still
  imports from `/app/legacy_import`, it just cannot write there.
- Input files that live outside `app/` (a SQLite dump, a CSV) must be mounted
  as well, exactly like the tool directory.

---

## `import_legacy.py`

Imports the legacy database of the **old website** into TroopConnect. It reads
the djangoCMS-era SQLite dump directly and rebuilds rows into the current
models — a `famille` (household) entity that no longer exists is flattened
away:

```
auth_user + accounts_myprofile + accounts_parent  ->  Account + Person (Parent)
accounts_anime                                    ->  Person (Animé / Animateur)
accounts_famille + accounts_liendeparente         ->  ParentChild
inscriptions_section                              ->  Section (+ Branch)
inscriptions_inscription                          ->  Enrollment (current year only)
cotisations_cotisationrule                        ->  FeeRule + CotisationConfig
cotisations_cotisationpayement                    ->  Payment (attributed to a payer)
inscriptions_evenement                            ->  homepage.Event
auth_user_groups                                  ->  PersonRole (secondary roles)
```

### Before you start

1. **Get the dump.** `db21sv_20240520.sqlite` is not in git — it is the old
   site's database export, kept outside the repository (the local copy lives
   in the untracked `workspace/` directory). Put it somewhere on the host and
   mount it in.
2. **Start from a freshly-migrated database.** The importer assumes an empty
   target: reference rows (roles, branches, school years) come from
   migrations, and members are created from scratch.
3. **Run it once.** Most rows are created with `get_or_create`, but payments
   and events are inserted unconditionally — a second run on the same
   database *duplicates every payment and event*.
4. **On production, take a database backup first** (and still start with a
   dry run).

### Dry run first

Always. `--dry-run` performs the whole import and then rolls it back, so it
reports exactly what would change without touching anything.

```bash
# from the repository root
docker compose -f compose.yml -f compose.dev.yml run --rm \
  -v "$PWD/contrib/legacy-import:/app/legacy_import" \
  -v "$PWD/workspace/db21sv_20240520.sqlite:/data/legacy.sqlite:ro" \
  web uv run python /app/legacy_import/import_legacy.py /data/legacy.sqlite --dry-run
```

Read the summary it prints at the end — a count per imported model, plus a
warning line for every row it could not make sense of (a broken phone number,
a payment with no payer, a person with no first name). Warnings are not
fatal; decide whether they are acceptable, or fix the source data.

### The real run

Same command without `--dry-run`:

```bash
docker compose -f compose.yml -f compose.dev.yml run --rm \
  -v "$PWD/contrib/legacy-import:/app/legacy_import" \
  -v "$PWD/workspace/db21sv_20240520.sqlite:/data/legacy.sqlite:ro" \
  web uv run python /app/legacy_import/import_legacy.py /data/legacy.sqlite
```

The whole import runs inside a single transaction. If anything raises, the
transaction is rolled back and the database is left untouched, so a failed run
is safe to repeat.

### Against production

Same idea, using the production compose file and the gunicorn service name
(`troopconnect`). Python lives at `/usr/local/bin/python` in the prod image —
it has no `uv`:

```bash
# on the server, in the repository directory
docker compose -f compose.yml run --rm \
  -v "$PWD/contrib/legacy-import:/app/legacy_import" \
  -v "/root/legacy.sqlite:/data/legacy.sqlite:ro" \
  web python /app/legacy_import/import_legacy.py /data/legacy.sqlite --dry-run
```

`docker compose run` overrides the image's `CMD` (the gunicorn entrypoint
script), so the tool starts instead of the web server — but it still inherits
the service's database environment.

### Adjusting the import

The source data is what it is, but a few mappings are worth checking against
the dump before a real run. They are plain tables near the top of
[`import_legacy.py`](import_legacy.py):

| Table | Maps |
|-------|------|
| `BRANCHES` | Branch name → age range on 31 December |
| `SECTION_MAP` | Legacy section code (`bal1`, `lou2`, …) → branch + sex |
| `QUALITE_TO_ROLE` | Legacy `inscription.qualite` → primary role |
| `GROUP_TO_ROLE` | Legacy Django group name → secondary role |

### Tests

The tests live next to the tool (they were moved out of `app/tests/` with it)
and need the Django test runner, so the folder is mounted into a container:

```bash
docker compose -f compose.yml -f compose.dev.yml run --rm \
  -v "$PWD/contrib/legacy-import:/app/legacy_import" \
  web uv run /app/manage.py test legacy_import.test_import_legacy --noinput
```

They build a small SQLite file mimicking the legacy schema, run the importer
against it, and assert what lands in each target model — including that a
`--dry-run` persists nothing.

The `__init__.py` in this folder is what makes that work: mounted at
`/app/legacy_import`, it lets the test runner import `legacy_import` as a package.
Leave it there.

Because these tests live outside `app/tests/`, they are **not** part of
`manage.py test tests`. Run the command above when you touch the importer.

### Linting

```bash
docker compose -f compose.yml -f compose.dev.yml run --rm \
  -v "$PWD/contrib/legacy-import:/app/legacy_import" \
  web uv run ruff check --config /app/ruff.toml /app/legacy_import
```

---

## Adding another one-off tool

If another migration or repair ever needs one:

1. Give it its own directory under `contrib/` — a plain script, not a
   management command. If it needs the ORM, copy the `Bootstrap Django` block
   from the top of `import_legacy.py`. It has to sit *above* your
   `from members...` imports, because a plain script gets neither the project
   root on `sys.path` nor an app registry for free:

   ```python
   # --- Bootstrap Django --- (see import_legacy.py for the full block)
   HERE = Path(__file__).resolve().parent
   for _root in (HERE.parent, HERE.parent / "app"):   # /app, or repo checkout
       if (_root / "manage.py").is_file():
           sys.path.insert(0, str(_root))
           break
   os.environ.setdefault("DJANGO_SETTINGS_MODULE", "troopconnect.settings")
   import django  # noqa: E402
   django.setup()

   from members.models import Person  # noqa: E402
   ```

   The `# noqa: E402` markers are required — ruff (rightly) complains about
   imports below code.

2. Write a README in that directory saying what it is for, which occasion
   needs it, and how to run it.
3. If it is more than a handful of lines, add a `test_your_tool.py` beside it
   (see `test_import_legacy.py` for the shape) and document how to run it.
4. Keep it outside `app/`. That is the point of `contrib/`.
