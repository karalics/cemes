from modeltranslation.translator import TranslationOptions, translator

from cemes.core.translation import TranslatedRichText
from cemes.galleries.models import Gallery, GalleryImage


class TranslatedGallery(TranslatedRichText):
    fields = ()


class TranslatedGalleryImage(TranslationOptions):
    fields = ("description",)


translator.register(Gallery, TranslatedGallery)
translator.register(GalleryImage, TranslatedGalleryImage)
