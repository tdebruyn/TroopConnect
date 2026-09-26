"""Keep post_office's template cache honest.

``post_office.utils.get_email_template`` caches each template under the key
``"{name}:{language}"``, but ``EmailTemplate.save()`` only ever deletes
``"{name}"``. Editing a template -- in the admin, or from a data migration --
therefore leaves the previous copy being sent until the cache entry expires,
which makes ``manage.py migrate`` on a live instance look like it did nothing.

The key is built inside post_office (its own cache wrapper, which prefixes and
slugifies), so it has to be invalidated through the same wrapper rather than
through Django's cache directly.
"""

from post_office import cache as template_cache


def cache_token(template):
    """The name post_office caches ``template`` under, before its own mangling."""
    return f"{template.name}:{template.language}"


def forget_template(sender, instance, **kwargs):
    template_cache.delete(cache_token(instance))


def connect():
    """Subscribe the cache fix (idempotent)."""
    from django.db.models.signals import post_delete, post_save
    from post_office.models import EmailTemplate

    post_save.connect(
        forget_template,
        sender=EmailTemplate,
        dispatch_uid="troopconnect.postoffice.forget_template_on_save",
    )
    post_delete.connect(
        forget_template,
        sender=EmailTemplate,
        dispatch_uid="troopconnect.postoffice.forget_template_on_delete",
    )
