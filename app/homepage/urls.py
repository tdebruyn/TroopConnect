from django.urls import path

from homepage import views

urlpatterns = [
    path("", views.HomePage.as_view(), name="homepage"),
    path("faq/", views.FAQ.as_view(), name="faq"),
    path("agenda/", views.Agenda.as_view(), name="agenda"),
    path("editor/", views.HomePageEditorView.as_view(), name="homepage_editor"),
    path("editor/save/", views.HomePageEditorSaveView.as_view(), name="homepage_editor_save"),
    path(
        "editor/assets/",
        views.HomePageEditorAssetsView.as_view(),
        name="homepage_editor_assets",
    ),
]
