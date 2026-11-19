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


def __getattr__(name: str) -> Any:
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute = target
    value = getattr(import_module(module_name), attribute)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
