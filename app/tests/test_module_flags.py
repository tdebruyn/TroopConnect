"""The three module switches, enforced end to end.

`fees_enabled`, `signing_enabled` and `public_agenda_enabled` used to be
navigation switches: turning one off hid the menu entry and left the URLs
answering, so a troop that does not use membership fees still served /finance/
to anyone holding the treasurer role. These tests pin the whole switch — the
URLs 404, the UI disappears, and what the module stores is left alone — and,
just as importantly, that a module which is *on* is unaffected.

The switch itself is one helper (`members.modules.module_enabled`), reached
from views through `requires_module` / `ModuleRequiredMixin` and from templates
through `{% module_enabled %}`.
"""

from django.template import Context, Template
from django.urls import reverse
from django.utils import timezone

from attestations.models import AttestationCampaign
from homepage.models import Event
from members import modules
from members.forms import AdminUserUpdateForm
from members.models import Account, Person, PersonRole, Role, TroopSettings
from members.permissions import TRESORIER

from .base import TroopSettingsTestCase


class ModuleTestBase(TroopSettingsTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.parent_role = Role.objects.get(short="p")
        cls.treasurer_role = Role.objects.get(short=TRESORIER)
        cls.staff_person = Person.objects.create(
            first_name="Ada",
            last_name="Staff",
            primary_role=cls.parent_role,
            status="a",
        )
        Account.objects.create_user(
            email="staff@test.be",
            password="testpass",
            person=cls.staff_person,
            is_staff=True,
        )

    def setUp(self):
        super().setUp()
        self.login_staff()

    def login_staff(self):
        self.assertTrue(self.client.login(email="staff@test.be", password="testpass"))

    def set_flags(self, **fields):
        """Flip module switches, returning the reloaded settings row."""
        troop = TroopSettings.get_settings()
        for name, value in fields.items():
            setattr(troop, name, value)
        troop.save(update_fields=list(fields))
        return TroopSettings.get_settings()

    def member(self, **kwargs):
        fields = {
            "first_name": "Mem",
            "last_name": "Ber",
            "primary_role": self.parent_role,
            "status": "a",
        }
        fields.update(kwargs)
        return Person.objects.create(**fields)


class FeesModuleTest(ModuleTestBase):
    """fees_enabled=False closes the membership-fees module."""

    def finance_urls(self):
        return [
            ("finance:billing", []),
            ("finance:prices", []),
            ("finance:record_payment", []),
            ("finance:reminders", []),
            ("finance:payment_history", [self.member().pk]),
        ]

    def test_every_url_is_closed_when_the_module_is_off(self):
        self.set_flags(fees_enabled=False)

        for name, args in self.finance_urls():
            with self.subTest(url=name):
                self.assertEqual(
                    self.client.get(reverse(name, args=args)).status_code, 404
                )

    def test_the_module_still_works_when_it_is_on(self):
        """The 404s above are the flag talking, not a broken view."""
        self.assertEqual(self.client.get(reverse("finance:billing")).status_code, 200)

    def test_the_nav_entry_follows_the_module(self):
        billing = reverse("finance:billing")
        self.assertContains(self.client.get(reverse("homepage")), billing)

        self.set_flags(fees_enabled=False)

        self.assertNotContains(self.client.get(reverse("homepage")), billing)

    def test_the_treasurer_role_is_not_offered(self):
        """The role grants nothing with no finance screens, so it is hidden."""
        member = self.member()
        self.assertIn(
            TRESORIER,
            [role.short for role in AdminUserUpdateForm(instance=member)
             .fields["secondary_roles"].queryset],
        )

        self.set_flags(fees_enabled=False)

        self.assertNotIn(
            TRESORIER,
            [role.short for role in AdminUserUpdateForm(instance=member)
             .fields["secondary_roles"].queryset],
        )

    def form_data(self, member):
        return {
            "first_name": member.first_name,
            "last_name": member.last_name,
            "primary_role": self.parent_role.pk,
            "birthday": "1980-01-01",
            "email": "",
        }

    def test_an_existing_treasurer_keeps_the_role_when_the_module_is_off(self):
        """Hiding the checkbox must not quietly delete the assignment: the
        form no longer offers the role, so it cannot be said to have been
        un-ticked."""
        member = self.member()
        PersonRole.objects.create(person=member, role=self.treasurer_role)
        self.set_flags(fees_enabled=False)

        form = AdminUserUpdateForm(instance=member, data=self.form_data(member))
        self.assertTrue(form.is_valid(), form.errors)
        form.save()

        self.assertTrue(
            PersonRole.objects.filter(person=member, role=self.treasurer_role).exists()
        )

    def test_an_un_ticked_treasurer_loses_the_role_when_the_module_is_on(self):
        """With the module on the checkbox is on screen, so leaving it empty
        does mean "not a treasurer" — the contrast that gives the test above
        its meaning."""
        member = self.member()
        PersonRole.objects.create(person=member, role=self.treasurer_role)

        form = AdminUserUpdateForm(instance=member, data=self.form_data(member))
        self.assertTrue(form.is_valid(), form.errors)
        form.save()

        self.assertFalse(
            PersonRole.objects.filter(person=member, role=self.treasurer_role).exists()
        )


class FeesModuleAdminTest(ModuleTestBase):
    """The fee count on the purge warning goes with the module.

    Its own class because the purge page is reserved for superusers and unit
    admins, while the rest of these tests only need staff.
    """

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.root_person = Person.objects.create(
            first_name="Root",
            last_name="User",
            primary_role=Role.objects.get(short="p"),
            status="a",
        )
        Account.objects.create_user(
            email="root@test.be",
            password="testpass",
            person=cls.root_person,
            is_staff=True,
            is_superuser=True,
        )

    def test_the_payments_row_follows_the_module(self):
        member = self.member(status="ar")
        self.client.logout()
        self.assertTrue(self.client.login(email="root@test.be", password="testpass"))
        url = reverse("members:member_purge", kwargs={"pk": member.pk})

        # The row's label, in the site's default language: the language
        # middleware activates it for the request whatever the test asks for.
        self.assertContains(self.client.get(url), "Paiements")

        self.set_flags(fees_enabled=False)

        self.assertNotContains(self.client.get(url), "Paiements")


class SigningModuleTest(ModuleTestBase):
    """signing_enabled=False closes the attestation wizard."""

    def campaign(self):
        return AttestationCampaign.objects.create(
            title="Attestations",
            created_by=self.staff_person,
            page_range_start=1,
            page_range_end=1,
            name_page=1,
        )

    def test_every_step_is_closed_when_the_module_is_off(self):
        campaign = self.campaign()
        self.set_flags(signing_enabled=False)
        urls = [
            ("attestations:index", []),
            ("attestations:create", []),
            ("attestations:step1", [campaign.pk]),
            ("attestations:step2", [campaign.pk]),
            ("attestations:step3", [campaign.pk]),
            ("attestations:step4", [campaign.pk]),
            ("attestations:review", [campaign.pk]),
            ("attestations:send", [campaign.pk]),
            ("attestations:accept_suggestion", [campaign.pk, 1]),
            ("attestations:dismiss_suggestion", [campaign.pk, 1]),
        ]

        for name, args in urls:
            with self.subTest(url=name):
                self.assertEqual(
                    self.client.get(reverse(name, args=args)).status_code, 404
                )

    def test_the_wizard_still_opens_when_the_module_is_on(self):
        campaign = self.campaign()

        self.assertEqual(self.client.get(reverse("attestations:index")).status_code, 200)
        self.assertEqual(
            self.client.get(reverse("attestations:step1", args=[campaign.pk])).status_code,
            200,
        )

    def test_the_gate_runs_before_the_view_body(self):
        """A POST-only route answers 405 when the module is on and 404 when it
        is off, which is only true if the switch is checked first."""
        campaign = self.campaign()
        url = reverse("attestations:accept_suggestion", args=[campaign.pk, 1])

        self.assertEqual(self.client.get(url).status_code, 405)

        self.set_flags(signing_enabled=False)

        self.assertEqual(self.client.get(url).status_code, 404)

    def test_the_nav_entry_follows_the_module(self):
        index = reverse("attestations:index")
        self.assertContains(self.client.get(reverse("homepage")), index)

        self.set_flags(signing_enabled=False)

        self.assertNotContains(self.client.get(reverse("homepage")), index)


class PublicAgendaModuleTest(ModuleTestBase):
    """public_agenda_enabled=False hides the agenda and keeps its events."""

    def setUp(self):
        super().setUp()
        self.event = Event.objects.create(title="Grand camp", date=timezone.now().date())
        # The agenda is public: these tests are about the flag, not about roles.
        self.client.logout()

    def test_the_agenda_is_hidden_when_the_module_is_off(self):
        self.set_flags(public_agenda_enabled=False)

        self.assertEqual(self.client.get(reverse("agenda")).status_code, 404)

    def test_the_agenda_is_public_when_the_module_is_on(self):
        response = self.client.get(reverse("agenda"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Grand camp")

    def test_the_events_are_kept_and_come_back(self):
        self.set_flags(public_agenda_enabled=False)
        self.assertEqual(self.client.get(reverse("agenda")).status_code, 404)

        self.assertTrue(Event.objects.filter(pk=self.event.pk).exists())

        self.set_flags(public_agenda_enabled=True)

        self.assertContains(self.client.get(reverse("agenda")), "Grand camp")

    def test_the_nav_entry_follows_the_module(self):
        self.login_staff()
        agenda = reverse("agenda")
        self.assertContains(self.client.get(reverse("homepage")), agenda)

        self.set_flags(public_agenda_enabled=False)

        self.assertNotContains(self.client.get(reverse("homepage")), agenda)


class ModuleTemplateTagTest(ModuleTestBase):
    """Templates ask through the tag, so they cannot disagree with the views."""

    TEMPLATE = Template(
        "{% load modules %}{% module_enabled 'fees' as on %}{% if on %}on{% else %}off{% endif %}"
    )

    def render(self):
        return self.TEMPLATE.render(Context({}))

    def test_the_tag_follows_the_switch(self):
        self.assertEqual(self.render(), "on")

        self.set_flags(fees_enabled=False)

        self.assertEqual(self.render(), "off")

    def test_an_unknown_module_is_a_loud_error(self):
        with self.assertRaises(ValueError):
            modules.module_enabled("membership-fees")


class ModuleSwitchReachabilityTest(ModuleTestBase):
    """What must stay open when a module is switched off."""

    def test_the_settings_page_still_renders(self):
        """Otherwise a troop could switch a module off and never back on."""
        self.set_flags(
            fees_enabled=False,
            signing_enabled=False,
            public_agenda_enabled=False,
        )

        response = self.client.get(reverse("members:troop_settings"))

        self.assertEqual(response.status_code, 200)
        for field in ("fees_enabled", "signing_enabled", "public_agenda_enabled"):
            with self.subTest(field=field):
                self.assertContains(response, f'name="{field}"')

    def test_an_anonymous_visitor_is_sent_to_the_login_page(self):
        """The gate sits below @login_required, so a stranger learns nothing
        about which modules the troop uses."""
        self.set_flags(fees_enabled=False)
        self.client.logout()

        response = self.client.get(reverse("finance:billing"))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("account_login"), response["Location"])


class ModuleFlagDefaultsTest(ModuleTestBase):
    """Every module ships switched on."""

    def test_the_flags_default_to_on(self):
        troop = TroopSettings.get_settings()

        self.assertTrue(troop.fees_enabled)
        self.assertTrue(troop.signing_enabled)
        self.assertTrue(troop.public_agenda_enabled)

    def test_the_helper_agrees_with_the_model(self):
        for name, field in modules.MODULE_FIELDS.items():
            with self.subTest(module=name):
                self.assertEqual(
                    modules.module_enabled(name),
                    getattr(TroopSettings.get_settings(), field),
                )
