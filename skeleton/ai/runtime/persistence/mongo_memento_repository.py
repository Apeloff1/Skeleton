"""Mongo transactional sidecar for cryptographic mementos.

Only the existing MongoConversationAuthority owns conversation state. This
adapter stores derivative ciphertext in the same Mongo database and commits its
pointer/head on the authoritative conversation thread in one majority-durable
transaction. Standalone Mongo without multi-document transactions FAILS CLOSED.

Provisioning, retention/deletion fencing and application routing must be wired
by the canonical backend before production activation.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any

from skeleton.context.sealed_memento import (
    ARCHIVE_WINDOW_MESSAGES,
    MementoCatalogHead,
    MementoRecord,
    SealedMementoArchive,
    decode_catalog_head,
    encode_catalog_head,
)
from skeleton.context.sealed_sandwich import (
    SealedContextBoundaryError,
    SealedContextError,
    SealedContextLimitError,
    SealedContextReplayError,
)

from skeleton.persistence.mongo_source_epoch import fence_memento_write

_MAX_READ_BYTES = 16 * 1024 * 1024
_HEAD_FIELD = "_sealed_memento_head"
_BINDING_FIELD = "_sealed_memento_binding"
_RETIRED_FIELD = "_sealed_memento_retired"
_CUSTODY_FIELD = "_sealed_memento_custody"


class MongoMementoConflict(SealedContextReplayError):
    """A write or read violated the independently pinned authority state."""


class MongoMementoUnavailable(SealedContextError):
    """Transactionality, crypto or majority durability could not be verified."""


@dataclass(frozen=True, slots=True)
class MongoMementoPage:
    records: tuple[MementoRecord, ...]
    starting_head: MementoCatalogHead
    verified_head: MementoCatalogHead
    authoritative_head: MementoCatalogHead
    source_thread_version: int

    @property
    def has_more(self) -> bool:
        return self.verified_head.serial < self.authoritative_head.serial


def _binding_digest(archive: SealedMementoArchive) -> str:
    b = archive.binding
    payload = json.dumps(
        [b.tenant_id, b.owner_id, b.conversation_id, b.model_id, b.policy_id],
        ensure_ascii=False, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(b"skeleton.memento.binding.v1\x00" + payload).hexdigest()


def _authorized_filter(archive: SealedMementoArchive) -> dict[str, str]:
    b = archive.binding
    return {"_id": b.conversation_id, "tenant_id": b.tenant_id, "owner_id": b.owner_id}


def _current(doc: dict[str, Any], archive: SealedMementoArchive) -> MementoCatalogHead:
    if doc.get(_RETIRED_FIELD):
        raise SealedContextBoundaryError("memento archive retired by canonical deletion")
    if _HEAD_FIELD not in doc:
        if _BINDING_FIELD in doc:
            raise MongoMementoConflict("incomplete memento head metadata")
        return MementoCatalogHead()
    if doc.get(_BINDING_FIELD) != _binding_digest(archive):
        raise SealedContextBoundaryError("memento owner/model/policy binding changed")
    return decode_catalog_head(bytes(doc[_HEAD_FIELD]))


def memento_retirement_requires_witness(thread: dict[str, Any], *, witness_present: bool) -> bool:
    """Do not downgrade an unknown or witnessed archive during deletion.

    Earlier unmarked archives require explicit, authorized custody migration.
    """
    mode = thread.get(_CUSTODY_FIELD)
    if mode not in ("legacy", "witnessed"):
        raise MongoMementoUnavailable("sealed archive custody is missing or invalid")
    if mode == "witnessed" and not witness_present:
        raise MongoMementoUnavailable("witnessed archive requires independent retirement authority")
    return mode == "witnessed"


class MongoMementoAuthority:
    """Strictly transactional derived archive sharing the canonical Mongo owner.

    The canonical MongoConversationAuthority is injected; consumers must not
    construct their own database handle, transaction store or client head.
    """

    def __init__(self, conversation: Any) -> None:
        if not all(hasattr(conversation, name) for name in (
            "database", "threads", "get_thread", "_admit_storage"
        )):
            raise TypeError("canonical MongoConversationAuthority required")
        self.conversation = conversation
        self.frames = conversation.database["conversation_memento_frames"]

    async def ensure_indexes(self) -> None:
        """Canonical bootstrap must call this before allowing writes."""
        try:
            await self.frames.create_index(
                [("thread_id", 1), ("global_serial", 1)],
                unique=True, name="memento_thread_serial_unique",
            )
            await self.frames.create_index(
                [("tenant_id", 1), ("thread_id", 1)],
                name="memento_tenant_thread_deletion",
            )
        except Exception as exc:
            raise MongoMementoUnavailable("memento indexes could not be established") from exc

    async def _start(self) -> Any:
        """Require snapshot isolation plus majority write concern; never fallback."""
        try:
            from pymongo.read_concern import ReadConcern
            from pymongo.write_concern import WriteConcern
            session = await self.conversation.database.client.start_session()
            return session, {"read_concern": ReadConcern("snapshot"),
                             "write_concern": WriteConcern(w="majority")}
        except Exception as exc:
            raise MongoMementoUnavailable("majority Mongo sessions unavailable") from exc

    async def _thread(self, archive: SealedMementoArchive, session: Any) -> dict[str, Any]:
        doc = await self.conversation.threads.find_one(
            _authorized_filter(archive), session=session,
        )
        if doc is None:
            raise SealedContextBoundaryError("conversation authority denied archive access")
        return doc

    async def trusted_head(self, *, archive: SealedMementoArchive) -> MementoCatalogHead:
        """Read the independently persisted thread head with owner authorization."""
        if not isinstance(archive, SealedMementoArchive):
            raise SealedContextError("cryptographic archive binding required")
        try:
            thread = await self.conversation.threads.find_one(_authorized_filter(archive))
            if thread is None:
                raise SealedContextBoundaryError("conversation authority denied archive access")
            return _current(thread, archive)
        except SealedContextError:
            raise
        except Exception as exc:
            raise MongoMementoUnavailable("authoritative memento head unavailable") from exc

    @fence_memento_write
    async def publish(
        self, *, archive: SealedMementoArchive, expected_head: MementoCatalogHead,
        expected_thread_version: int, stream: str, ciphertext: bytes,
        custody_mode: str = "legacy",
    ) -> MementoCatalogHead:
        """Atomic ciphertext and thread-CAS; no partial availability is success."""
        if not isinstance(archive, SealedMementoArchive) or not isinstance(
            expected_head, MementoCatalogHead
        ) or type(expected_thread_version) is not int or expected_thread_version < 1:
            raise SealedContextError("invalid CAS publication authority")
        if custody_mode not in ("legacy", "witnessed"):
            raise SealedContextBoundaryError("invalid archival custody mode")
        if custody_mode == "legacy" and getattr(self.conversation, "memento_witness", None) is not None:
            raise SealedContextBoundaryError("witness-enabled conversation cannot publish legacy custody")
        if not isinstance(ciphertext, bytes) or len(ciphertext) > 4 * 1024 * 1024:
            raise SealedContextLimitError("invalid encrypted memento envelope size")
        # Decode/authenticate before storage admission, and repeat against the
        # in-transaction head so a stale candidate never commits.
        record, next_head = archive.verify_append(stream, ciphertext, previous=expected_head)
        b = archive.binding
        await self.conversation._admit_storage(
            tenant_id=b.tenant_id, resource_id="conversation-memento",
            write_id=f"memento:{b.conversation_id}:{record.serial}:{next_head.commitment}",
            payload={"thread_id": b.conversation_id, "ciphertext_bytes": len(ciphertext),
                     "global_serial": record.serial, "stream": stream},
        )
        session, options = await self._start()
        try:
            async with session:
                async with session.start_transaction(**options):
                    doc = await self._thread(archive, session)
                    if doc.get("version") != expected_thread_version:
                        raise MongoMementoConflict("canonical conversation version changed")
                    if doc.get("state") != "active":
                        raise SealedContextBoundaryError("canonical conversation is not active")
                    previous = _current(doc, archive)
                    if previous != expected_head:
                        raise MongoMementoConflict("stale memento catalog head")
                    current_custody = doc.get(_CUSTODY_FIELD)
                    if current_custody not in (None, "legacy", "witnessed"):
                        raise MongoMementoConflict("invalid canonical archive custody")
                    if current_custody is not None and current_custody != custody_mode:
                        raise MongoMementoConflict("archive custody cannot change during publication")
                    if previous.serial and current_custody is None and custody_mode != "legacy":
                        raise MongoMementoConflict("unmarked archive needs explicit custody migration")
                    if record.causal_serial is not None:
                        predecessor = await self.frames.find_one({
                            "thread_id": b.conversation_id,
                            "tenant_id": b.tenant_id,
                            "global_serial": record.causal_serial,
                        }, session=session)
                        if predecessor is None:
                            raise MongoMementoConflict("causal predecessor was not committed")
                    await self.frames.insert_one({
                        "_id": f"{b.conversation_id}:{record.serial}",
                        "tenant_id": b.tenant_id,
                        "owner_id": b.owner_id,
                        "thread_id": b.conversation_id,
                        "global_serial": record.serial,
                        "stream": stream,
                        "ciphertext": ciphertext,
                        "head_blob": encode_catalog_head(next_head),
                    }, session=session)
                    predicate: dict[str, Any] = {
                        **_authorized_filter(archive),
                        "version": expected_thread_version,
                        "state": "active",
                        _RETIRED_FIELD: {"$ne": True},
                    }
                    if previous.serial:
                        predicate[_HEAD_FIELD] = encode_catalog_head(previous)
                        predicate[_BINDING_FIELD] = _binding_digest(archive)
                        predicate[_CUSTODY_FIELD] = (
                            {"$exists": False} if current_custody is None else custody_mode
                        )
                    else:
                        predicate[_HEAD_FIELD] = {"$exists": False}
                        predicate[_BINDING_FIELD] = {"$exists": False}
                        predicate[_CUSTODY_FIELD] = {"$exists": False}
                    updated = await self.conversation.threads.update_one(
                        predicate,
                        {"$set": {_HEAD_FIELD: encode_catalog_head(next_head),
                                  _BINDING_FIELD: _binding_digest(archive),
                                  _CUSTODY_FIELD: custody_mode}},
                        session=session,
                    )
                    if updated.modified_count != 1:
                        raise MongoMementoConflict("trusted thread CAS failed")
            return next_head
        except (MongoMementoConflict, SealedContextError):
            raise
        except Exception as exc:
            raise MongoMementoUnavailable("memento transaction not durably committed") from exc

    async def read_window(
        self, *, archive: SealedMementoArchive, after_serial: int = 0,
        limit: int = ARCHIVE_WINDOW_MESSAGES,
        expected_starting_head: MementoCatalogHead | None = None,
    ) -> MongoMementoPage:
        """Snapshot-isolated authenticated page, including pinned final head."""
        if type(after_serial) is not int or after_serial < 0 or (
            type(limit) is not int or not 1 <= limit <= ARCHIVE_WINDOW_MESSAGES
        ):
            raise SealedContextLimitError("invalid bounded archive cursor")
        if expected_starting_head is not None and (
            not isinstance(expected_starting_head, MementoCatalogHead)
            or expected_starting_head.serial != after_serial
        ):
            raise MongoMementoConflict("caller-pinned archive cursor is invalid")
        session, options = await self._start()
        b = archive.binding
        try:
            async with session:
                async with session.start_transaction(**options):
                    thread = await self._thread(archive, session)
                    trusted = _current(thread, archive)
                    if after_serial > trusted.serial:
                        raise MongoMementoConflict("cursor exceeds authoritative head")
                    if after_serial:
                        cursor_doc = await self.frames.find_one({
                            "thread_id": b.conversation_id, "tenant_id": b.tenant_id,
                            "owner_id": b.owner_id, "global_serial": after_serial,
                        }, session=session)
                        if cursor_doc is None:
                            raise MongoMementoConflict("authenticated cursor frame unavailable")
                        starting = decode_catalog_head(bytes(cursor_doc["head_blob"]))
                        if starting.serial != after_serial:
                            raise MongoMementoConflict("invalid cursor checkpoint")
                    else:
                        starting = MementoCatalogHead()
                    if expected_starting_head is not None and starting != expected_starting_head:
                        raise MongoMementoConflict("archive cursor disagrees with verified prior page")
                    rows = await (self.frames.find({
                        "thread_id": b.conversation_id, "tenant_id": b.tenant_id,
                        "owner_id": b.owner_id,
                        "global_serial": {"$gt": after_serial, "$lte": trusted.serial},
                    }, session=session).sort("global_serial", 1).limit(limit).to_list(length=limit))
                    if sum(len(row["ciphertext"]) for row in rows) > _MAX_READ_BYTES:
                        raise SealedContextLimitError("encrypted archive read exceeds 16 MiB")
                    for serial, row in enumerate(rows, start=after_serial + 1):
                        if row["global_serial"] != serial:
                            raise MongoMementoConflict("archive serial missing from snapshot")
                    ending = (decode_catalog_head(bytes(rows[-1]["head_blob"]))
                              if rows else starting)
                    if not rows and starting != trusted:
                        raise MongoMementoConflict("authoritative archive tail is missing")
                    records = archive.replay(
                        ((row["stream"], bytes(row["ciphertext"])) for row in rows),
                        starting_head=starting, trusted_head=ending, max_messages=limit,
                    ) if rows else ()
                    if ending.serial > trusted.serial or (
                        ending.serial == trusted.serial and ending != trusted
                    ):
                        raise MongoMementoConflict("archive tail disagrees with trusted head")
                    return MongoMementoPage(
                        records, starting, ending, trusted, int(thread["version"]),
                    )
        except (MongoMementoConflict, SealedContextError):
            raise
        except Exception as exc:
            raise MongoMementoUnavailable("snapshot archive read failed closed") from exc

    @fence_memento_write
    async def retire_thread(
        self, *, tenant_id: str, owner_id: str, thread_id: str,
    ) -> int:
        """Fence all future appends, then erase ciphertext for governed deletion.

        The owning deletion workflow invokes this *before* deleting a thread or
        any message. A failed purge remains retryable and never un-retires the
        head. Thread CAS conflicts abort in-flight publication transactions.
        """
        if not all(isinstance(value, str) and value for value in (
            tenant_id, owner_id, thread_id
        )):
            raise SealedContextBoundaryError("memento deletion scope missing")
        scoped = {"_id": thread_id, "tenant_id": tenant_id, "owner_id": owner_id}
        try:
            from pymongo.write_concern import WriteConcern
            majority = WriteConcern(w="majority")
            threads = self.conversation.threads.with_options(write_concern=majority)
            frames = self.frames.with_options(write_concern=majority)
            doc = await threads.find_one(scoped)
            if doc is None:
                raise SealedContextBoundaryError("conversation deletion scope unauthorized")
            if _HEAD_FIELD in doc or _CUSTODY_FIELD in doc:
                witness = getattr(self.conversation, "memento_witness", None)
                witnessed = memento_retirement_requires_witness(
                    doc, witness_present=callable(getattr(witness, "read", None)),
                )
                if witnessed:
                    # The tombstone must already be externally durable. A
                    # Mongo-only deletion is never a substitute for witnessed
                    # retirement, even if the caller bypasses the facade.
                    from skeleton.persistence.sealed_memento_witness import WitnessPosition

                    binding = doc.get(_BINDING_FIELD)
                    if (not isinstance(binding, str) or len(binding) != 64
                            or any(ch not in "0123456789abcdef" for ch in binding)):
                        raise MongoMementoUnavailable("witnessed retirement binding unavailable")
                    try:
                        position = await witness.read(binding_digest=binding)
                    except Exception as exc:
                        raise MongoMementoUnavailable("independent retirement witness unavailable") from exc
                    if (not isinstance(position, WitnessPosition)
                            or position.binding_digest != binding or not position.retired):
                        raise MongoMementoUnavailable(
                            "independent retirement tombstone not acknowledged"
                        )
            result = await threads.update_one(
                scoped, {"$set": {_RETIRED_FIELD: True}},
            )
            if result.matched_count != 1:
                raise MongoMementoConflict("deletion fence was not applied")
            removed = await frames.delete_many({
                "tenant_id": tenant_id, "owner_id": owner_id, "thread_id": thread_id,
            })
            remaining = await frames.find_one({
                "tenant_id": tenant_id, "owner_id": owner_id, "thread_id": thread_id,
            })
            if remaining is not None:
                raise MongoMementoUnavailable("memento ciphertext deletion is incomplete")
            return int(removed.deleted_count)
        except (SealedContextError, MongoMementoConflict):
            raise
        except Exception as exc:
            raise MongoMementoUnavailable("memento deletion fence or purge failed") from exc
