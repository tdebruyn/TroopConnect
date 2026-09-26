# Releasing TroopConnect

## Versions

Versions are **`0.Y.Z` until 1.0**. While the project is pre-1.0, a minor bump
is the breaking-change signal and a patch bump is anything else.

Images go to `ghcr.io/tdebruyn/troopconnect`, a public package, built for
`linux/amd64` and `linux/arm64`.

## Publishing

Pushing a tag that looks like `vX.Y.Z` publishes three tags:

| Git tag | Image tags published |
| --- | --- |
| `v0.4.2` | `0.4.2`, `0.4`, `0` |

The floating tags are what make `TC_VERSION` useful: an instance pinned to `0`
takes every 0.x release, one pinned to `0.4` takes patch releases only, and one
pinned to `0.4.2` never moves.

Every commit on `main` also publishes `edge`, which is built but never
advertised.

**`latest` is never published.** Nothing should resolve to "the newest thing"
by accident — a troop that wants to move has to say so, by changing
`TC_VERSION`.

`compose.yml` defaults to `${TC_VERSION:-0}`, so a fresh install tracks the 0.x
line. That default becomes `1` at the 1.0 release, together with a note that
instances still on `0` should be moved deliberately.

Pull requests build the image (amd64 only, for speed) without pushing it.

The version is baked into the image as `TC_APP_VERSION`. Ask it directly —
`--entrypoint` is needed because the image starts the application by default:

```bash
docker run --rm --entrypoint printenv ghcr.io/tdebruyn/troopconnect:0.4.2 TC_APP_VERSION
```

## Cutting a release

```bash
git switch main && git pull
git tag -a v0.4.2 -m "v0.4.2"
git push origin v0.4.2
```

The `image` workflow does the rest. Watch it under Actions; when it finishes,
the tags are on the package page.

## One-time setup, after the first push

**This is a manual step, and nothing works for anybody else until it is done.**
A newly pushed GHCR package is private, so `docker compose pull` on a troop's
server fails with `denied` until it is made public.

1. Let the `image` workflow publish once — a push to `main` is enough, it
   publishes `edge`.
2. Open the package page: your GitHub profile → **Packages** →
   `troopconnect`, or
   <https://github.com/users/tdebruyn/packages/container/troopconnect>.
3. **Package settings** → **Danger Zone** → **Change visibility** → **Public**,
   and confirm when asked to type the package name.
4. On the same settings page, under **Repository**, connect
   `tdebruyn/TroopConnect`. The package then shows on the repository page and
   inherits its access, and future releases stay linked automatically.
5. Check it anonymously, which is what a troop's server does:

   ```bash
   docker logout ghcr.io
   docker pull ghcr.io/tdebruyn/troopconnect:edge
   ```

   If that succeeds without credentials, self-hosting works.

If the project ever moves to an organisation, step 4 also needs
**Manage Actions access** for the repository that publishes.

## How a troop upgrades

```bash
# in .env
TC_VERSION=0.4.2

docker compose pull
docker compose up -d
```

Migrations run automatically, under a Postgres advisory lock, so a rolling
restart is safe. The secrets live in volumes and are never regenerated, so
existing sessions and the database connection survive the upgrade.
