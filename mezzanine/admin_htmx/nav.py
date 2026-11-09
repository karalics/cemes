"""
Builds the admin navigation from the ``ADMIN_MENU_ORDER`` setting.

This is a port of ``mezzanine.core.templatetags.mezzanine_tags``'s
``admin_app_list``, keeping its grouping, ordering and permission
semantics identical, but reversing model URLs into this app's
namespace. Entries given as ``(title, url_name)`` pairs, such as the
media library, still reverse against their original URL names and so
continue to point at the classic admin where that's where they live.
"""
from django.urls import NoReverseMatch, reverse
from django.utils.text import capfirst

from mezzanine.admin_htmx.introspect import get_registry, model_label, try_admin_url
from mezzanine.conf import settings


def _menu_order():
    """
    Flatten ``ADMIN_MENU_ORDER`` into a lookup of
    ``item -> (group index, group title, item index, item title)``.
    """
    order = {}
    for group_index, group in enumerate(settings.ADMIN_MENU_ORDER):
        group_title, items = group
        for item_index, item in enumerate(items):
            if isinstance(item, (tuple, list)):
                item_title, item = item
            else:
                item_title = None
            order[item] = (group_index, group_title, item_index, item_title)
    return order


def app_list(request):
    """
    Return the navigation as a list of groups, each a dict with a
    ``name`` and a list of ``models``. Models the user may not touch,
    and models whose admin hides itself via ``has_module_permission``
    (which is how ``ContentTypedAdmin`` keeps ``Page`` subclasses out of
    the menu), are left out.
    """
    groups = {}
    menu_order = _menu_order()

    for model, model_admin in get_registry().items():
        opts = model._meta
        if not model_admin.has_module_permission(request):
            continue
        if not request.user.has_module_perms(opts.app_label):
            continue

        change_url = add_url = None
        if model_admin.has_change_permission(request) or (
            model_admin.has_view_permission(request)
        ):
            change_url = try_admin_url(model, "changelist")
        if model_admin.has_add_permission(request):
            add_url = try_admin_url(model, "add")
        if change_url is None and add_url is None:
            continue

        label = model_label(model)
        try:
            group_index, group_title, item_index, item_title = menu_order.pop(label)
        except KeyError:
            group_index = item_index = None
            item_title = None
            try:
                group_title = opts.app_config.verbose_name.title()
            except AttributeError:
                # Third party admin classes doing weird things.
                group_title = ""

        groups.setdefault(
            group_title, {"index": group_index, "name": group_title, "models": []}
        )
        groups[group_title]["models"].append(
            {
                "index": item_index,
                "name": item_title or capfirst(opts.verbose_name_plural),
                "object_name": opts.object_name,
                "admin_url": change_url,
                "add_url": add_url,
            }
        )

    # Remaining entries are view or URL pattern names, given in the
    # setting as ``(title, name)`` - eg the media library.
    for item_url, item in menu_order.items():
        group_index, group_title, item_index, item_title = item
        try:
            item_url = reverse(item_url)
        except NoReverseMatch:
            continue
        groups.setdefault(
            group_title, {"index": group_index, "name": group_title, "models": []}
        )
        groups[group_title]["models"].append(
            {
                "index": item_index,
                "name": item_title,
                "object_name": None,
                "admin_url": item_url,
                "add_url": None,
            }
        )

    def sort_key(item):
        return (item["index"] if item["index"] is not None else 999, item["name"])

    result = list(groups.values())
    for group in result:
        group["models"].sort(key=sort_key)
    result.sort(key=sort_key)
    return result


def mark_active(groups, path):
    """
    Flag the navigation entry matching the current path, so the
    template can highlight it. The longest matching URL wins, so that
    ``/admin/pages/page/`` doesn't claim ``/admin/pages/page/3/change/``
    away from a more specific entry.
    """
    best = None
    for group in groups:
        for item in group["models"]:
            url = item["admin_url"]
            item["active"] = False
            if url and path.startswith(url):
                if best is None or len(url) > len(best[1]["admin_url"]):
                    best = (group, item)
    if best is not None:
        group, item = best
        item["active"] = True
        group["active"] = True
    return groups
