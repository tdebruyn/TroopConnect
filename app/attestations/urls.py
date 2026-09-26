from django.urls import path

from . import views

app_name = "attestations"

urlpatterns = [
    path("", views.index, name="index"),
    path("create/", views.step1, name="create"),
    path("<int:pk>/step1/", views.step1, name="step1"),
    path("<int:pk>/step2/", views.step2, name="step2"),
    path("<int:pk>/step3/", views.step3, name="step3"),
    path("<int:pk>/step4/", views.step4, name="step4"),
    path("<int:pk>/review/", views.review, name="review"),
    path(
        "<int:pk>/suggestion/<int:item_pk>/accept/",
        views.accept_suggestion,
        name="accept_suggestion",
    ),
    path(
        "<int:pk>/suggestion/<int:item_pk>/dismiss/",
        views.dismiss_suggestion,
        name="dismiss_suggestion",
    ),
    path("<int:pk>/send/", views.send, name="send"),
]
