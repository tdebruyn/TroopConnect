# Vendored: Les Scouts `template-unite`

The Les Scouts (Baden-Powell de Belgique) unit-site theme. Everything in this
directory is the work of Les Scouts asbl, copied here unchanged so that the
design this project ships is the design the federation publishes — and so that
a later upgrade is a diff against a known commit rather than a guess.

**Nothing in this directory may be edited.** Our own styling goes in
`app/static/css/troopconnect.css`, which is loaded *after* `css/base.css`.
A local edit here would be silently lost the next time the theme is refreshed.

| | |
| --- | --- |
| Source | <https://github.com/lesscouts/template-unite> |
| Commit | `c8bcce215e3674fa3cf68972a962c8b107c2f090` (branch `main`, 2022-03-31) |
| Licence | MIT — see `LICENSE.md`, © 2022 Les Scouts asbl |
| Licence check | MIT is permissive and one-way compatible with this project's AGPL-3.0: the theme can be redistributed inside an AGPL-3.0 work, provided the MIT notice travels with it. It is recorded in `docs/dev/CONTRACT.md`. |

## What is here

| Path | Contents |
| --- | --- |
| `css/base.css` | The theme's compiled stylesheet — Bootstrap 5.1.3 plus the Les Scouts graphical charter. This is the file the site loads. |
| `scss/` | The sources `css/base.css` is compiled from. Not built by this project; kept so an upgrade can be diffed. |
| `fonts/` | Muli, Housepaint, CaveatBrush, Mali and Roboto Mono, as `@font-face`-ed by `css/base.css`. |
| `images/toppings/` | The section "toppings" the stylesheet uses as decorative backgrounds. |
| `images/logos/` | The federation mark and the four branch marks. |
| `images/illustrations/` | Illustration used by the theme's own example pages. |

`css/base.css` addresses its assets relatively (`../fonts/…`, `../images/…`), so
the directory layout above is not cosmetic: moving a file breaks the stylesheet.

## What was left out

Upstream also ships `documentation/`, `exemples/`, `index.html`, `README.md`,
`SECURITY.md` and the `composer.json`/`package.json` manifests. They are the
theme's own doc site and build config, neither of which this project uses, so
they were not copied. `assets/` — our own logo, illustration and JavaScript —
lives outside this directory, under `app/static/`.

`images/logos/*` is not referenced by the stylesheet either: those are the
federation mark and the four branch marks, which the theme's example pages use
and which nothing in this project displays yet. They are kept — byte-identical,
in their original layout — so that a section page can use the theme's own mark
for a branch rather than a second set invented here.

The theme's five branch families, as `scss/_ls-variables.scss` names them. The
shortcut is the one that appears in the generated classes (`.topping-louveteaux`
and `.topping-l` are the same rule):

| Key | Family | Branch mark |
| --- | --- | --- |
| `f` | `federation` | `logo_Federation_*.png` |
| `b` | `baladins` | `logo_Baladins.png` |
| `l` | `louveteaux` | `logo_Louveteaux.png` |
| `e` | `eclaireurs` | `logo_Eclaireurs.png` |
| `p` | `pionniers` | `logo_Pionniers.png` |

`members.Branch` has no field naming one of these, so nothing selects them
today; see `docs/dev/CONTRACT.md` for what that would take.

## Updating

1. Pick the upstream commit to move to and read its diff.
2. Replace the files above with that commit's versions, byte for byte —
   `git diff` in this directory must show no local modification.
3. Try to compile `scss/base.scss` and reconcile it with the shipped
   `css/base.css` if the theme changed its build.
4. Update the commit and date in the table above.
5. Check `app/static/css/troopconnect.css` still overrides what it means to:
   a theme upgrade can drop or rename the class an override targets.
