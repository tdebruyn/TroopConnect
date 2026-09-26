import json
import re
import shutil
import tempfile
from pathlib import Path

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils.translation import override

from homepage.models import ImageAsset, SiteContent
from members.models import Account, Person, Role


class HomePageEditorTestBase(TestCase):
    """Shared users and helpers for the homepage editor tests."""

    @classmethod
    def setUpTestData(cls):
        cls.role_parent = Role.objects.get(short="p")
        cls.superuser = Account.objects.create_user(
            email="super@test.be",
            password="pass",
            is_staff=True,
            is_superuser=True,
            person=Person.objects.create(
                first_name="Super",
                last_name="User",
                primary_role=cls.role_parent,
                status="a",
            ),
        )
        cls.staff_user = Account.objects.create_user(
            email="staff@test.be",
            password="pass",
            is_staff=True,
            person=Person.objects.create(
                first_name="Staff",
                last_name="Only",
                primary_role=cls.role_parent,
                status="a",
            ),
        )
        cls.regular_user = Account.objects.create_user(
            email="parent@test.be",
            password="pass",
            person=Person.objects.create(
                first_name="Regular",
                last_name="Parent",
                primary_role=cls.role_parent,
                status="a",
            ),
        )

    def _save(self, client, page, lang, html, css="", project=None):
        return client.post(
            reverse("homepage_editor_save"),
            data=json.dumps(
                {
                    "page": page,
                    "lang": lang,
                    "html": html,
                    "css": css,
                    "project": project if project is not None else {"pages": []},
                }
            ),
            content_type="application/json",
        )


class EditorPageAccessTest(HomePageEditorTestBase):
    """The editor page is superuser-only."""

    def test_superuser_can_open_editor(self):
        self.client.force_login(self.superuser)
        response = self.client.get(reverse("homepage_editor"))
        self.assertEqual(response.status_code, 200)

    def test_staff_non_superuser_gets_403(self):
        self.client.force_login(self.staff_user)
        response = self.client.get(reverse("homepage_editor"))
        self.assertEqual(response.status_code, 403)

    def test_regular_user_gets_403(self):
        self.client.force_login(self.regular_user)
        response = self.client.get(reverse("homepage_editor"))
        self.assertEqual(response.status_code, 403)

    def test_anonymous_is_redirected_to_login(self):
        response = self.client.get(reverse("homepage_editor"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    def test_invalid_page_returns_400(self):
        self.client.force_login(self.superuser)
        response = self.client.get(reverse("homepage_editor"), {"page": "agenda"})
        self.assertEqual(response.status_code, 400)

    def test_invalid_lang_returns_400(self):
        self.client.force_login(self.superuser)
        response = self.client.get(reverse("homepage_editor"), {"lang": "de"})
        self.assertEqual(response.status_code, 400)

    def test_empty_project_seeds_default_content(self):
        # A project without components (abandoned session) must not load a
        # blank canvas — the editor seeds the current default look instead.
        SiteContent.objects.create(page=SiteContent.Page.HOME, project_json='{"pages": []}')
        self.client.force_login(self.superuser)
        response = self.client.get(reverse("homepage_editor"))
        self.assertContains(response, "Description principale")

    def test_project_with_frames_is_loaded(self):
        # GrapesJS 0.23 keeps a page's component tree on its frame. Looking for
        # it on the page itself, as this used to, found nothing in real project
        # data: every saved page was treated as empty and re-seeded, and the
        # next save wrote that default back over the stored content.
        SiteContent.objects.create(
            page=SiteContent.Page.HOME,
            project_json='{"pages": [{"frames": [{"component": {"type": "wrapper"}}]}]}',
        )
        self.client.force_login(self.superuser)
        response = self.client.get(reverse("homepage_editor"))
        # The saved project ships to the editor; no seed markup is injected.
        self.assertContains(response, "project-json")
        self.assertNotContains(response, "Description principale")

    def test_project_with_empty_frames_seeds_default_content(self):
        # An abandoned session can leave a page whose frame holds nothing.
        SiteContent.objects.create(
            page=SiteContent.Page.HOME,
            project_json='{"pages": [{"frames": [{"component": null}]}]}',
        )
        self.client.force_login(self.superuser)
        response = self.client.get(reverse("homepage_editor"))
        self.assertContains(response, "Description principale")

    def test_project_ships_as_an_object_not_a_json_string(self):
        # json_script encodes whatever it is handed. Passing it the stored JSON
        # *string* shipped a JSON-encoded string, and GrapesJS reads a string
        # project as a storage key: it cleared the canvas, found nothing, and
        # left a blank editor.
        SiteContent.objects.create(
            page=SiteContent.Page.HOME,
            project_json='{"pages": [{"frames": [{"component": {"type": "wrapper"}}]}]}',
        )
        self.client.force_login(self.superuser)
        response = self.client.get(reverse("homepage_editor"))
        match = re.search(
            r'<script id="project-json" type="application/json">(.*?)</script>',
            response.content.decode(),
            re.DOTALL,
        )
        self.assertIsNotNone(match, "the editor shipped no project-json")
        project = json.loads(match.group(1))
        self.assertIsInstance(project, dict)
        self.assertIn("pages", project)


class EditorSaveTest(HomePageEditorTestBase):
    """Saving content from the editor and rendering it on the pages."""

    def test_superuser_can_save_home_content(self):
        self.client.force_login(self.superuser)
        response = self._save(self.client, "home", "fr", "<div><h1>Bienvenue</h1></div>")
        self.assertEqual(response.status_code, 200)
        response = self.client.get(reverse("homepage"))
        self.assertContains(response, "<h1>Bienvenue</h1>")

    def test_superuser_can_save_faq_content(self):
        self.client.force_login(self.superuser)
        response = self._save(self.client, "faq", "fr", "<div><h2>FAQ éditée</h2></div>")
        self.assertEqual(response.status_code, 200)
        response = self.client.get(reverse("faq"))
        self.assertContains(response, "<h2>FAQ éditée</h2>")

    def test_non_superuser_save_gets_403(self):
        self.client.force_login(self.regular_user)
        response = self._save(self.client, "home", "fr", "<div>x</div>")
        self.assertEqual(response.status_code, 403)

    def test_invalid_lang_save_returns_400(self):
        self.client.force_login(self.superuser)
        response = self._save(self.client, "home", "de", "<div>x</div>")
        self.assertEqual(response.status_code, 400)

    def test_invalid_payload_returns_400(self):
        self.client.force_login(self.superuser)
        response = self.client.post(
            reverse("homepage_editor_save"), data="not json", content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)

    def test_default_content_shown_without_save(self):
        response = self.client.get(reverse("homepage"))
        self.assertContains(response, "Description principale")

    def test_nl_falls_back_to_french(self):
        self.client.force_login(self.superuser)
        self._save(self.client, "home", "fr", '<div class="fr-only">Contenu FR</div>')
        with override("nl"):
            response = self.client.get(reverse("homepage"))
        self.assertContains(response, "Contenu FR")

    def test_clearing_content_restores_default(self):
        self.client.force_login(self.superuser)
        self._save(self.client, "home", "fr", "<div><h1>Bienvenue</h1></div>")
        self._save(self.client, "home", "fr", "")
        response = self.client.get(reverse("homepage"))
        self.assertContains(response, "Description principale")

    def test_edited_css_is_rendered(self):
        self.client.force_login(self.superuser)
        self._save(
            self.client, "home", "fr", "<div class='x'>y</div>", css="#gjs-x{color:red}"
        )
        response = self.client.get(reverse("homepage"))
        self.assertContains(response, "color:red")


class EditorAssetsTest(HomePageEditorTestBase):
    """Image uploads through the asset manager endpoint."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_superuser_can_upload_image(self):
        self.client.force_login(self.superuser)
        upload = SimpleUploadedFile("logo.png", b"\x89PNG...", content_type="image/png")
        response = self.client.post(
            reverse("homepage_editor_assets"), {"file": upload}
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["src"].startswith("/media/homepage_images/"))
        self.assertEqual(ImageAsset.objects.count(), 1)

    def test_bad_extension_rejected(self):
        self.client.force_login(self.superuser)
        upload = SimpleUploadedFile("virus.exe", b"MZ...", content_type="application/x-exe")
        response = self.client.post(
            reverse("homepage_editor_assets"), {"file": upload}
        )
        self.assertEqual(response.status_code, 400)

    def test_non_superuser_upload_gets_403(self):
        self.client.force_login(self.regular_user)
        upload = SimpleUploadedFile("logo.png", b"\x89PNG...", content_type="image/png")
        response = self.client.post(
            reverse("homepage_editor_assets"), {"file": upload}
        )
        self.assertEqual(response.status_code, 403)

    def test_missing_file_returns_400(self):
        self.client.force_login(self.superuser)
        response = self.client.post(reverse("homepage_editor_assets"))
        self.assertEqual(response.status_code, 400)

class EditLinkTest(HomePageEditorTestBase):
    """The 'Edit homepage' link is superuser-only."""

    def test_superuser_sees_edit_homepage_link(self):
        self.client.force_login(self.superuser)
        response = self.client.get(reverse("homepage"))
        self.assertContains(response, reverse("homepage_editor"))

    def test_regular_user_does_not_see_edit_homepage_link(self):
        self.client.force_login(self.regular_user)
        response = self.client.get(reverse("homepage"))
        self.assertNotContains(response, reverse("homepage_editor"))

    def test_anonymous_does_not_see_edit_homepage_link(self):
        response = self.client.get(reverse("homepage"))
        self.assertNotContains(response, reverse("homepage_editor"))


class WrapperSanitizerTest(HomePageEditorTestBase):
    """GrapesJS wrapper output cannot restyle the real page.

    The editor exports its canvas wrapper as a literal <body> element;
    injected mid-page the browser merges that tag's attributes onto the
    real <body>, shifting the page chrome (navbar included).
    """

    def test_save_strips_body_wrapper(self):
        self.client.force_login(self.superuser)
        response = self._save(
            self.client,
            "home",
            "fr",
            '<body style="padding: 60px;"><div><h1>x</h1></div></body>',
        )
        self.assertEqual(response.status_code, 200)
        content = SiteContent.get_content(SiteContent.Page.HOME)
        self.assertEqual(content.html, "<div><h1>x</h1></div>")

    def test_render_strips_wrapper_from_legacy_saves(self):
        # Content that predates the sanitizer still renders unwrapped.
        SiteContent.objects.create(
            page=SiteContent.Page.HOME,
            project_json="{}",
            html='<body style="padding: 60px;"><div><h1>legacy</h1></div></body>',
            css="body { padding: 60px; } #id1 { color: red; }",
        )
        response = self.client.get(reverse("homepage"))
        self.assertNotContains(response, '<body style="padding: 60px;">')
        self.assertNotContains(response, "padding: 60px")
        self.assertContains(response, "color: red")

    def test_save_strips_wrapper_css_rules(self):
        self.client.force_login(self.superuser)
        response = self._save(
            self.client,
            "home",
            "fr",
            "<div class='x'>y</div>",
            css=(
                "* { box-sizing: border-box; } body {margin: 0;}"
                "#gjs-x{color:red}"
                "@media (max-width: 768px) { body { padding: 0; } #gjs-x{color:blue} }"
            ),
        )
        self.assertEqual(response.status_code, 200)
        content = SiteContent.get_content(SiteContent.Page.HOME)
        self.assertEqual(
            content.css,
            "#gjs-x{color:red}@media (max-width: 768px) {#gjs-x{color:blue}}",
        )

    def test_content_selectors_survive(self):
        # Rules that merely mention body (descendant selectors) must stay.
        SiteContent.objects.create(
            page=SiteContent.Page.HOME,
            project_json="{}",
            html="<div><h1>hi</h1></div>",
            css="body > div { color: red; }",
        )
        response = self.client.get(reverse("homepage"))
        self.assertContains(response, "body > div { color: red; }")


class LegacyFaqHeaderTest(HomePageEditorTestBase):
    """The FAQ page renders a fixed hat banner; saved content must not duplicate it.

    FAQ content saved before the banner existed still embeds the masthead
    card the old default snippet seeded. It is stripped at render and at
    save; the Home page keeps its own card (real content there).
    """

    LEGACY_FAQ_HTML = (
        '<body><div class="container row"><header class="masthead"><div class="card">'
        '<h2>FAQ</h2><p>Questions fréquemment posées.</p></div></header>'
        '<p id="ihuux">Ceci est un test</p></div></body>'
    )

    def test_render_strips_legacy_header_from_faq(self):
        SiteContent.objects.create(
            page=SiteContent.Page.FAQ,
            project_json="{}",
            html=self.LEGACY_FAQ_HTML,
        )
        response = self.client.get(reverse("faq"))
        # The saved body content stays; the seeded card does not.
        self.assertContains(response, "Ceci est un test")
        self.assertContains(response, "Questions fréquemment posées.")  # banner text
        self.assertNotContains(response, "masthead")
        self.assertNotContains(response, '<h2>FAQ</h2>')

    def test_save_strips_legacy_header_from_faq(self):
        self.client.force_login(self.superuser)
        response = self._save(self.client, "faq", "fr", self.LEGACY_FAQ_HTML)
        self.assertEqual(response.status_code, 200)
        content = SiteContent.get_content(SiteContent.Page.FAQ)
        # The user's own wrapper div stays; only the seeded card is dropped.
        self.assertEqual(
            content.html,
            '<div class="container row"><p id="ihuux">Ceci est un test</p></div>',
        )

    def test_home_masthead_is_kept(self):
        SiteContent.objects.create(
            page=SiteContent.Page.HOME,
            project_json="{}",
            html=(
                '<div class="container row"><header class="masthead">'
                "<h2>Description principale</h2></header></div>"
            ),
        )
        response = self.client.get(reverse("homepage"))
        self.assertContains(response, "masthead")


class LegacyHomeHeroTest(HomePageEditorTestBase):
    """The home hero used to be wrapped in a Bootstrap grid div.

    The hero is an ordinary block now. Left inside that div the full-bleed
    photo would be inset by the grid's gutters and the card laid out as a flex
    item, so saved content is unwrapped at render and at save — the same
    treatment the FAQ masthead gets.
    """

    LEGACY_HOME_HTML = (
        '<div class="container row"><header class="masthead"><div class="card">'
        "<h2>Description principale</h2></div></header></div>"
        '<section class="py-4"><h1>Bloc ajouté</h1></section>'
    )

    def test_render_unwraps_legacy_hero(self):
        SiteContent.objects.create(
            page=SiteContent.Page.HOME,
            project_json="{}",
            html=self.LEGACY_HOME_HTML,
        )
        response = self.client.get(reverse("homepage"))
        self.assertContains(response, "<h1>Bloc ajouté</h1>")
        self.assertContains(response, "masthead")
        self.assertNotContains(response, '<div class="container row">')

    def test_save_unwraps_legacy_hero(self):
        self.client.force_login(self.superuser)
        self._save(self.client, "home", "fr", self.LEGACY_HOME_HTML)
        content = SiteContent.get_content(SiteContent.Page.HOME)
        self.assertEqual(
            content.html,
            '<header class="masthead"><div class="card"><h2>Description principale'
            '</h2></div></header><section class="py-4"><h1>Bloc ajouté</h1></section>',
        )

    def test_row_without_a_hero_is_left_alone(self):
        SiteContent.objects.create(
            page=SiteContent.Page.HOME,
            project_json="{}",
            html='<div class="container row"><p>Texte</p></div>',
        )
        response = self.client.get(reverse("homepage"))
        self.assertContains(response, '<div class="container row"><p>Texte</p></div>')


class HomeSeedStructureTest(HomePageEditorTestBase):
    """The default home page is a hero, then the area blocks are dropped into.

    The content area is what makes the space under the hero droppable: without
    it the only drop target on the canvas is the body itself.
    """

    def test_default_page_has_a_content_area_after_the_hero(self):
        page = self.client.get(reverse("homepage")).content.decode()
        hero_at = page.find('class="masthead"')
        content_at = page.find('<main class="tc-page-content"')
        self.assertNotEqual(hero_at, -1, "the default home page has no hero")
        self.assertNotEqual(content_at, -1, "the default home page has no content area")
        self.assertGreater(content_at, hero_at)

    def test_editor_seed_has_the_content_area(self):
        self.client.force_login(self.superuser)
        response = self.client.get(reverse("homepage_editor"))
        self.assertContains(response, '<main class="tc-page-content">')


class EditorCanvasStylesTest(SimpleTestCase):
    """The canvas must load the same assets as the site.

    jsdelivr resolves its paths literally, so a canvas stylesheet URL that does
    not match base.html answers 404. That failure is silent — the editor simply
    renders without Bootstrap, which is how the hero's card came to show white
    text on a white background — so it is worth a test rather than a close eye.
    """

    def test_canvas_uses_the_same_bootstrap_css_as_the_site(self):
        base = (Path(settings.BASE_DIR) / "templates" / "base.html").read_text(
            encoding="utf-8"
        )
        editor = (Path(settings.BASE_DIR) / "static" / "js" / "homepage-editor.js").read_text(
            encoding="utf-8"
        )
        site_urls = re.findall(
            r"https://cdn\.jsdelivr\.net/npm/bootstrap@[\d.]+/[^\"']*bootstrap\.min\.css",
            base,
        )
        self.assertTrue(site_urls, "base.html no longer loads Bootstrap CSS")
        for url in site_urls:
            self.assertIn(
                url, editor, "the editor canvas loads a different Bootstrap URL"
            )


class NavbarBrandLinkTest(HomePageEditorTestBase):
    """Logo and site name link back to the home page."""

    def test_brand_links_to_homepage(self):
        """The navbar brand links back to the home page.

        Matches any attribute order and tolerates more than one brand element
        (e.g. a separate one for the mobile collapse): the previous
        ``<a class="navbar-brand[^>]*>`` pattern pinned ``class`` as the first
        attribute and the count at exactly one, failing on refactors that break
        nothing.
        """
        response = self.client.get(reverse("homepage"))
        brands = re.findall(r"<a[^>]*navbar-brand[^>]*>", response.content.decode())
        self.assertTrue(brands, "no navbar-brand link rendered")
        self.assertTrue(
            any(f'href="{reverse("homepage")}"' in brand for brand in brands),
            "no navbar-brand link points back to the home page",
        )
