from django.contrib.auth import get_user_model
from django.contrib.sites.models import Site
from django.urls import reverse

from cemes.admin_htmx import nav
from cemes.admin_htmx.introspect import (
    content_models,
    filter_media,
    get_model_admin,
    is_concrete_content_model,
)
from cemes.blog.models import BlogPost
from cemes.conf import settings
from cemes.core.models import CONTENT_STATUS_DRAFT, CONTENT_STATUS_PUBLISHED
from cemes.pages.models import Page, RichTextPage
from cemes.utils.tests import TestCase

User = get_user_model()


def setUpModule():
    """
    Loading the project's URLconf runs ``admin.autodiscover()``, which
    is what fills the registry this interface reads its metadata from.
    """
    reverse("admin_htmx:index")


class AdminHtmxTestCase(TestCase):
    """
    The htmx admin reads everything from the registered ModelAdmin
    classes, so these tests are mostly about that reuse holding: that
    the pages the interface serves reflect what the admin classes say,
    and that Cemes's admin behaviours - content typed redirection,
    per-site staff access, the single form for settings - survive the
    move.

    The change list tests use ``BlogPost`` rather than a page, because
    the admin for a ``Page`` subclass deliberately has no list of its
    own: it redirects to the page tree.
    """

    def setUp(self):
        super().setUp()
        self.client.force_login(self._user)

    def post(self, **fields):
        return BlogPost.objects.create(user=self._user, **fields)

    def request_for(self, path):
        request = self._request_factory.get(path)
        request.user = self._user
        # Normally set by SitePermissionMiddleware.
        request.user.has_site_permission = True
        return request


class AccessTests(AdminHtmxTestCase):
    def test_dashboard_renders(self):
        response = self.client.get(reverse("admin_htmx:index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Dashboard")

    def test_login_required(self):
        self.client.logout()
        response = self.client.get(reverse("admin_htmx:index"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("admin_htmx:login"), response["Location"])

    def test_non_staff_is_rejected(self):
        User.objects.create_user("plain", "plain@example.com", "pass")
        self.client.logout()
        self.client.login(username="plain", password="pass")
        response = self.client.get(reverse("admin_htmx:index"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("admin_htmx:login"), response["Location"])

    def test_staff_without_site_permission_is_rejected(self):
        """
        SitePermissionMiddleware only guards paths below the classic
        admin's prefix, so this interface enforces the same rule itself.
        """
        User.objects.create_user("editor", "editor@example.com", "pass", is_staff=True)
        self.client.logout()
        self.client.login(username="editor", password="pass")
        response = self.client.get(reverse("admin_htmx:index"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("admin_htmx:login"))

    def test_unregistered_model_is_404(self):
        url = reverse("admin_htmx:changelist", args=("nonesuch", "nothing"))
        self.assertEqual(self.client.get(url).status_code, 404)


class ChangeListTests(AdminHtmxTestCase):

    url_args = ("blog", "blogpost")

    @property
    def url(self):
        return reverse("admin_htmx:changelist", args=self.url_args)

    def test_changelist_lists_objects(self):
        self.post(title="Colophon")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Colophon")

    def test_columns_come_from_list_display(self):
        """
        The headers are built by Django's ChangeList from the admin
        class's own ``list_display``, plus the action checkbox column.
        """
        self.post(title="Colophon")
        model_admin = get_model_admin(*self.url_args)
        response = self.client.get(self.url)
        self.assertEqual(
            len(response.context["headers"]), len(model_admin.list_display) + 1
        )

    def test_filters_come_from_list_filter(self):
        """
        Only filters with something to show are rendered - Django drops
        the rest - so this checks the status filter declared by
        DisplayableAdmin arrives with its choices resolved.
        """
        self.post(title="Colophon")
        response = self.client.get(self.url)
        titles = [
            str(spec["title"]).lower() for spec in response.context["filter_specs"]
        ]
        self.assertIn("status", titles)
        status = response.context["filter_specs"][titles.index("status")]
        self.assertTrue(status["choices"])
        self.assertTrue(all("query_string" in choice for choice in status["choices"]))

    def test_htmx_request_returns_only_the_results_region(self):
        self.post(title="Colophon")
        response = self.client.get(self.url, HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="cl-main"')
        self.assertNotContains(response, "<body")

    def test_full_request_returns_the_whole_page(self):
        response = self.client.get(self.url)
        self.assertContains(response, "<body")

    def test_search_form_is_inside_the_swapped_region(self):
        """
        Search and filtering each have to carry the other's state. That
        only holds if the search form - whose hidden inputs replay the
        active filters - is re-rendered by every swap, so it has to live
        inside the partial, not in the page around it.
        """
        self.post(title="Colophon")
        response = self.client.get(self.url, HTTP_HX_REQUEST="true")
        self.assertContains(response, 'class="search-form"')

    def test_search_keeps_active_filters(self):
        self.post(title="Colophon", status=CONTENT_STATUS_PUBLISHED)
        response = self.client.get(
            self.url,
            {"q": "Colophon", "status__exact": str(CONTENT_STATUS_PUBLISHED)},
            HTTP_HX_REQUEST="true",
        )
        # Replayed as a hidden input so the next keystroke resubmits it.
        self.assertContains(response, 'name="status__exact"')

    def test_search_filters_results(self):
        self.post(title="Colophon")
        self.post(title="Errata")
        response = self.client.get(self.url, {"q": "Colophon"}, HTTP_HX_REQUEST="true")
        self.assertContains(response, "Colophon")
        self.assertNotContains(response, "Errata")

    def test_row_links_target_this_interface(self):
        post = self.post(title="Colophon")
        response = self.client.get(self.url)
        expected = reverse("admin_htmx:change", args=self.url_args + (post.pk,))
        self.assertContains(response, expected)

    def test_actions_are_dispatched_by_the_model_admin(self):
        post = self.post(title="Doomed")
        response = self.client.post(
            self.url,
            {
                "action": "delete_selected",
                "index": "0",
                "select_across": "0",
                "_selected_action": [str(post.pk)],
            },
        )
        # delete_selected renders its own confirmation page rather than
        # deleting straight away.
        self.assertEqual(response.status_code, 200)
        self.assertTrue(BlogPost.objects.filter(pk=post.pk).exists())

    def test_list_editable_saves(self):
        """
        DisplayableAdmin declares ``list_editable = ("status",)``.
        """
        post = self.post(title="Colophon", status=CONTENT_STATUS_DRAFT)
        response = self.client.post(
            self.url,
            {
                "_save": "1",
                "form-TOTAL_FORMS": "1",
                "form-INITIAL_FORMS": "1",
                "form-MIN_NUM_FORMS": "0",
                "form-MAX_NUM_FORMS": "0",
                "form-0-id": str(post.pk),
                "form-0-status": str(CONTENT_STATUS_PUBLISHED),
            },
        )
        self.assertEqual(response.status_code, 302)
        post.refresh_from_db()
        self.assertEqual(post.status, CONTENT_STATUS_PUBLISHED)

    def test_pagination_is_offered_past_list_per_page(self):
        model_admin = get_model_admin(*self.url_args)
        for index in range(model_admin.list_per_page + 1):
            self.post(title=f"Post {index}")
        response = self.client.get(self.url)
        self.assertTrue(response.context["page_numbers"])

    def test_settings_changelist_redirects_to_the_settings_form(self):
        url = reverse("admin_htmx:changelist", args=("conf", "setting"))
        self.assertRedirects(
            self.client.get(url),
            reverse("admin_htmx:settings"),
            fetch_redirect_response=False,
        )

    def test_page_subclass_changelist_redirects_to_the_tree(self):
        url = reverse("admin_htmx:changelist", args=("pages", "richtextpage"))
        self.assertRedirects(
            self.client.get(url),
            reverse("admin_htmx:changelist", args=("pages", "page")),
            fetch_redirect_response=False,
        )


class ChangeFormTests(AdminHtmxTestCase):

    url_args = ("pages", "richtextpage")

    def published_page_data(self, **overrides):
        data = {
            "title": "A page",
            "status": str(CONTENT_STATUS_PUBLISHED),
            "content": "<p>Body</p>",
            "gen_description": "1",
            "in_sitemap": "1",
        }
        data.update(overrides)
        return data

    def test_add_form_renders_declared_fieldsets(self):
        url = reverse("admin_htmx:add", args=self.url_args)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        names = [str(fieldset.name) for fieldset in response.context["adminform"]]
        self.assertIn("Meta data", names)

    def test_add_creates_object(self):
        url = reverse("admin_htmx:add", args=self.url_args)
        response = self.client.post(url, self.published_page_data(title="Created here"))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(RichTextPage.objects.filter(title="Created here").exists())

    def test_save_and_continue_returns_to_the_change_form(self):
        url = reverse("admin_htmx:add", args=self.url_args)
        response = self.client.post(
            url, self.published_page_data(title="Keep editing", _continue="1")
        )
        page = RichTextPage.objects.get(title="Keep editing")
        self.assertEqual(
            response["Location"],
            reverse("admin_htmx:change", args=self.url_args + (page.pk,)),
        )

    def test_save_and_add_another_returns_to_the_add_form(self):
        url = reverse("admin_htmx:add", args=self.url_args)
        response = self.client.post(
            url, self.published_page_data(title="Another", _addanother="1")
        )
        self.assertEqual(response["Location"], url)

    def test_save_returns_to_the_change_list(self):
        url = reverse("admin_htmx:add", args=self.url_args)
        response = self.client.post(url, self.published_page_data(_save="1"))
        self.assertEqual(
            response["Location"],
            reverse("admin_htmx:changelist", args=self.url_args),
        )

    def test_invalid_form_redisplays_with_errors(self):
        url = reverse("admin_htmx:add", args=self.url_args)
        response = self.client.post(url, {"title": ""})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["adminform"].form.errors)

    def test_published_page_requires_content(self):
        """
        Enforced by ``DisplayableAdminForm.clean_content``, which this
        interface uses because it asks the admin class for its form.
        """
        url = reverse("admin_htmx:add", args=self.url_args)
        response = self.client.post(url, self.published_page_data(content=""))
        self.assertEqual(response.status_code, 200)
        self.assertIn("content", response.context["adminform"].form.errors)

    def test_change_saves_edits(self):
        page = RichTextPage.objects.create(title="Before")
        url = reverse("admin_htmx:change", args=self.url_args + (page.pk,))
        response = self.client.post(
            url, self.published_page_data(title="After", slug=page.slug)
        )
        self.assertEqual(response.status_code, 302)
        page.refresh_from_db()
        self.assertEqual(page.title, "After")

    def test_concrete_change_view_redirects_to_the_content_model(self):
        """
        A ``Page`` row is a stub; editing it must land on the subclass
        holding the content, as ``ContentTypedAdmin.change_view`` does.
        """
        page = RichTextPage.objects.create(title="Colophon")
        url = reverse("admin_htmx:change", args=("pages", "page", page.pk))
        self.assertRedirects(
            self.client.get(url),
            reverse("admin_htmx:change", args=self.url_args + (page.pk,)),
            fetch_redirect_response=False,
        )

    def test_add_page_redirects_to_the_first_content_model(self):
        url = reverse("admin_htmx:add", args=("pages", "page"))
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertNotEqual(response["Location"], url)

    def test_new_page_keeps_its_parent(self):
        parent = RichTextPage.objects.create(title="Parent")
        url = reverse("admin_htmx:add", args=self.url_args)
        response = self.client.post(
            f"{url}?parent={parent.id}", self.published_page_data(title="Child")
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(RichTextPage.objects.get(title="Child").parent_id, parent.id)

    def test_missing_object_is_404(self):
        url = reverse("admin_htmx:change", args=self.url_args + (12345,))
        self.assertEqual(self.client.get(url).status_code, 404)


class DeleteTests(AdminHtmxTestCase):
    def test_confirmation_then_delete(self):
        page = RichTextPage.objects.create(title="Doomed")
        url = reverse("admin_htmx:delete", args=("pages", "richtextpage", page.pk))
        self.assertEqual(self.client.get(url).status_code, 200)
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(RichTextPage.objects.filter(pk=page.pk).exists())


class PageTreeTests(AdminHtmxTestCase):

    url = None

    def setUp(self):
        super().setUp()
        self.url = reverse("admin_htmx:changelist", args=("pages", "page"))

    def test_page_changelist_renders_the_tree(self):
        parent = RichTextPage.objects.create(title="Parent")
        child = RichTextPage.objects.create(title="Child", parent=parent)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-page-tree")
        self.assertContains(response, f'data-page-id="{child.id}"')

    def test_tree_nests_children(self):
        parent = RichTextPage.objects.create(title="Parent")
        RichTextPage.objects.create(title="Child", parent=parent)
        tree = self.client.get(self.url).context["tree"]
        self.assertEqual(len(tree), 1)
        self.assertEqual(len(tree[0]["children"]), 1)
        self.assertEqual(tree[0]["children"][0]["title"], "Child")

    def test_tree_links_to_the_content_model(self):
        page = RichTextPage.objects.create(title="Colophon")
        tree = self.client.get(self.url).context["tree"]
        self.assertEqual(
            tree[0]["change_url"],
            reverse("admin_htmx:change", args=("pages", "richtextpage", page.pk)),
        )

    def test_reordering_goes_through_cemess_own_view(self):
        first = RichTextPage.objects.create(title="First")
        second = RichTextPage.objects.create(title="Second")
        response = self.client.post(
            reverse("admin_htmx:page_ordering"),
            {
                "id": str(second.id),
                "parent_id": "",
                "siblings[]": [str(second.id), str(first.id)],
            },
        )
        self.assertEqual(response.content, b"ok")
        self.assertEqual(Page.objects.get(id=second.id)._order, 0)
        self.assertEqual(Page.objects.get(id=first.id)._order, 1)

    def test_reordering_can_nest(self):
        parent = RichTextPage.objects.create(title="Parent")
        child = RichTextPage.objects.create(title="Child")
        response = self.client.post(
            reverse("admin_htmx:page_ordering"),
            {
                "id": str(child.id),
                "parent_id": str(parent.id),
                "siblings[]": [str(child.id)],
            },
        )
        self.assertEqual(response.content, b"ok")
        self.assertEqual(Page.objects.get(id=child.id).parent_id, parent.id)

    def test_reordering_rejects_get(self):
        self.assertEqual(
            self.client.get(reverse("admin_htmx:page_ordering")).status_code, 405
        )


class SettingsTests(AdminHtmxTestCase):
    def test_form_renders_editable_settings_only(self):
        response = self.client.get(reverse("admin_htmx:settings"))
        self.assertEqual(response.status_code, 200)
        fields = response.context["settings_form"].fields
        self.assertIn("SITE_TITLE", fields)
        # ADMIN_MENU_ORDER is registered with editable=False.
        self.assertNotIn("ADMIN_MENU_ORDER", fields)

    def test_saving_persists(self):
        """
        The settings form is one form over every editable setting, and
        numeric settings are required, so a save posts all of them -
        exactly as the rendered form does.
        """
        from django import forms

        from cemes.conf.forms import SettingsForm

        form = SettingsForm()
        data = {}
        for name, field in form.fields.items():
            initial = form.get_initial_for_field(field, name)
            if isinstance(field, forms.BooleanField):
                if initial:
                    data[name] = "on"
            else:
                data[name] = "" if initial is None else initial
        data["SITE_TITLE"] = "Renamed"

        response = self.client.post(reverse("admin_htmx:settings"), data)
        self.assertEqual(response.status_code, 302)
        settings.clear_cache()
        self.assertEqual(settings.SITE_TITLE, "Renamed")


class NavigationTests(AdminHtmxTestCase):
    def test_groups_follow_admin_menu_order(self):
        groups = nav.app_list(self.request_for(reverse("admin_htmx:index")))
        names = [group["name"] for group in groups]
        expected = [str(group[0]) for group in settings.ADMIN_MENU_ORDER]
        self.assertEqual(names[: len(expected)], expected)

    def test_page_subclasses_are_hidden_from_the_menu(self):
        """
        ``ContentTypedAdmin.has_module_permission`` returns False for
        subclasses, which is what keeps every page type out of the menu.
        """
        groups = nav.app_list(self.request_for(reverse("admin_htmx:index")))
        listed = {model["object_name"] for group in groups for model in group["models"]}
        self.assertIn("Page", listed)
        self.assertNotIn("RichTextPage", listed)

    def test_urls_point_at_this_interface(self):
        groups = nav.app_list(self.request_for(reverse("admin_htmx:index")))
        page_entries = [
            model
            for group in groups
            for model in group["models"]
            if model["object_name"] == "Page"
        ]
        self.assertEqual(
            page_entries[0]["admin_url"],
            reverse("admin_htmx:changelist", args=("pages", "page")),
        )

    def test_active_item_is_marked(self):
        path = reverse("admin_htmx:changelist", args=("pages", "page"))
        groups = nav.mark_active(nav.app_list(self.request_for(path)), path)
        active = [
            model["name"]
            for group in groups
            for model in group["models"]
            if model.get("active")
        ]
        self.assertEqual(len(active), 1)


class MediaFilterTests(TestCase):
    def test_excluded_scripts_are_dropped(self):
        from django import forms

        media = forms.Media(
            js=[
                "cemes/js/admin/dynamic_inline.js",
                "cemes/tinymce/tinymce.min.js",
            ]
        )
        kept = [str(path) for path in filter_media(media)._js]
        self.assertTrue(any("tinymce" in path for path in kept))
        self.assertFalse(any("dynamic_inline" in path for path in kept))

    def test_widget_css_is_kept(self):
        from django import forms

        media = forms.Media(css={"all": ["cemes/css/admin/form.css"]})
        self.assertEqual(len(filter_media(media)._css["all"]), 1)

    def test_jquery_shim_is_inserted_right_after_jquery_init(self):
        """
        Cemes's widget scripts call the global jQuery that Grappelli
        provides; Django only exposes django.jQuery. The shim restoring
        the alias has to run after jquery.init.js and before any script
        that depends on it.
        """
        from django import forms

        media = forms.Media(
            js=[
                "admin/js/vendor/jquery/jquery.js",
                "admin/js/jquery.init.js",
                "cemes/js/admin/keywords_field.js",
            ]
        )
        js = [str(path) for path in filter_media(media)._js]
        init = next(i for i, p in enumerate(js) if p.endswith("jquery.init.js"))
        shim = next(i for i, p in enumerate(js) if "jquery-compat" in p)
        dependent = next(i for i, p in enumerate(js) if "keywords_field" in p)
        self.assertEqual(shim, init + 1)
        self.assertLess(shim, dependent)

    def test_no_shim_when_jquery_init_is_absent(self):
        from django import forms

        media = forms.Media(js=["cemes/tinymce/tinymce.min.js"])
        js = [str(path) for path in filter_media(media)._js]
        self.assertFalse(any("jquery-compat" in path for path in js))


class JavaScriptCatalogTests(AdminHtmxTestCase):
    def test_catalog_is_served_by_this_app(self):
        """
        Django's admin widget scripts call gettext() as they load, and
        this interface can't rely on the classic admin being mounted to
        supply the catalog.
        """
        response = self.client.get(reverse("admin_htmx:jsi18n"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("javascript", response["Content-Type"])

    def test_pages_load_the_catalog_before_form_media(self):
        url = reverse("admin_htmx:add", args=("pages", "richtextpage"))
        html = self.client.get(url).content.decode()
        catalog = html.index(reverse("admin_htmx:jsi18n"))
        calendar = html.index("admin/js/calendar.js")
        self.assertLess(catalog, calendar)


class IntrospectionTests(TestCase):
    def test_page_is_the_concrete_content_model(self):
        self.assertTrue(is_concrete_content_model(get_model_admin("pages", "page")))
        self.assertFalse(
            is_concrete_content_model(get_model_admin("pages", "richtextpage"))
        )

    def test_blog_post_is_not_content_typed(self):
        self.assertFalse(is_concrete_content_model(get_model_admin("blog", "blogpost")))

    def test_content_models_are_addable_subclasses(self):
        models = content_models(get_model_admin("pages", "page"))
        names = [model["model"].__name__ for model in models]
        self.assertIn("RichTextPage", names)
        self.assertNotIn("Page", names)
        for model in models:
            self.assertTrue(model["add_url"].startswith("/"))

    def test_model_name_lookup_is_case_insensitive(self):
        self.assertIs(
            get_model_admin("Pages", "Page"), get_model_admin("pages", "page")
        )


class SiteFilteringTests(AdminHtmxTestCase):
    def test_changelist_respects_the_admins_queryset(self):
        """
        Cemes's admin querysets are filtered to the current site, so
        objects belonging to another site must not leak into the list.
        """
        other = Site.objects.create(domain="other.example.com", name="Other")
        post = self.post(title="Elsewhere")
        BlogPost.objects.filter(pk=post.pk).update(site=other)
        url = reverse("admin_htmx:changelist", args=("blog", "blogpost"))
        self.assertNotContains(self.client.get(url), "Elsewhere")
