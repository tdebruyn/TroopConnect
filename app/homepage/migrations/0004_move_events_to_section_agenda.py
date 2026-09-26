"""Replace the troop-wide public agenda with the per-section one.

``homepage.Event`` was the old agenda: a single public list for the whole
troop. Its replacement is ``members.SectionEvent``, whose entries belong to one
section. This copies across the rows that name a section — the only kind the
new model can hold — and then drops the old table.

Rows without a section (troop-wide entries, plus everything the messaging form
created for a group that was not a section) have nowhere to go and go with it.

The reverse is deliberately empty: the old table is gone, and reconstructing it
from the section agendas would invent a public agenda the site no longer has.
"""

from django.db import migrations


def move_events_to_section_agenda(apps, schema_editor):
    Event = apps.get_model("homepage", "Event")
    SectionEvent = apps.get_model("members", "SectionEvent")

    for event in Event.objects.filter(section__isnull=False):
        SectionEvent.objects.create(
            section_id=event.section_id,
            # The old model had no activity type; a plain meeting is the
            # neutral choice, and a leader can recategorise it.
            activity_type="reunion",
            title=event.title,
            description=event.description,
            start_date=event.date,
            created_from_message_id=event.created_from_message_id,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("homepage", "0003_imageasset_sitecontent"),
        # The new model has to exist before anything can be copied into it.
        ("members", "0031_rename_public_agenda_enabled_troopsettings_agenda_enabled_and_more"),
    ]

    operations = [
        migrations.RunPython(
            move_events_to_section_agenda, migrations.RunPython.noop
        ),
        migrations.DeleteModel(name="Event"),
    ]
