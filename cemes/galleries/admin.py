from django.contrib import admin

from cemes.core.admin import TabularDynamicInlineAdmin
from cemes.galleries.models import Gallery, GalleryImage
from cemes.pages.admin import PageAdmin
from cemes.utils.static import static_lazy as static


class GalleryImageInline(TabularDynamicInlineAdmin):
    model = GalleryImage


class GalleryAdmin(PageAdmin):
    class Media:
        css = {"all": (static("cemes/css/admin/gallery.css"),)}

    inlines = (GalleryImageInline,)


admin.site.register(Gallery, GalleryAdmin)
