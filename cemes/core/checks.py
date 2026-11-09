from django.core.checks import Warning, register

from cemes.conf import settings
from cemes.utils.conf import middlewares_or_subclasses_installed
from cemes.utils.sites import SITE_PERMISSION_MIDDLEWARE

LOADER_TAGS_WARNING = (
    "You have included 'cemes.template.loader_tags' as a builtin in your template "
    "configuration. 'loader_tags' no longer exists and should be removed. If you're "
    "still using the {% overextends %} tag please replace it with Django's "
    "{% extend %} for identical results."
)


@register()
def check_template_settings(app_configs, **kwargs):
    issues = []

    if any(
        "cemes.template.loader_tags"
        in config.get("OPTIONS", {}).get("builtins", {})
        for config in settings.TEMPLATES
    ):
        issues.append(Warning(LOADER_TAGS_WARNING, id="cemes.core.W05"))

    return issues


@register()
def check_sites_middleware(app_configs, **kwargs):

    if not middlewares_or_subclasses_installed([SITE_PERMISSION_MIDDLEWARE]):
        return [
            Warning(
                f"{SITE_PERMISSION_MIDDLEWARE} missing from settings.MIDDLEWARE - "
                "per site permissions not applied",
                id="cemes.core.W04",
            )
        ]
    return []
