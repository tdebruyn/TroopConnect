from django.urls import path

from . import views

app_name = "finance"

urlpatterns = [
    path("", views.billing_overview, name="billing"),
    path("prices/", views.edit_prices, name="prices"),
    path("payment/", views.record_payment, name="record_payment"),
    path("payment/history/<uuid:person_id>/", views.payment_history, name="payment_history"),
    path("reminders/", views.send_reminders, name="reminders"),
    path("households/", views.household_list, name="households"),
    path("households/assign/", views.assign_household, name="assign_household"),
    path("households/<int:pk>/", views.household_detail, name="household_detail"),
    path("households/<int:pk>/delete/", views.household_delete, name="household_delete"),
    path(
        "households/<int:pk>/adjustments/<int:adjustment_pk>/delete/",
        views.adjustment_delete,
        name="adjustment_delete",
    ),
]
