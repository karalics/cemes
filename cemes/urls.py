"""
This is the main ``urlconf`` for Cemes - it sets up patterns for
all the various Cemes apps, third-party apps like Grappelli and
filebrowser.
"""
from django.contrib.sitemaps.views import sitemap
from django.http import HttpResponse
from django.urls import include, path, re_path
from django.views.i18n import JavaScriptCatalog

from cemes.conf import settings
from cemes.core.sitemaps import DisplayableSitemap

urlpatterns = []

# JavaScript localization feature
js_info_dict = {"domain": "django"}
urlpatterns += [
    re_path(r"^jsi18n/(?P<packages>\S+?)/$", JavaScriptCatalog.as_view(), js_info_dict),
]

if settings.DEBUG and "debug_toolbar" in settings.INSTALLED_APPS:
    try:
        import debug_toolbar
    except ImportError:
        pass
    else:
        urlpatterns += [
            path("__debug__/", include(debug_toolbar.urls)),
        ]

# Django's sitemap app.
if "django.contrib.sitemaps" in settings.INSTALLED_APPS:
    sitemaps = {"sitemaps": {"all": DisplayableSitemap}}
    urlpatterns += [
        path("sitemap.xml", sitemap, sitemaps),
    ]

# Return a robots.txt that disallows all spiders when DEBUG is True.
if getattr(settings, "DEBUG", False):
    urlpatterns += [
        path(
            "robots.txt",
            lambda r: HttpResponse(
                "User-agent: *\nDisallow: /", content_type="text/plain"
            ),
        ),
    ]

# Miscellanous Cemes patterns.
urlpatterns += [
    path("", include("cemes.core.urls")),
    path("", include("cemes.generic.urls")),
]

# Cemes's Accounts app
if "cemes.accounts" in settings.INSTALLED_APPS:
    # We don't define a URL prefix here such as /account/ since we want
    # to honour the LOGIN_* settings, which Django has prefixed with
    # /account/ by default. So those settings are used in accounts.urls
    urlpatterns += [
        path("", include("cemes.accounts.urls")),
    ]

# Cemes's Blog app.
blog_installed = "cemes.blog" in settings.INSTALLED_APPS
if blog_installed:
    BLOG_SLUG = settings.BLOG_SLUG.rstrip("/")
    if BLOG_SLUG:
        BLOG_SLUG += "/"
    blog_patterns = [
        path(BLOG_SLUG, include("cemes.blog.urls")),
    ]
    urlpatterns += blog_patterns

# Cemes's Pages app.
PAGES_SLUG = ""
if "cemes.pages" in settings.INSTALLED_APPS:
    # No BLOG_SLUG means catch-all patterns belong to the blog,
    # so give pages their own prefix and inject them before the
    # blog urlpatterns.
    if blog_installed and not BLOG_SLUG.rstrip("/"):
        PAGES_SLUG = str(getattr(settings, "PAGES_SLUG", "pages").strip("/") + "/")
        blog_patterns_start = urlpatterns.index(blog_patterns[0])
        urlpatterns[blog_patterns_start : len(blog_patterns)] = [
            path(PAGES_SLUG, include("cemes.pages.urls")),
        ]
    else:
        urlpatterns += [
            path("", include("cemes.pages.urls")),
        ]
