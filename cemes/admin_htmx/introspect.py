"""
Helpers for reading metadata out of the ``ModelAdmin`` classes
registered against Django's admin site, and for reversing URLs into
this app's namespace rather than the classic admin's.
"""
import django
from django.contrib import admin
from django.contrib.admin.utils import quote
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.urls import NoReverseMatch, reverse

NAMESPACE = "admin_htmx"

# The querystring parameter Django's ChangeList uses for pagination was
# 0-indexed until Django 3.2, and 1-indexed from 3.2 onwards.
PAGE_NUM_IS_ONE_BASED = django.VERSION >= (3, 2)


JQUERY_COMPAT = "cemes/admin_htmx/js/jquery-compat.js"


def filter_media(media):
    """
    Adapt a ``Media`` instance declared for the classic admin so it can
    be loaded by this interface.

    Two things happen here.

    Assets listed in ``ADMIN_HTMX_EXCLUDED_MEDIA`` are dropped. Most of
    what admin classes declare - rich text editors, the media library's
    file picker, date pickers, related object lookups - is widget level
    and works unchanged, so media is passed through rather than
    discarded. The exceptions are the few scripts that drive admin
    chrome this app renders itself; loading those would mean two
    implementations binding the same elements.

    The jQuery compatibility shim is then slotted in directly after
    Django's ``jquery.init.js``, so that widget scripts expecting the
    global ``jQuery`` that Grappelli provides find one before they run.
    """
    from django import forms
    from django.templatetags.static import static

    from cemes.conf import settings

    excluded = tuple(settings.ADMIN_HTMX_EXCLUDED_MEDIA)

    def keep(path):
        return not any(fragment in str(path) for fragment in excluded)

    js = []
    for path in media._js:
        if not keep(path):
            continue
        js.append(path)
        if str(path).endswith("jquery.init.js"):
            js.append(static(JQUERY_COMPAT))

    return forms.Media(
        js=js,
        css={
            medium: [path for path in paths if keep(path)]
            for medium, paths in media._css.items()
        },
    )


def get_registry():
    """
    The live registry of the admin site. Looked up on each call rather
    than cached, because ``LazyAdminSite`` populates it during
    ``autodiscover()`` and ``ADMIN_REMOVAL`` prunes it afterwards.
    """
    return admin.site._registry


def model_label(model):
    """``app.Model``, the format used by ``ADMIN_MENU_ORDER``."""
    opts = model._meta
    return f"{opts.app_label}.{opts.object_name}"


def get_model_admin(app_label, model_name):
    """
    Return the registered ``ModelAdmin`` for the given labels, raising
    404 for models that aren't registered. Matching is case insensitive
    on the model name, as Django's own admin URLs are lowercase.
    """
    app_label = app_label.lower()
    model_name = model_name.lower()
    for model, model_admin in get_registry().items():
        opts = model._meta
        if opts.app_label.lower() == app_label and opts.model_name == model_name:
            return model_admin
    raise Http404(f"No registered admin for {app_label}.{model_name}")


def admin_url(model, action, *args):
    """
    Reverse a URL in this app's namespace. Mirrors the signature of
    ``cemes.utils.urls.admin_url``, which reverses into the classic
    admin's namespace instead.
    """
    opts = model._meta
    return reverse(
        f"{NAMESPACE}:{action}",
        args=(opts.app_label, opts.model_name) + tuple(quote(a) for a in args),
    )


def try_admin_url(model, action, *args):
    """``admin_url`` returning ``None`` instead of raising."""
    try:
        return admin_url(model, action, *args)
    except NoReverseMatch:
        return None


#########################
# Permission delegation #
#########################


def check_model_permission(request, model_admin, action, obj=None):
    """
    Run both halves of Cemes's permission story and raise
    ``PermissionDenied`` if either refuses:

    1. Django's standard ``has_{action}_permission`` on the ModelAdmin.
    2. Cemes's ``check_permission(request, obj, action)`` hook,
       which ``PageAdmin`` implements in terms of the page's own
       ``can_add`` / ``can_change`` / ``can_delete`` methods, and which
       honours per-site permissions.
    """
    checker = getattr(model_admin, f"has_{action}_permission", None)
    if checker is not None:
        # ``has_add_permission`` takes no object, the others accept one.
        allowed = checker(request) if action == "add" else checker(request, obj)
        if not allowed:
            raise PermissionDenied
    hook = getattr(model_admin, "check_permission", None)
    if hook is not None and obj is not None:
        # Raises PermissionDenied itself when it refuses.
        hook(request, obj, action)


def model_perms(request, model_admin):
    """
    The add/change/delete/view flags for a model, as used to decide
    which controls to render.
    """
    return {
        "add": model_admin.has_add_permission(request),
        "change": model_admin.has_change_permission(request),
        "delete": model_admin.has_delete_permission(request),
        "view": model_admin.has_view_permission(request),
    }


##############################
# Content typed (Page) models #
##############################


def is_content_typed(model_admin):
    """
    Whether this admin manages a ``ContentTyped`` model, ie a ``Page``
    or one of its subclasses, which need add/change redirection between
    the concrete model and the subclass that holds the content.
    """
    return getattr(model_admin, "concrete_model", None) is not None


def is_concrete_content_model(model_admin):
    """Whether this admin is for the base model, eg ``Page`` itself."""
    return is_content_typed(model_admin) and (
        model_admin.model is model_admin.concrete_model
    )


def content_models(model_admin):
    """
    The admin-registered subclasses of a content typed model, ordered by
    the admin class's own ``get_content_models()`` so that the
    ``ADD_PAGE_ORDER`` setting is honoured, with URLs rewritten into
    this app's namespace.
    """
    models = []
    registry = get_registry()
    for model in model_admin.concrete_model.get_content_models():
        if model not in registry:
            continue
        add_url = try_admin_url(model, "add")
        if add_url is None:
            continue
        models.append(
            {
                "model": model,
                "verbose_name": model._meta.verbose_name,
                "add_url": add_url,
            }
        )
    # ``get_content_models`` on PageAdmin applies ADD_PAGE_ORDER, but it
    # also decorates the model classes with URLs for the classic admin,
    # so only its ordering is reused here.
    try:
        ordered = model_admin.get_content_models()
    except Exception:
        return models
    order = {m: i for i, m in enumerate(ordered)}
    return sorted(models, key=lambda m: order.get(m["model"], len(order)))


################
# Pagination   #
################


def page_query_value(number):
    """
    Translate a 1-based page number into the value Django's ChangeList
    expects in the querystring for the running version.
    """
    return number if PAGE_NUM_IS_ONE_BASED else number - 1


def current_page_number(change_list):
    """The 1-based number of the page a ChangeList is showing."""
    if PAGE_NUM_IS_ONE_BASED:
        return change_list.page_num
    return change_list.page_num + 1
