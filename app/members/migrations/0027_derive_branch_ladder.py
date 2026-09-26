"""Turn the age ladder the passage used to infer into explicit links.

Until now ``run_passage`` worked out where a member went by scanning the
branches ordered by ``min_age_dec_31`` and taking the first one whose age range
matched. This migration writes that same order down as ``promotes_to`` links,
and marks the final branch as the one members graduate out of, so an existing
troop's ladder behaves exactly as before while a troop that reorders or renames
its branches is no longer fighting an assumption in the code.
"""

from django.db import migrations


def derive_ladder(apps, schema_editor):
    Branch = apps.get_model("members", "Branch")

    # The order the passage itself used — branches without a minimum age sort
    # last (NULLs last), so one of those becomes the graduation branch rather
    # than silently breaking the chain. Staff can correct either in the admin.
    branches = list(Branch.objects.order_by("min_age_dec_31", "name"))

    for current, following in zip(branches, branches[1:]):
        current.promotes_to = following
        current.save(update_fields=["promotes_to"])

    if branches:
        top = branches[-1]
        top.is_top = True
        top.save(update_fields=["is_top"])


def clear_ladder(apps, schema_editor):
    Branch = apps.get_model("members", "Branch")
    Branch.objects.update(promotes_to=None, is_top=False)


class Migration(migrations.Migration):

    dependencies = [
        ("members", "0026_branch_is_top_branch_promotes_to_and_more"),
    ]

    operations = [
        migrations.RunPython(derive_ladder, clear_ladder),
    ]
