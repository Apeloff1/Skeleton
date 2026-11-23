"""Opt-in guarded Docker engine-memory enrollment in the canonical Mongo epoch.

The engine and backend use independent database clients. Their writer epoch
objects are necessarily different Python objects; the stable *physical*
authority is the same authenticated Mongo primary and fixed shared epoch
collection. This module provides a strict read-only admission before enabling
the existing MongoMemoryRepository's actor-scoped writer decorator.

No epoch records, indexes, leases or migration state are created here.
"""
from __future__ import annotations

import asyncio
import os
from typing import Any


class EngineEpochStartupError(RuntimeError):
    """The engine cannot safely bind a canonical memory writer epoch."""


def engine_epoch_requested(raw: object = None) -> bool:
    if raw is None:
        raw = os.getenv("SKL_ENGINE_CANONICAL_EPOCH_FENCE_REQUIRED", "0")
    if raw == "0":
        return False
    if raw == "1":
        return True
    raise EngineEpochStartupError("engine canonical epoch policy must be exactly 0 or 1")


async def enroll_engine_memory_epoch(client: Any) -> Any:
    """Return a real majority epoch only after an actual primary/read proof."""
    from skeleton.persistence.docker_epoch_preflight import _primary_identity
    from skeleton.persistence.mongo_source_epoch import MongoCanonicalSourceEpoch

    if not callable(getattr(client, "__getitem__", None)):
        raise EngineEpochStartupError("canonical Mongo engine client is missing")
    try:
        async with asyncio.timeout(3):
            primary = await client.admin.command({"hello": 1, "maxTimeMS": 2000})
        _primary_identity(primary)
        from skeleton.persistence.docker_epoch_writer_policy import (
            observe_writer_policy_async,
        )
        policy = await observe_writer_policy_async(client)
        if (policy.get("explicit_majority_journal_policy") is not True
                or policy.get("primary_identity_stable_across_probe") is not True):
            raise EngineEpochStartupError("journaled majority policy unavailable")
        epoch = MongoCanonicalSourceEpoch(client["skeleton_guarded_source"])
        async with asyncio.timeout(3):
            await epoch._reader.find_one(
                {"_id": "__skeleton_engine_epoch_enrollment_read_only__"},
                projection={"_id": 1}, max_time_ms=2000,
            )
    except Exception:
        raise EngineEpochStartupError(
            "engine epoch primary identity or linearizable read unavailable"
        ) from None
    return epoch


__all__ = [
    "EngineEpochStartupError", "engine_epoch_requested",
    "enroll_engine_memory_epoch",
]
