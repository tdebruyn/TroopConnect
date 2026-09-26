"""Rename ``SiteSettings`` to ``TroopSettings``, and its fields to match.

Hand-written rather than autodetected for two reasons:

* Django proposes a renamed model as a ``DeleteModel`` plus a ``CreateModel``,
  which would drop the row every existing install has been editing in the
  admin. ``RenameModel`` renames the table and keeps it.
* ``name`` is a *translated* field, so renaming it also means renaming the
  per-language columns modeltranslation added for ``site_name`` in 0014
  (``site_name_fr``/``_nl``/``_en``). The autodetector pairs neither of those
  with the base field, so it would drop the translations.

The rest of the widening (the new Organisation/Locale/Calendar/Modules fields)
is generated in 0024.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("members", "0022_generic_sitesettings_defaults"),
    ]

    operations = [
        migrations.RenameModel(
            old_name="SiteSettings",
            new_name="TroopSettings",
        ),
        # The unit's name, and the three per-language columns that hold it.
        migrations.RenameField("troopsettings", "site_name", "name"),
        migrations.RenameField("troopsettings", "site_name_fr", "name_fr"),
        migrations.RenameField("troopsettings", "site_name_nl", "name_nl"),
        migrations.RenameField("troopsettings", "site_name_en", "name_en"),
        migrations.RenameField(
            "troopsettings", "available_languages", "enabled_languages"
        ),
        migrations.RenameField(
            "troopsettings", "contact_address", "footer_address"
        ),
    ]
