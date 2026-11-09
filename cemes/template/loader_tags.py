from django import template

register = template.Library()

# TODO: Remove this file a couple releases after Cemes 5
# We've kept this file because users upgrading to Cemes 5 might still refer to it.
# However, cemes.core.checks should warn them about it being deprecated.
