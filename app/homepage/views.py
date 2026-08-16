import json
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.mixins import UserPassesTestMixin
from django.core.exceptions import ValidationError
from django.http import HttpResponseBadRequest, JsonResponse
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.utils.translation import override
from django.views import View
from django.views.generic import TemplateView

from homepage.models import Event, ImageAsset, SiteContent

# Languages offered in the editor's language tabs (modeltranslation languages).
EDITOR_LANGUAGES = settings.MODELTRANSLATION_LANGUAGES

# Default markup seeded into the editor when a page/language was never edited,
# so first-time editing starts from the current look.
EDITOR_SEED_TEMPLATES = {
    SiteContent.Page.HOME: "homepage/snippets/home_default.html",
    SiteContent.Page.FAQ: "homepage/snippets/faq_default.html",
}


def _edited_context(page):
    """Context entries for rendering a page's edited content (if any)."""
    content = SiteContent.get_content(page)
    if content is None:
        return {"page_html": None, "page_css": None}
    # modeltranslation resolves the active language, falling back to French
    # when the current language was never edited.
    return {"page_html": content.html, "page_css": content.css}


class HomePage(TemplateView):
    template_name = "homepage/home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_edited_context(SiteContent.Page.HOME))
        return context


class FAQ(TemplateView):
    template_name = "homepage/faq.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_edited_context(SiteContent.Page.FAQ))
        return context


class Agenda(TemplateView):
    template_name = "homepage/agenda.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.now().date()
        cutoff = today - timedelta(days=30)
        # Show events from the last 30 days onwards (future + recent past)
        context["events"] = Event.objects.filter(date__gte=cutoff).order_by("date")
        return context


class HomePageEditorView(UserPassesTestMixin, TemplateView):
    """Full-page GrapesJS editor for the Home/FAQ content, superuser-only."""

    template_name = "homepage/editor.html"

    def test_func(self):
        return self.request.user.is_superuser

    def get(self, request, *args, **kwargs):
        # Validate page/lang from query params before rendering.
        try:
            kwargs["page"] = SiteContent.Page(request.GET.get("page", "home"))
        except ValueError:
            return HttpResponseBadRequest("Invalid page.")
        kwargs["lang"] = request.GET.get("lang", settings.LANGUAGE_CODE)
        if kwargs["lang"] not in EDITOR_LANGUAGES:
            return HttpResponseBadRequest("Invalid language.")
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        page = kwargs["page"]
        lang = kwargs["lang"]

        content = SiteContent.get_content(page)
        with override(lang):
            project_json = content.project_json if content else None
            if not project_json:
                # Seed the canvas with the default look, translated for the
                # editor language.
                seed_html = render_to_string(
                    EDITOR_SEED_TEMPLATES[page], context={"user": self.request.user}
                )
            else:
                seed_html = None

        context["page"] = page
        context["lang"] = lang
        context["project_json"] = project_json
        context["seed_html"] = seed_html
        context["assets"] = [
            {"src": asset.file.url, "name": asset.original_name}
            for asset in ImageAsset.objects.all()
        ]
        context["editor_strings"] = {
            "uploadFailed": str(_("Image upload failed.")),
            "saveFailed": str(_("Save failed.")),
        }
        return context


class HomePageEditorSaveView(UserPassesTestMixin, View):
    """Persist editor output: {page, lang, project, html, css} JSON body."""

    def test_func(self):
        return self.request.user.is_superuser

    def post(self, request, *args, **kwargs):
        try:
            data = json.loads(request.body)
            page = SiteContent.Page(data["page"])
            lang = data["lang"]
        except (json.JSONDecodeError, KeyError, ValueError):
            return HttpResponseBadRequest("Invalid payload.")
        if lang not in EDITOR_LANGUAGES:
            return HttpResponseBadRequest("Invalid language.")

        # Empty string => None so a cleared language falls back to French.
        with override(lang):
            content, _ = SiteContent.objects.get_or_create(page=page)
            content.project_json = data.get("project") or None
            content.html = data.get("html") or None
            content.css = data.get("css") or None
            content.save()
        return JsonResponse({"ok": True})


class HomePageEditorAssetsView(UserPassesTestMixin, View):
    """List uploaded images (GET) and store a new upload (POST, multipart)."""

    def test_func(self):
        return self.request.user.is_superuser

    def get(self, request, *args, **kwargs):
        assets = [
            {"src": asset.file.url, "name": asset.original_name}
            for asset in ImageAsset.objects.all()
        ]
        return JsonResponse({"assets": assets})

    def post(self, request, *args, **kwargs):
        upload = request.FILES.get("file")
        if upload is None:
            return HttpResponseBadRequest("Missing file.")
        asset = ImageAsset(file=upload, original_name=upload.name)
        try:
            asset.full_clean()
        except ValidationError:
            return HttpResponseBadRequest("Invalid file.")
        asset.save()
        return JsonResponse({"src": asset.file.url, "name": asset.original_name})
