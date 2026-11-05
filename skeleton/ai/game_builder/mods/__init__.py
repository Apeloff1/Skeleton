"""Mod API for generated games.

Builds on the #807 B09x platform slice instead of adding a second plugin layer:
hooks run as B095 ``content_hook`` plugins inside a scope-checked ``Host``, and
packages are signed/installed through B099 ``ModPackage``/``install``. Packages
travel in the project bundle format (``project_bundle.bundle_io``).
No exec/eval, no outside runtime, no core-engine changes.
"""
from .hooks import ContentHook, DeclarativeHook, HookError, apply_mods
from .manifest import ModError, ModManifest, SemVer, VersionSpec
from .package import pack_mod, unpack_mod
from .resolve import ResolveError, resolve_load_order

__all__ = [
    "ContentHook", "DeclarativeHook", "HookError", "apply_mods", "ModError", "ModManifest", "SemVer",
    "VersionSpec", "pack_mod", "unpack_mod", "ResolveError", "resolve_load_order",
]
