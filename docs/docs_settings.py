# flake8: noqa

"""
This is the local_settings file for Cemes's docs.
"""

from random import choice

from cemes.project_template.project_name.settings import *

DEBUG = False
ROOT_URLCONF = "cemes.project_template.project_name.urls"

characters = "abcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*(-_=+)"
# Generate a SECRET_KEY for this build
SECRET_KEY = "".join(choice(characters) for i in range(50))

if "cemes.accounts" not in INSTALLED_APPS:
    INSTALLED_APPS = tuple(INSTALLED_APPS) + ("cemes.accounts",)

if "cemes.twitter" not in INSTALLED_APPS:
    INSTALLED_APPS = tuple(INSTALLED_APPS) + ("cemes.twitter",)
