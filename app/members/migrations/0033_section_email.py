from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("members", "0032_drop_old_cleanup_events_schedule"),
    ]

    operations = [
        migrations.AddField(
            model_name="section",
            name="email",
            field=models.EmailField(
                blank=True,
                default="",
                help_text=(
                    "Where answers to this section's messages should go. "
                    "Empty uses the unit's reply-to address."
                ),
                max_length=254,
            ),
        ),
    ]
