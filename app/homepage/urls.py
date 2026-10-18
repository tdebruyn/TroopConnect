from django.urls import path

from homepage import views

urlpatterns = [
    path("", views.HomePage.as_view(), name="homepage"),
    # The troop's own page at a URL that does not change shape with who is
    # looking: `/` is the tool for anyone signed in, this is the public page.
    # See HomePage.
    path("unite/", views.UnitPage.as_view(), name="unit_page"),
]
