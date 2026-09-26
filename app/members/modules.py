"""The troop's module switches, in one place.

`TroopSettings` carries three flags that turn a whole feature off: membership
fees, document signing and the public agenda. A flag is more than a navigation
switch — when a troop says it does not use a module, its URLs answer 404 and
the UI that belongs to it disappears, so the feature reads as not installed.
What the module *stores* is never touched, so turning the flag back on
restores everything.

One implementation, three surfaces:

* :func:`requires_module` (and :class:`ModuleRequiredMixin` for class-based
  views) for views,
* ``{% module_enabled "fees" as fees_on %}`` for templates, from
  ``members/templatetags/modules.py``,
* ``members.context_processors.contact_info``, which exposes the same three
  booleans as context variables for templates that prefer a variable.

The settings page and the Django admin are deliberately **not** gated: a troop
that switches a module off has to be able to switch it back on.
"""

from functools import wraps

from django.http import Http404
from django.utils.translation import gettext_lazy as _

#: Module keys, used by the decorator, the template tag and the tests.
FEES = "fees"
SIGNING = "signing"
AGENDA = "agenda"

#: The `TroopSettings` field each module is switched by.
MODULE_FIELDS = {
    FEES: "fees_enabled",
    SIGNING: "signing_enabled",
    AGENDA: "public_agenda_enabled",
}

#: How each module is named to a human, in the 404 and in the admin.
MODULE_LABELS = {
    FEES: _("membership fees"),
    SIGNING: _("document signing"),
    AGENDA: _("the public agenda"),
}


def module_enabled(name):
    """True when the troop has this module switched on.

    An unknown name raises rather than answering False: a typo in a decorator
    or a template should fail loudly, not quietly hide a working feature.
    """
    from .models import TroopSettings

    try:
        field = MODULE_FIELDS[name]
    except KeyError:
        raise ValueError(
            f"Unknown module {name!r}; expected one of {sorted(MODULE_FIELDS)}."
        ) from None
    return bool(getattr(TroopSettings.get_settings(), field))


def _off(name):
    """The 404 a switched-off module answers with."""
    return Http404(
        _("The %(module)s module is not in use by this troop.")
        % {"module": MODULE_LABELS[name]}
    )


def requires_module(name):
    """View decorator: answer 404 while the module is switched off.

    Put it *below* ``@login_required`` so an anonymous visitor is sent to the
    login page rather than told anything about the troop's configuration::

        @login_required
        @requires_module(FEES)
        def billing_overview(request):
            ...
    """

    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if not module_enabled(name):
                raise _off(name)
            return view(request, *args, **kwargs)

        return wrapper

    return decorator


class ModuleRequiredMixin:
    """The same gate for a class-based view.

    ``required_module`` is mandatory: a subclass that forgets it would be a
    view that looks gated and is not, so it raises instead::

        class Agenda(ModuleRequiredMixin, TemplateView):
            required_module = AGENDA
    """

    required_module = None

    def dispatch(self, request, *args, **kwargs):
        if self.required_module is None:
            raise ValueError(
                f"{type(self).__name__} inherits ModuleRequiredMixin but sets "
                "no required_module."
            )
        if not module_enabled(self.required_module):
            raise _off(self.required_module)
        return super().dispatch(request, *args, **kwargs)
