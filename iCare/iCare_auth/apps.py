from django.apps import AppConfig


class IcareAuthConfig(AppConfig):
    name = 'iCare_auth'

    def ready(self):
        import iCare_auth.signals  # noqa
