from django.contrib.auth.models import Group
from django.db.models.signals import m2m_changed
from django.dispatch import receiver
from .models import CustomGroup, SchoolYear
from django.db.models import Q


@receiver(m2m_changed, sender=Group.user_set.through)
def check_user_group_membership(sender, instance, action, reverse, pk_set, **kwargs):
    if action == "pre_add":
        if not pk_set:
            return
        demande = CustomGroup.objects.get(name="Demandée")
        archive = CustomGroup.objects.get(name="Archivée")
        new_group_year = CustomGroup.objects.get(pk__in=pk_set).year

        if CustomGroup.objects.get(pk__in=pk_set) == archive:
            instance.groups.remove(demande)
        elif new_group_year is not None:
            existing_group_year = instance.groups.filter(
                customgroup__year=new_group_year
            ).first()
            # when adding a group for a year, previous group from same year needs to be removed
            instance.groups.remove(existing_group_year)
            instance.groups.remove(demande)
            if (
                CustomGroup.objects.get(pk__in=pk_set).year.name
                >= SchoolYear.current().name
            ):
                instance.groups.remove(archive)
