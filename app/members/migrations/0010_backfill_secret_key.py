from django.db import migrations


def backfill_secret_keys(apps, schema_editor):
    Person = apps.get_model("members", "Person")
    for person in Person.objects.filter(secret_key="").exclude(id=None):
        Person.objects.filter(pk=person.pk).update(
            secret_key=str(person.id)[:6]
        )


class Migration(migrations.Migration):
    dependencies = [
        ("members", "0009_add_secret_key"),
    ]

    operations = [
        migrations.RunPython(backfill_secret_keys, migrations.RunPython.noop),
    ]
