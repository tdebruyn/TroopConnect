import base64
import calendar
import json
from collections import defaultdict
from datetime import date, timedelta
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import Http404, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import formats, timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST
from django.views.generic import ListView, TemplateView, UpdateView, View
from post_office.models import STATUS, Email

from .absences import notify_section
from .constants import (
    ERROR_MESSAGES,
)
from .filters import PersonFilter
from .forms import (
    AbsenceForm,
    AdminUserUpdateForm,
    AnimeProfileForm,
    CalendarSettingsForm,
    ChildForm,
    ChildFromKey,
    LocaleSettingsForm,
    ModuleSettingsForm,
    OnboardingForm,
    OrganisationSettingsForm,
    ProfileEditForm,
    SectionEventForm,
)
from .importexport import columns as cols
from .importexport import exporter
from .importexport.files import FileError, read_table, write_table
from .importexport.importer import apply_plan, build_plan
from .mail import absolute_url, send_templated
from .models import (
    PASSAGE_MODE_MANUAL,
    Absence,
    Account,
    Enrollment,
    ImportantDocument,
    Person,
    SchoolYear,
    SectionEvent,
    TroopSettings,
    get_registration_admins,
)
from .modules import AGENDA, FEES, module_enabled, requires_module
from .permissions import (
    can_access_finance,
    can_delete_member,
    can_edit_section_agenda,
    can_manage_unit,
    get_person,
    is_htmx,
    reportable_children,
    visible_sections,
)
from .tasks import run_passage


class Login(TemplateView):
    template_name = "members/login.html"


class OnboardingView(LoginRequiredMixin, TemplateView):
    template_name = "members/onboarding.html"

    def dispatch(self, request, *args, **kwargs):
        if (
            hasattr(request.user, "person")
            and request.user.person.status == "a"
        ):
            return redirect("homepage")
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        person = request.user.person
        form = OnboardingForm(
            person=person,
            initial={
                "first_name": person.first_name,
                "last_name": person.last_name,
                "address": person.address,
                "phone": person.phone,
            },
        )
        return self.render_to_response(self.get_context_data(form=form))

    def post(self, request, *args, **kwargs):
        form = OnboardingForm(request.POST, person=request.user.person)
        if form.is_valid():
            form.save(request.user)
            return redirect("homepage")
        return self.render_to_response(self.get_context_data(form=form))


class AdminListView(UserPassesTestMixin, ListView):
    """
    Filter : first_name + totem, last_name, birthday (upper, lower), year selection, parents/members/all
    List: first_name + totem, last_name, if adult => adult type, section or status
    """

    model = Person
    fields = "__all__"
    template_name = "members/admin_list.html"
    context_object_name = "members"
    paginate_by = 15

    # Filter fields that are persisted in the session so a filter survives
    # navigating away (e.g. to the edit page) and back until it is reset.
    filter_param_keys = ("first_name", "last_name", "birth_year", "year", "section", "role")
    filter_session_key = "admin_list_filter"

    sortable_fields = {
        "first_name": "first_name",
        "last_name": "last_name",
        "birthday": "birthday",
        "sex": "sex",
        # Note: section and role are computed fields, not directly sortable
    }

    def get(self, request, *args, **kwargs):
        params = request.GET

        # The "Reset" button lands here with ?reset and clears the saved filter.
        if "reset" in params:
            request.session.pop(self.filter_session_key, None)
            return redirect("members:admin_list")

        if any(key in params for key in self.filter_param_keys):
            # A filter form was submitted (or a filtered link followed): remember
            # the non-empty filter values so they survive navigating away and back.
            saved = urlencode(
                {key: params[key] for key in self.filter_param_keys if params.get(key)}
            )
            if saved:
                request.session[self.filter_session_key] = saved
            else:
                request.session.pop(self.filter_session_key, None)
        else:
            # No filter in the URL (e.g. returning from the edit page): restore the
            # last saved filter if there is one.
            saved = request.session.get(self.filter_session_key)
            if saved:
                return redirect(f"{reverse('members:admin_list')}?{saved}")

        return super().get(request, *args, **kwargs)

    def get_ordering(self):
        """
        Get the ordering based on the request parameters
        """
        ordering = self.request.GET.get("sort", "last_name")
        direction = self.request.GET.get("direction", "asc")

        # Check if the requested field is sortable
        if ordering in self.sortable_fields:
            field = self.sortable_fields[ordering]
            if direction == "desc":
                return f"-{field}"
            return field

        return "last_name"

    def _get_selected_year(self):
        """Resolve the `?year=` filter, tolerating a stale or malformed value.

        The year is round-tripped through the session filter, so an id that no
        longer exists (or was hand-edited) must not 500 the page.
        """
        year_id = self.request.GET.get("year")
        if year_id:
            try:
                return SchoolYear.objects.get(pk=year_id)
            except (SchoolYear.DoesNotExist, ValueError):
                pass
        return SchoolYear.current()

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(**kwargs)

        selected_year = self._get_selected_year()

        # The template only reads `filter.form.*`; `get_queryset()` has already
        # applied the filters, so reuse that same FilterSet instead of running
        # the whole filtering pass a second time.
        context["filter"] = self._get_filterset()

        troop = TroopSettings.get_settings()
        for person in context["object_list"]:
            try:
                enrollment = person.enrollment_set.filter(
                    school_year=selected_year
                ).select_related("section__branch").first()
                person.section_display = enrollment.section.name if enrollment else "-"
                # Check age compatibility with section's branch, using the same
                # age definition the passage task and the role rules use.
                person.age_mismatch = False
                if enrollment and person.birthday and enrollment.section.branch:
                    age_at_reference = troop.age_at_reference(person, selected_year)
                    branch = enrollment.section.branch
                    if (
                        age_at_reference is not None
                        and branch.min_age_dec_31 is not None
                        and branch.max_age_dec_31 is not None
                    ):
                        if not (
                            branch.min_age_dec_31
                            <= age_at_reference
                            <= branch.max_age_dec_31
                        ):
                            person.age_mismatch = True
                            person.age_mismatch_detail = _(
                                "%(age)s years old — branch %(branch)s: "
                                "%(min)s-%(max)s years old"
                            ) % {
                                "age": age_at_reference,
                                "branch": branch.name,
                                "min": branch.min_age_dec_31,
                                "max": branch.max_age_dec_31,
                            }
            except (SchoolYear.DoesNotExist, AttributeError):
                person.section_display = "-"
                person.age_mismatch = False

            # `primary_role` is select_related in get_queryset(), so this costs
            # no query per row. It can legitimately be unset.
            person.role = person.primary_role

        context["current_sort"] = self.request.GET.get("sort", "last_name")
        context["current_direction"] = self.request.GET.get("direction", "asc")
        context["sortable_fields"] = self.sortable_fields.keys()

        context["fields_map"] = [
            ("first_name", _("First name")),
            ("last_name", _("Last name")),
            ("birthday", _("Date of birth")),
            ("sex", _("Sex")),
            ("section", _("Section")),
            ("primary_role", _("Role")),
        ]
        if module_enabled(FEES):
            # Not a model field and so not sortable. `fields_map` drives the
            # header row and the cell after the role below, and a household is
            # only ever a billing group, so the column follows the module.
            context["fields_map"].append(("household", _("Household")))

        return context

    def _get_filterset(self):
        """Build the FilterSet once per request and reuse it for list + context."""
        if not hasattr(self, "_filterset"):
            self._filterset = PersonFilter(
                self.request.GET, queryset=super().get_queryset()
            )
        return self._filterset

    def get_queryset(self):
        queryset = self._get_filterset().qs.select_related(
            "primary_role"
        ).prefetch_related("households")

        ordering = self.get_ordering()
        if ordering:
            queryset = queryset.order_by(ordering)

        return queryset

    def test_func(self):
        return self.request.user.is_staff


class AdminUpdateView(UserPassesTestMixin, UpdateView):
    form_class = AdminUserUpdateForm
    model = Person
    template_name = "members/admin_update.html"
    success_url = reverse_lazy("members:admin_list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["children"] = self.object.children.all()
        context["parents"] = self.object.parents.all()
        # Gates the delete/purge buttons: staff reach this page, but only a
        # superuser or an ADMIN may destroy a member's record.
        context["can_delete"] = can_delete_member(self.request.user)
        context["is_self"] = self.object.pk == getattr(
            get_person(self.request.user), "pk", None
        )
        context.update(self._household_context())
        return context

    def _household_context(self):
        """Data for the household panel on the member page.

        The `finance` imports are inside the method rather than at module
        level: `finance` already depends on `members`, and importing it back
        would make the two apps import each other for one panel.

        The panel is hidden when the troop does not use the fees module — a
        household exists only to say who is billed with whom.
        """
        if not module_enabled(FEES) or not can_access_finance(self.request.user):
            return {"household_enabled": False}

        from finance.forms import HouseholdAssignmentForm
        from finance.models import household_index

        current_year = SchoolYear.current()
        group = (
            household_index(current_year).get(self.object.pk) if current_year else None
        )
        explicit = self.object.households.first()

        return {
            "household_enabled": True,
            "household_explicit": explicit,
            "household_group": group,
            "household_school_year": current_year,
            "household_others": (
                [m for m in group["members"] if m.pk != self.object.pk]
                if group
                else []
            ),
            "household_form": HouseholdAssignmentForm(
                initial={"person_id": self.object.pk, "household": explicit}
            ),
        }

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        form_class = self.get_form_class()
        form = form_class(instance=self.object)

        if hasattr(self.object, "account"):
            form.fields["email"].initial = self.object.account.email

        try:
            current_year = SchoolYear.current()
            enrollment = self.object.enrollment_set.filter(
                school_year=current_year
            ).first()
            if enrollment:
                form.fields["current_section"].initial = enrollment.section
        except (AttributeError, KeyError):
            pass

        try:
            next_year_name = current_year.name + 1
            try:
                next_year = SchoolYear.objects.get(name=next_year_name)
                enrollment = self.object.enrollment_set.filter(
                    school_year=next_year
                ).first()
                if enrollment:
                    form.fields["next_section"].initial = enrollment.section
            except SchoolYear.DoesNotExist:
                pass
        except (AttributeError, KeyError):
            pass

        return self.render_to_response(self.get_context_data(form=form))

    def form_valid(self, form):
        # Save the form, which handles Person, Roles, Enrollments, and the
        # Account creation/update internally.
        form.save()
        return super().form_valid(form)

    def test_func(self):
        return self.request.user.is_staff


class ProfileView(LoginRequiredMixin, UpdateView):
    form_class = ProfileEditForm
    model = Account
    template_name = "members/profile.html"

    def get_success_url(self):
        return reverse_lazy("members:profile", kwargs={"pk": self.request.user.pk})

    def get_queryset(self):
        queryset = super().get_queryset()
        queryset = queryset.filter(email=self.request.user.email)
        return queryset

    def get_object(self, queryset=None):
        pk = self.kwargs.get("pk")
        try:
            obj = Account.objects.get(pk=pk)
        except Account.DoesNotExist:
            raise Http404(ERROR_MESSAGES["no_user_found"]) from None

        if obj != self.request.user:
            raise Http404(ERROR_MESSAGES["no_permission"])
        return obj

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        form_class = self.get_form_class()
        form = form_class(instance=self.object)
        return self.render_to_response(self.get_context_data(form=form))

    def get_form_class(self):
        try:
            if self.object.person.primary_role.short == "e":
                return AnimeProfileForm
        except AttributeError:
            pass
        return self.form_class

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form_class = self.get_form_class()
        form = form_class(request.POST, instance=self.object)
        if form.is_valid():
            form.save()
            return redirect(self.get_success_url())
        return self.render_to_response(self.get_context_data(form=form))


def add_new_child_view(request):
    form = ChildForm()
    if request.method == "POST":
        form = ChildForm(request.POST)
        if form.is_valid():
            # Reject a duplicate: the same parent re-adding a child with the
            # same first and last name. Comparison is case-insensitive so
            # "Jean" and "jean" are treated as the same name.
            if Person.objects.filter(
                parents=request.user.person,
                first_name__iexact=form.cleaned_data["first_name"],
                last_name__iexact=form.cleaned_data["last_name"],
            ).exists():
                form.add_error(
                    "first_name",
                    _("%(first)s %(last)s is already attached to your account.")
                    % {
                        "first": form.cleaned_data["first_name"],
                        "last": form.cleaned_data["last_name"],
                    },
                )
                return render(request, "members/child_form.html", {"form": form})

            child = form.save(commit=False)
            child.address = request.user.person.address
            child.phone = request.user.person.phone
            child.photo_consent = request.user.person.photo_consent
            child.save()
            form.save_account(child)
            child.parents.add(request.user.person)

            # The parent confirmation email only makes sense when the child has
            # an email (and thus an account). Adding a child without an email is
            # a quick add: the HTMX childListChanged/showMessage response is the
            # confirmation, so no email should be sent.
            if form.cleaned_data.get("email"):
                send_templated(
                    recipients=request.user.email,
                    template="new_child_parent",
                    language=getattr(request.user, "preferred_language", None),
                    context={
                        "first_name": child.first_name,
                        "last_name": child.last_name,
                        "parent": f"{request.user.person.first_name} {request.user.person.last_name}",
                    },
                )
            send_templated(
                recipients=get_registration_admins(),
                template="new_child_staff",
                # Staff notifications are sent in the site default language.
                language=settings.LANGUAGE_CODE,
                context={
                    "first_name": child.first_name,
                    "last_name": child.last_name,
                    "url": absolute_url(f"/users/adminupdate/{child.id}"),
                },
            )
            return HttpResponse(
                status=204,
                headers={
                    "HX-Trigger": json.dumps(
                        {
                            "childListChanged": None,
                            "showMessage": _("%(first)s %(last)s added.")
                            % {"first": child.first_name, "last": child.last_name},
                        }
                    )
                },
            )
    return render(request, "members/child_form.html", {"form": form})


def child_list(request):
    # "children" is the list of Person which has request.user.person as one of the parent
    if not is_htmx(request):
        return HttpResponseBadRequest(_("Invalid request"))
    return render(
        request,
        "members/child_list.html",
        {
            "children": Person.objects.filter(parents__id=request.user.person.id),
        },
    )


def edit_child(request, pk):
    if not is_htmx(request):
        return HttpResponseBadRequest(_("Invalid request"))
    # `request.user` already is the Account, so no need to re-fetch it.
    parent_person_id = request.user.person.id
    child = get_object_or_404(Person, id=pk, parents__id=parent_person_id)

    if request.method == "POST":
        form = ChildForm(request.POST, instance=child)
        if form.is_valid():
            form.save()
            return HttpResponse(
                status=204,
                headers={
                    "HX-Trigger": json.dumps(
                        {
                            "childListChanged": None,
                            "showMessage": _("%(first)s modified.")
                            % {"first": child.first_name},
                        }
                    )
                },
            )
    else:
        form = ChildForm(instance=child)

    return render(
        request,
        "members/child_form.html",
        {
            "form": form,
            "child": child,
        },
    )


def add_child_key_view(request):
    if request.method == "POST":
        form = ChildFromKey(request.POST)
        if form.is_valid():
            child = Person.objects.get(secret_key=form.cleaned_data["secret_key"])
            child.parents.add(request.user.person)

            return HttpResponse(
                status=204,
                headers={
                    "HX-Trigger": json.dumps(
                        {
                            "childListChanged": None,
                            "showMessage": _("%(first)s %(last)s added.")
                            % {"first": child.first_name, "last": child.last_name},
                        }
                    )
                },
            )
    else:
        form = ChildFromKey()
    return render(request, "members/child_from_key_form.html", {"form": form})


def _can_detach(child):
    """Whether a parent may detach this child from their account.

    A child must keep at least one parent — unless they are over 18 *and* hold
    their own account, in which case they no longer need a parent attached.
    This mirrors the rule stated on the detach confirmation page; it lives in
    one place so the page and the confirm view cannot drift apart.
    """
    return child.parents.count() >= 2 or (child.is_adult() and child.has_account)


def dettach_child(request, pk):
    context = {"allow_dettach": False}
    child = get_object_or_404(Person, id=pk)
    parent = request.user.person
    context["child"] = child
    if not child.parents.filter(id=parent.id).exists():
        context["message"] = _("%(first)s is not attached to your account.") % {
            "first": child.first_name
        }
    elif not _can_detach(child):
        context["message"] = _(
            "You cannot detach %(first)s.\n"
            "To detach a child, they must either be attached to other parents, "
            "or be over 18 years old and have an associated account.\n"
            "%(first)s has %(count)s parent(s)\n"
            "%(first)s was born on %(birthday)s and %(has_account)s."
        ) % {
            "first": child.first_name,
            "count": child.parents.count(),
            "birthday": child.birthday,
            "has_account": _("has an account") if child.has_account else _("does not have an account"),
        }
    else:
        context["message"] = _(
            'To confirm that you want to detach %(first)s from your account, click "Detach".'
        ) % {"first": child.first_name}
        context["allow_dettach"] = True
    return render(
        request=request, template_name="members/dettach_child.html", context=context
    )


def dettach_confirm(request, pk):
    child = get_object_or_404(Person, id=pk)
    parent = request.user.person
    profile_url = reverse_lazy("members:profile", kwargs={"pk": request.user.pk})
    if not child.parents.filter(id=parent.id).exists():
        return redirect(profile_url)
    # Same rule as the confirmation page that links here.
    if not _can_detach(child):
        return redirect(profile_url)
    child.parents.remove(parent)
    return redirect(profile_url)


def deregister_child(request, pk):
    child = get_object_or_404(Person, id=pk)
    parent = request.user.person

    if not child.parents.filter(id=parent.id).exists():
        return redirect(reverse_lazy("members:profile", kwargs={"pk": request.user.pk}))

    context = {"allow_deregister": False}
    context["child"] = child
    if child.parents.filter(id=parent.id).exists():
        context["allow_deregister"] = True

    # The footnote tells the parent when the scout year starts. That date is
    # the troop's own, so read it from the settings rather than naming a month.
    troop = TroopSettings.get_settings()
    year_start, _year_end = troop.school_year_bounds(
        troop.school_year_for(timezone.localdate())
    )
    context["year_start"] = formats.date_format(year_start, "j F")
    return render(
        request=request, template_name="members/deregister_child.html", context=context
    )


def _archive_child(child):
    """Archive a child, stamping the date that drives the retention clock."""
    child.status = "ar"
    child.archived_date = timezone.now().date()
    child.save(update_fields=["status", "archived_date"])


def _notify_deregistration_admins(child, parent):
    """Warn the registration admins that a current-year deregistration needs handling.

    A child actively enrolled for the current year cannot be fully unwound
    automatically (fees and attestations are already built on that enrolment),
    so the admins are told to follow the internal-regulations procedure.
    """
    send_templated(
        recipients=get_registration_admins(),
        template="deregistration_admin",
        # Staff notifications go out in the site default language.
        language=settings.LANGUAGE_CODE,
        context={
            "first_name": child.first_name,
            "last_name": child.last_name,
            "parent": f"{parent.first_name} {parent.last_name}",
            "url": absolute_url(f"/users/adminupdate/{child.id}"),
        },
    )


def deregister_confirm(request, pk, action):
    """Process a deregistration request.

    ``action`` comes from deregister_child.html and is either "next_year" or
    "this_year". The two buttons must not behave alike:

    * "next_year" — processed immediately: drop the upcoming school year's
      enrolment and any manual passage override. The current year is untouched.
    * "this_year" on a child still in the "request" state — there is no active
      enrolment to unwind, so this is processed immediately as well.
    * "this_year" on a child actively enrolled — the child is archived but the
      enrolment is deliberately left in place, and the registration admins are
      emailed, because unwinding the current year is a manual procedure.
    """
    child = get_object_or_404(Person, id=pk)
    parent = request.user.person
    profile_url = reverse_lazy("members:profile", kwargs={"pk": request.user.pk})

    if not child.parents.filter(id=parent.id).exists():
        return redirect(profile_url)

    if action == "next_year":
        next_year = SchoolYear.next_school_year()
        if next_year:
            Enrollment.objects.filter(user=child, school_year=next_year).delete()
        if child.next_section_id:
            child.next_section = None
            child.save(update_fields=["next_section"])
        messages.success(
            request,
            _("%(first)s will not be re-enrolled next year.")
            % {"first": child.first_name},
        )
        return redirect(profile_url)

    was_confirmed = child.status != "r"
    _archive_child(child)
    if was_confirmed:
        _notify_deregistration_admins(child, parent)
        messages.success(
            request,
            _(
                "%(first)s has been deregistered. The registration team has been "
                "notified to complete the current-year procedure."
            )
            % {"first": child.first_name},
        )
    else:
        messages.success(
            request,
            _("%(first)s has been deregistered.") % {"first": child.first_name},
        )
    return redirect(profile_url)


def remove_child(request, pk):
    """Confirmation page for deleting a child that has no section assigned yet.

    Only offered in place of "Deregister" when the child is not enrolled (see
    child_list.html). Deleting is final, so the actual removal happens in a
    separate confirm view.
    """
    child = get_object_or_404(Person, id=pk)
    parent = request.user.person
    context = {"child": child, "allow_remove": False}
    if not child.parents.filter(id=parent.id).exists():
        return redirect(reverse_lazy("members:profile", kwargs={"pk": request.user.pk}))
    if child.has_section:
        context["message"] = _(
            "%(first)s is assigned to a section and must be deregistered, not removed."
        ) % {"first": child.first_name}
    else:
        context["allow_remove"] = True
    return render(
        request=request, template_name="members/remove_child.html", context=context
    )


def remove_child_confirm(request, pk):
    child = get_object_or_404(Person, id=pk)
    parent = request.user.person
    if not child.parents.filter(id=parent.id).exists():
        return redirect(reverse_lazy("members:profile", kwargs={"pk": request.user.pk}))
    # Never delete an enrolled child — they go through deregister_confirm.
    if not child.has_section:
        child.delete()
    return redirect(reverse_lazy("members:profile", kwargs={"pk": request.user.pk}))


# --- Deleting a member (superuser / ADMIN role only) ------------------------
#
# Deleting a member from the admin side is a two-phase affair: `member_delete`
# archives the person (history kept, login shut off) and `member_purge` is the
# separate, later action that destroys the record for good. Both are reached
# from the member's modify page, and neither does anything on a GET, so a
# prefetching browser or a stale link cannot remove anyone.


def _require_member_deleter(request):
    """Raise 403 unless the requesting user may delete members."""
    if not can_delete_member(request.user):
        raise PermissionDenied


def _is_self(request, person):
    """True when `person` is the requesting user's own record."""
    own_person = get_person(request.user)
    return own_person is not None and own_person.pk == person.pk


def _archive_member(person):
    """Soft-delete a member: archive them and shut off their login.

    Enrolments, payments and messages are deliberately left alone — that is
    what separates this from a purge. Mirrors `_archive_child`, which is not
    reused as-is because a deregistered child keeps a usable account.
    """
    person.status = "ar"
    person.archived_date = timezone.now().date()
    person.save(update_fields=["status", "archived_date"])

    account = getattr(person, "account", None)
    if account is not None and account.is_active:
        account.is_active = False
        account.save(update_fields=["is_active"])


def _member_record_context(person):
    """The linked records that make the delete/purge warning pages concrete."""
    return {
        "person": person,
        "enrollments": person.enrollment_set.select_related(
            "section", "school_year"
        ).order_by("-school_year__name"),
        "children": person.children.all(),
        "parents": person.parents.all(),
        "payments": person.payments.select_related("school_year").order_by("-date"),
        "received_messages": person.received_messages.count(),
        "attestation_items": person.attestation_items.count(),
    }


@login_required
def member_delete(request, pk):
    """Delete a member the soft way: archive the person and disable the login.

    The last step of the flow — the member's modify page links here, this page
    spells out what an archive does and does not touch, and only the POST its
    button issues actually performs it.
    """
    _require_member_deleter(request)
    person = get_object_or_404(Person, id=pk)

    if _is_self(request, person):
        messages.error(request, _("You cannot delete your own account."))
        return redirect("members:admin_list")

    if person.status == "ar":
        # Already archived, so the only thing left to do is the purge.
        return redirect("members:member_purge", pk=person.pk)

    if request.method == "POST":
        _archive_member(person)
        messages.success(
            request,
            _("%(name)s has been archived: their login is disabled.")
            % {"name": person},
        )
        return redirect("members:admin_list")

    return render(
        request, "members/member_delete.html", _member_record_context(person)
    )


@login_required
def member_purge(request, pk):
    """Permanently destroy an archived member and everything linked to them.

    Only archived members can be purged, so a hand-typed URL cannot destroy
    someone who is still active — they have to be archived first.
    """
    _require_member_deleter(request)
    person = get_object_or_404(Person, id=pk)

    if _is_self(request, person):
        messages.error(request, _("You cannot delete your own account."))
        return redirect("members:admin_list")

    if person.status != "ar":
        messages.error(
            request,
            _("%(name)s is not archived — archive the member first.")
            % {"name": person},
        )
        return redirect("members:admin_update", pk=person.pk)

    if request.method == "POST":
        name = str(person)
        person.delete()
        messages.success(
            request,
            _("%(name)s and all their records have been permanently deleted.")
            % {"name": name},
        )
        return redirect("members:admin_list")

    return render(request, "members/member_purge.html", _member_record_context(person))



class DocumentListView(LoginRequiredMixin, ListView):
    model = ImportantDocument
    template_name = "members/documents.html"
    context_object_name = "documents"


class MailQueueView(UserPassesTestMixin, TemplateView):
    """Staff view to monitor and recover the post_office email queue."""

    template_name = "members/mail_queue.html"

    def test_func(self):
        return self.request.user.is_staff

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["queued_count"] = Email.objects.filter(status=STATUS.queued).count()
        context["requeued_count"] = Email.objects.filter(status=STATUS.requeued).count()
        context["failed_count"] = Email.objects.filter(status=STATUS.failed).count()
        return context

    def post(self, request, *args, **kwargs):
        action = request.POST.get("action")
        if action == "requeue":
            count = Email.objects.filter(status=STATUS.failed).update(
                status=STATUS.queued,
                number_of_retries=0,
                scheduled_time=None,
            )
            messages.success(
                request, _("%(count)s email(s) requeued.") % {"count": count}
            )
        elif action == "purge":
            count, _deleted = Email.objects.filter(status=STATUS.failed).delete()
            messages.success(request, _("%(count)s email(s) purged.") % {"count": count})
        return redirect("members:mail_queue")


class TroopSettingsView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    """Staff page for the troop's own settings, in four grouped sections.

    Each section is an independent form posting to this same view, so editing
    the calendar cannot quietly overwrite mail settings nobody looked at. An
    HTMX post gets that one section back; a plain post — JavaScript off, or a
    stray Enter key — gets a redirect.

    ``LoginRequiredMixin`` first, so an anonymous visitor is sent to the login
    page rather than shown a bare 403.
    """

    template_name = "members/settings.html"
    section_template_name = "members/_settings_section.html"

    def test_func(self):
        return self.request.user.is_staff

    def _sections(self):
        """The page's sections, in order.

        Built per request rather than held in a class attribute so the titles
        are translated in the language actually being rendered.
        """
        return (
            ("organisation", _("Organisation"), OrganisationSettingsForm),
            ("locale", _("Locale"), LocaleSettingsForm),
            ("calendar", _("Calendar"), CalendarSettingsForm),
            ("modules", _("Modules"), ModuleSettingsForm),
        )

    def _section_context(self, key, form, saved=False):
        title = next(title for k, title, _cls in self._sections() if k == key)
        return {"key": key, "title": title, "form": form, "saved": saved}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        instance = TroopSettings.get_settings()
        bound_key = kwargs.get("bound_key")
        bound_form = kwargs.get("bound_form")

        context["sections"] = [
            self._section_context(
                key, bound_form if key == bound_key else form_class(instance=instance)
            )
            for key, _title, form_class in self._sections()
        ]
        return context

    def post(self, request, *args, **kwargs):
        key = request.POST.get("section")
        form_class = {k: cls for k, _title, cls in self._sections()}.get(key)
        if form_class is None:
            return HttpResponseBadRequest(_("Unknown settings section."))

        # request.FILES as well as request.POST: the organisation section
        # carries the logo and favicon uploads, and a bound ModelForm that is
        # not handed the files treats an unchanged upload as "cleared".
        form = form_class(
            request.POST, request.FILES, instance=TroopSettings.get_settings()
        )

        if form.is_valid():
            form.save()
            if is_htmx(request):
                return render(
                    request,
                    self.section_template_name,
                    {
                        "section": self._section_context(
                            key,
                            form_class(instance=TroopSettings.get_settings()),
                            saved=True,
                        )
                    },
                )
            messages.success(request, _("Settings saved."))
            return redirect("members:troop_settings")

        # Invalid: hand the bound form back so the errors and what was typed
        # are both still on screen.
        if is_htmx(request):
            return render(
                request,
                self.section_template_name,
                {"section": self._section_context(key, form)},
            )
        return self.render_to_response(
            self.get_context_data(bound_key=key, bound_form=form)
        )


class PassageView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    """Staff page for the yearly passage: when it runs, and who it could not place.

    The automatic run answers to the troop's calendar and ``passage_mode``; this
    page is the manual counterpart. Its button calls the very same task the
    nightly run does, with ``force=True``, so the two cannot drift apart — a
    forced run skips the guards that exist to stop the *daily* task acting early
    or twice, and still records the marker so the nightly task will not repeat
    the work.
    """

    template_name = "members/passage.html"

    def test_func(self):
        return self.request.user.is_staff

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        troop = TroopSettings.get_settings()
        context["target_year"] = SchoolYear.next_school_year()
        context["automatic"] = troop.passage_mode != PASSAGE_MODE_MANUAL
        # Formatted here rather than in the template: a date filter cannot be
        # used inside a blocktranslate block.
        context["next_due"] = formats.date_format(
            troop.next_passage_datetime(), "j F Y"
        )
        context["last_run_year"] = troop.last_passage_school_year
        context["flagged"] = Person.objects.exclude(passage_review="").order_by(
            "last_name", "first_name"
        )
        return context

    def post(self, request, *args, **kwargs):
        result = run_passage(force=True)
        if result is None:
            messages.error(
                request,
                _(
                    "The passage did not run: there is no coming school year yet."
                ),
            )
        else:
            messages.success(
                request,
                _(
                    "Passage done: %(promoted)s placed, %(graduated)s graduated, "
                    "%(flagged)s waiting for a decision."
                )
                % {
                    "promoted": result["promoted"],
                    "graduated": result["aged_out"],
                    "flagged": result["flagged"],
                },
            )
        return redirect("members:passage")


# --- Section agenda ---------------------------------------------------------
#
# A month grid per section, with the chosen day's activities loaded into a
# frame beneath it. Which sections a reader may open is
# `permissions.visible_sections`; which one they may write to is
# `permissions.can_edit_section_agenda`.


def _selected_section(request, sections):
    """The section this request is about, from ``?section=``.

    Falls back to the first section the reader may see, so the page always has
    something to show. Asking for a section they may not see is answered the
    same way as asking for one that does not exist.
    """
    wanted = request.GET.get("section") or request.POST.get("section")
    if wanted:
        for section in sections:
            if str(section.pk) == str(wanted):
                return section
        raise Http404
    return sections[0] if sections else None


def _selected_month(request):
    """The first day of the month to display, from ``?month=YYYY-MM``."""
    raw = request.GET.get("month")
    if not raw:
        return timezone.localdate().replace(day=1)
    try:
        year, month = (int(part) for part in raw.split("-", 1))
        return date(year, month, 1)
    except (TypeError, ValueError):
        raise Http404 from None


def _selected_day(request):
    """The day the detail frame was asked for, from ``?date=``."""
    raw = request.GET.get("date")
    if not raw:
        return timezone.localdate()
    try:
        return date.fromisoformat(raw)
    except ValueError:
        raise Http404 from None


def _shift_month(month_start, months):
    """`month_start` moved by `months`, always landing on the 1st."""
    index = month_start.year * 12 + month_start.month - 1 + months
    return date(index // 12, index % 12 + 1, 1)


def _month_days(month_start):
    """The six weeks of days the grid shows, as lists of `date`.

    Always six, so that paging through the year does not make the grid grow and
    shrink under the reader's cursor. Weeks run Monday to Sunday.
    """
    weeks = calendar.Calendar(firstweekday=0).monthdatescalendar(
        month_start.year, month_start.month
    )
    while len(weeks) < 6:
        weeks.append([day + timedelta(days=7) for day in weeks[-1]])
    return weeks


def _events_in(section, first_day, last_day):
    """The section's activities touching the ``first_day``–``last_day`` range.

    An activity belongs to a month when it *overlaps* it, not when it starts in
    it: a week-end that began in September still has to appear in October's
    grid.
    """
    return list(
        SectionEvent.objects.filter(
            section=section, start_date__lte=last_day
        ).filter(
            Q(end_date__gte=first_day)
            | Q(end_date__isnull=True, start_date__gte=first_day)
        )
    )


def _events_on(section, day):
    """The section's activities covering `day`, in reading order."""
    return (
        SectionEvent.objects.filter(section=section, start_date__lte=day)
        .filter(Q(end_date__gte=day) | Q(end_date__isnull=True, start_date=day))
        .order_by("start_time", "title")
    )


def _agenda_scope(request):
    """The reader's sections, the one in play, and whether they may write to it."""
    sections = visible_sections(request.user)
    section = _selected_section(request, sections)
    return {
        "sections": sections,
        "section": section,
        "can_edit": section is not None
        and can_edit_section_agenda(request.user, section),
    }


def _grid_context(request):
    """`_agenda_scope` plus the month of day cells it renders."""
    context = _agenda_scope(request)
    section = context["section"]
    if section is None:
        return context

    month_start = _selected_month(request)
    days = _month_days(month_start)
    # One pass over the activities rather than a filter per cell: a week-end
    # lands in several days of the grid at once.
    by_day = defaultdict(list)
    for event in _events_in(section, days[0][0], days[-1][-1]):
        day = event.start_date
        while day <= event.last_date:
            by_day[day].append(event)
            day += timedelta(days=1)

    context.update(
        {
            "month_start": month_start,
            "previous_month": _shift_month(month_start, -1),
            "next_month": _shift_month(month_start, 1),
            "today": timezone.localdate(),
            "weeks": [
                [
                    {
                        "date": day,
                        "events": by_day.get(day, []),
                        "in_month": day.month == month_start.month,
                    }
                    for day in week
                ]
                for week in days
            ],
        }
    )
    return context


def _agenda_url(section, day=None):
    """The agenda page for `section`, opened on the month `day` falls in."""
    params = {"section": section.pk}
    if day is not None:
        params["month"] = f"{day.year:04d}-{day.month:02d}"
    return f"{reverse('members:agenda')}?{urlencode(params)}"


@login_required
@requires_module(AGENDA)
def agenda(request):
    """The section agenda: a month grid, and a frame for the chosen day."""
    return render(request, "members/agenda.html", _grid_context(request))


@login_required
@requires_module(AGENDA)
def agenda_grid(request):
    """Just the month grid, for the arrows and the section picker (HTMX)."""
    context = _grid_context(request)
    if context["section"] is None:
        raise Http404
    return render(request, "members/_agenda_grid.html", context)


def _absences_by_event(user, events, sees_every_notice):
    """The absence notices to show against each activity, keyed by event id.

    Whoever answers "who is missing on Saturday?" sees the whole list: the
    section's own leaders, and unit staff, who may read any section's agenda
    and run the outing when a leader is away. The list is who is *not* coming,
    which is exactly what the day view is opened for on the morning of an
    activity.

    A family sees only the notices it is party to. The day view has no business
    telling one parent which of the other children will be away.
    """
    if not events:
        return {}

    notices = Absence.objects.filter(event__in=events).select_related(
        "child", "reported_by"
    )
    if not sees_every_notice:
        person = get_person(user)
        if person is None:
            return {}
        # Either parent may have been the one to report, so the child's parents
        # are checked as well as the reporter.
        notices = notices.filter(Q(reported_by=person) | Q(child__parents=person))

    by_event = defaultdict(list)
    for absence in notices.order_by("child__last_name", "child__first_name").distinct():
        by_event[absence.event_id].append(absence)
    return by_event


@login_required
@requires_module(AGENDA)
def agenda_day(request):
    """The activities of one day, into the frame beneath the grid (HTMX)."""
    context = _agenda_scope(request)
    section = context["section"]
    if section is None:
        raise Http404
    day = _selected_day(request)
    events = list(_events_on(section, day))
    # The notices are hung off the activity they belong to rather than passed
    # as a dict: a Django template cannot look a dict up by a variable key, and
    # this keeps the day template a plain nested loop.
    sees_every_notice = context["can_edit"] or can_manage_unit(request.user)
    notices = _absences_by_event(request.user, events, sees_every_notice)
    for event in events:
        event.notices = notices.get(event.pk, [])

    context.update(
        {
            "day": day,
            "events": events,
            # Whether this reader has a child to report for at all; the day
            # view offers the button per activity only when they do.
            "can_report": reportable_children(request.user, section).exists(),
        }
    )
    return render(request, "members/_agenda_day.html", context)


@login_required
@requires_module(AGENDA)
def agenda_event_create(request):
    """Add an activity to a section the user leads."""
    sections = visible_sections(request.user)
    section = _selected_section(request, sections)
    if section is None or not can_edit_section_agenda(request.user, section):
        raise Http404

    if request.method == "POST":
        form = SectionEventForm(request.POST, section=section)
        if form.is_valid():
            event = form.save()
            messages.success(
                request, _("The activity has been added to the agenda.")
            )
            return redirect(_agenda_url(section, event.start_date))
    else:
        form = SectionEventForm(section=section, initial=_prefilled_day(request))
    return render(
        request,
        "members/agenda_event_form.html",
        {"form": form, "section": section, "event": None},
    )


def _prefilled_day(request):
    """A ``?date=`` on the URL prefills a new activity's first day."""
    raw = request.GET.get("date")
    if not raw:
        return {}
    try:
        return {"start_date": date.fromisoformat(raw)}
    except ValueError:
        return {}


@login_required
@requires_module(AGENDA)
def agenda_event_edit(request, pk):
    """Edit one activity, if the user leads the section it belongs to."""
    event = get_object_or_404(SectionEvent, pk=pk)
    if not can_edit_section_agenda(request.user, event.section):
        raise Http404

    if request.method == "POST":
        form = SectionEventForm(request.POST, instance=event, section=event.section)
        if form.is_valid():
            event = form.save()
            messages.success(request, _("The activity has been updated."))
            return redirect(_agenda_url(event.section, event.start_date))
    else:
        form = SectionEventForm(instance=event, section=event.section)
    return render(
        request,
        "members/agenda_event_form.html",
        {"form": form, "section": event.section, "event": event},
    )


@login_required
@requires_module(AGENDA)
@require_POST
def agenda_event_delete(request, pk):
    """Remove one activity, if the user leads the section it belongs to."""
    event = get_object_or_404(SectionEvent, pk=pk)
    if not can_edit_section_agenda(request.user, event.section):
        raise Http404
    section, day = event.section, event.start_date
    event.delete()
    messages.success(request, _("The activity has been removed from the agenda."))
    return redirect(_agenda_url(section, day))


@login_required
@requires_module(AGENDA)
def absence_report(request, pk):
    """Report a child absent from one activity, or correct a notice.

    Reached from the day the activity falls on. A parent is the only person who
    reports an absence, and only for a child of theirs enrolled in that
    section, so anything else is a 404 rather than a refusal.
    """
    event = get_object_or_404(SectionEvent, pk=pk)
    section = event.section
    if event.is_past or not reportable_children(request.user, section).exists():
        raise Http404

    if request.method == "POST":
        form = AbsenceForm(request.POST, event=event, user=request.user)
        if form.is_valid():
            absence = form.save()
            notify_section(absence, _agenda_url(section, event.start_date))
            messages.success(
                request, _("The absence has been reported to the section.")
            )
            return redirect(_agenda_url(section, event.start_date))
    else:
        form = AbsenceForm(event=event, user=request.user)

    return render(
        request,
        "members/absence_form.html",
        {"form": form, "event": event, "section": section},
    )


@login_required
@requires_module(AGENDA)
@require_POST
def absence_cancel(request, pk):
    """Withdraw an absence notice: the child's family, or a section leader.

    A family withdraws a notice when the child turns out to be coming after
    all; a leader clears one that was reported twice or that no longer holds.
    """
    absence = get_object_or_404(Absence, pk=pk)
    event = absence.event
    person = get_person(request.user)
    is_family = person is not None and absence.child.parents.filter(
        pk=person.pk
    ).exists()
    if not (
        is_family or can_edit_section_agenda(request.user, section=event.section)
    ):
        raise Http404

    absence.delete()
    messages.success(request, _("The absence has been withdrawn."))
    return redirect(_agenda_url(event.section, event.start_date))


# --- Member import and export ------------------------------------------------
#
# The page, its preview and its downloads. All of the reading, writing and rule
# checking lives in `members.importexport`; this is the HTTP around it.


#: Where an uploaded file waits between the preview and the confirmation.
#: Sessions are database-backed, so the two POSTs may be served by different
#: workers and still agree about what was uploaded.
IMPORT_SESSION_KEY = "member_import"

#: The largest upload worth carrying in a session row. Two megabytes of CSV is
#: some twenty thousand members, which is far past any troop's roster.
IMPORT_MAX_BYTES = 2 * 1024 * 1024

#: How many problem rows the preview spells out. Past this it says how many
#: more there are rather than rendering a page nobody can read.
PREVIEW_ROW_LIMIT = 200

EXPORT_CONTENT_TYPES = {
    "csv": "text/csv; charset=utf-8",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def _import_file_error(error):
    """The reader's own words for a file it could not make sense of.

    ``FileError`` carries either one of the short codes the readers raise or,
    when it comes from the planner, a finished sentence about a missing column.
    """
    return {
        "empty": _("The file is empty."),
        "unreadable": _("The file could not be read. Upload a CSV or an XLSX file."),
        "no-headers": _("No column in the file matches the format."),
    }.get(str(error), str(error))


def _column_hints():
    """What each kind of column accepts, in the reader's language.

    Built per request rather than declared at module level: a translated string
    evaluated at import time is frozen in whatever language the process started
    in.
    """
    return {
        "date": _("A date, e.g. 2020-05-04 or 04/05/2020."),
        "sex": _("M for a boy, F for a girl."),
        "bool": _("yes or no."),
        "role": _("A role's short code, or its name."),
        "roles": _("Role short codes or names, separated by semicolons."),
        "list": _("Separate several values with a semicolon."),
        "section": _("A section name, or branch:name when two sections share one."),
        "status": _("a (active), ar (archived) or r (requested)."),
        "amount": _("An amount, e.g. 12.50."),
        "year": _("The year the school year starts in, e.g. 2025."),
        "text": "",
    }


def _legend(column_set):
    hints = _column_hints()
    return [
        {"heading": column.heading(), "hint": hints.get(column.kind, "")}
        for column in column_set
    ]


def _stash_uploads(request, member_upload, payment_upload):
    """Keep the uploaded files for the confirmation that follows the preview.

    In the session rather than on disk: a file left behind by a preview nobody
    confirmed is a copy of the troop's member list sitting in the media folder,
    and a session row expires itself.
    """
    stash = {}
    for key, upload in (("members", member_upload), ("payments", payment_upload)):
        if upload is None:
            continue
        if upload.size > IMPORT_MAX_BYTES:
            raise ValueError(
                _("“%(name)s” is larger than %(limit)s MB.")
                % {"name": upload.name, "limit": IMPORT_MAX_BYTES // (1024 * 1024)}
            )
        stash[key] = {
            "name": upload.name,
            "data": base64.b64encode(upload.read()).decode("ascii"),
        }
    request.session[IMPORT_SESSION_KEY] = stash
    return stash


def _stashed_uploads(request):
    """``{which: (filename, bytes)}`` for the files a preview left behind."""
    stash = request.session.get(IMPORT_SESSION_KEY) or {}
    return {
        key: (entry["name"], base64.b64decode(entry["data"]))
        for key, entry in stash.items()
    }


def _plan_from_uploads(uploads):
    """Build the plan the preview shows and the confirmation applies."""
    member_name, member_data = uploads["members"]
    # Read against the widest member format — the export's balances included —
    # so a file exported from here imports without the import complaining about
    # three columns the export itself wrote. They are read and dropped.
    member_table = read_table(
        member_name, member_data, column_set=cols.member_columns(include_balances=True)
    )
    payment_table = None
    if "payments" in uploads:
        payment_name, payment_data = uploads["payments"]
        payment_table = read_table(
            payment_name, payment_data, column_set=cols.PAYMENT_COLUMNS
        )
    return build_plan(member_table, payment_table)


def _import_context(request):
    """What the page needs whichever step of the flow it is rendering."""
    troop = TroopSettings.get_settings()
    return {
        "fees_enabled": troop.fees_enabled,
        "member_legend": _legend(cols.MEMBER_COLUMNS),
        "payment_legend": _legend(cols.PAYMENT_COLUMNS) if troop.fees_enabled else [],
        "balance_headings": (
            [column.heading() for column in cols.BALANCE_COLUMNS]
            if troop.fees_enabled
            else []
        ),
        "max_megabytes": IMPORT_MAX_BYTES // (1024 * 1024),
    }


def _preview_context(plan):
    """The problem rows, which are the ones worth reading."""
    problems = [
        row
        for row in plan.members + plan.payments
        if row.errors or row.warnings
    ]
    return {
        "plan": plan,
        "counts": plan.counts(),
        "problems": problems[:PREVIEW_ROW_LIMIT],
        "problem_total": len(problems),
    }


class MemberImportView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    """Staff page: import a member file, export one, or download a template.

    ``LoginRequiredMixin`` first, so an anonymous visitor is sent to the login
    page rather than shown a bare 403.
    """

    template_name = "members/import.html"

    def test_func(self):
        return self.request.user.is_staff

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_import_context(self.request))
        context.setdefault("plan", None)
        return context

    def post(self, request, *args, **kwargs):
        action = request.POST.get("action", "")
        if action == "preview":
            return self._preview(request)
        if action == "apply":
            return self._apply(request)
        if action == "cancel":
            request.session.pop(IMPORT_SESSION_KEY, None)
            messages.success(request, _("Nothing was imported."))
            return redirect(reverse("members:member_import"))
        return redirect(reverse("members:member_import"))

    def _preview(self, request):
        if request.FILES.get("members") is None:
            messages.error(request, _("Choose a file to import."))
            return redirect(reverse("members:member_import"))
        try:
            _stash_uploads(
                request, request.FILES.get("members"), request.FILES.get("payments")
            )
        except ValueError as error:
            messages.error(request, str(error))
            return redirect(reverse("members:member_import"))
        return self._render(request)

    def _apply(self, request):
        uploads = _stashed_uploads(request)
        if "members" not in uploads:
            messages.error(request, _("The upload has expired; choose the file again."))
            return redirect(reverse("members:member_import"))
        plan = self._build(request, uploads)
        if plan is None:
            return redirect(reverse("members:member_import"))
        if plan.has_errors:
            messages.error(request, _("Nothing was imported: the file has errors."))
            return self._render_preview(request, plan)
        counts = apply_plan(plan, actor=get_person(request.user))
        request.session.pop(IMPORT_SESSION_KEY, None)
        messages.success(
            request,
            _(
                "%(created)s members created, %(updated)s updated, "
                "%(payments)s payments recorded."
            )
            % {
                "created": counts["members_created"],
                "updated": counts["members_updated"],
                "payments": counts["payments_created"],
            },
        )
        return redirect(reverse("members:member_import"))

    def _build(self, request, uploads):
        try:
            return _plan_from_uploads(uploads)
        except FileError as error:
            messages.error(request, _import_file_error(error))
            return None

    def _render(self, request, uploads=None):
        """Show the preview, or go back to the page when the file is unreadable."""
        plan = self._build(request, uploads or _stashed_uploads(request))
        if plan is None:
            return redirect(reverse("members:member_import"))
        return self._render_preview(request, plan)

    def _render_preview(self, request, plan):
        context = self.get_context_data()
        context.update(_preview_context(plan))
        return render(request, self.template_name, context)


class ExportDownloadView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Staff-only download: the member table, the payment table or a template."""

    def test_func(self):
        return self.request.user.is_staff

    def get(self, request, kind, extension):
        if extension not in EXPORT_CONTENT_TYPES:
            raise Http404
        fees = TroopSettings.get_settings().fees_enabled
        if kind == "template":
            column_set, records, title = cols.MEMBER_COLUMNS, [], _("Members")
        elif kind == "members":
            column_set = cols.member_columns(include_balances=fees)
            records = exporter.member_records(include_balances=fees)
            title = _("Members")
        elif kind == "payments" and fees:
            column_set, records, title = (
                cols.PAYMENT_COLUMNS,
                exporter.payment_records(),
                _("Payments"),
            )
        else:
            raise Http404

        payload = write_table(column_set, records, extension, title=title)
        response = HttpResponse(payload, content_type=EXPORT_CONTENT_TYPES[extension])
        stamp = timezone.localdate().isoformat()
        name = f"{kind}-{stamp}.{extension}" if kind != "template" else f"members-template.{extension}"
        response["Content-Disposition"] = f'attachment; filename="{name}"'
        # A download of the troop's own member list has no business being kept
        # by anything between here and the browser.
        response["Cache-Control"] = "no-store"
        return response
