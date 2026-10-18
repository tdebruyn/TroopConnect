"""The About block no longer claims a place in the sequence.

Its help text said "after the enrolment desk"; the troop now chooses the
order, so the field says what the block is rather than where it sat.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("members", "0046_troopsettings_homepage_block_order"),
    ]

    operations = [
        migrations.AlterField(
            model_name="troopsettings",
            name="homepage_about_enabled",
            field=models.BooleanField(
                default=False,
                help_text="A longer introduction, on its own sheet.",
            ),
        ),
    ]
