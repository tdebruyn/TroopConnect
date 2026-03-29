from django.test import TestCase, RequestFactory

from members.models import Branch, Section
from members.context_processors import nav_sections
from post_office.models import EmailTemplate


class NavSectionsContextProcessorTest(TestCase):
    """Test that nav_sections context processor returns sections."""

    @classmethod
    def setUpTestData(cls):
        EmailTemplate.objects.create(
            name="new_child_staff", subject="Test", content="Test",
        )
        cls.branch = Branch.objects.create(
            name="Baladins", min_age_dec_31=6, max_age_dec_31=8,
        )
        cls.section = Section.objects.create(name="Baladins 1", branch=cls.branch)

    def test_returns_sections(self):
        factory = RequestFactory()
        request = factory.get("/")
        context = nav_sections(request)
        self.assertIn("nav_sections", context)
        self.assertEqual(list(context["nav_sections"]), [self.section])

    def test_empty_sections(self):
        Section.objects.all().delete()
        factory = RequestFactory()
        request = factory.get("/")
        context = nav_sections(request)
        self.assertEqual(list(context["nav_sections"]), [])

    def test_sections_ordered_by_branch_and_name(self):
        branch2 = Branch.objects.create(
            name="Baladins", min_age_dec_31=6, max_age_dec_31=8,
        )
        # Create a second branch with a different name to test ordering
        branch3 = Branch.objects.create(
            name="Loups", min_age_dec_31=9, max_age_dec_31=11,
        )
        s1 = Section.objects.create(name="Loups 1", branch=branch3)
        factory = RequestFactory()
        request = factory.get("/")
        context = nav_sections(request)
        names = [s.name for s in context["nav_sections"]]
        # Loups (branch3) comes after Baladins alphabetically
        self.assertEqual(names[0], "Baladins 1")
        self.assertEqual(names[-1], "Loups 1")
