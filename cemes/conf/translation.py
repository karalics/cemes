from modeltranslation.translator import TranslationOptions, translator

from cemes.conf.models import Setting


class TranslatedSetting(TranslationOptions):
    fields = ("value",)


translator.register(Setting, TranslatedSetting)
