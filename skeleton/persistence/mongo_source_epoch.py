"""Majority-durable canonical-source writer epoch (fail-closed seqlock).

This fence protects read *windows* only when installed on ALL canonical writer
paths for the actor. A writer must persist WRITING before mutating any source
and persist STABLE only after every source write is durably acknowledged.
There is deliberately no automatic lease takeover: crash leaves the actor
unavailable until an operator performs separately audited reconciliation.

It is NOT a two-phase commit, distributed transaction or proof that
unregistered external writers cannot modify Mongo. Production activation
must ensure all mutations are routed through the participating owners.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from hashlib import sha256
from uuid import uuid4
from typing import Any

from skeleton.context.sealed_sandwich import SealedContextBoundaryError


@dataclass(frozen=True, slots=True)
class _BoundWriter:
    tenant_id: str
    actor_id: str
    task: asyncio.Task[Any]
    token: str


class MongoCanonicalSourceEpoch:
    """Tenant/actor scoped durable writer fence shared by source owners."""

    def __init__(self, database: Any) -> None:
        # A memory-only dummy/independently created collection is NOT accepted
        # as the production epoch witness.
        if not callable(getattr(database, "get_collection", None)):
            raise SealedContextBoundaryError("canonical Mongo database required")
        try:
            from pymongo.read_concern import ReadConcern
            from pymongo.write_concern import WriteConcern
            collection = database.get_collection(
                "canonical_source_epochs",
                read_concern=ReadConcern("majority"),
                write_concern=WriteConcern(w="majority", wtimeout=10000),
            )
        except Exception as exc:
            raise SealedContextBoundaryError("majority-durable source epoch unavailable") from exc
        for method in ("find_one", "find_one_and_update", "insert_one"):
            if not callable(getattr(collection, method, None)):
                raise SealedContextBoundaryError("durable source epoch collection unavailable")
        self._collection = collection
        self._active: ContextVar[_BoundWriter | None] = ContextVar(
            "skeleton.canonical_source_writer", default=None,
        )

    @staticmethod
    def _key(tenant_id: str, actor_id: str) -> str:
        if any(not isinstance(v, str) or not v or v != v.strip()
               or len(v.encode("utf-8", "strict")) > 512 for v in (tenant_id, actor_id)):
            raise SealedContextBoundaryError("canonical source writer identity invalid")
        return sha256(
            ("skeleton.canonical-source-epoch.v1\0" + tenant_id + "\0" + actor_id)
            .encode("utf-8")
        ).hexdigest()

    async def read_epoch(self, *, tenant_id: str, actor_id: str, context_id: str) -> int:
        # Scope includes context for callers, but the epoch deliberately fences
        # ALL contexts for one actor: memory mutations affect every conversation.
        self._key(tenant_id, context_id)
        doc = await self._collection.find_one({
            "_id": self._key(tenant_id, actor_id),
            "tenant_id": tenant_id, "actor_id": actor_id,
        })
        if (not isinstance(doc, dict) or doc.get("phase") != "stable"
                or type(doc.get("epoch")) is not int or doc["epoch"] < 2
                or doc["epoch"] % 2):
            raise SealedContextBoundaryError("canonical source epoch missing, writing or quarantined")
        return doc["epoch"]

    async def provision_migration_epoch(self, *, tenant_id: str, actor_id: str) -> None:
        """ONLY for an operator-controlled quiescent migration; never on reads."""
        key = self._key(tenant_id, actor_id)
        try:
            await self._collection.insert_one({
                "_id": key, "tenant_id": tenant_id, "actor_id": actor_id,
                "phase": "stable", "epoch": 2, "writer_token": None,
            })
        except Exception as exc:
            raise SealedContextBoundaryError(
                "source epoch already initialized or migration unavailable"
            ) from exc

    @asynccontextmanager
    async def writer(self, *, tenant_id: str, actor_id: str):
        key = self._key(tenant_id, actor_id)
        task = asyncio.current_task()
        if task is None:
            raise SealedContextBoundaryError("canonical source writer task required")
        active = self._active.get()
        if active is not None:
            if (active.task is not task or active.tenant_id != tenant_id
                    or active.actor_id != actor_id):
                raise SealedContextBoundaryError("canonical writer scope cannot be inherited")
            yield
            return
        token = str(uuid4())
        try:
            from pymongo import ReturnDocument
            acquired = await self._collection.find_one_and_update(
                {"_id": key, "tenant_id": tenant_id, "actor_id": actor_id,
                 "phase": "stable", "writer_token": None},
                {"$inc": {"epoch": 1},
                 "$set": {"phase": "writing", "writer_token": token}},
                return_document=ReturnDocument.AFTER,
            )
        except Exception as exc:
            raise SealedContextBoundaryError("canonical writer admission unavailable") from exc
        if (not isinstance(acquired, dict) or acquired.get("writer_token") != token
                or acquired.get("phase") != "writing"
                or type(acquired.get("epoch")) is not int
                or acquired["epoch"] < 3 or acquired["epoch"] % 2 != 1):
            raise SealedContextBoundaryError("canonical writer epoch not owned")
        scope = self._active.set(_BoundWriter(tenant_id, actor_id, task, token))
        try:
            yield
            try:
                closed = await self._collection.find_one_and_update(
                    {"_id": key, "tenant_id": tenant_id, "actor_id": actor_id,
                     "phase": "writing", "writer_token": token,
                     "epoch": acquired["epoch"]},
                    {"$inc": {"epoch": 1},
                     "$set": {"phase": "stable", "writer_token": None}},
                    return_document=ReturnDocument.AFTER,
                )
            except Exception as exc:
                raise SealedContextBoundaryError(
                    "canonical writer completion unavailable; epoch remains quarantined"
                ) from exc
            if (not isinstance(closed, dict) or closed.get("phase") != "stable"
                    or closed.get("epoch") != acquired["epoch"] + 1):
                raise SealedContextBoundaryError("canonical writer CAS lost; epoch quarantined")
        finally:
            # An exception in the protected mutation intentionally leaves the
            # epoch WRITING: data might be partially committed and cannot be
            # released on the basis of an in-process exception handler.
            self._active.reset(scope)



def fence_conversation_write(method):
    """Apply configured writer fencing to real conversation mutation entrypoints."""
    from functools import wraps

    @wraps(method)
    async def guarded(self, *args, **kwargs):
        epoch = getattr(self, "canonical_source_epoch", None)
        if epoch is None:
            return await method(self, *args, **kwargs)
        tenant_id, actor_id = kwargs.get("tenant_id"), kwargs.get("owner_id")
        if not isinstance(tenant_id, str) or not isinstance(actor_id, str):
            raise SealedContextBoundaryError("canonical conversation write actor missing")
        async with epoch.writer(tenant_id=tenant_id, actor_id=actor_id):
            return await method(self, *args, **kwargs)

    return guarded


def fence_memory_commit(method):
    """Admit governed memory mutation before reservation, CAS and publication."""
    from functools import wraps

    @wraps(method)
    async def guarded(self, proposal, *args, **kwargs):
        epoch = getattr(self, "canonical_source_epoch", None)
        if epoch is None:
            return await method(self, proposal, *args, **kwargs)
        from skeleton.contracts.memory_record import MemoryWriteProposal

        if not isinstance(proposal, MemoryWriteProposal):
            raise SealedContextBoundaryError("canonical memory write proposal required")
        async with epoch.writer(tenant_id=proposal.tenant_id, actor_id=proposal.subject_id):
            return await method(self, proposal, *args, **kwargs)

    return guarded


def fence_memory_tombstone(method):
    """Pin current memory subject before tombstone; underlying CAS rechecks it."""
    from functools import wraps

    @wraps(method)
    async def guarded(self, memory_id, *args, **kwargs):
        epoch = getattr(self, "canonical_source_epoch", None)
        if epoch is None:
            return await method(self, memory_id, *args, **kwargs)
        tenant_id = kwargs.get("tenant_id")
        namespace = kwargs.get("namespace")
        current = await self.get(
            memory_id, tenant_id=tenant_id, namespace=namespace,
            include_tombstoned=True,
        )
        if current.tenant_id != tenant_id or current.namespace != namespace:
            raise SealedContextBoundaryError("canonical memory tombstone scope changed")
        async with epoch.writer(tenant_id=tenant_id, actor_id=current.subject_id):
            return await method(self, memory_id, *args, **kwargs)

    return guarded


__all__ = [
    "MongoCanonicalSourceEpoch", "fence_conversation_write",
    "fence_memory_commit", "fence_memory_tombstone",
]
