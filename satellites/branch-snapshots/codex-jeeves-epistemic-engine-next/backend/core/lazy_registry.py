"""
core/lazy_registry.py — LAZY ACCESS TO EVERY CORE MODULE (deferred import).

Wraps all `core/*.py` modules behind lazy proxies so heavy modules
(universal_forge, systems_forge_ext, snowball_axes, the big seed data, …) are
imported ONLY on first real use — lowering cold-start RAM and import time.

Usage (drop-in, transparent):
    from core import lazy_registry as L
    L.universal_forge.forge(spec)        # universal_forge imported here, first touch
    L.snowball_axes.resolve(spec, 2)     # snowball_axes imported on first touch

PEP 562 module __getattr__ means ANY attribute access `L.<module>` returns a
lazy proxy for `core.<module>` — every core module is "wrapped" without touching
existing import sites. Already-imported modules are reused by importlib's cache,
so this never double-imports.
"""
from __future__ import annotations

import pathlib
import sys

from core.unbulk import lazy_import

_proxies: dict = {}
_DIR = pathlib.Path(__file__).resolve().parent
# Modules that must NOT be lazily proxied (this module, and ultra-hot tiny ones
# that are always needed at import time anyway).
_SKIP = {"lazy_registry", "unbulk", "databases"}


def __getattr__(name: str):  # PEP 562 — lazy attribute access on the module
    if name.startswith("_") or name in _SKIP:
        raise AttributeError(f"module 'core.lazy_registry' has no attribute '{name}'")
    if name not in _proxies:
        _proxies[name] = lazy_import(f"core.{name}")
    return _proxies[name]


def module_names() -> list[str]:
    """Every importable core module (sans the skip list)."""
    return sorted(
        f.stem for f in _DIR.glob("*.py")
        if not f.stem.startswith("_") and f.stem not in _SKIP
    )


def wrap_all() -> dict:
    """Return {module_name: lazy_proxy} for EVERY core module — wrap them all."""
    for n in module_names():
        if n not in _proxies:
            _proxies[n] = lazy_import(f"core.{n}")
    return dict(_proxies)


def status() -> dict:
    """Introspection: which core modules are deferred vs already loaded."""
    names = module_names()
    loaded = [n for n in names if f"core.{n}" in sys.modules]
    return {
        "total": len(names),
        "loaded": len(loaded),
        "deferred": len(names) - len(loaded),
        "wrapped_proxies": len(_proxies),
        "loaded_modules": loaded,
    }


# ── NON-CORE packages (seeds / routes) — lazy-wrapped the same way ───────────
_NONCORE = ("seeds",)            # routes must be eager (FastAPI registers them)
_noncore_proxies: dict = {}
_ROOT = _DIR.parent


def _pkg_module_names(pkg: str) -> list[str]:
    d = _ROOT / pkg
    if not d.exists():
        return []
    return sorted(f.stem for f in d.glob("*.py") if not f.stem.startswith("_"))


def seed(name: str):
    """Lazy proxy for a `seeds.<name>` module (imported on first use)."""
    key = f"seeds.{name}"
    if key not in _noncore_proxies:
        _noncore_proxies[key] = lazy_import(key)
    return _noncore_proxies[key]


def wrap_noncore() -> dict:
    """Wrap every non-core (seeds) module as a lazy proxy."""
    for pkg in _NONCORE:
        for n in _pkg_module_names(pkg):
            key = f"{pkg}.{n}"
            if key not in _noncore_proxies:
                _noncore_proxies[key] = lazy_import(key)
    return dict(_noncore_proxies)


def wrap_flagged() -> dict:
    """Wrap exactly the FLAGGED heavy modules (unbulk.lazy_eligible) as lazy
    proxies — the big seed data that should never sit on the import path."""
    from core import unbulk
    inv = unbulk.module_inventory(top=10_000)
    out = {}
    for m in inv["biggest"]:
        if not m.get("lazy_eligible"):
            continue
        mod = m["module"].replace("/", ".").removesuffix(".py")  # seeds/x.py → seeds.x
        if mod not in _noncore_proxies:
            _noncore_proxies[mod] = lazy_import(mod)
        out[mod] = _noncore_proxies[mod]
    return out


def full_status() -> dict:
    """Combined loaded-vs-deferred picture across core + seeds + flagged."""
    core_names = module_names()
    seed_names = [f"seeds.{n}" for n in _pkg_module_names("seeds")]
    from core import unbulk
    flagged = [m["module"].replace("/", ".").removesuffix(".py")
               for m in unbulk.module_inventory(top=10_000)["biggest"]
               if m.get("lazy_eligible")]
    def _split(keys, pfx_core=False):
        ld = [k for k in keys if (f"core.{k}" if pfx_core else k) in sys.modules]
        return len(keys), len(ld), [k for k in keys if (f"core.{k}" if pfx_core else k) not in sys.modules]
    c_t, c_l, c_def = _split(core_names, pfx_core=True)
    s_t, s_l, s_def = _split(seed_names)
    f_t, f_l, f_def = _split(flagged)
    return {
        "core": {"total": c_t, "loaded": c_l, "deferred": c_t - c_l},
        "seeds": {"total": s_t, "loaded": s_l, "deferred": s_t - s_l, "deferred_modules": s_def},
        "flagged": {"total": f_t, "loaded": f_l, "deferred": f_t - f_l,
                    "modules": flagged, "still_deferred": f_def},
        "wrapped_proxies": {"core": len(_proxies), "noncore": len(_noncore_proxies)},
    }
