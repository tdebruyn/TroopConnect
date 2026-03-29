from django.urls import path
from homepage import views

urlpatterns = [
    path("", views.HomePage.as_view(), name="homepage"),
    path("faq/", views.FAQ.as_view(), name="faq"),
    path("agenda/", views.Agenda.as_view(), name="agenda"),
]
