"""
Skeleton — Root package metadata

Root exports are intentionally lazy: importing a lightweight submodule must not
eagerly import configuration, crypto, database, or web-framework dependencies.
Public compatibility is preserved through module __getattr__.
"""
from __future__ import annotations

from importlib import import_module
from typing import Any

__version__ = "16.0.0"
__codename__ = "Skeleton"

_LAZY_EXPORTS = {
    "SkeletonError": ("skeleton.kernel.errors", "SkeletonError"),
    "DomainEvent": ("skeleton.kernel.events", "DomainEvent"),
    "EventBus": ("skeleton.kernel.events", "EventBus"),
    "CapabilityRegistry": ("skeleton.kernel.registry", "CapabilityRegistry"),
    "SettingsSnapshotBridge": ("skeleton.config.snapshots", "SettingsSnapshotBridge"),
    "Fuser": ("skeleton.retrieval.fusion", "Fuser"),
    "FusionStrategy": ("skeleton.retrieval.fusion", "FusionStrategy"),
    "ScoredResult": ("skeleton.retrieval.fusion", "ScoredResult"),
    "Ranker": ("skeleton.retrieval.ranking", "Ranker"),
    "AccessPolicy": ("skeleton.vault.access", "AccessPolicy"),
    "Role": ("skeleton.vault.access", "Role"),
    "EnvelopeKMS": ("skeleton.vault.kms", "EnvelopeKMS"),
    "Coordinator": ("skeleton.agents.coordination", "Coordinator"),
    "Sampler": ("skeleton.observability.sampling", "Sampler"),
    "default_sampler": ("skeleton.observability.sampling", "default_sampler"),
    "TestCase": ("skeleton.testing.scaffold", "TestCase"),
    "TestOutcome": ("skeleton.testing.scaffold", "TestOutcome"),
    "TestScaffold": ("skeleton.testing.scaffold", "TestScaffold"),
}

__all__ = ["__version__", "__codename__"]
__all__ += list(_LAZY_EXPORTS)

# Eagerly bind common subpackages so dotted-path tools (unittest.mock.patch,
# pytest collection) can resolve skeleton.ai, skeleton.forge, etc. without
# relying on __getattr__ timing. These imports are lightweight package
# markers; heavy dependencies remain lazy inside the packages.
for _sub in ("ai", "forge", "api", "app", "application", "kernel"):
    try:
        globals()[_sub] = import_module(f"{__name__}.{_sub}")
    except Exception:
        pass
del _sub


def _load_reviewed_export_owner(module_name: str):
    """Keep import side effects limited to explicitly reviewed modules."""
    if module_name == "skeleton.agents.coordination":
        return import_module("skeleton.agents.coordination")
    if module_name == "skeleton.config.snapshots":
        return import_module("skeleton.config.snapshots")
    if module_name == "skeleton.kernel.errors":
        return import_module("skeleton.kernel.errors")
    if module_name == "skeleton.kernel.events":
        return import_module("skeleton.kernel.events")
    if module_name == "skeleton.kernel.registry":
        return import_module("skeleton.kernel.registry")
    if module_name == "skeleton.observability.sampling":
        return import_module("skeleton.observability.sampling")
    if module_name == "skeleton.retrieval.fusion":
        return import_module("skeleton.retrieval.fusion")
    if module_name == "skeleton.retrieval.ranking":
        return import_module("skeleton.retrieval.ranking")
    if module_name == "skeleton.testing.scaffold":
        return import_module("skeleton.testing.scaffold")
    if module_name == "skeleton.vault.access":
        return import_module("skeleton.vault.access")
    if module_name == "skeleton.vault.kms":
        return import_module("skeleton.vault.kms")
    raise ImportError("unregistered lazy export owner")


def __getattr__(name: str) -> Any:
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        # Bind existing subpackages on first access so tools such as
        # unittest.mock.patch can resolve dotted paths like skeleton.ai.*
        import importlib.util
        spec = importlib.util.find_spec(f"{__name__}.{name}")
        if spec is not None and spec.submodule_search_locations is not None:
            module = import_module(f"{__name__}.{name}")
            globals()[name] = module
            return module
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute = target
    value = getattr(_load_reviewed_export_owner(module_name), attribute)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
