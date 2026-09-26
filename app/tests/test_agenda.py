"""The section agenda: who reads which section, and who may write to one.

The agenda replaced the old public homepage list, so what matters here are the
edges: a parent reaching their child's section, a child and an animateur
reaching their own, a leader reaching *only* the section they lead, and unit
admins reading every section without being able to change any of it.
"""

from datetime import time, timedelta
from urllib.parse import urlencode

from django.core.exceptions import ValidationError
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from members.models import (
    Account,
    Enrollment,
    ParentChild,
    Person,
    Role,
    SchoolYear,
    Section,
    SectionEvent,
)

from .base import TroopSettingsTestCase


def url(name, **params):
    """A named URL with query parameters, which is how these views are driven."""
    return f"{reverse(name)}?{urlencode(params)}"


class AgendaTestBase(TroopSettingsTestCase):
    """Two sections with a leader each, plus a parent, a child and staff.

    Every view here reads `TroopSettings` for the module switch, so the base
    clears the cached row rather than leaving this module's copy behind for the
    next test to find.
    """

    @classmethod
    def setUpTestData(cls):
        cls.year = SchoolYear.current()
        parent_role = Role.objects.get(short="p")
        animateur_role = Role.objects.get(short="a")
        child_role = Role.objects.get(short="e")

        cls.meute = Section.objects.create(name="Meute")
        cls.troupe = Section.objects.create(name="Troupe")

        cls.meute_leader = Person.objects.create(
            first_name="Lou",
            last_name="Meute",
            primary_role=animateur_role,
            status="a",
        )
        cls.troupe_leader = Person.objects.create(
            first_name="Theo",
            last_name="Troupe",
            primary_role=animateur_role,
            status="a",
        )
        cls.parent = Person.objects.create(
            first_name="Paul",
            last_name="Parent",
            primary_role=parent_role,
            status="a",
        )
        cls.child = Person.objects.create(
            first_name="Chloe",
            last_name="Child",
            primary_role=child_role,
            status="a",
        )
        cls.unit_admin = Person.objects.create(
            first_name="Ada",
            last_name="Responsable",
            primary_role=parent_role,
            status="a",
        )
        cls.unit_admin.roles.add(Role.objects.get(short="ar"))
        cls.staff = Person.objects.create(
            first_name="Sam",
            last_name="Staff",
            primary_role=parent_role,
            status="a",
        )
        cls.unrelated = Person.objects.create(
            first_name="Ursula",
            last_name="Unrelated",
            primary_role=parent_role,
            status="a",
        )

        ParentChild.objects.create(parent=cls.parent, child=cls.child)

        for person, section in (
            (cls.meute_leader, cls.meute),
            (cls.troupe_leader, cls.troupe),
            (cls.child, cls.meute),
        ):
            Enrollment.objects.create(user=person, section=section, school_year=cls.year)

        for person, email in (
            (cls.meute_leader, "meute@test.be"),
            (cls.troupe_leader, "troupe@test.be"),
            (cls.parent, "parent@test.be"),
            (cls.child, "child@test.be"),
            (cls.unit_admin, "unitadmin@test.be"),
            (cls.unrelated, "unrelated@test.be"),
        ):
            Account.objects.create_user(email=email, password="testpass", person=person)
        Account.objects.create_user(
            email="staff@test.be",
            password="testpass",
            person=cls.staff,
            is_staff=True,
        )

        cls.today = timezone.localdate()
        cls.meute_event = SectionEvent.objects.create(
            title="Reunion de meute",
            section=cls.meute,
            start_date=cls.today,
            start_time=time(14, 0),
            end_time=time(17, 0),
            description="Grand jeu dans les bois",
        )
        cls.weekend = SectionEvent.objects.create(
            title="Week-end troupe",
            section=cls.troupe,
            activity_type=SectionEvent.ActivityType.WEEKEND,
            start_date=cls.today + timedelta(days=2),
            end_date=cls.today + timedelta(days=3),
        )

    def setUp(self):
        self.client = Client()

    def login(self, email):
        self.assertTrue(self.client.login(email=email, password="testpass"))

    def month_of(self, day):
        return f"{day.year:04d}-{day.month:02d}"


class ActivityModelTest(AgendaTestBase):
    """The small pieces of formatting the templates lean on."""

    def test_a_range_needs_both_ends(self):
        self.assertEqual(SectionEvent(start_time=time(9, 0)).time_range, "09:00")
        self.assertEqual(
            SectionEvent(start_time=time(9, 0), end_time=time(12, 30)).time_range,
            "09:00 – 12:30",
        )

    def test_an_activity_without_times_says_nothing_about_them(self):
        """Entries created from a section message carry a date but no time."""
        self.assertEqual(SectionEvent().time_range, "")

    def test_identical_times_are_printed_once(self):
        self.assertEqual(
            SectionEvent(start_time=time(9, 0), end_time=time(9, 0)).time_range,
            "09:00",
        )

    def test_a_week_end_covers_both_of_its_days(self):
        self.assertTrue(self.weekend.is_multi_day)
        self.assertTrue(self.weekend.occurs_on(self.today + timedelta(days=2)))
        self.assertTrue(self.weekend.occurs_on(self.today + timedelta(days=3)))
        self.assertFalse(self.weekend.occurs_on(self.today + timedelta(days=1)))
        self.assertFalse(self.weekend.occurs_on(self.today + timedelta(days=4)))

    def test_a_one_day_activity_covers_only_its_date(self):
        self.assertFalse(self.meute_event.is_multi_day)
        self.assertEqual(self.meute_event.last_date, self.today)
        self.assertTrue(self.meute_event.occurs_on(self.today))
        self.assertFalse(self.meute_event.occurs_on(self.today + timedelta(days=1)))

    def test_every_activity_type_has_its_own_colour(self):
        colours = {
            self.meute_event.type_css_class,
            self.weekend.type_css_class,
            SectionEvent(
                activity_type=SectionEvent.ActivityType.JOURNEE
            ).type_css_class,
        }

        self.assertEqual(len(colours), 3)
        self.assertNotIn("", colours)

    def test_an_end_before_the_start_is_refused(self):
        event = SectionEvent(
            section=self.meute,
            start_date=self.today,
            end_date=self.today - timedelta(days=1),
        )

        with self.assertRaises(ValidationError) as caught:
            event.full_clean()

        # The site's default language is French, and the message is lazy.
        self.assertIn("date de fin ne peut pas précéder", str(caught.exception))

    def test_an_end_time_before_the_start_time_is_refused(self):
        event = SectionEvent(
            section=self.meute,
            start_date=self.today,
            start_time=time(17, 0),
            end_time=time(14, 0),
        )

        with self.assertRaises(ValidationError) as caught:
            event.full_clean()

        self.assertIn("heure de fin ne peut pas précéder", str(caught.exception))


class AgendaVisibilityTest(AgendaTestBase):
    """Who is offered which section."""

    def test_a_parent_sees_the_sections_of_their_children(self):
        self.login("parent@test.be")

        response = self.client.get(reverse("members:agenda"))

        self.assertContains(response, self.meute_event.title)
        self.assertNotContains(response, self.weekend.title)

    def test_a_child_sees_their_own_section(self):
        self.login("child@test.be")

        response = self.client.get(reverse("members:agenda"))

        self.assertContains(response, self.meute_event.title)

    def test_a_leader_sees_the_section_they_lead(self):
        self.login("meute@test.be")

        response = self.client.get(reverse("members:agenda"))

        self.assertContains(response, self.meute_event.title)
        self.assertNotContains(response, self.weekend.title)

    def test_an_outsider_cannot_open_another_section(self):
        """Asking for a section out of reach is answered like one that is not
        there, rather than by an empty calendar."""
        self.login("parent@test.be")

        response = self.client.get(url("members:agenda", section=self.troupe.pk))

        self.assertEqual(response.status_code, 404)

    def test_somebody_linked_to_no_section_is_told_so(self):
        self.login("unrelated@test.be")

        response = self.client.get(reverse("members:agenda"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "lié à aucune section cette année")

    def test_unit_admins_see_every_section(self):
        """An animateur responsable runs the unit, so "what is the Meute doing
        in October?" is a question they have to be able to answer."""
        self.login("unitadmin@test.be")

        response = self.client.get(
            url(
                "members:agenda",
                section=self.troupe.pk,
                month=self.month_of(self.weekend.start_date),
            )
        )

        self.assertContains(response, self.weekend.title)

    def test_staff_see_every_section(self):
        self.login("staff@test.be")

        response = self.client.get(
            url(
                "members:agenda",
                section=self.troupe.pk,
                month=self.month_of(self.weekend.start_date),
            )
        )

        self.assertContains(response, self.weekend.title)

    def test_the_page_names_the_section_being_shown(self):
        self.login("child@test.be")

        response = self.client.get(reverse("members:agenda"))

        self.assertContains(response, self.meute.name)
        self.assertNotContains(response, self.troupe.name)

    def test_a_staff_reader_may_switch_between_sections(self):
        self.login("staff@test.be")

        response = self.client.get(reverse("members:agenda"))

        self.assertContains(response, "Meute")
        self.assertContains(response, "Troupe")


class AgendaGridTest(AgendaTestBase):
    """What the month grid shows, and what it deliberately does not."""

    def test_the_grid_shows_the_title_and_the_time(self):
        self.login("child@test.be")

        response = self.client.get(reverse("members:agenda"))

        self.assertContains(response, self.meute_event.title)
        self.assertContains(response, "14:00 – 17:00")

    def test_the_grid_keeps_the_description_for_the_day_frame(self):
        """A parent scanning a month reads titles; the rest is one click away."""
        self.login("child@test.be")

        response = self.client.get(reverse("members:agenda"))

        self.assertNotContains(response, self.meute_event.description)

    def test_the_grid_colours_the_entry_by_activity_type(self):
        self.login("child@test.be")

        response = self.client.get(reverse("members:agenda"))

        self.assertContains(response, self.meute_event.type_css_class)

    def test_a_week_end_shows_on_every_day_it_covers(self):
        self.login("troupe@test.be")

        for day in (self.weekend.start_date, self.weekend.last_date):
            with self.subTest(day=day):
                response = self.client.get(
                    url("members:agenda_day", section=self.troupe.pk, date=day)
                )
                self.assertContains(response, self.weekend.title)

    def test_the_grid_follows_the_month_asked_for(self):
        """Two months on, the activity is behind us."""
        self.login("troupe@test.be")

        response = self.client.get(
            url(
                "members:agenda",
                section=self.troupe.pk,
                month=self.month_of(self.weekend.start_date + timedelta(days=60)),
            )
        )

        self.assertNotContains(response, self.weekend.title)

    def test_the_grid_carries_a_fresh_day_frame(self):
        """Paging months swaps the grid, and the day frame with it: a frame
        left over from the old month would describe a month no longer shown."""
        self.login("child@test.be")

        response = self.client.get(url("members:agenda_grid", section=self.meute.pk))

        self.assertContains(response, 'id="agenda-day"')
        self.assertContains(response, "Choisissez un jour")

    def test_the_grid_is_always_six_weeks(self):
        """A grid that changes height moves the month arrows under the cursor."""
        self.login("child@test.be")

        response = self.client.get(reverse("members:agenda"))

        self.assertEqual(len(response.context["weeks"]), 6)
        self.assertTrue(all(len(week) == 7 for week in response.context["weeks"]))
        # ...and the header names the seven days, from the first week's dates.
        self.assertEqual(response.content.decode().count('<th scope="col">'), 7)


class AgendaDayFrameTest(AgendaTestBase):
    """Clicking a day is what reveals an activity in full."""

    def day_url(self, day, section=None):
        return url(
            "members:agenda_day",
            section=section or self.meute.pk,
            date=day.isoformat(),
        )

    def test_the_frame_carries_the_description(self):
        self.login("child@test.be")

        response = self.client.get(self.day_url(self.today))

        self.assertContains(response, self.meute_event.description)

    def test_the_frame_names_the_type_of_activity(self):
        self.login("child@test.be")

        response = self.client.get(self.day_url(self.today))

        self.assertContains(response, "Réunion")

    def test_a_day_with_nothing_on_says_so(self):
        self.login("child@test.be")

        response = self.client.get(self.day_url(self.today + timedelta(days=30)))

        self.assertContains(response, "Rien de prévu")

    def test_a_leader_is_offered_the_edit_and_delete_controls(self):
        self.login("meute@test.be")

        response = self.client.get(self.day_url(self.today))

        self.assertContains(
            response, reverse("members:agenda_event_edit", args=[self.meute_event.pk])
        )

    def test_a_reader_who_does_not_lead_the_section_gets_no_controls(self):
        self.login("parent@test.be")

        response = self.client.get(self.day_url(self.today))

        self.assertNotContains(
            response, reverse("members:agenda_event_edit", args=[self.meute_event.pk])
        )


class AgendaTemplateSyntaxTest(AgendaTestBase):
    """None of these screens renders template syntax as text.

    ``{# … #}`` is a *single-line* comment in Django. Written across several
    lines it is not a comment at all: the grid showed its own explanatory notes
    to every reader. A plain string assertion is what catches that — the page
    renders fine either way.
    """

    def agenda_responses(self):
        return {
            "page": self.client.get(reverse("members:agenda")),
            "grid": self.client.get(url("members:agenda_grid", section=self.meute.pk)),
            "day": self.client.get(
                url(
                    "members:agenda_day",
                    section=self.meute.pk,
                    date=self.today.isoformat(),
                )
            ),
            "form": self.client.get(
                url("members:agenda_event_create", section=self.meute.pk)
            ),
        }

    def test_nothing_unrendered_reaches_the_reader(self):
        self.login("meute@test.be")

        for view, response in self.agenda_responses().items():
            with self.subTest(view=view):
                self.assertNotContains(response, "{#")
                self.assertNotContains(response, "{%")


class AgendaWritingTest(AgendaTestBase):
    """Only the leader of a section writes to its agenda."""

    def form_data(self, **overrides):
        data = {
            "activity_type": SectionEvent.ActivityType.REUNION,
            "title": "Sortie au parc",
            "description": "Prevoir des bottes",
            "start_date": self.today.isoformat(),
            "start_time": "10:00",
            "end_date": "",
            "end_time": "12:00",
        }
        data.update(overrides)
        return data

    def create_url(self, section):
        return url("members:agenda_event_create", section=section.pk)

    def test_a_leader_can_add_an_activity_to_their_section(self):
        self.login("meute@test.be")

        response = self.client.post(self.create_url(self.meute), self.form_data())

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            SectionEvent.objects.filter(
                title="Sortie au parc", section=self.meute
            ).exists()
        )

    def test_a_leader_of_two_sections_writes_to_the_one_they_opened(self):
        """The section travels in the form body, so the entry cannot be filed
        under whichever section happens to sort first."""
        Enrollment.objects.create(
            user=self.meute_leader, section=self.troupe, school_year=self.year
        )
        self.login("meute@test.be")

        response = self.client.post(
            reverse("members:agenda_event_create"),
            self.form_data(section=str(self.troupe.pk)),
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            SectionEvent.objects.filter(
                title="Sortie au parc", section=self.troupe
            ).exists()
        )

    def test_a_leader_can_edit_an_activity_of_their_section(self):
        self.login("meute@test.be")

        response = self.client.post(
            reverse("members:agenda_event_edit", args=[self.meute_event.pk]),
            self.form_data(title="Reunion reportee"),
        )

        self.assertEqual(response.status_code, 302)
        self.meute_event.refresh_from_db()
        self.assertEqual(self.meute_event.title, "Reunion reportee")

    def test_a_leader_can_delete_an_activity_of_their_section(self):
        self.login("meute@test.be")

        response = self.client.post(
            reverse("members:agenda_event_delete", args=[self.meute_event.pk])
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(SectionEvent.objects.filter(pk=self.meute_event.pk).exists())

    def test_a_leader_cannot_write_to_another_section(self):
        self.login("meute@test.be")

        self.assertEqual(self.client.get(self.create_url(self.troupe)).status_code, 404)
        self.assertEqual(
            self.client.post(self.create_url(self.troupe), self.form_data()).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(
                reverse("members:agenda_event_edit", args=[self.weekend.pk])
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                reverse("members:agenda_event_delete", args=[self.weekend.pk])
            ).status_code,
            404,
        )
        self.assertTrue(SectionEvent.objects.filter(pk=self.weekend.pk).exists())

    def test_unit_admins_read_but_do_not_write(self):
        """They see every section, and change none of them: the agenda belongs
        to the section that keeps it."""
        self.login("unitadmin@test.be")

        self.assertEqual(self.client.get(self.create_url(self.meute)).status_code, 404)
        self.assertEqual(
            self.client.get(
                reverse("members:agenda_event_edit", args=[self.meute_event.pk])
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                reverse("members:agenda_event_delete", args=[self.meute_event.pk])
            ).status_code,
            404,
        )
        self.assertTrue(SectionEvent.objects.filter(pk=self.meute_event.pk).exists())

    def test_staff_read_but_do_not_write(self):
        self.login("staff@test.be")

        self.assertEqual(self.client.get(self.create_url(self.meute)).status_code, 404)
        self.assertEqual(
            self.client.get(
                reverse("members:agenda_event_edit", args=[self.meute_event.pk])
            ).status_code,
            404,
        )

    def test_a_parent_cannot_write(self):
        self.login("parent@test.be")

        self.assertEqual(self.client.get(self.create_url(self.meute)).status_code, 404)

    def test_the_form_refuses_an_end_before_the_start(self):
        self.login("meute@test.be")

        response = self.client.post(
            self.create_url(self.meute),
            self.form_data(end_date=(self.today - timedelta(days=1)).isoformat()),
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(SectionEvent.objects.filter(title="Sortie au parc").exists())

    def test_a_new_activity_can_be_prefilled_from_the_day_frame(self):
        self.login("meute@test.be")

        response = self.client.get(
            url(
                "members:agenda_event_create",
                section=self.meute.pk,
                date=self.today.isoformat(),
            )
        )

        self.assertContains(response, f'value="{self.today.isoformat()}"')

    def test_deleting_is_not_reachable_by_get(self):
        """The agenda's state changes on POST only."""
        self.login("meute@test.be")

        response = self.client.get(
            reverse("members:agenda_event_delete", args=[self.meute_event.pk])
        )

        self.assertEqual(response.status_code, 405)
        self.assertTrue(SectionEvent.objects.filter(pk=self.meute_event.pk).exists())
