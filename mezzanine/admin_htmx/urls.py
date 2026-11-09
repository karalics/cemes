"""
URLs for the htmx admin.

Include these under whatever prefix the project uses for its admin::

    path("admin/", include("mezzanine.admin_htmx.urls")),

The classic admin should stay mounted as well, under its own prefix,
because Django's related-object widgets and the media library reverse
their popups against the ``admin`` namespace::

    path("admin-classic/", include(admin.site.urls)),
"""
from django.urls import path
from django.views.i18n import JavaScriptCatalog

from mezzanine.admin_htmx import views
from mezzanine.conf import settings

app_name = "admin_htmx"

urlpatterns = [
    path("", views.index, name="index"),
    # Django's admin widget scripts call gettext() at load time, so the
    # catalog has to be served here rather than being borrowed from the
    # classic admin, which a project may not have mounted.
    path(
        "jsi18n/",
        JavaScriptCatalog.as_view(packages=["django.contrib.admin"]),
        name="jsi18n",
    ),
    path("login/", views.LoginView.as_view(), name="login"),
    path("logout/", views.LogoutView.as_view(), name="logout"),
    path("settings/", views.site_settings, name="settings"),
]

if "mezzanine.pages" in settings.INSTALLED_APPS:
    urlpatterns += [
        path("page-ordering/", views.page_ordering, name="page_ordering"),
    ]

urlpatterns += [
    path("<str:app_label>/<str:model_name>/", views.changelist, name="changelist"),
    path("<str:app_label>/<str:model_name>/add/", views.add, name="add"),
    path(
        "<str:app_label>/<str:model_name>/<path:object_id>/change/",
        views.change,
        name="change",
    ),
    path(
        "<str:app_label>/<str:model_name>/<path:object_id>/delete/",
        views.delete,
        name="delete",
    ),
]
