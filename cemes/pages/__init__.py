"""
Provides the main structure of a Cemes site with a hierarchical tree
of pages, each subclassing the Page model to create a content structure.
"""
from cemes import __version__  # noqa

default_app_config = "cemes.pages.apps.PagesConfig"
