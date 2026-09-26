"""The wizard's URLs, mounted at ``/setup/``.

The structure editor's routes come first: ``<str:step>`` would otherwise
swallow them, and a step called "structure" is not the same page as the
buttons inside it.
"""

from django.urls import path

from . import views

app_name = "setup"

urlpatterns = [
    path("", views.SetupWizardView.as_view(), name="index"),
    path(
        "structure/<str:action>",
        views.StructureRowView.as_view(),
        name="structure_row",
    ),
    path("<str:step>", views.SetupWizardView.as_view(), name="step"),
]
