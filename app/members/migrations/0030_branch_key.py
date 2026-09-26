from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("members", "0029_seed_troop_logo"),
    ]

    operations = [
        migrations.AddField(
            model_name="branch",
            name="key",
            field=models.CharField(
                blank=True,
                default="",
                help_text=(
                    "Stable identifier from a branch preset, used to recognise "
                    "this branch again when the preset is applied a second time."
                ),
                max_length=30,
            ),
        ),
    ]
