from django.urls import path

from . import views

app_name = "attestations"

urlpatterns = [
    path("", views.index, name="index"),
    path("create/", views.create, name="create"),
    path("<int:pk>/configure/", views.configure, name="configure"),
    path("<int:pk>/review/", views.review, name="review"),
    path("<int:pk>/send/", views.send, name="send"),
]
