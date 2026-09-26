"""`manage.py setup`, and the steps it is made of.

Two things have to hold for every step, and most of these tests are one of
them: a step fills what is missing, and a step that runs a second time on an
instance somebody has since edited changes nothing.
"""

import json
import shutil
import tempfile
from datetime import date
from io import StringIO
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django_celery_beat.models import CrontabSchedule, PeriodicTask
from post_office.models import EmailTemplate

from homepage.models import SiteContent
from members import email_templates, permissions, setup
from members.management.commands.setup import (
    DATE_FLAGS,
    SETTINGS_FLAGS,
)
from members.management.commands.setup import (
    Command as SetupCommand,
)
from members.models import (
    Account,
    Branch,
    PersonRole,
    SchoolYear,
    Section,
    TroopSettings,
)
from members.presets import load_preset

from .base import TroopSettingsTestCase
from .mail import MailTestCase

STRONG_PASSWORD = "Vlinders-van-het-Woud-42"


class EmptyInstanceTestCase(TroopSettingsTestCase):
    """A database stripped back to what a troop starts from.

    ``migrate`` seeds the settings row, the school years and the email
    templates, so anything that wants to watch setup create them has to take
    them away first — which is also the state a genuinely empty database is in.
    """

    def setUp(self):
        super().setUp()
        Branch.objects.all().delete()
        SchoolYear.objects.all().delete()
        SiteContent.objects.all().delete()
        PeriodicTask.objects.all().delete()
        CrontabSchedule.objects.all().delete()
        EmailTemplate.objects.all().delete()
        TroopSettings.objects.all().delete()
        TroopSettings.clear_cache()


class FillSettingsTest(TroopSettingsTestCase):
    """Writing the troop's own settings, without treading on what is there."""

    def test_a_value_still_holding_its_default_is_filled(self):
        setup.fill_settings({"name": "Les Scouts de Limal", "currency": "CHF"})

        troop = TroopSettings.get_settings()
        self.assertEqual(troop.name_fr, "Les Scouts de Limal")
        self.assertEqual(troop.currency, "CHF")

    def test_a_value_somebody_chose_is_kept(self):
        """The whole point: setup is safe to run on an instance in use."""
        troop = TroopSettings.get_settings()
        troop.contact_email = "vrai@example.org"
        troop.save()

        step = setup.fill_settings({"contact_email": "autre@example.org"})

        self.assertEqual(TroopSettings.get_settings().contact_email, "vrai@example.org")
        self.assertIn("contact_email", step.kept)
        self.assertNotIn("contact_email", step.created)

    def test_a_translated_field_given_once_is_written_to_every_language(self):
        """So switching the site to Dutch shows the unit's name, not the default."""
        setup.fill_settings({"name": "Scouts de Limal"})

        troop = TroopSettings.get_settings()
        self.assertEqual(troop.name_fr, "Scouts de Limal")
        self.assertEqual(troop.name_nl, "Scouts de Limal")
        self.assertEqual(troop.name_en, "Scouts de Limal")

    def test_a_translated_field_can_name_its_languages(self):
        setup.fill_settings(
            {"site_description": {"fr": "En français", "nl": "In het Nederlands"}}
        )

        troop = TroopSettings.get_settings()
        self.assertEqual(troop.site_description_fr, "En français")
        self.assertEqual(troop.site_description_nl, "In het Nederlands")

    def test_a_translated_language_already_set_is_not_overwritten(self):
        troop = TroopSettings.get_settings()
        troop.name_nl = "Eigen naam"
        troop.save()

        setup.fill_settings({"name": "Scouts de Limal"})

        troop = TroopSettings.get_settings()
        self.assertEqual(troop.name_nl, "Eigen naam")
        self.assertEqual(troop.name_fr, "Scouts de Limal")

    def test_an_unknown_setting_is_refused(self):
        with self.assertRaises(setup.SetupError) as caught:
            setup.fill_settings({"colour": "blue"})
        self.assertIn("settings.colour", str(caught.exception))

    def test_an_upload_cannot_be_set_from_an_answers_file(self):
        with self.assertRaises(setup.SetupError) as caught:
            setup.fill_settings({"logo": "logo.png"})
        self.assertIn("settings.logo", str(caught.exception))

    def test_the_passage_marker_is_not_something_a_first_run_sets(self):
        with self.assertRaises(setup.SetupError):
            setup.fill_settings({"last_passage_school_year": 2026})

    def test_a_value_the_model_rejects_is_reported_against_its_field(self):
        with self.assertRaises(setup.SetupError) as caught:
            setup.fill_settings({"currency": "euros"})
        self.assertIn("settings.currency", str(caught.exception))

    def test_a_default_language_outside_the_enabled_ones_is_reported(self):
        with self.assertRaises(setup.SetupError) as caught:
            setup.fill_settings(
                {"enabled_languages": ["fr"], "default_language": "nl"}
            )
        self.assertIn("settings.default_language", str(caught.exception))

    def test_data_somebody_else_left_broken_does_not_block_the_run(self):
        """An unrelated field in a state validation would reject is not ours.

        Instances drift: a value the model's rules would refuse today can
        already be in the row. Setup fills what it was asked to fill, and does
        not turn somebody else's field into its own error.
        """
        TroopSettings.objects.filter(pk=1).update(facebook_url="not a url")
        TroopSettings.clear_cache()

        step = setup.fill_settings({"currency": "CHF"})

        self.assertIn("currency", step.created)
        self.assertEqual(TroopSettings.get_settings().currency, "CHF")

    def test_names_are_reported_by_field_not_by_value(self):
        step = setup.fill_settings({"contact_email": "info@example.org"})
        self.assertEqual(step.created, ["contact_email"])
        self.assertTrue(step.changed)


class SchoolYearTest(TroopSettingsTestCase):
    """The current school year and the next one."""

    def test_it_creates_the_year_today_falls_in_and_the_next(self):
        SchoolYear.objects.all().delete()

        step = setup.ensure_school_years(today=date(2026, 9, 26))

        self.assertEqual(sorted(step.created), ["2026", "2027"])
        year = SchoolYear.objects.get(name=2026)
        self.assertEqual((year.start_date, year.end_date), (date(2026, 8, 1), date(2027, 7, 31)))

    def test_it_follows_the_troop_s_own_year_boundary(self):
        """A troop whose year starts in January gets January's bounds."""
        SchoolYear.objects.all().delete()
        troop = TroopSettings.get_settings()
        troop.year_start_month, troop.year_start_day = 1, 1
        troop.save()

        setup.ensure_school_years(today=date(2026, 9, 26))

        self.assertEqual(SchoolYear.objects.get(name=2026).start_date, date(2026, 1, 1))

    def test_an_existing_year_is_left_alone(self):
        existing = SchoolYear.objects.order_by("name").first()

        step = setup.ensure_school_years()

        self.assertIn(str(existing.name), step.kept)
        self.assertEqual(
            SchoolYear.objects.get(name=existing.name).start_date, existing.start_date
        )

    def test_it_is_idempotent(self):
        SchoolYear.objects.all().delete()

        setup.ensure_school_years(today=date(2026, 9, 26))
        step = setup.ensure_school_years(today=date(2026, 9, 26))

        self.assertEqual(step.created, [])
        self.assertEqual(SchoolYear.objects.count(), 2)

    def test_the_nightly_task_runs_the_same_step(self):
        """The task and a first run cannot disagree about the year boundary."""
        SchoolYear.objects.all().delete()

        with mock.patch("members.tasks._today", return_value=date(2026, 9, 26)):
            from members.tasks import create_year_task

            create_year_task()

        self.assertEqual(sorted(SchoolYear.objects.values_list("name", flat=True)), [2026, 2027])


class PresetApplicationTest(EmptyInstanceTestCase):
    """Creating the ladder, and leaving alone whatever is already there."""

    def test_it_creates_the_branches_sections_and_links(self):
        step = setup.apply_preset()

        self.assertEqual(
            list(Branch.objects.order_by("min_age_dec_31").values_list("name", flat=True)),
            ["Baladins", "Louveteaux", "Éclaireurs", "Pionniers"],
        )
        baladins = Branch.objects.get(key="baladins")
        self.assertEqual(baladins.promotes_to.key, "louveteaux")
        self.assertTrue(Branch.objects.get(key="pionniers").is_top)
        self.assertEqual(Section.objects.count(), 4)
        self.assertEqual(Section.objects.get(branch=baladins).sex, Section.Sex.BOTH)
        self.assertTrue(step.created)

    def test_branches_are_named_in_every_language_the_preset_gives(self):
        setup.apply_preset()

        self.assertEqual(Branch.objects.get(key="louveteaux").name_nl, "Welpen")
        self.assertEqual(Branch.objects.get(key="louveteaux").name_fr, "Louveteaux")

    def test_it_is_idempotent(self):
        setup.apply_preset()

        before = self._shape()
        step = setup.apply_preset()

        self.assertEqual(step.created, [])
        self.assertEqual(Branch.objects.count(), 4)
        self.assertEqual(Section.objects.count(), 4)
        self.assertEqual(self._shape(), before)

    def _shape(self):
        """Every branch and section, with the links between them."""
        return (
            list(
                Branch.objects.order_by("pk").values_list(
                    "pk", "name_fr", "promotes_to_id", "is_top"
                )
            ),
            list(Section.objects.order_by("pk").values_list("pk", "name_fr", "branch_id")),
        )

    def test_a_branch_the_troop_renamed_is_recognised_by_its_key(self):
        """A rename is not a reason to add a second copy of the branch."""
        setup.apply_preset()
        branch = Branch.objects.get(key="baladins")
        branch.name_fr = "Les Baladins"
        branch.save()

        step = setup.apply_preset()

        self.assertEqual(step.created, [])
        self.assertEqual(Branch.objects.count(), 4)
        self.assertEqual(Branch.objects.get(key="baladins").name_fr, "Les Baladins")

    def test_a_branch_the_troop_reshaped_keeps_its_ages(self):
        setup.apply_preset()
        branch = Branch.objects.get(key="baladins")
        branch.min_age_dec_31, branch.max_age_dec_31 = 7, 9
        branch.save()

        setup.apply_preset()

        branch.refresh_from_db()
        self.assertEqual((branch.min_age_dec_31, branch.max_age_dec_31), (7, 9))

    def test_a_branch_that_has_no_ages_yet_gets_them(self):
        """A branch added by hand, or by an older version, is filled in."""
        Branch.objects.create(key="louveteaux", name_fr="Louveteaux", is_top=True)

        setup.apply_preset()

        self.assertEqual(Branch.objects.get(key="louveteaux").max_age_dec_31, 12)

    def test_a_ladder_link_the_troop_has_already_set_is_not_re_pointed(self):
        setup.apply_preset()
        baladins = Branch.objects.get(key="baladins")
        baladins.promotes_to = Branch.objects.get(key="pionniers")
        baladins.save()

        setup.apply_preset()

        baladins.refresh_from_db()
        self.assertEqual(baladins.promotes_to.key, "pionniers")

    def test_a_branch_the_troop_already_stocked_is_not_given_a_second_section(self):
        branch = Branch.objects.create(key="baladins", name_fr="Baladins", is_top=True)
        Section.objects.create(name_fr="Petit Bonheur", branch=branch)

        setup.apply_preset()

        self.assertEqual(Section.objects.filter(branch=branch).count(), 1)
        self.assertTrue(Section.objects.filter(name_fr="Petit Bonheur").exists())

    def test_a_preset_named_by_path_is_applied(self):
        preset = load_preset()
        step = setup.apply_preset(preset)
        self.assertEqual(len(step.created), 8)  # four branches, four sections

    def test_an_unusable_preset_is_reported_as_a_setup_problem(self):
        with self.assertRaises(setup.SetupError) as caught:
            setup.apply_preset("no-such-preset")
        self.assertIn("preset:", str(caught.exception))


class EmailTemplateTest(MailTestCase):
    """The shipped email copy, seeded rather than imposed."""

    def test_a_missing_template_is_written_in_every_language(self):
        EmailTemplate.objects.filter(name="new_child_parent").delete()

        step = setup.ensure_email_templates()

        self.assertCountEqual(
            step.created,
            ["new_child_parent/en", "new_child_parent/fr", "new_child_parent/nl"],
        )

    def test_a_template_the_troop_rewrote_is_kept(self):
        template = EmailTemplate.objects.get(name="new_child_parent", language="fr")
        template.content = "Notre propre texte."
        template.save()

        setup.ensure_email_templates()

        self.assertEqual(
            EmailTemplate.objects.get(name="new_child_parent", language="fr").content,
            "Notre propre texte.",
        )

    def test_a_template_still_holding_this_project_s_copy_is_replaced(self):
        """Rows seeded before the copy was generic name the old unit."""
        template = EmailTemplate.objects.get(name="new_child_parent", language="fr")
        template.content = "Scouts de Limal vous remercie."
        template.save()

        setup.ensure_email_templates()

        self.assertNotIn(
            "Scouts de Limal",
            EmailTemplate.objects.get(name="new_child_parent", language="fr").content,
        )

    def test_it_reports_what_was_already_there(self):
        step = setup.ensure_email_templates()

        self.assertEqual(step.created, [])
        self.assertEqual(len(step.kept), len(list(email_templates.rows())))


class SitePagesTest(EmptyInstanceTestCase):
    """Something for the homepage and the FAQ to show before anybody edits them."""

    def test_each_enabled_language_gets_a_page(self):
        troop = TroopSettings.get_settings()
        troop.enabled_languages = ["fr", "nl"]
        troop.save()

        step = setup.ensure_site_pages()

        self.assertCountEqual(
            step.created, ["home/fr", "home/nl", "faq/fr", "faq/nl"]
        )
        home = SiteContent.objects.get(page="home")
        self.assertIn("<div", home.html_fr)
        self.assertIn("<div", home.html_nl)

    def test_a_page_that_was_never_rendered_is_left_alone(self):
        SiteContent.objects.create(page="faq", html_fr="<p>Notre FAQ</p>")

        step = setup.ensure_site_pages()

        self.assertNotIn("faq/fr", step.created)
        self.assertEqual(
            SiteContent.objects.get(page="faq").html_fr, "<p>Notre FAQ</p>"
        )

    def test_it_is_idempotent(self):
        setup.ensure_site_pages()
        step = setup.ensure_site_pages()
        self.assertEqual(step.created, [])

    def test_a_language_enabled_later_gets_its_page_then(self):
        troop = TroopSettings.get_settings()
        troop.enabled_languages = ["fr"]
        troop.save()
        setup.ensure_site_pages()

        troop.enabled_languages = ["fr", "en"]
        troop.save()
        step = setup.ensure_site_pages()

        self.assertCountEqual(step.created, ["home/en", "faq/en"])


class PeriodicTasksTest(EmptyInstanceTestCase):
    """The schedule Celery beat reads out of the database."""

    def test_it_schedules_exactly_what_the_settings_declare(self):
        """One answer to "what runs when", not two that can drift apart."""
        step = setup.ensure_periodic_tasks()

        self.assertCountEqual(step.created, settings.CELERY_BEAT_SCHEDULE)
        for name, entry in settings.CELERY_BEAT_SCHEDULE.items():
            with self.subTest(name=name):
                row = PeriodicTask.objects.get(name=name)
                self.assertEqual(row.task, entry["task"])
                self.assertTrue(row.enabled)
                # The row holds each field as text, the crontab as whatever
                # `crontab(hour=3)` was given, so compare them as written.
                self.assertEqual(
                    row.crontab.minute, str(entry["schedule"]._orig_minute)
                )
                self.assertEqual(row.crontab.hour, str(entry["schedule"]._orig_hour))
                self.assertEqual(row.crontab.day_of_week, "*")
                self.assertEqual(row.crontab.month_of_year, "*")

    def test_the_schedule_carries_the_configured_timezone(self):
        setup.ensure_periodic_tasks()

        self.assertEqual(
            str(PeriodicTask.objects.get(task="run_passage").crontab.timezone),
            settings.TIME_ZONE,
        )

    def test_the_school_year_task_runs_daily_not_yearly(self):
        """Beat's catch-up is unreliable for yearly tasks; the task self-guards."""
        setup.ensure_periodic_tasks()

        row = PeriodicTask.objects.get(task="create_year_task").crontab
        self.assertEqual(row.month_of_year, "*")
        self.assertEqual(row.day_of_month, "*")

    def test_it_is_idempotent(self):
        setup.ensure_periodic_tasks()
        step = setup.ensure_periodic_tasks()

        self.assertEqual(step.created, [])
        self.assertEqual(PeriodicTask.objects.count(), len(settings.CELERY_BEAT_SCHEDULE))

    def test_a_task_already_scheduled_under_another_name_is_left_alone(self):
        """An instance that renamed the entry, or chose its own hour, keeps it."""
        schedule = CrontabSchedule.objects.create(
            minute="0", hour="1", day_of_month="*", month_of_year="*", day_of_week="*"
        )
        PeriodicTask.objects.create(
            name="our-passage", task="run_passage", crontab=schedule
        )

        step = setup.ensure_periodic_tasks()

        self.assertIn("run-passage-daily", step.kept)
        self.assertEqual(PeriodicTask.objects.filter(task="run_passage").count(), 1)
        row = PeriodicTask.objects.get(task="run_passage")
        self.assertEqual(row.name, "our-passage")
        self.assertEqual(row.crontab.hour, "1")

    def test_an_entry_added_by_the_troop_is_left_alone(self):
        schedule = CrontabSchedule.objects.create(
            minute="0", hour="6", day_of_month="*", month_of_year="*", day_of_week="*"
        )
        PeriodicTask.objects.create(
            name="our-own-task", task="messaging.tasks.cleanup_old_messages",
            crontab=schedule,
        )

        setup.ensure_periodic_tasks()

        self.assertTrue(
            PeriodicTask.objects.filter(name="our-own-task", enabled=True).exists()
        )


class AdminAccountTest(EmptyInstanceTestCase):
    """The first way into the instance."""

    def create(self, **overrides):
        arguments = {
            "email": "chef@example.org",
            "password": STRONG_PASSWORD,
            "first_name": "Ada",
            "last_name": "Chef",
        }
        arguments.update(overrides)
        return setup.ensure_admin_account(**arguments)

    def test_it_creates_a_leader_who_administers_the_unit(self):
        step = self.create()

        account = Account.objects.get(email="chef@example.org")
        self.assertTrue(account.is_staff)
        self.assertTrue(account.is_superuser)
        self.assertTrue(account.check_password(STRONG_PASSWORD))
        self.assertEqual(account.person.primary_role.short, permissions.ANIMATEUR)
        self.assertEqual(account.person.status, "a")
        self.assertTrue(
            PersonRole.objects.filter(
                person=account.person, role__short=permissions.ADMIN
            ).exists()
        )
        self.assertEqual(step.created, ["chef@example.org"])

    def test_the_address_is_verified_so_the_login_works(self):
        """ACCOUNT_EMAIL_VERIFICATION is mandatory; an unverified admin is stuck."""
        self.create()

        account = Account.objects.get(email="chef@example.org")
        address = account.emailaddress_set.get()
        self.assertTrue(address.verified)
        self.assertTrue(address.primary)

    def test_it_can_be_asked_for_a_staff_account_without_superuser(self):
        self.create(superuser=False)

        account = Account.objects.get(email="chef@example.org")
        self.assertTrue(account.is_staff)
        self.assertFalse(account.is_superuser)

    def test_it_takes_the_troop_s_default_language(self):
        troop = TroopSettings.get_settings()
        troop.default_language = "nl"
        troop.enabled_languages = ["nl"]
        troop.save()

        self.create()

        self.assertEqual(
            Account.objects.get(email="chef@example.org").preferred_language, "nl"
        )

    def test_an_address_that_already_has_an_account_is_left_alone(self):
        self.create()

        step = self.create(password="Another-Strong-One-9")

        self.assertEqual(step.created, [])
        self.assertEqual(step.kept, ["chef@example.org"])
        self.assertTrue(
            Account.objects.get(email="chef@example.org").check_password(
                STRONG_PASSWORD
            )
        )

    def test_a_weak_password_is_refused_with_the_reason(self):
        with self.assertRaises(setup.SetupError) as caught:
            self.create(password="password")
        self.assertIn("admin.password", str(caught.exception))
        self.assertFalse(Account.objects.exists())

    def test_no_password_creates_an_account_nobody_can_log_into(self):
        """Better than a weak one: the operator sets it with changepassword."""
        self.create(password="")

        self.assertFalse(
            Account.objects.get(email="chef@example.org").has_usable_password()
        )

    def test_a_missing_address_or_name_is_refused(self):
        for overrides, expected in (
            ({"email": ""}, "admin.email"),
            ({"first_name": ""}, "admin.first_name"),
            ({"last_name": ""}, "admin.last_name"),
        ):
            with self.subTest(**overrides):
                with self.assertRaises(setup.SetupError) as caught:
                    self.create(**overrides)
                self.assertIn(expected, str(caught.exception))

    def test_an_address_that_is_not_one_is_refused(self):
        with self.assertRaises(setup.SetupError) as caught:
            self.create(email="not an address")
        self.assertIn("admin.email", str(caught.exception))


class RunSetupTest(EmptyInstanceTestCase):
    """The run, all of it, in one transaction."""

    ANSWERS = {
        "settings": {
            "name": "Les Scouts de Limal",
            "contact_email": "info@example.org",
            "enabled_languages": ["fr", "nl"],
        },
        "admin": {
            "email": "chef@example.org",
            "password": STRONG_PASSWORD,
            "first_name": "Ada",
            "last_name": "Chef",
        },
    }

    def test_it_brings_an_empty_database_to_a_usable_state(self):
        steps = setup.run_setup(self.ANSWERS)

        self.assertEqual(
            [step.name for step in steps],
            [
                "settings",
                "preset",
                "school_years",
                "email_templates",
                "site_pages",
                "periodic_tasks",
                "admin",
            ],
        )
        troop = TroopSettings.get_settings()
        self.assertEqual(troop.name_fr, "Les Scouts de Limal")
        self.assertEqual(troop.contact_email, "info@example.org")
        self.assertEqual(Branch.objects.count(), 4)
        self.assertEqual(SchoolYear.objects.count(), 2)
        self.assertEqual(
            EmailTemplate.objects.count(), len(list(email_templates.rows()))
        )
        self.assertEqual(SiteContent.objects.count(), 2)
        self.assertEqual(
            PeriodicTask.objects.count(), len(settings.CELERY_BEAT_SCHEDULE)
        )
        self.assertTrue(Account.objects.filter(email="chef@example.org").exists())

    def test_a_second_run_changes_nothing(self):
        setup.run_setup(self.ANSWERS)
        before = (
            Branch.objects.count(),
            Section.objects.count(),
            SchoolYear.objects.count(),
            EmailTemplate.objects.count(),
            SiteContent.objects.count(),
            PeriodicTask.objects.count(),
            Account.objects.count(),
        )

        steps = setup.run_setup(self.ANSWERS)

        self.assertEqual(
            before,
            (
                Branch.objects.count(),
                Section.objects.count(),
                SchoolYear.objects.count(),
                EmailTemplate.objects.count(),
                SiteContent.objects.count(),
                PeriodicTask.objects.count(),
                Account.objects.count(),
            ),
        )
        self.assertFalse(any(step.changed for step in steps))

    def test_a_dry_run_writes_nothing(self):
        steps = setup.run_setup(self.ANSWERS, dry_run=True)

        self.assertTrue(any(step.changed for step in steps))
        self.assertEqual(Branch.objects.count(), 0)
        self.assertEqual(Section.objects.count(), 0)
        self.assertEqual(SchoolYear.objects.count(), 0)
        self.assertEqual(SiteContent.objects.count(), 0)
        self.assertEqual(PeriodicTask.objects.count(), 0)
        self.assertEqual(Account.objects.count(), 0)
        self.assertEqual(TroopSettings.get_settings().name_fr, "Scouts")

    def test_a_step_that_fails_leaves_nothing_behind(self):
        """A mistyped answer must not leave a half-provisioned instance."""
        answers = {
            **self.ANSWERS,
            "settings": {**self.ANSWERS["settings"], "currency": "euros"},
        }

        with self.assertRaises(setup.SetupError):
            setup.run_setup(answers)

        self.assertEqual(Branch.objects.count(), 0)
        self.assertEqual(Account.objects.count(), 0)
        self.assertEqual(TroopSettings.get_settings().name_fr, "Scouts")

    def test_a_step_can_be_switched_off(self):
        setup.run_setup({"steps": {"preset": False, "admin": False}})

        self.assertEqual(Branch.objects.count(), 0)
        self.assertEqual(Account.objects.count(), 0)
        self.assertTrue(SchoolYear.objects.exists())

    def test_asking_for_an_admin_without_an_address_says_what_to_do(self):
        steps = setup.run_setup({"steps": {"preset": False}})

        admin = next(step for step in steps if step.name == "admin")
        self.assertEqual(admin.created, [])
        self.assertIn("createsuperuser", admin.note)

    def test_unknown_answers_are_refused(self):
        with self.assertRaises(setup.SetupError) as caught:
            setup.run_setup({"colours": {"fees": "blue"}})
        self.assertIn("answers", str(caught.exception))

    def test_an_unknown_step_is_refused(self):
        with self.assertRaises(setup.SetupError) as caught:
            setup.run_setup({"steps": {"branches": False}})
        self.assertIn("steps", str(caught.exception))

    def test_the_preset_can_be_named_in_the_answers(self):
        setup.run_setup({"preset": "les-scouts", "steps": {"admin": False}})

        self.assertEqual(Branch.objects.count(), 4)

    def test_an_unusable_preset_stops_the_run(self):
        with self.assertRaises(setup.SetupError) as caught:
            setup.run_setup({"preset": "no-such-preset"})
        self.assertIn("preset", str(caught.exception))
        self.assertEqual(SchoolYear.objects.count(), 0)


class CommandTest(EmptyInstanceTestCase):
    """The command line around the steps."""

    def setUp(self):
        super().setUp()
        self.directory = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)

    def answers_file(self, data):
        path = self.directory / "answers.json"
        # The admin password that travels in `data` is STRONG_PASSWORD, a
        # literal declared in this module: writing it to a throwaway answers
        # file is the behaviour under test, not a secret put at rest.
        # codeql[py/clear-text-storage-sensitive-data]
        path.write_text(json.dumps(data), encoding="utf-8")
        return str(path)

    def run_setup_command(self, *args, **options):
        options.setdefault("noinput", True)
        return call_command("setup", *args, **options)

    def test_it_runs_with_every_answer_given_as_a_flag(self):
        self.run_setup_command(
            "--unit-name", "Les Scouts de Limal",
            "--contact-email", "info@example.org",
            "--languages", "fr,nl",
            "--year-start", "08-01",
            "--admin-email", "chef@example.org",
            "--admin-password", STRONG_PASSWORD,
            "--admin-first-name", "Ada",
            "--admin-last-name", "Chef",
        )

        troop = TroopSettings.get_settings()
        self.assertEqual(troop.name_fr, "Les Scouts de Limal")
        self.assertEqual(troop.enabled_languages, ["fr", "nl"])
        self.assertEqual(troop.year_start_month, 8)
        self.assertEqual(troop.year_start_day, 1)
        self.assertTrue(Account.objects.filter(email="chef@example.org").exists())

    def test_it_reads_an_answers_file(self):
        path = self.answers_file(
            {
                "settings": {"name": "Les Scouts de Limal", "currency": "CHF"},
                "preset": "les-scouts",
                "admin": {
                    "email": "chef@example.org",
                    "password": STRONG_PASSWORD,
                    "first_name": "Ada",
                    "last_name": "Chef",
                },
            }
        )

        self.run_setup_command("--answers", path)

        self.assertEqual(TroopSettings.get_settings().currency, "CHF")
        self.assertEqual(Branch.objects.count(), 4)

    def test_a_flag_beats_the_answers_file(self):
        path = self.answers_file({"settings": {"name": "From the file"}})

        self.run_setup_command(
            "--answers", path, "--unit-name", "From the flag", "--no-preset",
            "--no-admin", "--no-school-years", "--no-email-templates",
            "--no-site-pages", "--no-periodic-tasks",
        )

        self.assertEqual(TroopSettings.get_settings().name_fr, "From the flag")

    def test_a_step_can_be_skipped_from_the_command_line(self):
        self.run_setup_command(
            "--no-preset", "--no-admin", "--no-site-pages", "--no-periodic-tasks",
            "--no-email-templates", "--no-school-years",
        )

        self.assertEqual(Branch.objects.count(), 0)
        self.assertEqual(SchoolYear.objects.count(), 0)

    def capture(self, *args):
        """Run the command, and return what it printed."""
        stdout = StringIO()
        call_command("setup", *args, noinput=True, stdout=stdout)
        return stdout.getvalue()

    def test_dry_run_reports_but_writes_nothing(self):
        out = self.capture("--dry-run", "--unit-name", "Les Scouts de Limal")

        self.assertIn("Dry run", out)
        self.assertEqual(Branch.objects.count(), 0)

    def test_it_says_what_it_wrote(self):
        out = self.capture("--unit-name", "Les Scouts de Limal", "--no-admin")

        self.assertIn("settings", out)
        self.assertIn("Baladins", out)
        self.assertIn("school_years", out)

    def test_a_bad_answers_file_is_reported_with_its_line(self):
        path = self.directory / "broken.json"
        path.write_text("{ not json", encoding="utf-8")

        with self.assertRaises(CommandError) as caught:
            self.run_setup_command("--answers", str(path))
        self.assertIn("invalid JSON", str(caught.exception))

    def test_an_answers_file_that_cannot_be_read_is_reported(self):
        with self.assertRaises(CommandError) as caught:
            self.run_setup_command("--answers", "/nope/answers.json")
        self.assertIn("cannot be read", str(caught.exception))

    def test_a_language_this_build_does_not_ship_is_refused(self):
        with self.assertRaises(CommandError) as caught:
            self.run_setup_command("--languages", "fr,de")
        self.assertIn("de", str(caught.exception))

    def test_a_date_that_is_not_a_date_is_refused(self):
        with self.assertRaises(CommandError) as caught:
            self.run_setup_command("--year-start", "13-01")
        self.assertIn("--year-start", str(caught.exception))

    def test_a_date_that_is_not_shaped_like_one_is_refused(self):
        with self.assertRaises(CommandError) as caught:
            self.run_setup_command("--year-start", "August")
        self.assertIn("MM-DD", str(caught.exception))

    def test_a_setup_problem_is_reported_as_a_command_error(self):
        with self.assertRaises(CommandError) as caught:
            self.run_setup_command("--currency", "euros")
        self.assertIn("settings.currency", str(caught.exception))


class PromptTest(EmptyInstanceTestCase):
    """What happens when there is somebody at a terminal."""

    def at_a_terminal(self, replies=(), passwords=()):
        """Run the command with a person answering the questions."""
        patcher = mock.patch.object(SetupCommand, "_is_interactive", return_value=True)
        with patcher, mock.patch(
            "builtins.input", side_effect=list(replies)
        ), mock.patch("getpass.getpass", side_effect=list(passwords)):
            call_command(
                "setup",
                "--no-preset", "--no-school-years", "--no-email-templates",
                "--no-site-pages", "--no-periodic-tasks",
                noinput=False,
            )

    def test_the_prompts_fill_the_settings_and_the_admin(self):
        self.at_a_terminal(
            replies=[
                "Les Scouts de Limal",  # unit name
                "SV021",                # short name
                "info@example.org",     # contact email
                "fr,nl",                # languages
                "nl",                   # default language
                "chef@example.org",     # administrator email
                "Ada",                  # first name
                "Chef",                 # last name
            ],
            passwords=[STRONG_PASSWORD, STRONG_PASSWORD],
        )

        troop = TroopSettings.get_settings()
        self.assertEqual(troop.name_fr, "Les Scouts de Limal")
        self.assertEqual(troop.short_name, "SV021")
        self.assertEqual(troop.enabled_languages, ["fr", "nl"])
        self.assertEqual(troop.default_language, "nl")
        account = Account.objects.get(email="chef@example.org")
        self.assertTrue(account.check_password(STRONG_PASSWORD))

    def test_an_empty_answer_keeps_what_is_there(self):
        troop = TroopSettings.get_settings()
        troop.name_fr = "Déjà nommé"
        troop.save()

        self.at_a_terminal(replies=["", "", "", "", "", ""])

        self.assertEqual(TroopSettings.get_settings().name_fr, "Déjà nommé")
        self.assertFalse(Account.objects.exists())

    def test_a_mismatched_password_is_asked_for_again(self):
        self.at_a_terminal(
            replies=["", "", "", "", "", "chef@example.org", "", ""],
            passwords=["First-Password-1", "Second-Password-2", STRONG_PASSWORD, STRONG_PASSWORD],
        )

        self.assertTrue(
            Account.objects.get(email="chef@example.org").check_password(
                STRONG_PASSWORD
            )
        )

    def test_a_default_language_that_is_not_offered_is_corrected(self):
        """The model would refuse it, so the prompt does not let it through."""
        self.at_a_terminal(replies=["", "", "", "fr", "en", ""])

        self.assertEqual(TroopSettings.get_settings().default_language, "fr")

    def test_nothing_is_asked_when_the_answers_already_say_it(self):
        """Every question has an answer, so nobody is asked anything."""
        directory = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        path = directory / "answers.json"
        path.write_text(
            json.dumps(
                {
                    "settings": {
                        "name": "From the file",
                        "short_name": "FF",
                        "contact_email": "info@example.org",
                        "enabled_languages": ["fr"],
                        "default_language": "fr",
                    },
                    "steps": {"admin": False},
                }
            ),
            encoding="utf-8",
        )

        with mock.patch.object(
            SetupCommand, "_is_interactive", return_value=True
        ), mock.patch("builtins.input", side_effect=AssertionError("asked anyway")):
            call_command(
                "setup",
                "--answers", str(path),
                "--no-preset", "--no-school-years", "--no-email-templates",
                "--no-site-pages", "--no-periodic-tasks",
                noinput=False,
            )

        self.assertEqual(TroopSettings.get_settings().name_fr, "From the file")


class TheTablesMatchTheCodeTest(TroopSettingsTestCase):
    """The step tables name things that exist.

    Each of these is a list of names written down by hand — a flag, a page, a
    Celery task — and each of them fails silently when it drifts: a flag that
    names no field is a TypeError the first time somebody uses it, and a task
    nothing registers is beat dispatching into the void.
    """

    def test_every_settings_flag_names_a_setting_a_first_run_may_fill(self):
        answerable = setup.answerable_fields()
        for flag, field in SETTINGS_FLAGS.items():
            self.assertIn(field, answerable, flag)
        for flag, fields in DATE_FLAGS.items():
            for field in fields:
                self.assertIn(field, answerable, flag)

    def test_the_starter_pages_are_the_ones_the_editor_knows(self):
        from homepage.models import SiteContent
        from homepage.views import EDITOR_SEED_TEMPLATES

        self.assertEqual(
            {page.value for page in SiteContent.Page}, set(setup.PAGE_SNIPPETS)
        )
        for page in SiteContent.Page:
            self.assertEqual(
                setup.PAGE_SNIPPETS[page.value], EDITOR_SEED_TEMPLATES[page], page
            )

    def test_every_scheduled_task_is_registered_with_the_worker(self):
        """A name beat sends that the worker cannot resolve is a silent no-op.

        This is the check that would have caught `send_queued_mail`: beat sent
        it every five minutes and every worker answered "Received unregistered
        task of type 'send_queued_mail'". Tasks are registered by
        ``import_default_modules()`` — the call a worker and beat both make on
        startup — and not by finalizing the app on its own.
        """
        from troopconnect.celery import app

        app.loader.import_default_modules()
        registered = set(app.tasks)
        for name, entry in setup.periodic_task_schedule().items():
            with self.subTest(name=name):
                self.assertIn(entry["task"], registered)

    def test_the_schedule_does_not_run_one_task_twice(self):
        tasks = [entry["task"] for entry in setup.periodic_task_schedule().values()]
        self.assertEqual(len(tasks), len(set(tasks)))
