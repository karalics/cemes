from django.apps import AppConfig


class PagesConfig(AppConfig):

    name = "cemes.pages"

    def ready(self):
        from . import checks  # noqa
