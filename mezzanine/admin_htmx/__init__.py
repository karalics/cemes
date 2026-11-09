"""
An alternative admin interface for Mezzanine, built with htmx and
Alpine.js instead of jQuery and Grappelli.

The interface does not define its own registry. It reads all of its
metadata (fieldsets, inlines, list displays, permissions, querysets)
from the ``ModelAdmin`` classes already registered against
``django.contrib.admin.site``, which under Mezzanine is a
``mezzanine.boot.lazy_admin.LazyAdminSite``. Any existing admin class,
whether it ships with Mezzanine, with a third party app, or with the
project itself, is therefore usable without modification.

The classic admin remains mounted in parallel, and is still required
for the widget popups (related object lookups, the media library) that
Django's own form widgets reverse against the ``admin`` URL namespace.
"""

default_app_config = "mezzanine.admin_htmx.apps.AdminHtmxConfig"
