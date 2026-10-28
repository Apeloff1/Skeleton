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

class MongoSourceEpochError(RuntimeError):
    """Canonical source epoch is unavailable or violates write fencing."""



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
            raise MongoSourceEpochError("canonical Mongo database required")
        try:
            from pymongo.read_concern import ReadConcern
            from pymongo.write_concern import WriteConcern
            collection = database.get_collection(
                "canonical_source_epochs",
                read_concern=ReadConcern("majority"),
                write_concern=WriteConcern(w="majority", wtimeout=10000),
            )
        except Exception as exc:
            raise MongoSourceEpochError("majority-durable source epoch unavailable") from exc
        for method in ("find_one", "find_one_and_update", "insert_one"):
            if not callable(getattr(collection, method, None)):
                raise MongoSourceEpochError("durable source epoch collection unavailable")
        self._collection = collection
        self._active: ContextVar[_BoundWriter | None] = ContextVar(
            "skeleton.canonical_source_writer", default=None,
        )

    @staticmethod
    def _key(tenant_id: str, actor_id: str) -> str:
        if any(not isinstance(v, str) or not v or v != v.strip()
               or len(v.encode("utf-8", "strict")) > 512 for v in (tenant_id, actor_id)):
            raise MongoSourceEpochError("canonical source writer identity invalid")
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
                or doc.get("writer_token") is not None
                or type(doc.get("epoch")) is not int or doc["epoch"] < 2
                or doc["epoch"] % 2):
            raise MongoSourceEpochError("canonical source epoch missing, writing or quarantined")
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
            raise MongoSourceEpochError(
                "source epoch already initialized or migration unavailable"
            ) from exc

    def require_actor_writer(self, *, tenant_id: str, actor_id: str) -> None:
        """Guard lower-level mutation paths that cannot acquire own epoch."""
        active = self._active.get()
        if (active is None or active.task is not asyncio.current_task()
                or active.tenant_id != tenant_id or active.actor_id != actor_id):
            raise MongoSourceEpochError("canonical write requires owner-scoped epoch")

    def require_tenant_writer(self, *, tenant_id: str) -> None:
        """Deletion-only boundary; tenant sweeps cannot invent actor custody."""
        active = self._active.get()
        if (active is None or active.task is not asyncio.current_task()
                or active.tenant_id != tenant_id):
            raise MongoSourceEpochError("tenant deletion requires canonical actor writer")

    @asynccontextmanager
    async def writer(self, *, tenant_id: str, actor_id: str):
        key = self._key(tenant_id, actor_id)
        task = asyncio.current_task()
        if task is None:
            raise MongoSourceEpochError("canonical source writer task required")
        active = self._active.get()
        if active is not None:
            if (active.task is not task or active.tenant_id != tenant_id
                    or active.actor_id != actor_id):
                raise MongoSourceEpochError("canonical writer scope cannot be inherited")
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
            raise MongoSourceEpochError("canonical writer admission unavailable") from exc
        if (not isinstance(acquired, dict) or acquired.get("writer_token") != token
                or acquired.get("phase") != "writing"
                or type(acquired.get("epoch")) is not int
                or acquired["epoch"] < 3 or acquired["epoch"] % 2 != 1):
            raise MongoSourceEpochError("canonical writer epoch not owned")
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
                raise MongoSourceEpochError(
                    "canonical writer completion unavailable; epoch remains quarantined"
                ) from exc
            if (not isinstance(closed, dict) or closed.get("phase") != "stable"
                    or closed.get("epoch") != acquired["epoch"] + 1):
                raise MongoSourceEpochError("canonical writer CAS lost; epoch quarantined")
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
            raise MongoSourceEpochError("canonical conversation write actor missing")
        async with epoch.writer(tenant_id=tenant_id, actor_id=actor_id):
            return await method(self, *args, **kwargs)

    guarded.__canonical_source_writer_fence__ = "conversation"
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
            raise MongoSourceEpochError("canonical memory write proposal required")
        async with epoch.writer(tenant_id=proposal.tenant_id, actor_id=proposal.subject_id):
            return await method(self, proposal, *args, **kwargs)

    guarded.__canonical_source_writer_fence__ = "memory_commit"
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
            raise MongoSourceEpochError("canonical memory tombstone scope changed")
        async with epoch.writer(tenant_id=tenant_id, actor_id=current.subject_id):
            return await method(self, memory_id, *args, **kwargs)

    guarded.__canonical_source_writer_fence__ = "memory_tombstone"
    return guarded


def fence_memento_write(method):
    """Include canonical ciphertext publication/erasure in actor writer custody.

    The memento archive is derivative of the canonical conversation, but its
    frame transaction and retirement mutate that conversation's stored head.
    They must participate in the very same actor-scoped majority-durable epoch.
    """
    from functools import wraps

    @wraps(method)
    async def guarded(self, *args, **kwargs):
        conversation = getattr(self, "conversation", None)
        epoch = getattr(conversation, "canonical_source_epoch", None)
        if epoch is None:
            return await method(self, *args, **kwargs)
        if "archive" in kwargs:
            from skeleton.context.sealed_memento import SealedMementoArchive

            archive = kwargs["archive"]
            if not isinstance(archive, SealedMementoArchive):
                raise MongoSourceEpochError("canonical memento archive binding required")
            tenant_id, actor_id = archive.binding.tenant_id, archive.binding.owner_id
        else:
            tenant_id, actor_id = kwargs.get("tenant_id"), kwargs.get("owner_id")
        if (not isinstance(tenant_id, str) or not isinstance(actor_id, str)
                or not tenant_id or not actor_id):
            raise MongoSourceEpochError("canonical memento mutation actor missing")
        async with epoch.writer(tenant_id=tenant_id, actor_id=actor_id):
            return await method(self, *args, **kwargs)

    guarded.__canonical_source_writer_fence__ = "memento"
    return guarded


# This is an IN-PROCESS, versioned inventory of the known canonical source
# mutation surfaces. It is not proof of external deployment writer coverage:
# unregistered services and direct database operations still need operator audit.
_CONVERSATION_WRITER_METHODS = (
    "create_thread", "rename_thread", "append_message",
    "bind_chat_execution", "chat_dispatch", "append_user_message",
    "commit_assistant_message", "regenerate_assistant_message",
    "edit_user_message", "bind_user_request_refs",
    "bind_user_engine_command", "bind_regeneration_request",
    "transition_regeneration_dispatch", "set_state",
)
_MEMORY_WRITER_METHODS = {
    "commit": "memory_commit",
    "tombstone": "memory_tombstone",
}
_MEMORY_INTERNAL_MUTATION_METHODS = (
    "_ensure_revision_and_projection", "_recover_reservation",
    "_reserve", "_release_failed_reservation", "_commit_reservation",
)


def verify_canonical_source_writer_inventory(*, conversation: Any, memory: Any, epoch: Any) -> None:
    """Fail closed if an expected production Mongo mutation loses writer custody.

    This detects missing decorators or subclass overrides of the known canonical
    entrypoints. It does not assert that independently deployed readers, other
    owners, backups, restorers or raw Mongo clients have been reconciled.
    """
    from core.conversations import MongoConversationAuthority
    from skeleton.persistence.memory_repository import MongoMemoryRepository

    if not isinstance(epoch, MongoCanonicalSourceEpoch):
        raise MongoSourceEpochError("canonical source requires majority-durable epoch")
    if not isinstance(conversation, MongoConversationAuthority):
        raise MongoSourceEpochError("canonical conversation must be production Mongo authority")
    if type(memory) is not MongoMemoryRepository:
        raise MongoSourceEpochError("canonical memory must be production Mongo repository")
    if (conversation.canonical_source_epoch is not epoch
            or memory.canonical_source_epoch is not epoch):
        raise MongoSourceEpochError("canonical owners must share one installed epoch")

    for name in _CONVERSATION_WRITER_METHODS:
        expected = getattr(MongoConversationAuthority, name, None)
        active = getattr(type(conversation), name, None)
        if (active is not expected
                or getattr(active, "__canonical_source_writer_fence__", None) != "conversation"):
            raise MongoSourceEpochError("unfenced canonical conversation writer: " + name)
    for name, fence in _MEMORY_WRITER_METHODS.items():
        method = getattr(MongoMemoryRepository, name, None)
        if getattr(method, "__canonical_source_writer_fence__", None) != fence:
            raise MongoSourceEpochError("unfenced canonical memory writer: " + name)
    for name in _MEMORY_INTERNAL_MUTATION_METHODS:
        if not callable(getattr(MongoMemoryRepository, name, None)):
            raise MongoSourceEpochError("missing fenced Mongo memory mutation helper: " + name)
    if not callable(getattr(MongoMemoryRepository, "_require_canonical_writer", None)):
        raise MongoSourceEpochError("missing internal Mongo memory writer guard")
    from skeleton.persistence.mongo_memento_repository import MongoMementoAuthority

    # The ciphertext sidecar edits the canonical conversation's head and
    # physically erases its frames. Keep both operations in the known source
    # inventory: an un-fenced derivative writer breaks source epoch guarantees.
    for name in ("publish", "retire_thread"):
        method = getattr(MongoMementoAuthority, name, None)
        if getattr(method, "__canonical_source_writer_fence__", None) != "memento":
            raise MongoSourceEpochError("unfenced canonical memento writer: " + name)


__all__ = [
    "MongoSourceEpochError", "MongoCanonicalSourceEpoch", "fence_conversation_write",
    "fence_memory_commit", "fence_memory_tombstone",
    "verify_canonical_source_writer_inventory", "fence_memento_write",
]
