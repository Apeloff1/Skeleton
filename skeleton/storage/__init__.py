"""Governed storage primitives for durable AI state.

This namespace owns cross-cutting storage contracts that sit below higher-level
AI runtimes. Caches are accelerators only; durable stores remain authoritative.

FROZEN (issue #4122): ``skeleton.storage`` is frozen in place. New code must
import only ``skeleton.persistence``; migration into the canonical package is
tracked in issue #4122. Docstring-only notice: no behaviour change, no warning.

Deprecated: use skeleton.persistence.storage
(planned target; the move is tracked in the #4122 storage/state follow-up issue).
"""
__deprecated__ = "skeleton.persistence"  # issue #4122: docstring-only deprecation, no warning

from .cas import (
    AddressedObject,
    CacheEntry,
    CacheKey,
    CachePolicy,
    CompensationAction,
    ContentDigest,
    DigestPolicy,
    DurableSagaStateStore,
    GovernedContentCache,
    GovernedContentStore,
    SagaSnapshot,
    SagaStepSnapshot,
    StorageContractError,
    TransactionMode,
    TransactionPlan,
)

__all__ = [
    "AddressedObject",
    "CacheEntry",
    "CacheKey",
    "CachePolicy",
    "CompensationAction",
    "ContentDigest",
    "DigestPolicy",
    "DurableSagaStateStore",
    "GovernedContentCache",
    "GovernedContentStore",
    "SagaSnapshot",
    "SagaStepSnapshot",
    "StorageContractError",
    "TransactionMode",
    "TransactionPlan",
]
