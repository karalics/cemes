from django.core.checks import Warning, register

from cemes.conf import settings

TWITTER_DEPRECATED = Warning(
    "'cemes.twitter' is deprecated and will be removed in a future version",
    id="cemes.twitter.W001",
)


@register()
def check_twitter(app_configs, **kwargs):
    issues = []

    if "cemes.twitter" in settings.INSTALLED_APPS:
        issues.append(TWITTER_DEPRECATED)

    return issues
