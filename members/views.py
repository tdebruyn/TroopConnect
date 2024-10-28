from django.shortcuts import render, redirect
from django.urls import reverse_lazy
from django.views.generic import TemplateView, UpdateView, ListView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.sites.models import Site
from django.http import Http404, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext as _
from django.contrib.auth import get_user_model
from allauth.account.views import (
    PasswordResetView,
    PasswordResetFromKeyView,
    PasswordResetDoneView,
)


from .forms import (
    AdultUserChangeForm,
    ChildForm,
    ChildChangeForm,
    ChildFromKey,
    AdminUserUpdateForm,
    ChildAccountCreateForm,
    ChildAccountCreateConfirmForm,
)
from .models import CustomUser, CustomGroup, SchoolYear, get_registration_admins
from .filters import UsersFilter
import json
from post_office import mail
from shortuuid import uuid


class Login(TemplateView):
    template_name = "members/login.html"


class AdminListView(UserPassesTestMixin, ListView):
    """
    Filter : first_name + totem, last_name, birthday (upper, lower), year selection, parents/members/all
    List: first_name + totem, last_name, if adult => adult type, section or status
    """

    model = CustomUser
    fields = "__all__"
    template_name = "members/admin_list.html"
    context_object_name = "members"
    paginate_by = 15

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(**kwargs)
        year = self.request.GET.get("year", None)
        context["filter"] = UsersFilter(self.request.GET, queryset=self.get_queryset())
        for item in context["filter"].qs:
            item.year_section = item.get_section_year(year)
            item.adult_type = item.get_adult()
        return context

    def get_queryset(self):
        queryset = super().get_queryset()
        return UsersFilter(self.request.GET, queryset=queryset).qs

    def test_func(self):
        return self.request.user.groups.filter(name="InscriptionAdmin").exists()


class AdminUpdateView(UserPassesTestMixin, UpdateView):
    form_class = AdminUserUpdateForm
    model = CustomUser
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
        form.fields["adult"].initial = self.object.groups.filter(
            customgroup__parents__parents__name="Adulte"
        ).first()
        form.fields["current_section"].initial = (
            self.object.groups.filter(customgroup__parents__parents__name="Section")
            .filter(customgroup__year=SchoolYear.current())
            .first()
        )
        form.fields["next_section"].initial = (
            self.object.groups.filter(customgroup__parents__parents__name="Section")
            .filter(customgroup__year__name=SchoolYear.current().name + 1)
            .first()
        )
        return self.render_to_response(self.get_context_data(form=form))

    def test_func(self):
        return self.request.user.groups.filter(name="InscriptionAdmin").exists()


class ProfileView(LoginRequiredMixin, UpdateView):
    form_class = AdultUserChangeForm
    model = CustomUser
    template_name = "members/register.html"
    # success_url = reverse_lazy("members:profile", kwargs={'pk': })

    def get_success_url(self):
        return reverse_lazy("members:profile", kwargs={"pk": self.request.user.pk})

    def get_queryset(self):
        queryset = super().get_queryset()
        queryset = queryset.filter(username=self.request.user)
        return queryset

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        if obj.username != str(self.request.user):
            raise Http404
        return obj

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        form_class = self.get_form_class()
        form = form_class(instance=self.object)
        if not self.object.is_adult():
            form.fields["group"] = None
        else:
            form.fields["group"].initial = self.object.groups.filter(
                customgroup__parents__parents__name="Adulte"
            ).first()

        return self.render_to_response(self.get_context_data(form=form))


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
    form.fields["password1"].required = False
    form.fields["password2"].required = False
    form.fields["password1"].widget.attrs["autocomplete"] = "off"
    form.fields["password2"].widget.attrs["autocomplete"] = "off"
    if request.method == "POST":
        form = ChildForm(request.POST)
        if form.is_valid():
            child = form.save(commit=False)
            while (
                not (uuid4 := uuid()[:4])
                or CustomUser.objects.filter(secret_key=uuid).exists()
            ):
                pass
            child.secret_key = uuid4
            child.address = request.user.address
            child.phone = request.user.phone
            child.photo_consent = request.user.photo_consent
            child.save()
            child.parents.add(request.user)
            child.groups.add(CustomGroup.objects.get(name="Demandée"))
            child.groups.add(CustomGroup.objects.get(name="Animé"))

            mail.send(
                recipients=request.user.email,
                sender="staffunite@scouts-limal.be",
                template="new_child_parent",
                context={
                    "first_name": child.first_name,
                    "last_name": child.last_name,
                    "parent": f"{request.user.first_name} {request.user.last_name}",
                },
            )
            mail.send(
                recipients=get_registration_admins(),
                sender="staffunite@scouts-limal.be",
                template="new_child_staff",
                context={
                    "first_name": child.first_name,
                    "last_name": child.last_name,
                    "username": child.username,
                    "url": f"{Site.objects.get_current()}/users/adminupdate/{child.username}",
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
    if not request.META.get("HTTP_HX_REQUEST") == "true":
        return HttpResponseBadRequest("Invalid request")
    return render(
        request,
        "members/child_list.html",
        {
            "children": CustomUser.objects.filter(
                parents__username=request.user.username
            ),
        },
    )


def edit_child(request, pk):
    if not request.META.get("HTTP_HX_REQUEST") == "true":
        return HttpResponseBadRequest("Invalid request")
    child = get_object_or_404(
        CustomUser, pk=pk, parents__username=request.user.username
    )

    if request.method == "POST":
        form = ChildChangeForm(request.POST, instance=child)
        if form.is_valid():
            print(form.cleaned_data.items())
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
        form = ChildChangeForm(instance=child)

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
            child = CustomUser.objects.get(secret_key=form.cleaned_data["secret_key"])
            child.parents.add(request.user)

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
    """
    TODO, déplacer le texte vers le template
    """
    context = {"allow_dettach": False}
    child = CustomUser.objects.get(username=pk)
    context["child"] = child
    if not child.parents.filter(username=request.user).exists():
        context["message"] = _(
            f"{child.first_name} n'est pas attaché à votre utilisateur"
        )
    elif child.parents.count() < 2 and not child.is_adult() and not child.email:
        context["message"] = _(
            f"""Vous ne pouvez pas détacher {child.first_name}.\n
            Pour détacher un enfant, celui-ci doit soit être attaché à d'autres parents, soit avoir plus de 18 ans et avoir un email associé à son utilisateur.\n
                               {child.first_name} a {child.parents.count()} parent(s)\n
                               {child.first_name} est né le {child.birthday} et son adresse mail est {child.email}"""
        )
    else:
        context["message"] = _(
            f'Pour confirmer que vous souhaitez détacher {child.first_name} de votre utilisateur, cliquer sur "Détacher".'
        )
        context["allow_dettach"] = True
    return render(
        request=request, template_name="members/dettach_child.html", context=context
    )


def dettach_confirm(request, pk):
    child = CustomUser.objects.get(username=pk)
    if not child.parents.filter(username=request.user).exists():
        return redirect(reverse_lazy("members:profile", kwargs={"pk": request.user}))
    else:
        parent = CustomUser.objects.get(username=request.user)
        child.parents.remove(parent)
        return redirect(reverse_lazy("members:profile", kwargs={"pk": request.user}))


def deregister_child(request, pk):
    child = CustomUser.objects.get(username=pk)

    if not child.parents.filter(username=request.user).exists():
        return redirect(reverse_lazy("members:profile", kwargs={"pk": request.user}))

    context = {"allow_deregister": False}
    child = CustomUser.objects.get(username=pk)
    context["child"] = child
    if child.parents.filter(username=request.user).exists():
        context["allow_deregister"] = True
    return render(
        request=request, template_name="members/deregister_child.html", context=context
    )


def deregister_confirm(request, pk, action):
    child = CustomUser.objects.get(username=pk)
    if not child.parents.filter(username=request.user).exists():
        return redirect(reverse_lazy("members:profile", kwargs={"pk": request.user}))
    else:
        deregister = CustomGroup.objects.get(name="Désinscrire")
        child.groups.add(deregister)

        return redirect(reverse_lazy("members:profile", kwargs={"pk": request.user}))


def create_year():
    # SchoolYear.
    print("I WAS HERE")


# class ProfileView(LoginRequiredMixin, ListView):
#     model = CustomUser
#     template_name = "members/profile.html"

#     def get_queryset(self):
#         return CustomUser.objects.filter(username=self.request.user)
