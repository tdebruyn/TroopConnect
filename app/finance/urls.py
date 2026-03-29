from django.urls import path
from . import views

app_name = "finance"

urlpatterns = [
    path("", views.billing_overview, name="billing"),
    path("payment/", views.record_payment, name="record_payment"),
    path("reminders/", views.send_reminders, name="reminders"),
]
