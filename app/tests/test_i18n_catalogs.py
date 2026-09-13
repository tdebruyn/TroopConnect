"""Guard that newly added user-facing strings ship translated.

The project requires every user-facing string in French *and* Dutch. Nothing
fails when a catalog entry is missing — gettext silently falls back to the
English source — so a missing translation is invisible until someone reads the
French UI. These strings were introduced with the child-lifecycle and reminder
fixes; each must resolve to something other than its English source in both
target languages.
"""

from django.test import SimpleTestCase
from django.utils import translation
from django.utils.translation import gettext

# (source string, fragment expected in the French, fragment expected in Dutch)
NEW_STRINGS = [
    ("%(count)s reminder(s) could not be sent.", "rappel", "herinnering"),
    ("%(first)s will not be re-enrolled next year.", "réinscrit", "opnieuw"),
    ("%(first)s has been deregistered.", "désinscrit", "uitgeschreven"),
    (
        "%(first)s has been deregistered. The registration team has been "
        "notified to complete the current-year procedure.",
        "inscriptions",
        "inschrijvingsteam",
    ),
    ("No child matches that key.", "clé", "sleutel"),
]


class NewStringTranslationTest(SimpleTestCase):
    def test_translated_in_french(self):
        with translation.override("fr"):
            for source, fragment, _nl in NEW_STRINGS:
                with self.subTest(source=source):
                    translated = gettext(source)
                    self.assertNotEqual(
                        translated, source, f"no French translation for {source!r}"
                    )
                    self.assertIn(fragment, translated)

    def test_translated_in_dutch(self):
        with translation.override("nl"):
            for source, _fr, fragment in NEW_STRINGS:
                with self.subTest(source=source):
                    translated = gettext(source)
                    self.assertNotEqual(
                        translated, source, f"no Dutch translation for {source!r}"
                    )
                    self.assertIn(fragment, translated)

    def test_gettext_falls_back_to_the_english_source(self):
        """Sanity check that the assertions above can actually fail."""
        with translation.override("en"):
            self.assertEqual(gettext(NEW_STRINGS[0][0]), NEW_STRINGS[0][0])
