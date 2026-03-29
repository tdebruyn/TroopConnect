from datetime import timedelta

from django.test import TestCase, Client
from django.utils import timezone

from homepage.models import Event
from homepage.tasks import cleanup_old_events
from members.models import Section


class EventModelTest(TestCase):
    def test_str(self):
        event = Event(title="Camp d'été", date=timezone.now().date())
        self.assertIn("Camp d'été", str(event))

    def test_is_past_true(self):
        event = Event(title="Past", date=timezone.now().date() - timedelta(days=1))
        self.assertTrue(event.is_past)

    def test_is_past_false(self):
        event = Event(title="Future", date=timezone.now().date() + timedelta(days=1))
        self.assertFalse(event.is_past)

    def test_is_recent_past_true(self):
        event = Event(title="Recent", date=timezone.now().date() - timedelta(days=10))
        self.assertTrue(event.is_recent_past)

    def test_is_recent_past_false_future(self):
        event = Event(title="Future", date=timezone.now().date() + timedelta(days=1))
        self.assertFalse(event.is_recent_past)

    def test_is_recent_past_false_old(self):
        event = Event(title="Old", date=timezone.now().date() - timedelta(days=31))
        self.assertFalse(event.is_recent_past)

    def test_css_class_muted_for_recent_past(self):
        event = Event(title="Recent", date=timezone.now().date() - timedelta(days=5))
        self.assertEqual(event.css_class, "text-muted")

    def test_css_class_empty_for_future(self):
        event = Event(title="Future", date=timezone.now().date() + timedelta(days=5))
        self.assertEqual(event.css_class, "")

    def test_ordering(self):
        today = timezone.now().date()
        Event.objects.create(title="B", date=today + timedelta(days=2))
        Event.objects.create(title="A", date=today + timedelta(days=1))
        Event.objects.create(title="C", date=today + timedelta(days=1))
        events = list(Event.objects.all())
        dates = [e.date for e in events]
        self.assertEqual(dates, sorted(dates))
        # Same date: alphabetical by title
        same_date = [e for e in events if e.date == today + timedelta(days=1)]
        self.assertEqual([e.title for e in same_date], ["A", "C"])


class CleanupOldEventsTest(TestCase):
    def test_deletes_old_events(self):
        today = timezone.now().date()
        Event.objects.create(title="Old", date=today - timedelta(days=31))
        Event.objects.create(title="Recent", date=today - timedelta(days=10))
        Event.objects.create(title="Future", date=today + timedelta(days=5))
        deleted = cleanup_old_events()
        self.assertEqual(deleted, 1)
        self.assertEqual(Event.objects.count(), 2)
        self.assertFalse(Event.objects.filter(title="Old").exists())

    def test_no_deletions(self):
        today = timezone.now().date()
        Event.objects.create(title="Recent", date=today - timedelta(days=5))
        deleted = cleanup_old_events()
        self.assertEqual(deleted, 0)


class AgendaViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.today = timezone.now().date()

    def test_shows_future_events(self):
        Event.objects.create(title="Future event", date=self.today + timedelta(days=5))
        response = self.client.get("/agenda/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Future event")

    def test_shows_recent_past_events(self):
        Event.objects.create(title="Recent past", date=self.today - timedelta(days=10))
        response = self.client.get("/agenda/")
        self.assertContains(response, "Recent past")

    def test_hides_old_events(self):
        Event.objects.create(title="Very old", date=self.today - timedelta(days=31))
        response = self.client.get("/agenda/")
        self.assertNotContains(response, "Very old")

    def test_empty_state(self):
        response = self.client.get("/agenda/")
        self.assertContains(response, "Aucun événement")

    def test_events_ordered_by_date(self):
        Event.objects.create(title="Later", date=self.today + timedelta(days=10))
        Event.objects.create(title="Earlier", date=self.today + timedelta(days=2))
        response = self.client.get("/agenda/")
        content = response.content.decode()
        self.assertLess(content.index("Earlier"), content.index("Later"))

    def test_section_displayed(self):
        section = Section.objects.create(name="Louveteaux")
        Event.objects.create(title="Section event", date=self.today, section=section)
        response = self.client.get("/agenda/")
        self.assertContains(response, "Louveteaux")

    def test_past_event_has_muted_class(self):
        Event.objects.create(title="Past event", date=self.today - timedelta(days=5))
        response = self.client.get("/agenda/")
        self.assertContains(response, "text-muted")
