# Generated for the run_passage idempotency marker.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("members", "0012_email_templates"),
    ]

    operations = [
        migrations.AddField(
            model_name="sitesettings",
            name="last_passage_school_year",
            field=models.IntegerField(
                blank=True,
                null=True,
                help_text=(
                    "Dernière année scolaire (champ « name ») pour laquelle le "
                    "passage automatique a été exécuté. Anti-rejeu : si Celery "
                    "était arrêté le jour du passage, la tâche se rattrape au "
                    "prochain démarrage."
                ),
            ),
        ),
    ]
