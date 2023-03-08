from django.contrib.auth.models import Group
from django.db.models.signals import m2m_changed
from django.dispatch import receiver
from .models import CustomGroup


@receiver(m2m_changed, sender=Group.user_set.through)
def check_user_group_membership(sender, instance, action, reverse, pk_set, **kwargs):
    if action == "pre_add":
        # Ensure the user is only added to one group with "status" as parent
        status_groups = CustomGroup.objects.filter(parents__name="Status")
        existing_status_groups = status_groups.filter(user=instance)
        new_status_groups = status_groups.filter(pk__in=pk_set)

        if (
            len(existing_status_groups) == 1
            and len(new_status_groups) == 1
            and existing_status_groups[0] != new_status_groups[0]
        ):
            # Remove the existing group if the user is being added to a new group
            instance.groups.remove(existing_status_groups[0])
            print(
                f"Replacing group {existing_status_groups} with {new_status_groups}, due to sender {sender}, with pk_set {pk_set}"
            )
