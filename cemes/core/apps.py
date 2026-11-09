from django.apps import AppConfig


class CoreConfig(AppConfig):

    name = "cemes.core"

    def ready(self):
        from . import checks  # noqa
