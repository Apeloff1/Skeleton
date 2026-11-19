"""Opt-in backend conversation writer enrollment in the shared Mongo epoch.

The default service remains unchanged. This must be invoked by the trusted
FastAPI lifespan BEFORE any background seeders, Dragon callbacks or HTTP
requests become reachable. It performs a read-only topology capability check
and binds the *existing* canonical conversation authority to one majority
epoch; it never creates or resets epoch records.

This alone does not activate guarded Jeeves: the engine's memory writer,
trusted resolver, tokenizer and independent reviewer still need qualification.
"""
from __future__ import annotations

import asyncio
import os
from typing import Any

_TRUE = "1"
_FALSE = "0"


class BackendEpochStartupError(RuntimeError):
    """Protected conversation writer enrollment cannot be established."""


def guarded_epoch_requested(value: object) -> bool:
    """Only an explicit private deployer-owned bit may enable writer fencing."""
    if value is None or value == _FALSE:
        return False
    if value == _TRUE:
        return True
    raise BackendEpochStartupError("backend canonical source epoch policy is invalid")


async def install_backend_epoch_if_requested(
    authority: Any = None, *,
    mongo_client: Any = None,
    enabled: bool | None = None,
    mongo_uri: str | None = None,
) -> dict[str, object]:
    """Attach the canonical backend writer only after real Mongo admission."""
    request = guarded_epoch_requested(
        os.getenv("SKL_BACKEND_CANONICAL_EPOCH_FENCE_REQUIRED", "0")
    ) if enabled is None else enabled
    if type(request) is not bool:
        raise BackendEpochStartupError("backend epoch enforcement must be a boolean")
    if not request:
        return {
            "schema": "skeleton.backend.canonical-epoch-enrollment.v1",
            "status": "not_requested",
            "writer_epoch_bound": False,
            "guarded_chat_qualified": False,
        }

    from core.conversations import MongoConversationAuthority, conversation_authority
    from core.databases import client, core_db
    from skeleton.persistence.docker_epoch_preflight import (
        _primary_identity, _authenticated_internal_uri,
    )
    # Enrollment is deployer-controlled but must still be internal-only.
    # A replica-set response alone cannot authorize arbitrary remote Mongo.
    try:
        _authenticated_internal_uri(
            os.environ.get("MONGO_URL") if mongo_uri is None else mongo_uri
        )
    except Exception:
        raise BackendEpochStartupError(
            "backend guarded epoch requires authenticated internal Mongo"
        ) from None
    from skeleton.persistence.mongo_source_epoch import (
        MongoCanonicalSourceEpoch, _CONVERSATION_WRITER_METHODS,
    )

    owner = conversation_authority if authority is None else authority
    connected = client if mongo_client is None else mongo_client
    if (type(owner) is not MongoConversationAuthority
            or owner is not conversation_authority
            or owner.database is not core_db
            or owner.canonical_source_epoch is not None):
        raise BackendEpochStartupError("existing canonical conversation writer is not enrollable")
    # Require the production fenced method implementation, not merely a
    # convenient duck-typed instance or subclass override.
    for method_name in _CONVERSATION_WRITER_METHODS:
        method = getattr(MongoConversationAuthority, method_name, None)
        if getattr(method, "__canonical_source_writer_fence__", None) != "conversation":
            raise BackendEpochStartupError("canonical conversation mutation is unfenced")

    try:
        async with asyncio.timeout(3):
            hello = await connected.admin.command({"hello": 1, "maxTimeMS": 2000})
        set_name, _ = _primary_identity(hello)
        epoch = MongoCanonicalSourceEpoch(
            connected["skeleton_guarded_source"]
        )
        # A bounded linearizable read from the exact epoch reader verifies
        # real replica-set read behavior without creating a collection/index.
        async with asyncio.timeout(3):
            await epoch._reader.find_one(
                {"_id": "__skeleton_backend_epoch_enrollment_read_only__"},
                projection={"_id": 1}, max_time_ms=2000,
            )
    except Exception:
        raise BackendEpochStartupError(
            "backend writer epoch topology or linearizable read unavailable"
        ) from None

    # Publish the epoch to the global authority LAST. Every future decorated
    # actor mutation then acquires a majority durable epoch before any write.
    # Missing migration records reject new writes instead of self-provisioning.
    owner.canonical_source_epoch = epoch
    return {
        "schema": "skeleton.backend.canonical-epoch-enrollment.v1",
        "status": "backend_writer_epoch_installed_not_cross_process_qualified",
        "replica_set": set_name,
        "writer_epoch_bound": True,
        "engine_memory_epoch_bound": False,
        "actor_migration_complete": False,
        "guarded_chat_qualified": False,
    }


__all__ = [
    "BackendEpochStartupError", "guarded_epoch_requested",
    "install_backend_epoch_if_requested",
]
