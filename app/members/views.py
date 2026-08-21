import json

# from django.contrib.auth import get_user_model
from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.sites.models import Site
from django.http import Http404, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils.translation import gettext as _
from django.views.generic import ListView, TemplateView, UpdateView
from post_office import mail

from .constants import (
    ERROR_MESSAGES,
)
from .filters import PersonFilter
from .forms import (
    AdminUserUpdateForm,
    AnimeProfileForm,
    ChildForm,
    ChildFromKey,
    OnboardingForm,
    ProfileEditForm,
)
from .models import (
    Account,
    ImportantDocument,
    Person,
    Role,
    SchoolYear,
    get_registration_admins,
)


class Login(TemplateView):
    template_name = "members/login.html"


class OnboardingView(LoginRequiredMixin, TemplateView):
    template_name = "members/onboarding.html"

    def dispatch(self, request, *args, **kwargs):
        # If profile is already completed, redirect to homepage
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

    # Define sortable fields and their corresponding model fields
    sortable_fields = {
        "first_name": "first_name",
        "last_name": "last_name",
        "birthday": "birthday",
        "sex": "sex",
        # Note: section and role are computed fields, not directly sortable
    }

    def get_ordering(self):
        """
        Get the ordering based on the request parameters
        """
        ordering = self.request.GET.get(
            "sort", "last_name"
        )  # Default sort by last_name
        direction = self.request.GET.get("direction", "asc")  # Default ascending

        # Check if the requested field is sortable
        if ordering in self.sortable_fields:
            field = self.sortable_fields[ordering]
            if direction == "desc":
                return f"-{field}"
            return field

        # Default ordering
        return "last_name"

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(**kwargs)

        # Get the selected year from the request, default to current year if not specified
        selected_year_id = self.request.GET.get("year", None)
        if selected_year_id:
            selected_year = SchoolYear.objects.get(pk=selected_year_id)
        else:
            selected_year = SchoolYear.current()

        # Create the filter with the current queryset
        context["filter"] = PersonFilter(self.request.GET, queryset=self.get_queryset())

        # For each person in the (paginated) object_list, add their section for the selected year
        for person in context["object_list"]:
            try:
                enrollment = person.enrollment_set.filter(
                    school_year=selected_year
                ).select_related("section__branch").first()
                person.section_display = enrollment.section.name if enrollment else "-"
                # Check age compatibility with section's branch
                person.age_mismatch = False
                if enrollment and person.birthday and enrollment.section.branch:
                    age_at_dec_31 = selected_year.name - person.birthday.year
                    branch = enrollment.section.branch
                    if branch.min_age_dec_31 is not None and branch.max_age_dec_31 is not None:
                        if not (branch.min_age_dec_31 <= age_at_dec_31 <= branch.max_age_dec_31):
                            person.age_mismatch = True
                            person.age_mismatch_detail = _(
                                "%(age)s years old — branch %(branch)s: "
                                "%(min)s-%(max)s years old"
                            ) % {
                                "age": age_at_dec_31,
                                "branch": branch.name,
                                "min": branch.min_age_dec_31,
                                "max": branch.max_age_dec_31,
                            }
            except (SchoolYear.DoesNotExist, AttributeError):
                person.section_display = "-"
                person.age_mismatch = False

            # Get the primary role
            person.role = Role.objects.get(id=person.primary_role_id)
            #     person=person, role__is_primary=True
            # ).first()
            # person.role = primary_role.role.name if primary_role else "-"

        # Add sorting information to context
        context["current_sort"] = self.request.GET.get("sort", "last_name")
        context["current_direction"] = self.request.GET.get("direction", "asc")
        context["sortable_fields"] = self.sortable_fields.keys()

        # Define field names and their display names
        context["fields_map"] = [
            ("first_name", _("First name")),
            ("last_name", _("Last name")),
            ("birthday", _("Date of birth")),
            ("sex", _("Sex")),
            ("section", _("Section")),
            ("primary_role", _("Role")),
        ]

        return context

    def get_queryset(self):
        queryset = super().get_queryset()
        queryset = PersonFilter(self.request.GET, queryset=queryset).qs

        # Apply ordering
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
        return context

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        form_class = self.get_form_class()
        form = form_class(instance=self.object)

        # Set initial values for the form fields
        if hasattr(self.object, "account"):
            form.fields["email"].initial = self.object.account.email

        # Get current section enrollment
        try:
            current_year = SchoolYear.current()
            enrollment = self.object.enrollment_set.filter(
                school_year=current_year
            ).first()
            if enrollment:
                form.fields["current_section"].initial = enrollment.section
        except (AttributeError, KeyError):
            pass

        # Get next section enrollment if it exists
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

    # def form_valid(self, form):
    #     messages.success(self.request, SUCCESS_MESSAGES["profile_updated"])
    #     return super().form_valid(form)


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
                mail.send(
                    recipients=request.user.email,
                    sender=settings.DEFAULT_FROM_EMAIL,
                    template="new_child_parent",
                    language=getattr(request.user, "preferred_language", None) or settings.LANGUAGE_CODE,
                    context={
                        "first_name": child.first_name,
                        "last_name": child.last_name,
                        "parent": f"{request.user.person.first_name} {request.user.person.last_name}",
                    },
                )
            mail.send(
                recipients=get_registration_admins(),
                # sender="tom@tomctl.be",
                sender="MS_M3qCdl@tomctl.be",
                template="new_child_staff",
                # Staff notifications are sent in the site default language.
                language=settings.LANGUAGE_CODE,
                context={
                    "first_name": child.first_name,
                    "last_name": child.last_name,
                    "url": f"{Site.objects.get_current()}/users/adminupdate/{child.id}",
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
    if not request.META.get("HTTP_HX_REQUEST") == "true":
        return HttpResponseBadRequest(_("Invalid request"))
    return render(
        request,
        "members/child_list.html",
        {
            "children": Person.objects.filter(parents__id=request.user.person.id),
        },
    )


def edit_child(request, pk):
    if not request.META.get("HTTP_HX_REQUEST") == "true":
        return HttpResponseBadRequest(_("Invalid request"))
    parent_person_id = Account.objects.get(id=request.user.id).person.id
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


def dettach_child(request, pk):
    context = {"allow_dettach": False}
    child = get_object_or_404(Person, id=pk)
    parent = request.user.person
    context["child"] = child
    if not child.parents.filter(id=parent.id).exists():
        context["message"] = _("%(first)s is not attached to your account.") % {
            "first": child.first_name
        }
    elif child.parents.count() < 2 and not child.is_adult() and not child.has_account:
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
    if not child.parents.filter(id=parent.id).exists():
        return redirect(reverse_lazy("members:profile", kwargs={"pk": request.user.pk}))
    # Enforce at least one parent remains after detach
    if child.parents.count() <= 1:
        return redirect(reverse_lazy("members:profile", kwargs={"pk": request.user.pk}))
    child.parents.remove(parent)
    return redirect(reverse_lazy("members:profile", kwargs={"pk": request.user.pk}))


def deregister_child(request, pk):
    child = get_object_or_404(Person, id=pk)
    parent = request.user.person

    if not child.parents.filter(id=parent.id).exists():
        return redirect(reverse_lazy("members:profile", kwargs={"pk": request.user.pk}))

    context = {"allow_deregister": False}
    context["child"] = child
    if child.parents.filter(id=parent.id).exists():
        context["allow_deregister"] = True
    return render(
        request=request, template_name="members/deregister_child.html", context=context
    )


def deregister_confirm(request, pk, action):
    child = get_object_or_404(Person, id=pk)
    parent = request.user.person
    if not child.parents.filter(id=parent.id).exists():
        return redirect(reverse_lazy("members:profile", kwargs={"pk": request.user.pk}))
    # Set status to archived
    from django.utils import timezone
    child.status = "ar"
    child.archived_date = timezone.now().date()
    child.save()
    return redirect(reverse_lazy("members:profile", kwargs={"pk": request.user.pk}))


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


# class ProfileView(LoginRequiredMixin, ListView):
#     model = CustomUser
#     template_name = "members/profile.html"

#     def get_queryset(self):
#         return CustomUser.objects.filter(username=self.request.user)


class DocumentListView(LoginRequiredMixin, ListView):
    model = ImportantDocument
    template_name = "members/documents.html"
    context_object_name = "documents"
