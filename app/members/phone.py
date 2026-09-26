"""Phone numbers, parsed and displayed in the troop's own region.

``django-phonenumber-field`` takes the region once, when the field is built, and
Django builds a ``ModelForm``'s fields when the *class* is defined — which for
this project happens while the admin is being autodiscovered, before the troop's
settings row is necessarily readable. Reading ``TroopSettings.phone_region``
straight from the field would therefore either query the database during app
initialisation (Django warns about exactly that, and a first boot runs system
checks before ``migrate`` has created the table) or freeze whatever the region
happened to be at import time.

So the region is resolved lazily instead: the model field, the form field and the
widget each read it at the moment they parse or render a number, which is always
after the apps are loaded and the row exists.
"""

from django.apps import apps
from django.db import OperationalError, ProgrammingError
from phonenumber_field import formfields, widgets
from phonenumber_field.modelfields import PhoneNumberField


def troop_region():
    """The troop's phone region, or ``None`` when it cannot be read yet.

    ``None`` means "expect the number to carry its own country code", which is
    what the library does when no region is configured — the right answer while
    the settings table does not exist (a first boot checks the system before
    running ``migrate``) or the database is unreachable.

    A misspelled region is rejected where it is entered:
    ``members.models.validate_phone_region`` runs on the settings form.
    """
    if not apps.ready:
        # Still importing models and admin: nothing is parsing a number yet.
        return None

    from .models import TroopSettings

    try:
        return TroopSettings.get_settings().phone_region
    except (ProgrammingError, OperationalError):
        return None


class TroopRegionalPhoneWidget(widgets.RegionalPhoneNumberWidget):
    """Displays a number in the troop's region, resolved when it is rendered."""

    @property
    def region(self):
        return self._region or troop_region()

    @region.setter
    def region(self, value):
        self._region = value


class TroopPhoneNumberFormField(formfields.PhoneNumberField):
    """Parses a number in the troop's region, resolved when it is cleaned."""

    widget = TroopRegionalPhoneWidget

    @property
    def region(self):
        return self._region or troop_region()

    @region.setter
    def region(self, value):
        self._region = value


class TroopPhoneNumberField(PhoneNumberField):
    """The model field: reads and writes numbers in the troop's region.

    Stored values are unaffected — ``PHONENUMBER_DB_FORMAT`` is E.164, so the
    column holds an international number either way. The region only decides how
    a locally-written one ("0475 12 34 56") is read, and how it is shown back.
    """

    @property
    def region(self):
        return troop_region()

    def formfield(self, **kwargs):
        kwargs.setdefault("form_class", TroopPhoneNumberFormField)
        return super().formfield(**kwargs)

    def _check_region(self):
        """Leave the region check to the settings form.

        The library's own check reads ``self.region``, which here is a database
        query from inside ``manage.py check`` — needless, since the region is
        validated by ``validate_phone_region`` where the troop sets it.
        """
        return []
