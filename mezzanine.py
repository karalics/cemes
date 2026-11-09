"""
Backwards compatibility shim mapping the old ``mezzanine`` package name
onto ``cemes``.

This project is a fork of Mezzanine, renamed to Cemes. One of its
dependencies, ``filebrowser_safe``, imports from ``mezzanine`` directly:

    filebrowser_safe/functions.py    mezzanine.utils.sites.current_site_id
    filebrowser_safe/views.py        mezzanine.utils.html.escape
    filebrowser_safe/base.py         mezzanine.core.exceptions
    filebrowser_safe/templatetags/   mezzanine.core.templatetags.mezzanine_tags

Each of those imports is wrapped in ``try``/``except ImportError`` on
their side, so without this shim nothing crashes - but the media library
silently falls back to placeholder implementations and loses thumbnails
and per-site filtering.

Rather than vendoring or forking that package, this module registers a
meta path finder that resolves any ``mezzanine.*`` import to the
corresponding ``cemes.*`` module. The module objects are shared, not
copied, so there is exactly one ``cemes.conf.settings``, one admin
registry and so on, however they were reached.

This is meant to be temporary: it exists only to keep filebrowser_safe
working until the media library is replaced. Nothing inside Cemes itself
imports ``mezzanine``.
"""
import importlib
import importlib.abc
import importlib.machinery
import sys

_ALIAS = "mezzanine"
_TARGET = "cemes"

# The template tag library was renamed along with everything else, so the
# old dotted path has to be redirected explicitly.
_RENAMED = {
    f"{_ALIAS}.core.templatetags.mezzanine_tags":
        f"{_TARGET}.core.templatetags.cemes_tags",
}


def _translate(fullname):
    if fullname in _RENAMED:
        return _RENAMED[fullname]
    return _TARGET + fullname[len(_ALIAS):]


class _AliasFinder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """Resolves ``mezzanine.x.y`` to the already-imported ``cemes.x.y``."""

    def find_spec(self, fullname, path=None, target=None):
        if fullname != _ALIAS and not fullname.startswith(_ALIAS + "."):
            return None
        return importlib.machinery.ModuleSpec(fullname, self, is_package=True)

    def create_module(self, spec):
        # Returning the real module makes the alias an additional name for
        # it rather than a second copy.
        return importlib.import_module(_translate(spec.name))

    def exec_module(self, module):
        # Already executed under its real name.
        pass


if not any(isinstance(finder, _AliasFinder) for finder in sys.meta_path):
    sys.meta_path.insert(0, _AliasFinder())

# Marks this module as a package so that submodule imports are looked up
# through the finder above instead of being rejected outright.
__path__ = []

_cemes = importlib.import_module(_TARGET)
__version__ = _cemes.__version__
