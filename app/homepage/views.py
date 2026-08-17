import json
import re
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

# GrapesJS exports its canvas wrapper as a literal <body> element. Injected
# mid-page, the browser merges that tag's attributes onto the real <body>,
# so wrapper styling (padding, background…) shifts the whole page chrome.
# The attribute part is quote-aware so a ">" inside an attribute cannot end
# the tag early.
_TAG_ATTRS = r"(?:\"[^\"]*\"|'[^']*'|[^>])"
_WRAPPER_OPEN_RE = re.compile(
    rf"^\s*(?:<html{_TAG_ATTRS}*>\s*)?<body{_TAG_ATTRS}*>", re.IGNORECASE
)
_WRAPPER_CLOSE_RE = re.compile(r"</body>\s*(?:</html>\s*)?$", re.IGNORECASE)
# CSS selectors that target the page itself rather than editor content.
_WRAPPER_SELECTORS = {"", "html", "body", "*"}


# The FAQ page renders a fixed hat banner above edited content (like the
# other pages). Content saved before the banner existed still embeds the
# masthead card the old default snippet seeded, duplicating the title.
# Stripped at both render and save; the Home page keeps its card (it is
# real content there, and "masthead" carries no styling of its own).
_FAQ_MASTHEAD_RE = re.compile(r"<header class=\"masthead\">.*?</header>", re.DOTALL)
_FAQ_EMPTIED_CONTAINER_RE = re.compile(r"<div class=\"container row\">\s*</div>")


def _strip_legacy_faq_header(html):
    """Drop the pre-banner masthead card (and its emptied wrapper) from FAQ HTML."""
    if not html:
        return html
    html = _FAQ_MASTHEAD_RE.sub("", html)
    html = _FAQ_EMPTIED_CONTAINER_RE.sub("", html)
    return html.strip()


def _sanitize_html(html):
    """Unwrap the GrapesJS <body> wrapper from saved editor HTML."""
    if not html:
        return html
    html = _WRAPPER_OPEN_RE.sub("", html)
    html = _WRAPPER_CLOSE_RE.sub("", html)
    return html.strip()


def _has_content(project_json):
    """Whether a saved project actually holds editable content.

    An empty project ({"pages": []} or pages without components — e.g. from
    an abandoned editor session) must seed the canvas with the current page
    look instead of loading a blank project.
    """
    if not project_json:
        return False
    try:
        project = json.loads(project_json)
    except (TypeError, json.JSONDecodeError):
        return False
    pages = project.get("pages") if isinstance(project, dict) else None
    if not isinstance(pages, list):
        return False
    return any(page.get("component") or page.get("components") for page in pages)


def _sanitize_css(css):
    """Drop wrapper-targeting (html/body/*) rules from saved editor CSS.

    Scans rule by rule (brace-matching) so dropped rules cannot swallow the
    next one, and recurses into at-rule blocks (@media…) to catch responsive
    wrapper styling.
    """
    if not css:
        return css
    kept = []
    pos = 0
    while True:
        brace = css.find("{", pos)
        if brace == -1:
            kept.append(css[pos:])
            break
        selector = css[pos:brace]
        # Find the matching close brace, counting nested braces (@media…).
        depth = 1
        end = brace + 1
        while end < len(css) and depth:
            if css[end] == "{":
                depth += 1
            elif css[end] == "}":
                depth -= 1
            end += 1
        selectors = [part.strip() for part in selector.split(",")]
        if selectors and all(part in _WRAPPER_SELECTORS for part in selectors):
            pass  # wrapper rule: drop selector + block entirely
        elif selector.strip().startswith("@"):
            kept.append(selector + "{" + _sanitize_css(css[brace + 1 : end - 1]) + "}")
        else:
            kept.append(selector + css[brace:end])
        pos = end
    return "".join(kept).strip()


def _edited_context(page):
    """Context entries for rendering a page's edited content (if any)."""
    content = SiteContent.get_content(page)
    if content is None:
        return {"page_html": None, "page_css": None}
    # modeltranslation resolves the active language, falling back to French
    # when the current language was never edited. Sanitizing at render (not
    # only at save) also fixes content saved before the wrapper was stripped.
    html = _sanitize_html(content.html)
    if page == SiteContent.Page.FAQ:
        html = _strip_legacy_faq_header(html)
    return {
        "page_html": html,
        "page_css": _sanitize_css(content.css),
    }


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
            if _has_content(project_json):
                seed_html = None
            else:
                # Seed the canvas with the default look, translated for the
                # editor language.
                project_json = None
                seed_html = render_to_string(
                    EDITOR_SEED_TEMPLATES[page], context={"user": self.request.user}
                )

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
            "catStructure": str(_("Structure")),
            "catBasic": str(_("Basic")),
            "blockSection": str(_("Section")),
            "blockColumns": str(_("2 columns")),
            "blockColumns3": str(_("3 columns")),
            "blockHeading": str(_("Heading")),
            "blockText": str(_("Text")),
            "blockTextContent": str(_("Your text here.")),
            "blockImage": str(_("Image")),
            "blockButton": str(_("Button")),
            "blockButtonContent": str(_("Click here")),
            "blockDivider": str(_("Divider")),
            "sectorDimension": str(_("Dimensions")),
            "sectorTypography": str(_("Typography")),
            "sectorDecorations": str(_("Decorations")),
            "sectorExtra": str(_("Extra")),
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
        # The project arrives as a parsed JSON object; re-serialize it so the
        # TextField holds real JSON (str(dict) would store a Python repr).
        project = data.get("project")
        html = _sanitize_html(data.get("html"))
        css = _sanitize_css(data.get("css"))
        if page == SiteContent.Page.FAQ:
            html = _strip_legacy_faq_header(html)
        with override(lang):
            content, _ = SiteContent.objects.get_or_create(page=page)
            content.project_json = (
                json.dumps(project, ensure_ascii=False) if project else None
            )
            content.html = html or None
            content.css = css or None
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
