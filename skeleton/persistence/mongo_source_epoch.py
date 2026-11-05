"""Majority-durable canonical-source writer epoch (fail-closed seqlock).

This fence protects read *windows* only when installed on ALL canonical writer
paths for the actor. A writer must persist WRITING before mutating any source
and persist STABLE only after every source write is durably acknowledged.
There is deliberately no automatic lease takeover: crash leaves the actor
unavailable until an operator performs separately audited reconciliation.

Readers use a primary-bound linearizable read, not a majority snapshot: a
majority-committed snapshot may lag a writer that has already entered WRITING.
Linearizable reads require a MongoDB replica-set primary. A standalone server
cannot qualify this fence and must not silently fall back to weaker reads.

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

_EPOCH_READ_MAX_TIME_MS = 2000
_EPOCH_READ_DEADLINE_SECONDS = 3.0
# A Mongo write timeout is AMBIGUOUS: never retry or clear a WRITING epoch.
_EPOCH_MUTATION_DEADLINE_SECONDS = 6.0

class MongoSourceEpochError(RuntimeError):
    """Canonical source epoch is unavailable or violates write fencing."""



@dataclass(slots=True)
class _BoundWriter:
    tenant_id: str
    actor_id: str
    task: asyncio.Task[Any]
    token: str
    poisoned: bool = False


class MongoCanonicalSourceEpoch:
    """Tenant/actor scoped durable writer fence shared by source owners."""

    def __init__(
        self, database: Any, *, revocation_authorizer: Any | None = None,
        migration_authorizer: Any | None = None,
    ) -> None:
        # A memory-only dummy/independently created collection is NOT accepted
        # as the production epoch witness.
        if not callable(getattr(database, "get_collection", None)):
            raise MongoSourceEpochError("canonical Mongo database required")
        try:
            from pymongo.read_concern import ReadConcern
            from pymongo.read_preferences import ReadPreference
            from pymongo.write_concern import WriteConcern
            collection = database.get_collection(
                "canonical_source_epochs",
                read_concern=ReadConcern("majority"),
                write_concern=WriteConcern(w="majority", wtimeout=10000),
                read_preference=ReadPreference.PRIMARY,
            )
            reader = database.get_collection(
                "canonical_source_epochs",
                read_concern=ReadConcern("linearizable"),
                read_preference=ReadPreference.PRIMARY,
            )
        except Exception as exc:
            raise MongoSourceEpochError("majority-durable source epoch unavailable") from exc
        for method in ("find_one", "find_one_and_update", "insert_one"):
            if not callable(getattr(collection, method, None)):
                raise MongoSourceEpochError("durable source epoch collection unavailable")
        if not callable(getattr(reader, "find_one", None)):
            raise MongoSourceEpochError("linearizable source epoch reader unavailable")
        # Retain the exact database object for fail-closed composition identity.
        # Same-named collections on distinct clients are not the same witness.
        self._database = database
        # Only the trusted application root may inject operator authorization.
        # No environment flag or request field can enable revocation.
        self._revocation_authorizer = revocation_authorizer
        # An unconfigured application cannot silently initialize a stable
        # actor epoch. Quiescence and backup evidence remain operator duties.
        self._migration_authorizer = migration_authorizer
        self._collection = collection
        self._reader = reader
        self._active: ContextVar[_BoundWriter | None] = ContextVar(
            "skeleton.canonical_source_writer", default=None,
        )

    @staticmethod
    async def _bounded_mutation(operation: Any) -> Any:
        """Bound a majority-CAS operation without asserting rollback on timeout.

        The driver may commit a write just before cancellation; callers must
        treat timeout as uncertain, preserve the durable phase, and require
        operator reconciliation rather than replaying the mutation.
        """
        async with asyncio.timeout(_EPOCH_MUTATION_DEADLINE_SECONDS):
            return await operation

    @staticmethod
    def _key(tenant_id: str, actor_id: str) -> str:
        try:
            invalid = any(
                type(v) is not str or not v or v != v.strip()
                or len(v.encode("utf-8", "strict")) > 512
                or any(ord(ch) < 32 or ord(ch) == 127 for ch in v)
                for v in (tenant_id, actor_id)
            )
        except UnicodeError as exc:
            raise MongoSourceEpochError("canonical source writer identity invalid") from exc
        if invalid:
            raise MongoSourceEpochError("canonical source writer identity invalid")
        return sha256(
            ("skeleton.canonical-source-epoch.v1\0" + tenant_id + "\0" + actor_id)
            .encode("utf-8")
        ).hexdigest()

    async def read_epoch(self, *, tenant_id: str, actor_id: str, context_id: str) -> int:
        # Scope includes context for callers, but the epoch deliberately fences
        # ALL contexts for one actor: memory mutations affect every conversation.
        self._key(tenant_id, context_id)
        try:
            # Keep cancellation/task identity intact and bound both Mongo's
            # server-side operation and the caller's overall read window.
            async with asyncio.timeout(_EPOCH_READ_DEADLINE_SECONDS):
                doc = await self._reader.find_one({
                    "_id": self._key(tenant_id, actor_id),
                    "tenant_id": tenant_id, "actor_id": actor_id,
                }, max_time_ms=_EPOCH_READ_MAX_TIME_MS)
        except MongoSourceEpochError:
            raise
        except Exception as exc:
            raise MongoSourceEpochError("linearizable source epoch read unavailable") from exc
        if (type(doc) is not dict or type(doc.get("_id")) is not str
                or doc["_id"] != self._key(tenant_id, actor_id)
                or type(doc.get("tenant_id")) is not str
                or doc["tenant_id"] != tenant_id
                or type(doc.get("actor_id")) is not str
                or doc["actor_id"] != actor_id
                or type(doc.get("phase")) is not str
                or doc["phase"] != "stable"
                or doc.get("writer_token") is not None
                or type(doc.get("epoch")) is not int or doc["epoch"] < 2
                or doc["epoch"] >= (1 << 63) or doc["epoch"] % 2):
            raise MongoSourceEpochError("canonical source epoch missing, writing or quarantined")
        return doc["epoch"]

    async def provision_migration_epoch(self, *, tenant_id: str, actor_id: str) -> None:
        """ONLY for an operator-controlled quiescent migration; never on reads."""
        key = self._key(tenant_id, actor_id)
        # Never create an apparently stable source epoch on standalone Mongo.
        # This is a read-only capability probe, NOT replica-set migration.
        database = getattr(self, "_database", None)
        if not callable(getattr(database, "command", None)):
            raise MongoSourceEpochError("replica-set primary required for epoch migration")
        try:
            async with asyncio.timeout(3.0):
                hello = await database.command("hello")
        except Exception:
            raise MongoSourceEpochError("replica-set primary probe unavailable") from None
        if (type(hello) is not dict
                or type(hello.get("setName")) is not str
                or not hello["setName"]
                or len(hello["setName"]) > 128
                or any(ord(ch) < 33 or ord(ch) > 126 for ch in hello["setName"])
                or hello.get("isWritablePrimary") is not True):
            raise MongoSourceEpochError("replica-set primary required for epoch migration")
        authorizer = getattr(self, "_migration_authorizer", None)
        database_name = getattr(getattr(self, "_database", None), "name", None)
        if (not callable(authorizer) or type(database_name) is not str
                or not database_name):
            raise MongoSourceEpochError("operator migration authority required")
        try:
            async with asyncio.timeout(3.0):
                approved = await authorizer(
                    tenant_id=tenant_id, actor_id=actor_id,
                    database_name=database_name,
                    purpose="quiescent-initial-epoch-v1",
                )
        except Exception:
            raise MongoSourceEpochError("operator migration authorization unavailable") from None
        if approved is not True:
            raise MongoSourceEpochError("operator migration authorization denied")
        try:
            await self._bounded_mutation(self._collection.insert_one({
                "_id": key, "tenant_id": tenant_id, "actor_id": actor_id,
                "phase": "stable", "epoch": 2, "writer_token": None,
            }))
        except Exception as exc:
            raise MongoSourceEpochError(
                "source epoch already initialized or migration unavailable"
            ) from exc

    async def revoke_actor(
        self, *, tenant_id: str, actor_id: str,
        expected_epoch: int, reason_code: str,
    ) -> int:
        """Operator-authorized, majority-CAS terminal actor quarantine.

        Only a STABLE epoch can be revoked. A currently WRITING actor cannot
        be preempted safely by this protocol: its mutation may already have
        reached Mongo. Such attempts fail closed for operator reconciliation.
        Revocation is never an automatic recovery or migration primitive.
        """
        key = self._key(tenant_id, actor_id)
        if (type(expected_epoch) is not int or expected_epoch < 2
                or expected_epoch % 2 != 0 or expected_epoch >= (1 << 63) - 1):
            raise MongoSourceEpochError("revocation requires a stable expected epoch")
        # Reject hostile scalar subclasses before equality or Mongo encoding.
        # A string subclass can override __eq__ and falsely claim admission.
        if type(reason_code) is not str or reason_code not in (
            "operator-revoke", "credential-rotation", "source-integrity",
            "tenant-deletion",
        ):
            raise MongoSourceEpochError("revocation reason is not admitted")
        authorizer = getattr(self, "_revocation_authorizer", None)
        if not callable(authorizer):
            raise MongoSourceEpochError("independent operator revocation authority missing")
        try:
            async with asyncio.timeout(3.0):
                approved = await authorizer(
                    tenant_id=tenant_id, actor_id=actor_id,
                    expected_epoch=expected_epoch, reason_code=reason_code,
                )
        except Exception:
            raise MongoSourceEpochError("operator revocation authorization unavailable") from None
        if approved is not True:
            raise MongoSourceEpochError("operator revocation not authorized")
        try:
            from pymongo import ReturnDocument
            result = await self._bounded_mutation(self._collection.find_one_and_update(
                {
                    "_id": key, "tenant_id": tenant_id, "actor_id": actor_id,
                    "phase": "stable", "writer_token": None,
                    "epoch": expected_epoch,
                },
                {
                    "$inc": {"epoch": 1},
                    "$set": {"phase": "revoked", "revoked_reason": reason_code},
                },
                return_document=ReturnDocument.AFTER,
            ))
        except Exception:
            # A timed-out majority write may have committed. Never retry
            # blindly or reset the epoch; operator must read/reconcile.
            raise MongoSourceEpochError("actor revocation outcome uncertain") from None
        if (type(result) is not dict
                or type(result.get("_id")) is not str or result["_id"] != key
                or type(result.get("tenant_id")) is not str
                or result["tenant_id"] != tenant_id
                or type(result.get("actor_id")) is not str
                or result["actor_id"] != actor_id
                or type(result.get("phase")) is not str
                or result["phase"] != "revoked"
                or type(result.get("epoch")) is not int
                or result["epoch"] != expected_epoch + 1
                or type(result.get("revoked_reason")) is not str
                or result["revoked_reason"] != reason_code
                or result.get("writer_token") is not None):
            raise MongoSourceEpochError("actor revocation CAS rejected or unverified")
        return result["epoch"]

    def require_actor_writer(self, *, tenant_id: str, actor_id: str) -> None:
        """Guard lower-level mutation paths that cannot acquire own epoch."""
        # Lower-level callers may bypass writer() argument validation. Never
        # compare attacker-controlled string subclasses against the bound
        # scope: their __eq__ can forge a matching actor or tenant.
        self._key(tenant_id, actor_id)
        active = self._active.get()
        if (active is None or active.task is not asyncio.current_task()
                or active.tenant_id != tenant_id or active.actor_id != actor_id):
            raise MongoSourceEpochError("canonical write requires owner-scoped epoch")
        if active.poisoned:
            raise MongoSourceEpochError("canonical writer is poisoned")

    def require_tenant_writer(self, *, tenant_id: str) -> None:
        """Deletion-only boundary; tenant sweeps cannot invent actor custody."""
        # The deletion path has only a tenant argument; validate its exact
        # scalar type before comparison with an authenticated writer binding.
        self._key(tenant_id, tenant_id)
        active = self._active.get()
        if (active is None or active.task is not asyncio.current_task()
                or active.tenant_id != tenant_id):
            raise MongoSourceEpochError("tenant deletion requires canonical actor writer")
        if active.poisoned:
            raise MongoSourceEpochError("canonical writer is poisoned")

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
            if active.poisoned:
                raise MongoSourceEpochError("canonical writer is poisoned")
            # Reentrant writes share the same physical majority epoch.
            # A nested mutation that raises may have partially committed.
            # Even if its caller catches that exception, the outer writer
            # MUST NOT publish a stable epoch after an uncertain mutation.
            try:
                yield
            except BaseException:
                active.poisoned = True
                raise
            return
        token = str(uuid4())
        try:
            from pymongo import ReturnDocument
            acquired = await self._bounded_mutation(self._collection.find_one_and_update(
                {"_id": key, "tenant_id": tenant_id, "actor_id": actor_id,
                 "phase": "stable", "writer_token": None,
                 "epoch": {"$gte": 2, "$lt": (1 << 63) - 2}},
                {"$inc": {"epoch": 1},
                 "$set": {"phase": "writing", "writer_token": token}},
                return_document=ReturnDocument.AFTER,
            ))
        except Exception as exc:
            raise MongoSourceEpochError("canonical writer admission unavailable") from exc
        if (type(acquired) is not dict or type(acquired.get("_id")) is not str
                or acquired["_id"] != key
                or type(acquired.get("tenant_id")) is not str
                or acquired["tenant_id"] != tenant_id
                or type(acquired.get("actor_id")) is not str
                or acquired["actor_id"] != actor_id
                or type(acquired.get("phase")) is not str
                or type(acquired.get("writer_token")) is not str
                or acquired.get("writer_token") != token
                or acquired.get("phase") != "writing"
                or type(acquired.get("epoch")) is not int
                or acquired["epoch"] < 3 or acquired["epoch"] >= (1 << 63) - 1
                or acquired["epoch"] % 2 != 1):
            raise MongoSourceEpochError("canonical writer epoch not owned")
        binding = _BoundWriter(tenant_id, actor_id, task, token)
        scope = self._active.set(binding)
        try:
            yield
            if binding.poisoned:
                raise MongoSourceEpochError(
                    "nested canonical mutation failed; actor epoch quarantined"
                )
            try:
                closed = await self._bounded_mutation(self._collection.find_one_and_update(
                    {"_id": key, "tenant_id": tenant_id, "actor_id": actor_id,
                     "phase": "writing", "writer_token": token,
                     "epoch": acquired["epoch"]},
                    {"$inc": {"epoch": 1},
                     "$set": {"phase": "stable", "writer_token": None}},
                    return_document=ReturnDocument.AFTER,
                ))
            except Exception as exc:
                raise MongoSourceEpochError(
                    "canonical writer completion unavailable; epoch remains quarantined"
                ) from exc
            if (type(closed) is not dict or type(closed.get("_id")) is not str
                    or closed["_id"] != key
                    or type(closed.get("tenant_id")) is not str
                    or closed["tenant_id"] != tenant_id
                    or type(closed.get("actor_id")) is not str
                    or closed["actor_id"] != actor_id
                    or type(closed.get("phase")) is not str
                    or closed.get("phase") != "stable"
                    or closed.get("writer_token") is not None
                    or type(closed.get("epoch")) is not int
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
        if type(tenant_id) is not str or type(actor_id) is not str:
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
        # The lookup result is not an authority to select a different actor.
        # Validate exact scalar identities before comparisons or writer CAS:
        # hostile string subclasses can override equality and forge scope.
        if (type(tenant_id) is not str or type(namespace) is not str
                or current is None
                or type(getattr(current, "tenant_id", None)) is not str
                or type(getattr(current, "namespace", None)) is not str
                or type(getattr(current, "subject_id", None)) is not str
                or current.tenant_id != tenant_id or current.namespace != namespace):
            raise MongoSourceEpochError("canonical memory tombstone scope changed")
        epoch._key(tenant_id, current.subject_id)
        async with epoch.writer(tenant_id=tenant_id, actor_id=current.subject_id):
            return await method(self, memory_id, *args, **kwargs)

    guarded.__canonical_source_writer_fence__ = "memory_tombstone"
    return guarded


# A witnessed Mongo primitive may publish only while its own facade holds
# both the canonical actor epoch and the independent-witness handoff. This is
# an in-process routing assertion, not a substitute for external CAS security.
_ACTIVE_WITNESSED_HANDOFF: ContextVar[tuple[Any, Any, str, str, asyncio.Task[Any]] | None] = (
    ContextVar("skeleton.canonical_memento_witness_handoff", default=None)
)


@asynccontextmanager
async def _witnessed_memento_handoff(
    *, mongo: Any, witness: Any, tenant_id: str, actor_id: str,
):
    conversation = getattr(mongo, "conversation", None)
    epoch = getattr(conversation, "canonical_source_epoch", None)
    if epoch is None:
        yield
        return
    if witness is not getattr(conversation, "memento_witness", None):
        raise MongoSourceEpochError("witness handoff does not match canonical owner")
    epoch.require_actor_writer(tenant_id=tenant_id, actor_id=actor_id)
    task = asyncio.current_task()
    if task is None or _ACTIVE_WITNESSED_HANDOFF.get() is not None:
        raise MongoSourceEpochError("witness handoff must be unique to one writer task")
    token = _ACTIVE_WITNESSED_HANDOFF.set(
        (mongo, witness, tenant_id, actor_id, task)
    )
    try:
        yield
    finally:
        _ACTIVE_WITNESSED_HANDOFF.reset(token)


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
        if (type(tenant_id) is not str or type(actor_id) is not str
                or not tenant_id or not actor_id):
            raise MongoSourceEpochError("canonical memento mutation actor missing")
        if ("archive" not in kwargs and
                (type(kwargs.get("thread_id")) is not str
                 or not kwargs["thread_id"])):
            # Syntactically invalid no-write denials must not quarantine an
            # otherwise stable actor epoch merely by acquiring it.
            raise MongoSourceEpochError("canonical memento mutation thread missing")
        if "archive" in kwargs and method.__name__ == "publish":
            # A protected Mongo source must NEVER use the legacy independent-
            # witness bypass. Reject policy mistakes before acquiring the
            # majority epoch so a denied no-write call cannot quarantine it.
            if kwargs.get("custody_mode", "legacy") != "witnessed":
                raise MongoSourceEpochError("protected memento requires witnessed custody")
            witness = getattr(conversation, "memento_witness", None)
            if not all(callable(getattr(witness, name, None)) for name in (
                "read", "compare_and_set",
            )):
                raise MongoSourceEpochError("protected memento requires independent witness")
            handoff = _ACTIVE_WITNESSED_HANDOFF.get()
            if (handoff is None or handoff[0] is not self
                    or handoff[1] is not witness or handoff[2] != tenant_id
                    or handoff[3] != actor_id
                    or handoff[4] is not asyncio.current_task()):
                raise MongoSourceEpochError(
                    "protected memento publication requires witnessed handoff"
                )
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


def _require_unshadowed_writer(owner: Any, class_method: Any, name: str) -> None:
    """Reject instance-level overrides of otherwise decorated source writers.

    Checking only the class method misses a mutable instance attribute that
    shadows a fenced entrypoint. A protected owner must dispatch the exact
    class descriptor bound to that owner, including internal memory helpers.
    """
    try:
        bound = getattr(owner, name)
    except Exception:
        raise MongoSourceEpochError("canonical writer binding unavailable: " + name) from None
    if (not callable(class_method) or getattr(bound, "__self__", None) is not owner
            or getattr(bound, "__func__", None) is not class_method):
        raise MongoSourceEpochError("canonical writer instance override: " + name)


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
        _require_unshadowed_writer(conversation, expected, name)
    for name, fence in _MEMORY_WRITER_METHODS.items():
        method = getattr(MongoMemoryRepository, name, None)
        if getattr(method, "__canonical_source_writer_fence__", None) != fence:
            raise MongoSourceEpochError("unfenced canonical memory writer: " + name)
        _require_unshadowed_writer(memory, method, name)
    for name in _MEMORY_INTERNAL_MUTATION_METHODS:
        method = getattr(MongoMemoryRepository, name, None)
        if not callable(method):
            raise MongoSourceEpochError("missing fenced Mongo memory mutation helper: " + name)
        _require_unshadowed_writer(memory, method, name)
    method = getattr(MongoMemoryRepository, "_require_canonical_writer", None)
    if not callable(method):
        raise MongoSourceEpochError("missing internal Mongo memory writer guard")
    _require_unshadowed_writer(memory, method, "_require_canonical_writer")
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
