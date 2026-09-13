# Generated manually — adds FeeRule, backfills it from CotisationConfig,
# then drops the flat price fields from CotisationConfig.

from decimal import Decimal

import django.db.models.deletion
from django.db import migrations, models


def _backfill_fee_rules(apps, schema_editor):
    """Copy old flat pricing into generic (branch=None) FeeRule rows."""
    CotisationConfig = apps.get_model("finance", "CotisationConfig")
    FeeRule = apps.get_model("finance", "FeeRule")

    for config in CotisationConfig.objects.all():
        sibling = max(config.full_fee - config.sibling_discount, Decimal("0.00"))
        rows = [
            # Children: eldest full fee, siblings discounted (all branches).
            (config.school_year_id, None, 1, "child", config.full_fee),
            (config.school_year_id, None, 2, "child", sibling),
            (config.school_year_id, None, 3, "child", sibling),
            # Animators: flat fee repeated across ranks.
            (config.school_year_id, None, 1, "animator", config.animateur_fee),
            (config.school_year_id, None, 2, "animator", config.animateur_fee),
            (config.school_year_id, None, 3, "animator", config.animateur_fee),
        ]
        for school_year_id, branch_id, rank, member_type, amount in rows:
            FeeRule.objects.create(
                school_year_id=school_year_id,
                branch_id=branch_id,
                rank=rank,
                member_type=member_type,
                amount=amount,
            )


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0002_alter_cotisationconfig_options_alter_payment_options_and_more"),
        ("members", "0019_email_template_language"),
    ]

    operations = [
        migrations.CreateModel(
            name="FeeRule",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "rank",
                    models.PositiveSmallIntegerField(
                        choices=[
                            (1, "1st member"),
                            (2, "2nd member"),
                            (3, "3rd member or more"),
                        ]
                    ),
                ),
                (
                    "member_type",
                    models.CharField(
                        choices=[("child", "Child"), ("animator", "Animator")],
                        default="child",
                        max_length=10,
                    ),
                ),
                (
                    "amount",
                    models.DecimalField(
                        decimal_places=2, default=Decimal("0.00"), max_digits=8
                    ),
                ),
                (
                    "branch",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="members.branch",
                    ),
                ),
                (
                    "school_year",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="fee_rules",
                        to="members.schoolyear",
                    ),
                ),
            ],
            options={
                "verbose_name": "Fee rule",
                "verbose_name_plural": "Fee rules",
                "ordering": ["member_type", "rank", "branch__name"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("school_year", "branch", "rank", "member_type"),
                        name="uniq_fee_rule",
                    ),
                ],
            },
        ),
        migrations.RunPython(_backfill_fee_rules, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="cotisationconfig",
            name="full_fee",
        ),
        migrations.RemoveField(
            model_name="cotisationconfig",
            name="sibling_discount",
        ),
        migrations.RemoveField(
            model_name="cotisationconfig",
            name="animateur_fee",
        ),
    ]
