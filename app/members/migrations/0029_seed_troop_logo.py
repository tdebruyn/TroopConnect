"""Give an instance that is already in use the logo it is already showing.

Until now the header and the emails showed the mark shipped with the
application, hard-coded in ``templates/base.html``. From ``0028`` that mark is
the *fallback* for a troop that has uploaded nothing, so an instance that
upgrades keeps looking exactly as it did with no help from this migration.

What this does is make that logo the troop's own file rather than a path into
the application: the image is copied out of the static files into the media
storage and recorded on the settings row. From then on the troop owns it — it
survives the shipped default being replaced, and staff can swap it for their
own mark on the settings page without anything else changing.

**It only touches a database that was already in use** — one that holds at
least one member. A fresh install has no logo to preserve, and seeding one
would leave it showing a copy of a default it never chose, with the fallback it
is supposed to fall back to never exercised. So an empty database is left
alone and starts on the shipped mark; see ``TroopSettings.logo_url``.
"""

import os

from django.contrib.staticfiles import finders
from django.core.files.storage import default_storage
from django.db import migrations

from members.constants import DEFAULT_LOGO


def seed_logo(apps, schema_editor):
    TroopSettings = apps.get_model("members", "TroopSettings")
    Person = apps.get_model("members", "Person")

    if not Person.objects.exists():
        # A fresh install: there is no logo to preserve, and the mark it is
        # already showing is the shipped fallback.
        return

    try:
        troop = TroopSettings.objects.get(pk=1)
    except TroopSettings.DoesNotExist:
        # A database older than 0025; get_settings() creates the row on first
        # read, and it will fall back to the shipped mark, which is the point.
        return

    if troop.logo:
        return

    # Through the staticfiles finders rather than a path under BASE_DIR, so an
    # instance that collects its statics somewhere else still finds it.
    source = finders.find(DEFAULT_LOGO)
    if source is None:
        # Packaged without the asset is not a reason to fail a migration; the
        # fallback in TroopSettings.logo_url() covers it.
        return

    with open(source, "rb") as fh:
        stored = default_storage.save(f"troop/{os.path.basename(source)}", fh)

    troop.logo = stored
    troop.save(update_fields=["logo"])


def clear_logo(apps, schema_editor):
    """Drop the copy this migration made, putting the instance back on the fallback.

    Only the name this migration would have written is cleared, so a logo the
    troop uploaded itself — which is, by then, the point of the field — is left
    exactly where it is. The file is deleted rather than orphaned: this reverses
    a copy made here, and leaving 80 KB behind per rollback would only ever be
    found by hand.
    """
    TroopSettings = apps.get_model("members", "TroopSettings")
    Person = apps.get_model("members", "Person")

    if not Person.objects.exists():
        return

    try:
        troop = TroopSettings.objects.get(pk=1)
    except TroopSettings.DoesNotExist:
        return

    name = f"troop/{os.path.basename(DEFAULT_LOGO)}"
    if not troop.logo or troop.logo.name != name:
        return

    troop.logo = ""
    troop.save(update_fields=["logo"])

    if default_storage.exists(name):
        default_storage.delete(name)


class Migration(migrations.Migration):

    dependencies = [
        ("members", "0028_troopsettings_logo_favicon"),
    ]

    operations = [
        migrations.RunPython(seed_logo, clear_logo),
    ]
