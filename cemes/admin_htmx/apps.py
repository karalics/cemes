from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class AdminHtmxConfig(AppConfig):

    name = "cemes.admin_htmx"
    label = "admin_htmx"
    verbose_name = _("Admin (htmx)")
