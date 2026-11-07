"""Prood sibling ports + Pack J deepen.

Faithful ports of Prood ``backend/core/*``. Importing this package installs
a ``core.*`` compatibility shim so Prood-style imports resolve here.
"""
from __future__ import annotations

import importlib
import pkgutil
import sys
from types import ModuleType


def _ensure_pkg(name: str) -> ModuleType:
    mod = sys.modules.get(name)
    if mod is None:
        mod = ModuleType(name)
        mod.__path__ = []  # type: ignore[attr-defined]
        sys.modules[name] = mod
    return mod


def _install_core_shim() -> None:
    if getattr(_install_core_shim, "_done", False):
        return

    core = _ensure_pkg("core")
    databases = importlib.import_module("skeleton.prood._memory_db")
    sys.modules["core.databases"] = databases
    setattr(core, "databases", databases)

    swarm = ModuleType("core.swarm_agents")
    swarm.SWARM_DOMAINS = ["rendering", "audio", "design", "narrative", "tooling"]
    swarm.BY_ID = {d: {"id": d, "domain": d} for d in swarm.SWARM_DOMAINS}
    swarm.find_relevant = lambda *a, **k: list(swarm.BY_ID.values())[:3]
    swarm.pick_balanced = lambda *a, **k: list(swarm.BY_ID.values())[:2]
    sys.modules["core.swarm_agents"] = swarm
    setattr(core, "swarm_agents", swarm)

    routes = _ensure_pkg("routes")
    gke = ModuleType("routes.game_knowledge_engine")
    gke.KNOWLEDGE_DOMAINS = ["lore", "systems", "combat", "economy"]
    sys.modules["routes.game_knowledge_engine"] = gke

    if "zstandard" not in sys.modules:
        zst = ModuleType("zstandard")

        class _C:
            def compress(self, data: bytes) -> bytes:
                return data

        class _D:
            def decompress(self, data: bytes) -> bytes:
                return data

        zst.ZstdCompressor = _C
        zst.ZstdDecompressor = _D
        sys.modules["zstandard"] = zst

    prood_pkg = importlib.import_module("skeleton.prood")

    class _LazyCoreMod(ModuleType):
        def __init__(self, full_name: str, prood_name: str):
            super().__init__(full_name)
            self.__prood_name__ = prood_name
            self.__file__ = None
            self.__package__ = "core"
            self.__loaded = False

        def _load(self):
            if self.__loaded:
                return
            real = importlib.import_module(f"skeleton.prood.{self.__prood_name__}")
            self.__dict__.update({k: v for k, v in real.__dict__.items() if k != "__dict__"})
            self.__loaded = True
            sys.modules[self.__name__] = real
            setattr(core, self.__prood_name__, real)

        def __getattr__(self, item):
            self._load()
            return getattr(sys.modules[f"skeleton.prood.{self.__prood_name__}"], item)

    for mod in pkgutil.iter_modules(prood_pkg.__path__):
        name = mod.name
        if name.startswith("_"):
            continue
        full = f"core.{name}"
        if full not in sys.modules:
            lazy = _LazyCoreMod(full, name)
            sys.modules[full] = lazy
            setattr(core, name, lazy)

    # Support `from core import X`
    def _core_getattr(name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        full = f"core.{name}"
        mod = sys.modules.get(full)
        if isinstance(mod, _LazyCoreMod):
            mod._load()
            return sys.modules[f"skeleton.prood.{name}"]
        if mod is not None:
            return mod
        # try load skeleton.prood.name
        try:
            real = importlib.import_module(f"skeleton.prood.{name}")
        except ModuleNotFoundError as exc:
            raise AttributeError(name) from exc
        sys.modules[full] = real
        setattr(core, name, real)
        return real

    core.__getattr__ = _core_getattr  # type: ignore[attr-defined]
    _install_core_shim._done = True  # type: ignore[attr-defined]


_install_core_shim()

from skeleton.prood import forge_dna
from skeleton.prood import forge_registry
from skeleton.prood import anti_farm
from skeleton.prood import boot_timeline

__all__ = [
    "forge_dna",
    "forge_registry",
    "anti_farm",
    "boot_timeline",
]
