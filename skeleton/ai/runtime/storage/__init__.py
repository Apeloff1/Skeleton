"""Governed storage primitives for durable AI state.

This namespace owns cross-cutting storage contracts that sit below higher-level
AI runtimes. Caches are accelerators only; durable stores remain authoritative.
"""

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
