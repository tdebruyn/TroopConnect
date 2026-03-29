from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.sites.models import Site
from post_office import mail

from .models import Person, get_registration_admins


@receiver(post_save, sender=Person)
def notify_admins_on_profile_save(sender, instance, created, **kwargs):
    """
    When a Person (adult) is saved, notify registration admins.
    Children are already handled in add_new_child_view with a dedicated template.
    """
    if not created:
        return

    # Only notify for adults (persons without parents, i.e. not children)
    if instance.parents.exists():
        return

    recipients = get_registration_admins()
    if not recipients:
        return

    mail.send(
        recipients=recipients,
        sender="MS_M3qCdl@tomctl.be",
        template="new_child_staff",
        context={
            "first_name": instance.first_name,
            "last_name": instance.last_name,
            "url": f"{Site.objects.get_current()}/users/adminupdate/{instance.id}",
        },
    )
