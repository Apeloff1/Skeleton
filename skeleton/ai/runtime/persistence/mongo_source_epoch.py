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
_EPOCH_MUTATION_DEADLINE_SECONDS = 12.0
_MAX_EPOCH = (1 << 63) - 1

class MongoSourceEpochError(RuntimeError):
    """Canonical source epoch is unavailable or violates write fencing."""



@dataclass(slots=True)
class _BoundWriter:
    tenant_id: str
    actor_id: str
    task: asyncio.Task[Any]
    token: str
    poisoned: bool = False


def _epoch_integer(value: object) -> int | None:
    """Normalize exact BSON driver integers, rejecting bool and subclasses."""
    if type(value) is int:
        return value
    try:
        from bson.int64 import Int64
    except ImportError:
        return None
    if type(value) is Int64:
        return int(value)
    return None


def _verified_epoch_record(
    doc: object, *, key: str, tenant_id: str, actor_id: str,
    phase: str, writer_token: str | None,
) -> int | None:
    if (type(doc) is not dict or len(doc) > 32
            or any(type(item) is not str or len(item) > 128 for item in doc)):
        return None
    for field, value in (
        ("_id", key), ("tenant_id", tenant_id), ("actor_id", actor_id),
        ("phase", phase), ("writer_token", writer_token),
    ):
        if field not in doc or type(doc[field]) is not type(value) or doc[field] != value:
            return None
    number = _epoch_integer(doc.get("epoch"))
    if number is None or not 2 <= number <= _MAX_EPOCH:
        return None
    if number % 2 != (1 if phase in ("writing", "revoked") else 0):
        return None
    return number


class MongoCanonicalSourceEpoch:
    """Tenant/actor scoped durable writer fence shared by source owners."""

    def __init__(self, database: Any, *, migration_authorizer: Any = None,
                 revocation_authorizer: Any = None) -> None:
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
        self._database = database
        self._migration_authorizer = migration_authorizer
        self._revocation_authorizer = revocation_authorizer
        self._deployment_latch_pin = None
        self._deployment_latch_failed = False
        self._collection = collection
        self._reader = reader
        self._active: ContextVar[_BoundWriter | None] = ContextVar(
            "skeleton.canonical_source_writer", default=None,
        )

    @staticmethod
    def _key(tenant_id: str, actor_id: str) -> str:
        try:
            invalid = any(type(v) is not str or not v or len(v) > 512 or v != v.strip()
                          or any(ord(ch) < 32 or ord(ch) == 127 for ch in v)
                          or len(v.encode("utf-8", "strict")) > 512 for v in (tenant_id, actor_id))
        except UnicodeError as exc:
            raise MongoSourceEpochError("canonical source writer identity invalid") from exc
        if invalid:
            raise MongoSourceEpochError("canonical source writer identity invalid")
        return sha256(
            ("skeleton.canonical-source-epoch.v1\0" + tenant_id + "\0" + actor_id)
            .encode("utf-8")
        ).hexdigest()

    async def bind_deployment_latch(self, reservation: dict) -> None:
        """Install a process-owned, non-replaceable shared startup reservation.

        Only the trusted backend startup calls this after signed cutover and
        durable publication. No HTTP or model output can bind it.
        """
        if (getattr(self, "_deployment_latch_pin", None) is not None
                or getattr(self, "_deployment_latch_failed", False)
                or type(reservation) is not dict
                or set(reservation) != {"generation","latch_sha256"}
                or type(reservation["generation"]) is not int
                or not 1 <= reservation["generation"] < (1 << 63)
                or reservation["generation"] % 2 != 1
                or type(reservation["latch_sha256"]) is not str):
            raise MongoSourceEpochError("canonical writer deployment pin invalid")
        self._deployment_latch_pin = (reservation["generation"],reservation["latch_sha256"])
        await self._assert_deployment_latch()

    async def _assert_deployment_latch(self) -> None:
        if getattr(self, "_deployment_latch_failed", False):
            raise MongoSourceEpochError("canonical writer deployment reservation quarantined")
        pin = getattr(self, "_deployment_latch_pin", None)
        if pin is None:
            return
        try:
            from skeleton.app.canonical_writer_cutover import verify_writer_deployment
            await verify_writer_deployment(epoch=self, reservation={
                "generation":pin[0],"latch_sha256":pin[1],
            })
            if (self._deployment_latch_pin is not pin
                    or self._deployment_latch_failed):
                raise MongoSourceEpochError("canonical writer deployment pin changed")
        except asyncio.CancelledError:
            self._deployment_latch_failed = True
            raise
        except Exception:
            self._deployment_latch_failed = True
            raise MongoSourceEpochError("canonical writer deployment reservation lost") from None

    async def read_epoch(self, *, tenant_id: str, actor_id: str, context_id: str) -> int:
        # Scope includes context for callers, but the epoch deliberately fences
        # ALL contexts for one actor: memory mutations affect every conversation.
        self._key(tenant_id, context_id)
        await self._assert_deployment_latch()
        key = self._key(tenant_id, actor_id)
        try:
            # Keep cancellation/task identity intact and bound both Mongo's
            # server-side operation and the caller's overall read window.
            async with asyncio.timeout(_EPOCH_READ_DEADLINE_SECONDS):
                doc = await self._reader.find_one({
                    "_id": key,
                    "tenant_id": tenant_id, "actor_id": actor_id,
                }, max_time_ms=_EPOCH_READ_MAX_TIME_MS)
        except MongoSourceEpochError:
            raise
        except Exception:
            raise MongoSourceEpochError("linearizable source epoch read unavailable") from None
        number = _verified_epoch_record(
            doc, key=key, tenant_id=tenant_id, actor_id=actor_id,
            phase="stable", writer_token=None,
        )
        if number is None:
            raise MongoSourceEpochError("canonical source epoch missing, writing or quarantined")
        await self._assert_deployment_latch()
        return number

    async def _operator_snapshot(self) -> tuple[object, ...]:
        """Observe primary and authenticated roles; not proof of quiescence."""
        from skeleton.app.compose_guarded_preflight import (
            _authenticated_principals, _database_name, _plain_document, _trusted_topology,
        )

        database = self._database
        db_name = getattr(database, "name", None)
        if not _database_name(db_name) or not callable(getattr(database, "command", None)):
            raise MongoSourceEpochError("operator epoch database authority unavailable")
        try:
            async with asyncio.timeout(_EPOCH_READ_DEADLINE_SECONDS):
                hello = await database.command("hello")
                auth = await database.command("connectionStatus")
        except Exception:
            raise MongoSourceEpochError("operator replica-set authority unavailable") from None
        topology = _trusted_topology(hello)
        principals = _authenticated_principals(auth)
        if topology is None:
            raise MongoSourceEpochError("operator replica-set primary required")
        if (principals is None or not _plain_document(auth)
                or not _plain_document(auth.get("authInfo"))
                or not auth["authInfo"].get("authenticatedUserRoles")):
            raise MongoSourceEpochError("operator authenticated role custody required")
        return (db_name, topology, principals)

    async def _authorize_operator(self, authorizer: Any, **binding: Any) -> None:
        if not callable(authorizer):
            raise MongoSourceEpochError("explicit operator epoch authority required")
        try:
            async with asyncio.timeout(_EPOCH_READ_DEADLINE_SECONDS):
                granted = await authorizer(**binding)
        except Exception:
            raise MongoSourceEpochError("operator epoch authority unavailable") from None
        if granted is not True:
            raise MongoSourceEpochError("operator epoch authority denied")

    async def provision_migration_epoch(self, *, tenant_id: str, actor_id: str) -> None:
        """Insert once under explicit quiescent migration authority; never reset."""
        key = self._key(tenant_id, actor_id)
        if not callable(self._migration_authorizer):
            raise MongoSourceEpochError("explicit operator migration authority required")
        initial = await self._operator_snapshot()
        await self._authorize_operator(
            self._migration_authorizer, tenant_id=tenant_id, actor_id=actor_id,
            database_name=initial[0], purpose="quiescent-initial-epoch-v1",
        )
        if await self._operator_snapshot() != initial:
            raise MongoSourceEpochError("operator epoch authority changed before migration")
        try:
            async with asyncio.timeout(_EPOCH_MUTATION_DEADLINE_SECONDS):
                inserted = await self._collection.insert_one({
                    "_id": key, "tenant_id": tenant_id, "actor_id": actor_id,
                    "phase": "stable", "epoch": 2, "writer_token": None,
                })
            if (getattr(inserted, "acknowledged", None) is not True
                    or type(getattr(inserted, "inserted_id", None)) is not str
                    or inserted.inserted_id != key):
                raise MongoSourceEpochError("migration write acknowledgement unverified")
            observed = await self.read_epoch(
                tenant_id=tenant_id, actor_id=actor_id, context_id=actor_id,
            )
            if observed != 2 or await self._operator_snapshot() != initial:
                raise MongoSourceEpochError("migration state or authority changed")
        except Exception:
            # An ambiguous result may already be durable. Never retry or reset.
            raise MongoSourceEpochError(
                "source epoch already initialized or migration uncertain; reconcile"
            ) from None

    async def revoke_actor(
        self, *, tenant_id: str, actor_id: str, expected_epoch: int, reason_code: str,
    ) -> int:
        """Terminal actor quarantine using an exact stable-generation CAS."""
        key = self._key(tenant_id, actor_id)
        if (type(expected_epoch) is not int or not 2 <= expected_epoch < _MAX_EPOCH
                or expected_epoch % 2):
            raise MongoSourceEpochError("revocation requires a stable expected epoch")
        if type(reason_code) is not str or reason_code not in (
            "operator-revoke", "security-incident", "authority-retired",
        ):
            raise MongoSourceEpochError("revocation reason invalid")
        if not callable(self._revocation_authorizer):
            raise MongoSourceEpochError("explicit operator revocation authority required")
        initial = await self._operator_snapshot()
        await self._authorize_operator(
            self._revocation_authorizer, tenant_id=tenant_id, actor_id=actor_id,
            database_name=initial[0], expected_epoch=expected_epoch, reason_code=reason_code,
            purpose="terminal-actor-revocation-v1",
        )
        observed = await self.read_epoch(
            tenant_id=tenant_id, actor_id=actor_id, context_id=actor_id,
        )
        if observed != expected_epoch or await self._operator_snapshot() != initial:
            raise MongoSourceEpochError("revocation source authority changed")
        try:
            from pymongo import ReturnDocument
            async with asyncio.timeout(_EPOCH_MUTATION_DEADLINE_SECONDS):
                revoked = await self._collection.find_one_and_update(
                    {"_id": key, "tenant_id": tenant_id, "actor_id": actor_id,
                     "phase": "stable", "writer_token": None, "epoch": expected_epoch},
                    {"$inc": {"epoch": 1}, "$set": {
                        "phase": "revoked", "writer_token": None,
                        "revocation_reason": reason_code,
                    }},
                    return_document=ReturnDocument.AFTER,
                )
            generation = _verified_epoch_record(
                revoked, key=key, tenant_id=tenant_id, actor_id=actor_id,
                phase="revoked", writer_token=None,
            )
            if (generation != expected_epoch + 1
                    or type(revoked.get("revocation_reason")) is not str
                    or revoked["revocation_reason"] != reason_code):
                raise MongoSourceEpochError("revocation CAS unverified")
            async with asyncio.timeout(_EPOCH_READ_DEADLINE_SECONDS):
                record = await self._reader.find_one({
                    "_id": key, "tenant_id": tenant_id, "actor_id": actor_id,
                }, max_time_ms=_EPOCH_READ_MAX_TIME_MS)
            if (_verified_epoch_record(record, key=key, tenant_id=tenant_id, actor_id=actor_id,
                    phase="revoked", writer_token=None) != generation
                    or type(record.get("revocation_reason")) is not str
                    or record["revocation_reason"] != reason_code
                    or await self._operator_snapshot() != initial):
                raise MongoSourceEpochError("revocation readback unverified")
            return generation
        except Exception:
            raise MongoSourceEpochError("revocation uncertain; reconcile without retry") from None

    def require_actor_writer(self, *, tenant_id: str, actor_id: str) -> None:
        """Guard lower-level mutation paths that cannot acquire own epoch."""
        self._key(tenant_id, actor_id)
        active = self._active.get()
        if (active is None or active.poisoned or active.task is not asyncio.current_task()
                or active.tenant_id != tenant_id or active.actor_id != actor_id):
            raise MongoSourceEpochError("canonical write requires owner-scoped epoch")

    def require_tenant_writer(self, *, tenant_id: str) -> None:
        """Deletion-only boundary; tenant sweeps cannot invent actor custody."""
        self._key(tenant_id, tenant_id)
        active = self._active.get()
        if (active is None or active.poisoned or active.task is not asyncio.current_task()
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
            if active.poisoned:
                raise MongoSourceEpochError("canonical writer scope is quarantined")
            try:
                await self._assert_deployment_latch()
                yield
                await self._assert_deployment_latch()
            except BaseException:
                # Even a caught nested failure may have partially mutated data.
                active.poisoned = True
                raise
            return

        token = str(uuid4())
        try:
            from pymongo import ReturnDocument

            # A stable linearizable read followed by an exact epoch CAS is
            # essential: a generic phase query could increment corrupted,
            # overflowing or already replaced source state.
            expected = await self.read_epoch(
                tenant_id=tenant_id, actor_id=actor_id, context_id=actor_id,
            )
            if expected > _MAX_EPOCH - 2:
                raise MongoSourceEpochError("canonical epoch generation exhausted")
            async with asyncio.timeout(_EPOCH_MUTATION_DEADLINE_SECONDS):
                acquired = await self._collection.find_one_and_update(
                    {"_id": key, "tenant_id": tenant_id, "actor_id": actor_id,
                     "phase": "stable", "writer_token": None, "epoch": expected},
                    {"$inc": {"epoch": 1},
                     "$set": {"phase": "writing", "writer_token": token}},
                    return_document=ReturnDocument.AFTER,
                )
        except Exception:
            # An ambiguous driver timeout does not imply that the write failed.
            # Never roll back, retry, or disclose driver exception contents.
            raise MongoSourceEpochError("canonical writer admission unavailable") from None
        acquired_number = _verified_epoch_record(
            acquired, key=key, tenant_id=tenant_id, actor_id=actor_id,
            phase="writing", writer_token=token,
        )
        if acquired_number != expected + 1:
            raise MongoSourceEpochError("canonical writer epoch not owned")

        custody = _BoundWriter(tenant_id, actor_id, task, token)
        scope = self._active.set(custody)
        try:
            # If lost after durable actor admission, leave WRITING quarantined.
            await self._assert_deployment_latch()
            yield
            await self._assert_deployment_latch()
            if custody.poisoned:
                raise MongoSourceEpochError("canonical writer scope is quarantined")
            try:
                async with asyncio.timeout(_EPOCH_MUTATION_DEADLINE_SECONDS):
                    closed = await self._collection.find_one_and_update(
                        {"_id": key, "tenant_id": tenant_id, "actor_id": actor_id,
                         "phase": "writing", "writer_token": token,
                         "epoch": acquired_number},
                        {"$inc": {"epoch": 1},
                         "$set": {"phase": "stable", "writer_token": None}},
                        return_document=ReturnDocument.AFTER,
                    )
            except Exception:
                raise MongoSourceEpochError(
                    "canonical writer completion unavailable; reconcile uncertain epoch"
                ) from None
            closed_number = _verified_epoch_record(
                closed, key=key, tenant_id=tenant_id, actor_id=actor_id,
                phase="stable", writer_token=None,
            )
            if closed_number != acquired_number + 1:
                raise MongoSourceEpochError("canonical writer CAS lost; reconcile uncertain epoch")
            await self._assert_deployment_latch()
        finally:
            # An exception in protected mutation leaves the epoch WRITING.
            # A completion-ack failure is uncertain, not evidence of rollback.
            self._active.reset(scope)



def configured_canonical_epoch(owner: Any) -> Any:
    """Resolve the epoch without permitting an installed owner to downgrade.

    Legacy owners may have no binding. Once protected startup binds an exact
    owner, loss or replacement is a hard failure on every known write surface.
    This is a process-owned invariant, not protection against arbitrary Python
    code execution or independent clients with Mongo write credentials.
    """
    epoch = getattr(owner, "canonical_source_epoch", None)
    required = getattr(owner, "_required_canonical_source_epoch", None)
    if required is not None and (type(required) is not MongoCanonicalSourceEpoch
                                 or epoch is not required):
        raise MongoSourceEpochError("protected canonical writer epoch binding changed")
    if required is not None:
        pins = getattr(owner, "_required_canonical_source_handles", None)
        if pins is not None:
            if (type(pins) is not tuple or not pins
                    or any(getattr(owner, name, None) is not handle for name, handle in pins)):
                raise MongoSourceEpochError("protected canonical source handle changed")
            for _, handle in pins:
                _assert_majority_handle(handle)
    return epoch


def _assert_majority_handle(handle):
    from pymongo.read_preferences import ReadPreference
    concern = getattr(getattr(handle, "write_concern", None), "document", None)
    if (type(concern) is not dict or concern.get("w") != "majority"
            or concern.get("j") is not True or concern.get("wtimeout") != 10000
            or getattr(getattr(handle, "read_concern", None), "level", None) != "majority"
            or getattr(handle, "read_preference", None) != ReadPreference.PRIMARY):
        raise MongoSourceEpochError("protected canonical source durability unavailable")


def _majority_source_bindings(conversation, memory, epoch):
    """Prepare real database/collection handles without any database writes."""
    from pymongo.read_concern import ReadConcern
    from pymongo.read_preferences import ReadPreference
    from pymongo.write_concern import WriteConcern
    database = epoch._database
    options = dict(read_concern=ReadConcern("majority"), read_preference=ReadPreference.PRIMARY,
                   write_concern=WriteConcern(w="majority", j=True, wtimeout=10000))
    result = []
    for owner, names in (
        (conversation, (("database", None), ("threads","conversation_threads"),
                        ("messages","conversation_messages"))),
        (memory, (("records","canonical_memory_records"), ("idempotency","canonical_memory_idempotency"),
                  ("revisions","canonical_memory_revisions"), ("projection_outbox","canonical_memory_projection_outbox"))),
    ):
        pinned = []
        for attribute, collection_name in names:
            original = getattr(owner, attribute, None)
            actual_db = original if collection_name is None else getattr(original,"database",None)
            if (getattr(actual_db,"client",None) is not database.client
                    or getattr(actual_db,"name",None) != database.name
                    or (collection_name is not None and getattr(original,"name",None) != collection_name)):
                raise MongoSourceEpochError("protected canonical source collection ownership mismatch")
            protected = original.with_options(**options)
            _assert_majority_handle(protected)
            observed_db = protected if collection_name is None else protected.database
            if (observed_db.client is not database.client or observed_db.name != database.name
                    or (collection_name is not None and protected.name != collection_name)):
                raise MongoSourceEpochError("protected canonical source handle identity changed")
            pinned.append((attribute,protected))
        result.append((owner,tuple(pinned)))
    return tuple(result)


def bind_required_canonical_writers(*, conversation: Any, memory: Any, epoch: Any) -> None:
    """Install one sticky authority at trusted startup before accepting work.

    Validation failures leave both owners fenced/blocked rather than
    restoring an optional legacy mode. A failed deployment must restart and
    reconcile, never clear this marker in a live process.
    """
    if type(epoch) is not MongoCanonicalSourceEpoch:
        raise MongoSourceEpochError("protected writer requires canonical epoch")
    from core.conversations import MongoConversationAuthority
    from skeleton.persistence.memory_repository import MongoMemoryRepository
    if type(conversation) is not MongoConversationAuthority or type(memory) is not MongoMemoryRepository:
        raise MongoSourceEpochError("protected writer requires exact canonical owners")
    for owner in (conversation, memory):
        existing = configured_canonical_epoch(owner)
        if existing is not None and existing is not epoch:
            raise MongoSourceEpochError("canonical writer already bound")
        if getattr(owner, "_required_canonical_source_epoch", None) is not None:
            raise MongoSourceEpochError("protected writer binding already installed")
    prepared = _majority_source_bindings(conversation, memory, epoch)
    # No await between installing the deny marker, majority source handles
    # and actual shared authority. Never restore optional legacy mode.
    conversation._required_canonical_source_epoch = epoch
    memory._required_canonical_source_epoch = epoch
    for owner, handles in prepared:
        for attribute, handle in handles:
            setattr(owner, attribute, handle)
        owner._required_canonical_source_handles = handles
    conversation.canonical_source_epoch = epoch
    memory.canonical_source_epoch = epoch
    verify_canonical_source_writer_inventory(conversation=conversation, memory=memory, epoch=epoch)


def fence_conversation_write(method):
    """Apply configured writer fencing to real conversation mutation entrypoints."""
    from functools import wraps

    @wraps(method)
    async def guarded(self, *args, **kwargs):
        epoch = configured_canonical_epoch(self)
        if epoch is None:
            return await method(self, *args, **kwargs)
        tenant_id, actor_id = kwargs.get("tenant_id"), kwargs.get("owner_id")
        if not isinstance(tenant_id, str) or not isinstance(actor_id, str):
            raise MongoSourceEpochError("canonical conversation write actor missing")
        async with epoch.writer(tenant_id=tenant_id, actor_id=actor_id):
            result = await method(self, *args, **kwargs)
            if configured_canonical_epoch(self) is not epoch:
                raise MongoSourceEpochError("canonical conversation authority changed during mutation")
            return result

    guarded.__canonical_source_writer_fence__ = "conversation"
    return guarded


def fence_memory_commit(method):
    """Admit governed memory mutation before reservation, CAS and publication."""
    from functools import wraps

    @wraps(method)
    async def guarded(self, proposal, *args, **kwargs):
        epoch = configured_canonical_epoch(self)
        if epoch is None:
            return await method(self, proposal, *args, **kwargs)
        from skeleton.contracts.memory_record import MemoryWriteProposal

        if not isinstance(proposal, MemoryWriteProposal):
            raise MongoSourceEpochError("canonical memory write proposal required")
        async with epoch.writer(tenant_id=proposal.tenant_id, actor_id=proposal.subject_id):
            result = await method(self, proposal, *args, **kwargs)
            if configured_canonical_epoch(self) is not epoch:
                raise MongoSourceEpochError("canonical memory authority changed during mutation")
            return result

    guarded.__canonical_source_writer_fence__ = "memory_commit"
    return guarded


def fence_memory_tombstone(method):
    """Pin current memory subject before tombstone; underlying CAS rechecks it."""
    from functools import wraps

    @wraps(method)
    async def guarded(self, memory_id, *args, **kwargs):
        epoch = configured_canonical_epoch(self)
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
            result = await method(self, memory_id, *args, **kwargs)
            if configured_canonical_epoch(self) is not epoch:
                raise MongoSourceEpochError("canonical memory authority changed during retirement")
            return result

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
    epoch = configured_canonical_epoch(conversation)
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
        epoch = configured_canonical_epoch(conversation)
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
        if ("archive" not in kwargs and
                (not isinstance(kwargs.get("thread_id"), str)
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
            result = await method(self, *args, **kwargs)
            if configured_canonical_epoch(conversation) is not epoch:
                raise MongoSourceEpochError("canonical archive authority changed during mutation")
            return result

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
    if (configured_canonical_epoch(conversation) is not epoch
            or configured_canonical_epoch(memory) is not epoch):
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
    "configured_canonical_epoch", "bind_required_canonical_writers",
]
