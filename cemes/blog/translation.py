from modeltranslation.translator import translator

from cemes.blog.models import BlogCategory, BlogPost
from cemes.core.translation import (
    TranslatedDisplayable,
    TranslatedRichText,
    TranslatedSlugged,
)


class TranslatedBlogPost(TranslatedDisplayable, TranslatedRichText):
    fields = ()


class TranslatedBlogCategory(TranslatedSlugged):
    fields = ()


translator.register(BlogCategory, TranslatedBlogCategory)
translator.register(BlogPost, TranslatedBlogPost)
