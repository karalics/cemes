from modeltranslation.translator import TranslationOptions, translator

from cemes.core.translation import TranslatedDisplayable, TranslatedRichText
from cemes.pages.models import Link, Page, RichTextPage


class TranslatedPage(TranslatedDisplayable):
    fields = ("titles",)


class TranslatedRichTextPage(TranslatedRichText):
    fields = ()


class TranslatedLink(TranslationOptions):
    fields = ()


translator.register(Page, TranslatedPage)
translator.register(RichTextPage, TranslatedRichTextPage)
translator.register(Link, TranslatedLink)
