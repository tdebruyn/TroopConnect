from django.urls import path
from messaging import views

app_name = "messaging"

urlpatterns = [
    path("compose/", views.compose_message, name="compose"),
    path("history/", views.animateur_history, name="animateur_history"),
    path("history/<uuid:message_id>/", views.message_detail, name="message_detail"),
    path("section/<int:section_id>/", views.section_history, name="section_history"),
]
