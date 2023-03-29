from django.shortcuts import render, redirect
from django.urls import reverse_lazy
from django.views.generic import TemplateView, CreateView, UpdateView, ListView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from .forms import AdultUserChangeForm, ChildForm, ChildFromKey, AdminUserUpdateForm
from .models import CustomUser, CustomGroup
from .filters import UsersFilter
from django.http import Http404, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404
import json
from post_office import mail
from django.db.models import Q
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

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(**kwargs)
        year = self.request.GET.get("year", None)
        context["filter"] = UsersFilter(self.request.GET, queryset=self.get_queryset())
        print(context["filter"].qs)
        for item in context["filter"].qs:
            item.year_section = item.get_section_year(year)
            item.type_adulte = item.get_adulte()
        return context

    def test_func(self):
        return self.request.user.groups.filter(name="InscriptionAdmin").exists()


class AdminUpdateView(UserPassesTestMixin, UpdateView):
    form_class = AdminUserUpdateForm
    model = CustomUser
    template_name = "members/admin_update.html"
    success_url = reverse_lazy("members:admin_list")

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
        # Seuls les adultes peuvent créer un compte, les adultes peuvent être parents passif, parents actifs ou animateurs
        form.fields["group"].initial = self.object.groups.filter(
            customgroup__parents__parents__name="Adulte"
        ).first()

        return self.render_to_response(self.get_context_data(form=form))


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
            child.save()
            child.parents.add(request.user)
            child.groups.add(CustomGroup.objects.get(name="Demandée"))

            # mail.send(
            #     "tomdebruyne@gmail.com",
            #     "staffunite@scouts-limal.be",
            #     subject=f"La demande d'inscription de {child.first_name} est bien arrivée",
            #     message="Hi there",
            #     html_message="Hi <strong>there</strong>!",
            # )
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


# class ProfileView(LoginRequiredMixin, ListView):
#     model = CustomUser
#     template_name = "members/profile.html"

#     def get_queryset(self):
#         return CustomUser.objects.filter(username=self.request.user)
