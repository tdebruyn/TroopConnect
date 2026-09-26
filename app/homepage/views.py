import json
import re

from django.conf import settings
from django.contrib.auth.mixins import UserPassesTestMixin
from django.core.exceptions import ValidationError
from django.http import HttpResponseBadRequest, JsonResponse
from django.template.loader import render_to_string
from django.utils.translation import gettext_lazy as _
from django.utils.translation import override
from django.views import View
from django.views.generic import TemplateView

from homepage.models import ImageAsset, SiteContent

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


# The FAQ page renders a fixed hat banner above the edited content (like the
# other pages), so a `<header class="masthead">` card inside saved content
# duplicates the title. Stripped at both render and save; the Home page keeps
# its card (it is real content there, and "masthead" carries no styling of its
# own).
_FAQ_EMPTIED_CONTAINER_RE = re.compile(r"<div class=\"container row\">\s*</div>")


# These markers are matched with `str.find` rather than a regex to keep the pass
# linear. An unanchored `<header class="masthead">.*?</header>` walks to the end
# of the document from every position where the opening tag matches, so content
# that repeats that tag without ever closing it costs a scan per repetition.
# A cursor that only ever moves forward costs one pass whatever the input.
_MASTHEAD_OPEN = '<header class="masthead">'
_MASTHEAD_CLOSE = "</header>"
_HERO_ROW_OPEN = '<div class="container row">'
_HERO_ROW_CLOSE = "</div>"


def _cut_mastheads(html):
    """Drop every `<header class="masthead">…</header>` element from `html`."""
    pieces = []
    pos = 0
    while True:
        start = html.find(_MASTHEAD_OPEN, pos)
        if start == -1:
            break
        end = html.find(_MASTHEAD_CLOSE, start + len(_MASTHEAD_OPEN))
        if end == -1:
            # No close tag left in the document, so no later element has one
            # either — the same would-be match is not worth looking for again.
            break
        pieces.append(html[pos:start])
        pos = end + len(_MASTHEAD_CLOSE)
    pieces.append(html[pos:])
    return "".join(pieces)


def _back_over_blanks(html, pos):
    """The index where the run of blanks ending at `pos` begins."""
    while pos > 0 and html[pos - 1].isspace():
        pos -= 1
    return pos


def _forward_over_blanks(html, pos):
    """The first index at or after `pos` holding something other than a blank."""
    while pos < len(html) and html[pos].isspace():
        pos += 1
    return pos


def _unwrap_legacy_hero(html):
    """Lift the hero out of the grid div the old home snippet wrapped it in.

    The hero is an ordinary block now; left inside that div the full-bleed photo
    would be inset by the grid's gutters and the card laid out as a flex item.
    Pages saved before the change are unwrapped at render and at save, the way
    the FAQ masthead is — so they look right before anyone edits them again.
    Only a div holding the hero and nothing else is removed, which is what the
    old snippet produced. Anything else is left alone.
    """
    if not html:
        return html
    pieces = []
    # Two cursors: `search` skips past a hero that turns out not to be wrapped,
    # while `copied` only advances once the text before it has been kept.
    copied = 0
    search = 0
    while True:
        start = html.find(_MASTHEAD_OPEN, search)
        if start == -1:
            break
        end = html.find(_MASTHEAD_CLOSE, start + len(_MASTHEAD_OPEN))
        if end == -1:
            break  # no close tag left, so no later element is closed either
        end += len(_MASTHEAD_CLOSE)
        search = end
        row_end = _back_over_blanks(html, start)
        row_start = row_end - len(_HERO_ROW_OPEN)
        if row_start < copied or not html.startswith(_HERO_ROW_OPEN, row_start):
            continue
        row_close = _forward_over_blanks(html, end)
        if not html.startswith(_HERO_ROW_CLOSE, row_close):
            continue
        pieces.append(html[copied:row_start])
        pieces.append(html[start:end])
        copied = row_close + len(_HERO_ROW_CLOSE)
        search = copied
    pieces.append(html[copied:])
    return "".join(pieces)


def _strip_legacy_faq_header(html):
    """Drop the pre-banner masthead card (and its emptied wrapper) from FAQ HTML."""
    if not html:
        return html
    html = _cut_mastheads(html)
    html = _FAQ_EMPTIED_CONTAINER_RE.sub("", html)
    return html.strip()


def _sanitize_html(html):
    """Unwrap the GrapesJS <body> wrapper from saved editor HTML."""
    if not html:
        return html
    html = _WRAPPER_OPEN_RE.sub("", html)
    html = _WRAPPER_CLOSE_RE.sub("", html)
    return html.strip()


def _page_has_content(page):
    """Whether one saved GrapesJS page holds components.

    GrapesJS 0.23 keeps a page's component tree on its frame — the saved
    project looks like ``{"pages": [{"frames": [{"component": {...}}]}]}``.
    Reading ``page["components"]`` instead, as this used to, finds nothing on
    real project data: every saved page was treated as empty, so the editor
    quietly threw away what had been saved and re-seeded the default look —
    and the next save then wrote that default back over the stored content.
    """
    if not isinstance(page, dict):
        return False
    if page.get("component"):
        return True  # project data that carries the tree on the page itself
    frames = page.get("frames")
    return isinstance(frames, list) and any(
        isinstance(frame, dict) and frame.get("component") for frame in frames
    )


def _has_content(project_json):
    """Whether a saved project actually holds editable content.

    An empty project ({"pages": []}, or pages whose frames carry nothing —
    e.g. from an abandoned editor session) must seed the canvas with the
    current page look instead of loading a blank project.
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
    return any(_page_has_content(page) for page in pages)


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
    # when the current language was never edited. Sanitizing at render as well
    # as at save, so already-stored content is corrected at display time too.
    html = _sanitize_html(content.html)
    html = _unwrap_legacy_hero(html)
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
                # Hand the template a parsed object: json_script encodes what it
                # is given, so passing the stored JSON *string* would ship a
                # JSON-encoded string to the editor, and GrapesJS treats a
                # string project as "load from that storage key" — it clears
                # the canvas and finds nothing, leaving a blank editor.
                project_json = json.loads(project_json)
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
        html = _unwrap_legacy_hero(html)
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
