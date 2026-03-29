from django.shortcuts import render
from django.views.generic import TemplateView
from django.utils import timezone
from datetime import timedelta

from homepage.models import Event


class HomePage(TemplateView):
    template_name = "homepage/home.html"


class FAQ(TemplateView):
    template_name = "homepage/faq.html"


class Agenda(TemplateView):
    template_name = "homepage/agenda.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.now().date()
        cutoff = today - timedelta(days=30)
        # Show events from the last 30 days onwards (future + recent past)
        context["events"] = Event.objects.filter(date__gte=cutoff).order_by("date")
        return context
