from django.urls import path
from homepage import views

urlpatterns = [path("", views.HomePage.as_view(), name="homepage")]
