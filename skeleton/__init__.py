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

__all__ = ["__version__", "__codename__", *_LAZY_EXPORTS]


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
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute = target
    value = getattr(_load_reviewed_export_owner(module_name), attribute)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
