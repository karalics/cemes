"""
Views for the htmx admin.

Every view delegates to the registered ``ModelAdmin`` for metadata,
querysets, form construction, saving and permissions, so that admin
classes written for the classic admin behave identically here. Where
Django's admin views contain logic worth reusing verbatim - action
dispatch, change messages, deletion collection - the corresponding
``ModelAdmin`` method or admin utility is called rather than
reimplemented.
"""
from functools import wraps

from django.contrib import messages
from django.contrib.admin import helpers
from django.contrib.admin.models import LogEntry
from django.contrib.admin.templatetags.admin_list import (
    date_hierarchy,
    result_headers,
    results,
)
from django.contrib.admin.utils import get_deleted_objects, quote, unquote
from django.contrib.auth import logout
from django.contrib.auth import views as auth_views
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied
from django.db import router, transaction
from django.forms.formsets import all_valid
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from cemes.admin_htmx import nav
from cemes.admin_htmx.introspect import (
    NAMESPACE,
    admin_url,
    check_model_permission,
    content_models,
    current_page_number,
    filter_media,
    get_model_admin,
    is_concrete_content_model,
    is_content_typed,
    model_perms,
    page_query_value,
    try_admin_url,
)
from cemes.conf import settings
from cemes.utils.sites import current_site_id, has_site_permission

PAGES_INSTALLED = "cemes.pages" in settings.INSTALLED_APPS


def admin_view(view):
    """
    Restrict a view to active staff who have staff access to the
    current site, sending everyone else to the login page.

    The second half matters under Cemes: a user can be staff
    globally while only being granted access to some of the sites in a
    multi-site install. ``SitePermissionMiddleware`` resolves that per
    request, but only enforces it for paths below the classic admin's
    own prefix, so the check is repeated here for this interface.
    """

    @wraps(view)
    def inner(request, *args, **kwargs):
        user = request.user
        login_url = reverse(f"{NAMESPACE}:login")
        if not (user.is_authenticated and user.is_active and user.is_staff):
            return redirect_to_login(request.get_full_path(), login_url)
        if not has_site_permission(user):
            logout(request)
            messages.error(
                request,
                _("You don't have permission to administer this site."),
            )
            return HttpResponseRedirect(login_url)
        return view(request, *args, **kwargs)

    return inner


def _available_sites(request):
    """
    The sites this user may administer, for the site switcher. Returns
    an empty list for single-site installs, where the switcher is
    pointless.
    """
    from django.contrib.sites.models import Site

    if request.user.is_superuser:
        sites = Site.objects.all()
    else:
        try:
            sites = request.user.sitepermissions.sites.all()
        except ObjectDoesNotExist:
            return []
    sites = list(sites)
    return sites if len(sites) > 1 else []


def base_context(request, **extra):
    """
    Context every page needs: the navigation, and the bits of chrome
    that come from Cemes's settings.
    """
    context = {
        "nav_groups": nav.mark_active(nav.app_list(request), request.path),
        "site_title": settings.SITE_TITLE,
        "nav_collapsed": settings.ADMIN_MENU_COLLAPSED,
        "available_sites": _available_sites(request),
        "current_site_id": current_site_id(),
        # Switching site mid-edit would land on an object that may not
        # exist on the site being switched to, so hand the switcher a
        # destination that always exists.
        "switch_site_next": reverse(f"{NAMESPACE}:index"),
        "opts": None,
    }
    context.update(extra)
    return context


def _is_htmx(request):
    return request.headers.get("HX-Request") == "true"


#############
# Dashboard #
#############


@admin_view
def index(request):
    """
    The dashboard. Cemes's ``DASHBOARD_TAGS`` setting is not used
    here, because the template tags it points at render markup for the
    classic admin's stylesheets. The same information - the app list,
    recent actions, and recent comments - is rendered natively instead.
    """
    # Links are built against this app rather than through
    # ``LogEntry.get_admin_url``, which reverses into the classic
    # admin's namespace.
    log_entries = []
    entries = (
        LogEntry.objects.select_related("content_type", "user")
        .filter(user__id=request.user.pk)
        .order_by("-action_time")[:10]
    )
    for entry in entries:
        model = entry.content_type.model_class() if entry.content_type else None
        url = None
        if model is not None and not entry.is_deletion():
            url = try_admin_url(model, "change", entry.object_id)
        log_entries.append(
            {
                "repr": entry.object_repr,
                "url": url,
                "type": entry.content_type.name if entry.content_type else "",
                "action": (
                    "add"
                    if entry.is_addition()
                    else "change"
                    if entry.is_change()
                    else "delete"
                ),
            }
        )
    recent_comments = None
    if "cemes.generic" in settings.INSTALLED_APPS:
        from cemes.generic.models import ThreadedComment

        recent_comments = ThreadedComment.objects.visible().order_by("-submit_date")[:5]
    context = base_context(
        request,
        title=_("Dashboard"),
        log_entries=log_entries,
        recent_comments=recent_comments,
    )
    return render(request, "admin_htmx/dashboard.html", context)


##############
# Change list #
##############


def _patch_result_urls(change_list, model_admin):
    """
    Django's ChangeList links each row at the classic admin's change
    view, because it reverses against its ModelAdmin's ``admin_site``.
    Point the links at this app instead.
    """
    opts = model_admin.model._meta

    def url_for_result(result):
        pk = getattr(result, change_list.pk_attname)
        return reverse(
            f"{NAMESPACE}:change",
            args=(opts.app_label, opts.model_name, quote(pk)),
        )

    change_list.url_for_result = url_for_result


def _handle_list_editable(request, change_list, model_admin):
    """
    Save the editable columns of the change list, mirroring the
    corresponding block of ``ModelAdmin.changelist_view``. Returns a
    response to redirect to when a save happened, otherwise ``None``.
    """
    FormSet = model_admin.get_changelist_formset(request)
    prefix = FormSet.get_default_prefix()
    if not model_admin.has_change_permission(request):
        raise PermissionDenied
    get_editable_queryset = getattr(model_admin, "_get_list_editable_queryset", None)
    if get_editable_queryset is not None:
        queryset = get_editable_queryset(request, prefix)
    else:
        queryset = change_list.result_list
    formset = change_list.formset = FormSet(
        request.POST, request.FILES, queryset=queryset
    )
    if not formset.is_valid():
        return None
    changed = 0
    with transaction.atomic(using=router.db_for_write(model_admin.model)):
        for form in formset.forms:
            if not form.has_changed():
                continue
            obj = model_admin.save_form(request, form, change=True)
            check_model_permission(request, model_admin, "change", obj)
            model_admin.save_model(request, obj, form, change=True)
            model_admin.save_related(request, form, formsets=[], change=True)
            change_msg = model_admin.construct_change_message(request, form, None)
            model_admin.log_change(request, obj, change_msg)
            changed += 1
    if changed:
        messages.success(
            request,
            _("%(count)d item(s) changed successfully.") % {"count": changed},
        )
    return HttpResponseRedirect(request.get_full_path())


@admin_view
def changelist(request, app_label, model_name):
    model_admin = get_model_admin(app_label, model_name)
    if not (
        model_admin.has_view_permission(request)
        or model_admin.has_change_permission(request)
    ):
        raise PermissionDenied

    # Content typed models: only the concrete model is listed, and its
    # subclasses redirect to it, matching ContentTypedAdmin.
    if is_content_typed(model_admin) and not is_concrete_content_model(model_admin):
        return redirect(admin_url(model_admin.concrete_model, "changelist"))

    # Settings are edited as one form rather than as a list of rows.
    if model_admin.model._meta.label == "conf.Setting":
        return redirect(f"{NAMESPACE}:settings")

    # Pages are shown as a draggable tree instead of a flat list.
    if PAGES_INSTALLED:
        from cemes.pages.models import Page

        if model_admin.model is Page:
            return page_tree(request)

    change_list = model_admin.get_changelist_instance(request)
    _patch_result_urls(change_list, model_admin)

    # Actions, including delete_selected and any custom actions, are
    # dispatched by the ModelAdmin itself.
    actions = model_admin.get_actions(request)
    if actions and request.method == "POST" and "index" in request.POST:
        response = model_admin.response_action(
            request, queryset=change_list.get_queryset(request)
        )
        if response is not None:
            return response

    if (
        request.method == "POST"
        and change_list.list_editable
        and "_save" in request.POST
    ):
        response = _handle_list_editable(request, change_list, model_admin)
        if response is not None:
            return response
    elif change_list.list_editable and model_admin.has_change_permission(request):
        FormSet = model_admin.get_changelist_formset(request)
        change_list.formset = FormSet(queryset=change_list.result_list)
    else:
        change_list.formset = None

    opts = model_admin.model._meta
    context = base_context(
        request,
        title=change_list.title,
        opts=opts,
        cl=change_list,
        perms=model_perms(request, model_admin),
        headers=list(result_headers(change_list)),
        rows=list(results(change_list)),
        date_hierarchy=(
            date_hierarchy(change_list) if change_list.date_hierarchy else None
        ),
        # ``FilterSpec.choices()`` takes the change list as an argument,
        # which a template can't pass, so resolve them here.
        filter_specs=[
            {"title": spec.title, "choices": list(spec.choices(change_list))}
            for spec in change_list.filter_specs
        ],
        action_form=(helpers.ActionForm(auto_id=None) if actions else None),
        action_choices=model_admin.get_action_choices(request) if actions else [],
        media=filter_media(model_admin.media),
        page_numbers=_page_numbers(change_list),
        add_url=admin_url(model_admin.model, "add"),
        content_models=(
            content_models(model_admin)
            if is_concrete_content_model(model_admin)
            else None
        ),
    )
    if context["action_form"] is not None:
        context["action_form"].fields["action"].choices = context["action_choices"]
    if _is_htmx(request):
        # Search, filtering, sorting and pagination all swap just the
        # results region.
        return render(request, "admin_htmx/includes/results.html", context)
    return render(request, "admin_htmx/changelist.html", context)


def _page_numbers(change_list):
    """
    Pagination links as ``(label, querystring, is_current)`` triples,
    elided around the current page.
    """
    paginator = change_list.paginator
    if paginator.num_pages <= 1:
        return []
    current = current_page_number(change_list)
    numbers = []
    for number in paginator.page_range:
        near = abs(number - current) <= 2
        edge = number in (1, paginator.num_pages)
        if not (near or edge):
            if numbers and numbers[-1][0] != "…":
                numbers.append(("…", None, False))
            continue
        query = change_list.get_query_string({"p": page_query_value(number)})
        numbers.append((number, query, number == current))
    return numbers


###############
# Change form #
###############


def _changeform(request, model_admin, obj):
    """
    Shared implementation of the add and change views, following the
    order of operations in ``ModelAdmin._changeform_view``.
    """
    change = obj is not None
    opts = model_admin.model._meta
    action = "change" if change else "add"
    check_model_permission(request, model_admin, action, obj)

    ModelForm = model_admin.get_form(request, obj, change=change)
    if request.method == "POST":
        form = ModelForm(request.POST, request.FILES, instance=obj)
        form_validated = form.is_valid()
        if form_validated:
            new_object = model_admin.save_form(request, form, change=change)
        else:
            new_object = form.instance
        formsets, inline_instances = model_admin._create_formsets(
            request, new_object, change=change
        )
        if all_valid(formsets) and form_validated:
            model_admin.save_model(request, new_object, form, change)
            model_admin.save_related(request, form, formsets, change)
            if change:
                change_message = model_admin.construct_change_message(
                    request, form, formsets
                )
                model_admin.log_change(request, new_object, change_message)
            else:
                model_admin.log_addition(
                    request,
                    new_object,
                    model_admin.construct_change_message(request, form, formsets, True),
                )
            return _response_post_save(request, model_admin, new_object, change)
    else:
        initial = model_admin.get_changeform_initial_data(request) if not change else {}
        form = ModelForm(instance=obj, initial=initial or None)
        formsets, inline_instances = model_admin._create_formsets(
            request, obj if change else model_admin.model(), change=change
        )

    readonly = list(model_admin.get_readonly_fields(request, obj))
    admin_form = helpers.AdminForm(
        form,
        list(model_admin.get_fieldsets(request, obj)),
        model_admin.get_prepopulated_fields(request, obj)
        if model_admin.has_change_permission(request, obj) or not change
        else {},
        readonly,
        model_admin=model_admin,
    )
    inline_formsets = model_admin.get_inline_formsets(
        request, formsets, inline_instances, obj
    )
    media = model_admin.media + admin_form.media
    for inline_formset in inline_formsets:
        media = media + inline_formset.media
    media = filter_media(media)

    title = (_("Add %s") if not change else _("Change %s")) % opts.verbose_name
    perms = model_perms(request, model_admin)

    # PageAdmin signals these through extra_context in the classic
    # admin; honour the same flags here.
    hide_delete = False
    hide_slug = False
    if change and is_content_typed(model_admin):
        content_model = getattr(obj, "get_content_model", lambda: obj)()
        if hasattr(content_model, "can_delete"):
            hide_delete = not content_model.can_delete(request)
        if hasattr(content_model, "overridden"):
            hide_slug = content_model.overridden()

    context = base_context(
        request,
        title=title,
        opts=opts,
        original=obj,
        object_id=quote(obj.pk) if change else None,
        adminform=admin_form,
        inline_formsets=inline_formsets,
        media=media,
        errors=helpers.AdminErrorList(form, formsets),
        perms=perms,
        change=change,
        hide_delete_link=hide_delete,
        hide_slug_field=hide_slug,
        show_save_and_add_another=not getattr(model_admin, "singleton", False),
        changelist_url=admin_url(model_admin.model, "changelist"),
        delete_url=(
            admin_url(model_admin.model, "delete", obj.pk)
            if change and perms["delete"] and not hide_delete
            else None
        ),
        parent_id=request.GET.get("parent"),
    )
    return render(request, "admin_htmx/changeform.html", context)


def _response_post_save(request, model_admin, obj, change):
    """
    Where to go after a successful save, honouring the three save
    buttons, and preserving the ``parent`` querystring that
    ``PageAdmin`` uses to place a new page in the tree.
    """
    opts = model_admin.model._meta
    name = str(obj)
    if change:
        messages.success(
            request,
            format_html(
                _('The {} "{}" was changed successfully.'), opts.verbose_name, name
            ),
        )
    else:
        messages.success(
            request,
            format_html(
                _('The {} "{}" was added successfully.'), opts.verbose_name, name
            ),
        )

    parent = request.GET.get("parent")
    suffix = f"?parent={parent}" if parent else ""

    if "_continue" in request.POST:
        return HttpResponseRedirect(
            admin_url(model_admin.model, "change", obj.pk) + suffix
        )
    if "_addanother" in request.POST:
        return HttpResponseRedirect(admin_url(model_admin.model, "add") + suffix)
    return HttpResponseRedirect(admin_url(model_admin.model, "changelist"))


@admin_view
def add(request, app_label, model_name):
    model_admin = get_model_admin(app_label, model_name)
    if not model_admin.has_add_permission(request):
        raise PermissionDenied
    # Adding the concrete content typed model is meaningless - redirect
    # to the first of its subclasses, as PageAdmin.add_view does.
    if is_concrete_content_model(model_admin):
        available = content_models(model_admin)
        if available:
            return redirect(available[0]["add_url"])
    return _changeform(request, model_admin, None)


@admin_view
def change(request, app_label, model_name, object_id):
    model_admin = get_model_admin(app_label, model_name)
    obj = model_admin.get_object(request, unquote(object_id))
    if obj is None:
        raise Http404(
            _("%(name)s object with primary key %(key)r does not exist.")
            % {"name": model_admin.model._meta.verbose_name, "key": object_id}
        )
    # For a content typed model, the row in the concrete table is only
    # a stub - redirect to the admin of the subclass holding the data.
    if is_content_typed(model_admin):
        content_model = obj.get_content_model()
        if (
            content_model is not None
            and content_model.__class__ is not model_admin.model
        ):
            return redirect(
                admin_url(content_model.__class__, "change", content_model.pk)
            )
    return _changeform(request, model_admin, obj)


##########
# Delete #
##########


@admin_view
def delete(request, app_label, model_name, object_id):
    model_admin = get_model_admin(app_label, model_name)
    obj = model_admin.get_object(request, unquote(object_id))
    if obj is None:
        raise Http404
    check_model_permission(request, model_admin, "delete", obj)

    deleted, model_count, perms_needed, protected = get_deleted_objects(
        [obj], request, model_admin.admin_site
    )

    if request.method == "POST":
        if perms_needed:
            raise PermissionDenied
        name = str(obj)
        # log_deletion() is deprecated from Django 5.1 in favour of
        # log_deletions(), which doesn't exist before it.
        if hasattr(model_admin, "log_deletions"):
            model_admin.log_deletions(request, [obj])
        else:
            model_admin.log_deletion(request, obj, name)
        model_admin.delete_model(request, obj)
        messages.success(
            request,
            format_html(
                _('The {} "{}" was deleted successfully.'),
                model_admin.model._meta.verbose_name,
                name,
            ),
        )
        return HttpResponseRedirect(admin_url(model_admin.model, "changelist"))

    context = base_context(
        request,
        title=_("Are you sure?"),
        opts=model_admin.model._meta,
        original=obj,
        deleted_objects=deleted,
        model_count=dict(model_count).items(),
        perms_lacking=perms_needed,
        protected=protected,
        changelist_url=admin_url(model_admin.model, "changelist"),
    )
    return render(request, "admin_htmx/delete_confirm.html", context)


#############
# Page tree #
#############


@admin_view
def page_tree(request):
    """
    The page tree, listed as a nested, drag-and-drop sortable list.
    Reordering is posted to ``cemes.pages.views.admin_page_ordering``
    via ``page_ordering`` below, so the move permission checks and
    sibling reordering logic are shared with the classic admin.
    """
    from cemes.pages.models import Page

    model_admin = get_model_admin("pages", "page")
    pages = Page.objects.published(for_user=request.user).order_by("_order")
    pages = pages.select_related("site")

    # Build the tree in one pass, keyed by parent.
    children = {}
    for page in pages:
        children.setdefault(page.parent_id, []).append(page)

    def branch(parent_id):
        nodes = []
        for page in children.get(parent_id, []):
            content_model = page.get_content_model() or page
            nodes.append(
                {
                    "page": page,
                    "title": page.title,
                    "status": page.get_status_display(),
                    "is_published": page.status == 2,
                    "change_url": admin_url(
                        content_model.__class__, "change", content_model.pk
                    ),
                    "delete_url": (
                        admin_url(content_model.__class__, "delete", content_model.pk)
                        if content_model.can_delete(request)
                        else None
                    ),
                    "can_change": content_model.can_change(request),
                    "children": branch(page.id),
                }
            )
        return nodes

    context = base_context(
        request,
        title=_("Pages"),
        opts=Page._meta,
        tree=branch(None),
        perms=model_perms(request, model_admin),
        content_models=content_models(model_admin),
        ordering_url=reverse(f"{NAMESPACE}:page_ordering"),
    )
    return render(request, "admin_htmx/page_tree.html", context)


@admin_view
@require_POST
def page_ordering(request):
    """
    Thin wrapper around Cemes's existing ordering view, translating
    the htmx payload into the form that view expects.
    """
    from cemes.pages.views import admin_page_ordering

    return admin_page_ordering(request)


############
# Settings #
############


@admin_view
def site_settings(request):
    """
    All editable settings as a single form, matching the behaviour of
    ``cemes.conf.admin.SettingsAdmin``.
    """
    from cemes.conf.forms import SettingsForm
    from cemes.conf.models import Setting

    model_admin = get_model_admin("conf", "setting")
    if not model_admin.has_change_permission(request):
        raise PermissionDenied

    form = SettingsForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        settings.clear_cache()
        messages.success(request, _("Settings were successfully updated."))
        return redirect(f"{NAMESPACE}:settings")

    context = base_context(
        request,
        title=_("Settings"),
        opts=Setting._meta,
        settings_form=form,
        media=filter_media(form.media),
    )
    return render(request, "admin_htmx/settings.html", context)


#########
# Login #
#########


class LoginView(auth_views.LoginView):

    template_name = "admin_htmx/login.html"

    def dispatch(self, request, *args, **kwargs):
        """
        Send a user who may already administer this site straight on,
        rather than showing them a login form they don't need. This is
        deliberately narrower than Django's
        ``redirect_authenticated_user``, which would bounce an
        authenticated non-staff user between the login page and the
        dashboard forever.
        """
        user = request.user
        if (
            user.is_authenticated
            and user.is_active
            and user.is_staff
            and has_site_permission(user)
        ):
            return HttpResponseRedirect(self.get_success_url())
        return super().dispatch(request, *args, **kwargs)

    def get_success_url(self):
        # LoginView.next_page only exists from Django 4.0.
        return self.get_redirect_url() or reverse(f"{NAMESPACE}:index")

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        # Cemes's auth backend accepts either.
        form.fields["username"].label = _("Username or email")
        return form

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["site_title"] = settings.SITE_TITLE
        return context


class LogoutView(auth_views.LogoutView):

    template_name = "admin_htmx/logged_out.html"
