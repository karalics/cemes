from django.apps import AppConfig


class TwitterConfig(AppConfig):

    name = "cemes.twitter"

    def ready(self):
        from . import checks  # noqa
