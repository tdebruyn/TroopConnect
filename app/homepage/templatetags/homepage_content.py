"""Template tags for the homepage's own content."""
from django import template
from django.utils.translation import gettext_lazy as _

from members.models import TroopSettings

register = template.Library()


@register.simple_tag
def band_seed():
    """The unit's own words for its opening band.

    A tag rather than view context because the band's markup is rendered in two
    places — the public page and the unit's page — and both would otherwise
    have to be told to pass this.

    Both values are translated columns on the singleton, so a French, Dutch
    and English visitor each read the troop's own language rather than the
    fallback.
    """
    troop = TroopSettings.get_settings()
    return {
        "heading": troop.name or _("Our unit"),
        "text": troop.site_description
        or _("This is where the unit introduces itself to the families of the commune."),
    }
