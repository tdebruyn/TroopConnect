from django.urls import path
from messaging import views

app_name = "messaging"

urlpatterns = [
    path("animateurs/compose/", views.compose_message, name="compose"),
    path("animateurs/compose-all/", views.compose_all_message, name="compose_all"),
    path("animateurs/history/", views.animateur_history, name="animateur_history"),
    path("history/", views.section_history, name="section_history"),
]
