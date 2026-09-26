from django.apps import AppConfig


class MembersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "members"

    def ready(self):
        # Importing the project's checks module is what registers them with
        # Django; app startup is the only moment early enough for them to run
        # before the first request and before `manage.py migrate`.
        import troopconnect.checks  # noqa: F401
        from troopconnect import postoffice
        from troopconnect.siteconfig import connect

        connect(self)
        postoffice.connect()
