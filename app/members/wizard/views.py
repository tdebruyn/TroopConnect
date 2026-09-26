"""The wizard's HTTP surface.

One view walks the steps, one view serves the structure editor's buttons, and
between them they hold the three rules that make the wizard a wizard:

* it answers only while the instance still needs setting up, and 404s
  afterwards (see :func:`members.wizard.setup_required`);
* nothing past the setup code is reachable before the code has been entered,
  and the code itself is rate-limited;
* every page is a page you can land on. A step posts back the *next* step, so
  the browser's address bar follows along through ``HX-Push-Url``, and a
  reload, a bookmark or a Back button all resolve to something that renders.
"""

from django.http import Http404, HttpResponse
from django.shortcuts import redirect
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views import View

from members.models import TroopSettings
from members.permissions import is_htmx

from . import (
    attempts_left,
    client_address,
    record_failed_attempt,
    setup_required,
)
from .steps import (
    ORDER,
    SECTION_SEXES,
    SESSION_KEY,
    STEPS,
    StepError,
    new_branch_entry,
    new_section_entry,
)

#: The steps the progress list shows: the code is the gate rather than a step,
#: and "done" is what the list has been counting towards.
PROGRESS = ORDER[1:-1]


class SetupGuardMixin:
    """Refuses to serve the wizard to an instance that does not need it."""

    def require_setup(self, request):
        """404 — not 403 — once this instance has an administrator.

        The wizard is not a page with restricted access; past setup it is not
        a page at all, and saying so is what keeps it out of reach of anybody
        who goes looking for a second way in.
        """
        if setup_required():
            return
        # The session that just finished setup may still look at the last
        # page: the browser lands there and a refresh should not 404.
        if request.session.get("setup_finished"):
            return
        raise Http404("This instance has already been set up.")


class SetupWizardView(SetupGuardMixin, View):
    """Walk the steps, one form at a time."""

    def get(self, request, step=None):
        self.require_setup(request)
        name = self._step_for(request, step)
        if name != "code" and not self._code_accepted(request):
            return redirect("setup:step", step="code")
        return self._render(request, name)

    def post(self, request, step=None):
        self.require_setup(request)
        name = self._step_for(request, step)
        if name != "code" and not self._code_accepted(request):
            return redirect("setup:step", step="code")

        if name == "code":
            allowed, wait = attempts_left(client_address(request))
            if not allowed:
                return self._render(
                    request,
                    name,
                    error=_too_many(wait),
                    status=429,
                )

        current = STEPS[name](request)
        if not current.saves:
            # A page with nothing to fill in: there is nothing to post.
            return redirect("setup:step", step=name)

        form = current.form(data=request.POST, files=request.FILES)
        if not form.is_valid():
            if name == "code" and "code" in form.errors:
                record_failed_attempt(client_address(request))
            return self._render(request, name, form=form)

        try:
            note = current.save(form)
        except StepError as exc:
            return self._render(
                request, name, form=form, error=exc.message, detail=exc.detail
            )
        return self._advance(request, name, note)

    # -- where we are ------------------------------------------------------

    def _step_for(self, request, step):
        """Which step this request is for."""
        if not setup_required():
            # Setup is finished; the only page left to look at is the one that
            # says so, and the session that finished is the one that may.
            if step in (None, "done"):
                return "done"
            raise Http404("This instance has already been set up.")

        if step:
            if step not in STEPS:
                raise Http404(f"No step called {step!r}.")
            return step
        return self._resume(request)

    def _resume(self, request):
        """Where to pick up: the code first, then wherever the last save left off."""
        state = request.session.get(SESSION_KEY, {})
        if not state.get("code_ok"):
            return "code"
        step = state.get("step")
        if step in ORDER and ORDER.index(step) > ORDER.index("code"):
            return step
        return "admin"

    def _code_accepted(self, request):
        return bool(request.session.get(SESSION_KEY, {}).get("code_ok"))

    def _advance(self, request, name, note):
        """Move on, and show what comes next."""
        position = ORDER.index(name)
        following = ORDER[position + 1] if position + 1 < len(ORDER) else None
        request.session.setdefault(SESSION_KEY, {})["step"] = following or name
        request.session.modified = True

        if following is None:
            return redirect("homepage")
        return self._render(request, following, note=note)

    # -- rendering ---------------------------------------------------------

    def _render(self, request, name, form=None, note="", error="", detail="", status=200):
        step = STEPS[name](request)
        if form is None:
            form = step.form()
        context = {
            "current": name,
            "step": step,
            "form": form,
            "note": note,
            "error": error,
            "error_detail": detail,
            "progress": _progress(name),
            "previous": _previous(name),
            **step.context(form),
        }

        # An HTMX request gets the pane alone, to swap in; anything else — a
        # first visit, a reload, a browser without JavaScript — gets the whole
        # page around it.
        template = (
            "members/setup/_pane.html"
            if is_htmx(request)
            else "members/setup/wizard.html"
        )
        response = HttpResponse(
            render_to_string(template, context, request=request), status=status
        )
        if is_htmx(request):
            response["HX-Push-Url"] = reverse("setup:step", args=[name])
        return response


class StructureRowView(SetupGuardMixin, View):
    """The structure editor's buttons: one row added or removed at a time.

    Adding a row is a round trip rather than something the browser does to
    itself, so the markup for a row lives in one place — the template the
    server renders and the template the page was built from are the same file.
    Removing one needs no server at all, and the empty response is what tells
    HTMX to swap the row away.
    """

    def post(self, request, action):
        self.require_setup(request)
        languages = list(TroopSettings.get_settings().enabled_languages or ["fr"])

        if action == "add-branch":
            branch = new_branch_entry(languages)
            # A branch with no section in it is a branch nobody can be put in,
            # so a new one arrives with a section row ready to be named.
            branch.sections.append(new_section_entry(branch.id, languages))
            return self._render(
                request, "members/setup/_structure_branch.html", {"branch": branch}
            )

        if action == "add-section":
            section = new_section_entry(request.POST.get("branch-id", ""), languages)
            return self._render(
                request, "members/setup/_structure_section.html", {"section": section}
            )

        if action == "remove":
            return HttpResponse("")

        raise Http404(f"No structure action called {action!r}.")

    def _render(self, request, template, extra):
        context = {
            "languages": list(
                TroopSettings.get_settings().enabled_languages or ["fr"]
            ),
            "sexes": SECTION_SEXES,
            **extra,
        }
        return HttpResponse(render_to_string(template, context, request=request))


def _previous(name):
    """The step before this one, or None on the first.

    The setup code is deliberately not somewhere to go back to: it has been
    entered, and offering it again would only invite a second guess at it.
    """
    if name not in PROGRESS or PROGRESS.index(name) == 0:
        return None
    return PROGRESS[PROGRESS.index(name) - 1]


def _progress(current):
    """Every step, with where it stands, for the progress list."""
    if current == "done":
        return [{"name": name, "title": STEPS[name].title, "state": "done"} for name in PROGRESS]

    position = PROGRESS.index(current) if current in PROGRESS else -1
    entries = []
    for index, name in enumerate(PROGRESS):
        if index < position:
            state = "done"
        elif index == position:
            state = "current"
        else:
            state = "todo"
        entries.append({"name": name, "title": STEPS[name].title, "state": state})
    return entries


def _too_many(seconds):
    minutes = max(1, round(seconds / 60))
    return _(
        "Too many wrong codes from this address. Try again in %(minutes)s minutes."
    ) % {"minutes": minutes}
