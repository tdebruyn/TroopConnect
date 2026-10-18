"""Let the troop order the public page's blocks.

The public page's blocks were rendered in the template's own order. The
settings page now stores the troop's order here; existing rows get the order
the page used until now, so nothing moves on upgrade.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("members", "0045_responsable_communication_role"),
    ]

    operations = [
        migrations.AddField(
            model_name="troopsettings",
            name="homepage_block_order",
            field=models.CharField(
                blank=True,
                default="desk,place,about,faq",
                max_length=64,
            ),
        ),
    ]
