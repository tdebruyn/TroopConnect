from django.urls import path

from homepage import views

urlpatterns = [
    path("", views.HomePage.as_view(), name="homepage"),
    # The troop's own page at a URL that does not change shape with who is
    # looking: `/` is the tool for anyone signed in, this is the page the troop
    # edits. See HomePage.
    path("unite/", views.UnitPage.as_view(), name="unit_page"),
    path("faq/", views.FAQ.as_view(), name="faq"),
    path("editor/", views.HomePageEditorView.as_view(), name="homepage_editor"),
    path("editor/save/", views.HomePageEditorSaveView.as_view(), name="homepage_editor_save"),
    path(
        "editor/assets/",
        views.HomePageEditorAssetsView.as_view(),
        name="homepage_editor_assets",
    ),
]
