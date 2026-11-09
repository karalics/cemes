"""
Default settings for the ``mezzanine.admin_htmx`` app.
"""
from django.utils.translation import gettext_lazy as _

from mezzanine.conf import register_setting

register_setting(
    name="ADMIN_HTMX_EXCLUDED_MEDIA",
    description=_(
        "A sequence of substrings matched against the JavaScript and CSS "
        "assets declared by admin classes. Any asset whose path contains "
        "one of these is left out of the htmx admin's pages. It exists so "
        "that scripts written against the classic admin's jQuery and "
        "Grappelli markup - which the htmx admin reimplements natively, "
        "and which would otherwise fight it for control of the same "
        "elements - can be dropped, while widget assets such as the rich "
        "text editor and the media library are still loaded."
    ),
    editable=False,
    default=(
        "admin/dynamic_inline.js",
        "admin/page_tree.js",
        "admin/jquery.mjs.nestedSortable.js",
        "admin/navigation.js",
        "admin/collapse.js",
    ),
)
