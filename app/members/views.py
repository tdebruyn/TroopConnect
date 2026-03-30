from django.shortcuts import render, redirect
from django.urls import reverse_lazy
from django.views.generic import TemplateView, UpdateView, ListView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.sites.models import Site
from django.http import Http404, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext as _
from django.conf import settings

# from django.contrib.auth import get_user_model
from allauth.account.views import (
    PasswordResetView,
    PasswordResetFromKeyView,
    PasswordResetDoneView,
)


from .forms import (
    ProfileEditForm,
    AnimeProfileForm,
    ChildForm,
    ChildFromKey,
    AdminUserUpdateForm,
    ChildAccountCreateForm,
    ChildAccountCreateConfirmForm,
    OnboardingForm,
)
from .models import Person, SchoolYear, Account, Role, get_registration_admins, ImportantDocument
from .filters import PersonFilter
import json
from post_office import mail
from shortuuid import uuid
from .constants import (
    SUCCESS_MESSAGES,
    ERROR_MESSAGES,
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
            initial={
                "first_name": person.first_name,
                "last_name": person.last_name,
                "address": person.address,
                "phone": person.phone,
            }
        )
        return self.render_to_response(self.get_context_data(form=form))

    def post(self, request, *args, **kwargs):
        form = OnboardingForm(request.POST)
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
                            person.age_mismatch_detail = (
                                f"{age_at_dec_31} ans — branche {branch.name} : "
                                f"{branch.min_age_dec_31}-{branch.max_age_dec_31} ans"
                            )
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
            ("first_name", _("Prénom")),
            ("last_name", _("Nom")),
            ("birthday", _("Date de naissance")),
            ("sex", _("Sexe")),
            ("section", _("Section")),
            ("primary_role", _("Rôle")),
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
        # Save the form which will handle Person, Roles, and Enrollments
        person = form.save()

        # Get the email from the form
        email = form.cleaned_data.get("email")

        # Account creation/update is now handled in the form's save method

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
            raise Http404(ERROR_MESSAGES["no_user_found"])

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


class ChildAccountCreate(PasswordResetView):
    template_name = "members/child_account.html"
    success_url = reverse_lazy("members:child_account_create_done")
    form_class = ChildAccountCreateForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["child_user"] = self.kwargs.get("pk")  # Pass the "pk" value to the form
        return kwargs

    def get_email_confirmation_redirect_url(self):
        return reverse_lazy("members:child_account_create_confirm")


class ChildAccountCreateConfirm(PasswordResetFromKeyView):
    form_class = ChildAccountCreateConfirmForm

    def form_valid(self, form):
        form.save(self.request)
        return super().form_valid(form)


class ChildAccountCreateDone(PasswordResetDoneView):
    template_name = "members/child_account_done.html"


def add_new_child_view(request):
    form = ChildForm()
    if request.method == "POST":
        form = ChildForm(request.POST)
        if form.is_valid():
            child = form.save(commit=False)
            child.address = request.user.person.address
            child.phone = request.user.person.phone
            child.photo_consent = request.user.person.photo_consent
            child.save()
            child.parents.add(request.user.person)

            # mail.send(
            #     recipients=request.user.email,
            #     sender="staffunite@scouts-limal.be",
            #     template="new_child_parent",
            #     language="fr",
            #     context={
            #         "first_name": child.first_name,
            #         "last_name": child.last_name,
            #         "parent": f"{request.user.person.first_name} {request.user.person.last_name}",
            #     },
            # )
            mail.send(
                recipients=get_registration_admins(),
                # sender="tom@tomctl.be",
                sender="MS_M3qCdl@tomctl.be",
                template="new_child_staff",
                # language="fr",
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
                            "showMessage": f"{child.first_name} {child.last_name} ajouté.",
                        }
                    )
                },
            )
    return render(request, "members/child_form.html", {"form": form})


def child_list(request):
    # "children" is the list of Person which has request.user.person as one of the parent
    if not request.META.get("HTTP_HX_REQUEST") == "true":
        return HttpResponseBadRequest("Invalid request")
    return render(
        request,
        "members/child_list.html",
        {
            "children": Person.objects.filter(parents__id=request.user.person.id),
        },
    )


def edit_child(request, pk):
    if not request.META.get("HTTP_HX_REQUEST") == "true":
        return HttpResponseBadRequest("Invalid request")
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
                            "showMessage": f"{child.first_name} modifié.",
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
                            "showMessage": f"{child.first_name} {child.last_name} ajouté.",
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
        context["message"] = _(
            f"{child.first_name} n'est pas attaché à votre utilisateur"
        )
    elif child.parents.count() < 2 and not child.is_adult() and not child.has_account:
        context["message"] = _(
            f"""Vous ne pouvez pas détacher {child.first_name}.\n
            Pour détacher un enfant, celui-ci doit soit être attaché à d'autres parents, soit avoir plus de 18 ans et avoir un compte associé.\n
                               {child.first_name} a {child.parents.count()} parent(s)\n
                               {child.first_name} est né le {child.birthday} et {'a un compte' if child.has_account else "n'a pas de compte"}."""
        )
    else:
        context["message"] = _(
            f'Pour confirmer que vous souhaitez détacher {child.first_name} de votre utilisateur, cliquer sur "Détacher".'
        )
        context["allow_dettach"] = True
    return render(
        request=request, template_name="members/dettach_child.html", context=context
    )


def load_secondary_role(request):
    primary = request.GET.get("primary_role")
    form = ProfileEditForm(primary_role_value=primary)
    return render(request, "secondary_role.html", {"form": form})


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


# class ProfileView(LoginRequiredMixin, ListView):
#     model = CustomUser
#     template_name = "members/profile.html"

#     def get_queryset(self):
#         return CustomUser.objects.filter(username=self.request.user)


def get_secondary_role_label(request):
    primary_role = request.GET.get("primary_role", PARENT_ROLE)

    if primary_role == PARENT_ROLE:
        role_label = ROLE_LABELS["ACTIVE_PARENT_ROLE"]
    else:
        role_label = ROLE_LABELS["RESPONSIBLE_ANIMATOR_ROLE"]

    label = SECONDARY_ROLE_LABEL_TEMPLATE.format(role=role_label)
    return HttpResponse(label)


class DocumentListView(LoginRequiredMixin, ListView):
    model = ImportantDocument
    template_name = "members/documents.html"
    context_object_name = "documents"
