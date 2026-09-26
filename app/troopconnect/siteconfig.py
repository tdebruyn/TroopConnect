"""Keep the ``django.contrib.sites`` row in step with SITE_DOMAIN.

Reminder emails, attestation links and allauth's confirmation mails are built
from ``Site.objects.get_current()``. A fresh install leaves that row at its
factory value (``example.com``), which would put the wrong host in every link a
troop sends, so the row is rewritten from SITE_DOMAIN after each ``migrate``
(which the production entrypoint always runs).
"""

from django.conf import settings
from django.db.models.signals import post_migrate


def sync_site_domain(**kwargs):
    """Point the configured Site row at SITE_DOMAIN."""
    domain = getattr(settings, "SITE_DOMAIN", None)
    if not domain:
        # A missing SITE_DOMAIN is reported by troopconnect.checks; there is
        # nothing sensible to write here.
        return

    from django.contrib.sites.models import Site

    site, created = Site.objects.get_or_create(
        id=getattr(settings, "SITE_ID", 1),
        defaults={"domain": domain, "name": domain},
    )
    if not created and site.domain != domain:
        site.domain = domain
        site.save(update_fields=["domain"])


def connect(app_config):
    """Subscribe the sync to post_migrate for one app config (idempotent).

    Scoping it to a single app config means it runs once per ``migrate``
    rather than once per installed app. Every migration has been applied by
    the time post_migrate fires, so the sites table and its default row exist.
    """
    post_migrate.connect(
        sync_site_domain,
        sender=app_config,
        dispatch_uid="troopconnect.siteconfig.sync_site_domain",
    )
