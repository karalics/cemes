from django.conf import settings
from django.urls import path

from cemes.pages import page_processors, views

page_processors.autodiscover()


# Page patterns.
urlpatterns = [
    path(
        "<path:slug>" + ("/" if settings.APPEND_SLASH else ""),
        views.page,
        name="page",
    ),
]
