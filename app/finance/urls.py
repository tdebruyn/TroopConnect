from django.urls import path
from . import views

app_name = "finance"

urlpatterns = [
    path("", views.billing_overview, name="billing"),
    path("payment/", views.record_payment, name="record_payment"),
    path("payment/history/<uuid:person_id>/", views.payment_history, name="payment_history"),
    path("reminders/", views.send_reminders, name="reminders"),
]
