import json
import re
import shutil
import tempfile
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
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

    def test_project_with_components_is_loaded(self):
        SiteContent.objects.create(
            page=SiteContent.Page.HOME,
            project_json='{"pages": [{"component": true}]}',
        )
        self.client.force_login(self.superuser)
        response = self.client.get(reverse("homepage_editor"))
        # The saved project ships to the editor; no seed markup is injected.
        self.assertContains(response, "project-json")
        self.assertNotContains(response, "Description principale")


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

    @override_settings(MEDIA_ROOT=Path(tempfile.mkdtemp()))
    def test_uploaded_file_lands_in_media_root(self):
        self.client.force_login(self.superuser)
        upload = SimpleUploadedFile("logo.png", b"\x89PNG...", content_type="image/png")
        response = self.client.post(
            reverse("homepage_editor_assets"), {"file": upload}
        )
        self.assertEqual(response.status_code, 200)
        asset = ImageAsset.objects.first()
        self.assertTrue(asset.file.storage.exists(asset.file.name))


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


class SiteContentModelTest(HomePageEditorTestBase):
    """Model helpers."""

    def test_get_content_returns_none_when_absent(self):
        self.assertIsNone(SiteContent.get_content(SiteContent.Page.HOME))


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
        # Content saved before sanitization existed still renders unwrapped.
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


class NavbarBrandLinkTest(HomePageEditorTestBase):
    """Logo and site name link back to the home page."""

    def test_brand_links_to_homepage(self):
        response = self.client.get(reverse("homepage"))
        brands = re.findall(r'<a class="navbar-brand[^>]*>', response.content.decode())
        self.assertEqual(len(brands), 1)
        self.assertIn(f'href="{reverse("homepage")}"', brands[0])
