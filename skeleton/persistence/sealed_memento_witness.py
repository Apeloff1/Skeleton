"""Independent monotonic freshness boundary for encrypted conversation mementos.

This is a protocol and enforcement facade, NOT a witness database. Deployment
must supply an authenticated, durable, independently administered CAS service
whose state cannot be rolled back with Mongo/SQLite. In-memory and same-DB
implementations do not provide rollback resistance. Never auto-initialize a
missing witness from a client, model or restored conversation database.

Mongo's ciphertext+head transaction is authoritative for frame publication;
the external witness is authoritative for anti-rollback freshness/tombstones.
The two cannot atomically commit without distributed coordination: any crash
between commits leaves reads/writes unavailable until a separately authorized
recovery procedure reconciles durable evidence. No silent repair is performed.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Protocol

from skeleton.context.sealed_memento import MementoCatalogHead, SealedMementoArchive
from skeleton.context.sealed_sandwich import (
    SealedContextBoundaryError,
    SealedContextError,
    SealedContextReplayError,
)


class MementoWitnessUnavailable(SealedContextError):
    """Independent witness missing, malformed or unavailable; deny operation."""


class MementoWitnessDivergence(SealedContextReplayError):
    """Database and the independently held monotonic head disagree."""


class MementoWitnessIndeterminate(MementoWitnessUnavailable):
    """A Mongo commit may have succeeded without an acknowledged witness CAS."""


@dataclass(frozen=True, slots=True)
class WitnessPosition:
    """Externally stored monotonic position; not a self-authenticating signature."""

    binding_digest: str
    revision: int
    head: MementoCatalogHead
    retired: bool = False
    recovery_incident_id: str | None = None

    def __post_init__(self) -> None:
        if (not isinstance(self.binding_digest, str)
                or len(self.binding_digest) != 64
                or any(ch not in "0123456789abcdef" for ch in self.binding_digest)):
            raise MementoWitnessUnavailable("invalid independent witness scope digest")
        if type(self.revision) is not int or not 1 <= self.revision < 2**63:
            raise MementoWitnessUnavailable("invalid monotonic witness revision")
        if not isinstance(self.head, MementoCatalogHead) or type(self.retired) is not bool:
            raise MementoWitnessUnavailable("malformed witnessed archive state")
        if self.recovery_incident_id is not None and (
            not isinstance(self.recovery_incident_id, str)
            or not 1 <= len(self.recovery_incident_id) <= 128
            or self.recovery_incident_id != self.recovery_incident_id.strip()
            or any(ord(ch) < 32 or ord(ch) == 127 for ch in self.recovery_incident_id)
        ):
            raise MementoWitnessUnavailable("invalid witnessed recovery incident identity")


class IndependentMementoWitness(Protocol):
    """Required trust contract of an external durability/monotonic CAS provider.

    read and compare_and_set MUST be linearizable and authorization-bound to
    their exact binding_digest. compare_and_set MUST reject decreases, replay,
    revisions that skip or fork, and reactivation of a retirement tombstone.
    Clients MUST NOT possess authority to provision or reset records.
    """

    async def read(self, *, binding_digest: str) -> WitnessPosition | None: ...

    async def compare_and_set(
        self, *, binding_digest: str, previous: WitnessPosition,
        successor: WitnessPosition,
    ) -> bool: ...


def _binding_digest(archive: SealedMementoArchive) -> str:
    if not isinstance(archive, SealedMementoArchive):
        raise SealedContextBoundaryError("authorized encrypted archive binding required")
    b = archive.binding
    identity = json.dumps(
        [b.tenant_id, b.owner_id, b.conversation_id, b.model_id, b.policy_id],
        separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(b"skeleton.memento.binding.v1\x00" + identity).hexdigest()


class WitnessedMongoMementoAuthority:
    """Fail-closed facade over the canonical transactional Mongo memento owner.

    Caller must use this facade for all protected publish/read and retire paths;
    raw MongoMementoAuthority remains an internal transaction primitive.
    The witness is NOT provisioned or controlled here.
    """

    def __init__(
        self, mongo: Any, *, witness: IndependentMementoWitness,
        recovery_journal: Any | None = None,
    ) -> None:
        required = ("trusted_head", "publish", "read_window", "retire_thread")
        if not all(callable(getattr(mongo, name, None)) for name in required):
            raise TypeError("canonical transactional Mongo memento adapter required")
        if not all(callable(getattr(witness, name, None)) for name in (
            "read", "compare_and_set"
        )):
            raise TypeError("independent monotonic witness provider required")
        if recovery_journal is not None and not callable(getattr(recovery_journal, "read", None)):
            raise TypeError("independent recovery journal reader required")
        self.mongo = mongo
        self.witness = witness
        self.recovery_journal = recovery_journal

    async def _position(self, archive: SealedMementoArchive) -> WitnessPosition:
        scope = _binding_digest(archive)
        try:
            position = await self.witness.read(binding_digest=scope)
        except Exception as exc:
            raise MementoWitnessUnavailable("independent witness read failed") from exc
        if not isinstance(position, WitnessPosition) or position.binding_digest != scope:
            raise MementoWitnessUnavailable("authorized witness position not provisioned")
        if position.retired:
            raise SealedContextBoundaryError("encrypted conversation has a permanent retirement fence")
        # A recovery CAS can precede its journal acknowledgement. Without
        # this independent completion check, the witness and Mongo would agree
        # while an unfinalized recovery incident could leak plaintext.
        if position.recovery_incident_id is not None:
            if self.recovery_journal is None:
                raise MementoWitnessIndeterminate(
                    "witnessed recovery requires an independently finalized incident"
                )
            try:
                from skeleton.persistence.sealed_memento_recovery_journal import (
                    RecoveryJournalRecord,
                )

                record = await self.recovery_journal.read(
                    binding_digest=scope, incident_id=position.recovery_incident_id,
                )
            except Exception as exc:
                raise MementoWitnessIndeterminate(
                    "recovery journal completion could not be confirmed"
                ) from exc
            if (not isinstance(record, RecoveryJournalRecord)
                    or record.state != "completed"
                    or record.binding_digest != scope
                    or record.incident_id != position.recovery_incident_id
                    or record.witness_revision + 1 != position.revision
                    or record.candidate_serial != position.head.serial
                    or record.candidate_commitment != position.head.commitment):
                raise MementoWitnessIndeterminate(
                    "external recovery incident is unfinished or mismatched"
                )
        return position

    async def _consistent(self, archive: SealedMementoArchive) -> WitnessPosition:
        witness = await self._position(archive)
        try:
            db_head = await self.mongo.trusted_head(archive=archive)
        except Exception as exc:
            raise MementoWitnessUnavailable("canonical head read failed") from exc
        if db_head != witness.head:
            raise MementoWitnessDivergence("database head differs from external monotonic witness")
        return witness

    async def trusted_head(self, *, archive: SealedMementoArchive) -> MementoCatalogHead:
        """Admit a head only after matching independent monotonic authority."""
        before = await self._consistent(archive)
        after = await self._position(archive)
        if before != after:
            raise MementoWitnessDivergence("external head changed during admission")
        return before.head

    async def publish(
        self, *, archive: SealedMementoArchive, expected_head: MementoCatalogHead,
        expected_thread_version: int, stream: str, ciphertext: bytes,
    ) -> MementoCatalogHead:
        position = await self._consistent(archive)
        if position.head != expected_head:
            raise MementoWitnessDivergence("caller has stale independently witnessed head")
        # Mongo publishes the frame and its head in one majority transaction.
        # From here an exception may leave Mongo ahead of the witness. Do not
        # claim rollback, success or automatically force the external witness.
        result = await self.mongo.publish(
            archive=archive, expected_head=expected_head,
            expected_thread_version=expected_thread_version,
            stream=stream, ciphertext=ciphertext,
        )
        if not isinstance(result, MementoCatalogHead) or result.serial != position.head.serial + 1:
            raise MementoWitnessIndeterminate("published head has unexpected global serial")
        successor = WitnessPosition(position.binding_digest, position.revision + 1, result)
        try:
            accepted = await self.witness.compare_and_set(
                binding_digest=position.binding_digest, previous=position,
                successor=successor,
            )
        except Exception as exc:
            raise MementoWitnessIndeterminate(
                "external witness acknowledgement unavailable after Mongo commit"
            ) from exc
        if accepted is not True:
            raise MementoWitnessIndeterminate(
                "external head CAS did not acknowledge Mongo publication"
            )
        # Prevent a false success if a purported CAS witness lies or regresses.
        confirmed = await self._position(archive)
        if confirmed != successor:
            raise MementoWitnessIndeterminate("external witness post-commit head changed")
        return result

    async def read_window(self, *, archive: SealedMementoArchive, **options: Any) -> Any:
        before = await self._consistent(archive)
        page = await self.mongo.read_window(archive=archive, **options)
        if page.authoritative_head != before.head:
            raise MementoWitnessDivergence("replayed page disagrees with pinned external head")
        after = await self._consistent(archive)
        if after != before:
            raise MementoWitnessDivergence("external head changed during archive recovery")
        return page

    async def retire_thread(self, *, archive: SealedMementoArchive) -> int:
        """Witness tombstone FIRST, then owner-backed deletion and physical purge.

        A failure to purge leaves a permanent witness tombstone and requires
        operator intervention. Never resurrect the witness from Mongo state.
        """
        position = await self._consistent(archive)
        successor = WitnessPosition(
            position.binding_digest, position.revision + 1, position.head, retired=True,
        )
        try:
            accepted = await self.witness.compare_and_set(
                binding_digest=position.binding_digest, previous=position,
                successor=successor,
            )
        except Exception as exc:
            raise MementoWitnessUnavailable("retirement witness acknowledgement unavailable") from exc
        if accepted is not True:
            raise MementoWitnessUnavailable("retirement witness CAS not acknowledged")
        try:
            confirmation = await self.witness.read(binding_digest=position.binding_digest)
        except Exception as exc:
            raise MementoWitnessIndeterminate("retirement witness confirmation unavailable") from exc
        if confirmation != successor:
            raise MementoWitnessIndeterminate("retirement tombstone not externally confirmed")
        try:
            return await self.mongo.retire_thread(
                tenant_id=archive.binding.tenant_id,
                owner_id=archive.binding.owner_id,
                thread_id=archive.binding.conversation_id,
            )
        except Exception as exc:
            raise MementoWitnessIndeterminate("retirement tombstoned; Mongo purge unfinished") from exc

    async def retire_bound_thread(
        self, *, tenant_id: str, owner_id: str, thread_id: str,
        binding_digest: str,
    ) -> int:
        """Canonical governance deletion using a previously authorized stored binding.

        The existing conversation authority supplies the binding digest from
        its own thread document, not from a user request. No decrypting keys
        are required to tombstone an archive during GDPR/retention deletion.
        Retrying a physical purge after an acknowledged tombstone is safe.
        """
        if any(not isinstance(v, str) or not v or len(v) > 256 for v in (
            tenant_id, owner_id, thread_id,
        )):
            raise SealedContextBoundaryError("invalid governed archive deletion scope")
        if (not isinstance(binding_digest, str) or len(binding_digest) != 64
                or any(c not in "0123456789abcdef" for c in binding_digest)):
            raise SealedContextBoundaryError("invalid stored archive binding")
        conversation = getattr(self.mongo, "conversation", None)
        threads = getattr(conversation, "threads", None)
        if not callable(getattr(threads, "find_one", None)):
            raise MementoWitnessUnavailable("canonical governed deletion reader unavailable")
        try:
            doc = await threads.find_one({
                "_id": thread_id, "tenant_id": tenant_id, "owner_id": owner_id,
            })
        except Exception as exc:
            raise MementoWitnessUnavailable("governed deletion lookup unavailable") from exc
        if (not isinstance(doc, dict) or doc.get("_sealed_memento_binding") != binding_digest
                or "_sealed_memento_head" not in doc):
            raise SealedContextBoundaryError("canonical archive binding is missing or inconsistent")
        from skeleton.context.sealed_memento import decode_catalog_head

        expected_head = decode_catalog_head(bytes(doc["_sealed_memento_head"]))
        try:
            position = await self.witness.read(binding_digest=binding_digest)
        except Exception as exc:
            raise MementoWitnessUnavailable("governed deletion witness unavailable") from exc
        if not isinstance(position, WitnessPosition) or position.binding_digest != binding_digest:
            raise MementoWitnessUnavailable("governed deletion witness not provisioned")
        # An already committed tombstone is irreversible. A publication
        # racing with the original tombstone may have changed Mongo's head;
        # rejecting its physical purge would retain erased-user ciphertext.
        # On first retirement, however, a stale Mongo head is still denied.
        if expected_head != position.head and not position.retired:
            raise MementoWitnessDivergence("stored archive is inconsistent with deletion witness")
        if not position.retired:
            successor = WitnessPosition(
                binding_digest, position.revision + 1, position.head, retired=True,
            )
            try:
                accepted = await self.witness.compare_and_set(
                    binding_digest=binding_digest, previous=position, successor=successor,
                )
            except Exception as exc:
                raise MementoWitnessUnavailable("governed deletion tombstone unavailable") from exc
            if accepted is not True:
                raise MementoWitnessUnavailable("governed deletion tombstone rejected")
        else:
            successor = position
        try:
            confirmed = await self.witness.read(binding_digest=binding_digest)
        except Exception as exc:
            raise MementoWitnessIndeterminate("deletion tombstone recheck unavailable") from exc
        if confirmed != successor:
            raise MementoWitnessIndeterminate("external deletion tombstone not confirmed")
        try:
            return await self.mongo.retire_thread(
                tenant_id=tenant_id, owner_id=owner_id, thread_id=thread_id,
            )
        except Exception as exc:
            raise MementoWitnessIndeterminate("deletion tombstoned, physical purge incomplete") from exc
