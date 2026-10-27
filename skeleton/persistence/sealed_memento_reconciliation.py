"""Two-operator, signed, one-step reconciliation of a witnessed Mongo crash gap.

This is NOT automatic recovery. Public verification keys are pinned by the
operator's independent policy authority, not supplied by callers or Mongo.
Private signing keys never enter this module. A signed grant authorizes exactly
one independently checked witness revision and an authenticated Mongo suffix.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import time
from typing import Any, Callable, Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from skeleton.context.sealed_memento import MementoCatalogHead, SealedMementoArchive
from skeleton.context.sealed_sandwich import SealedContextBoundaryError
from skeleton.persistence.sealed_memento_recovery import inspect_memento_recovery
from skeleton.persistence.sealed_memento_recovery_journal import (
    IndependentRecoveryJournal, RecoveryJournalError, claim_record, completed_record,
)
from skeleton.persistence.sealed_memento_witness import (
    IndependentMementoWitness,
    MementoWitnessDivergence,
    MementoWitnessIndeterminate,
    MementoWitnessUnavailable,
    WitnessPosition,
    _binding_digest,
)

_DOMAIN = b"skeleton.memento.operator_recovery.v1\x00"
_MAX_TTL = 900


class MementoRecoveryDenied(SealedContextBoundaryError):
    """A recovery cannot be admitted by signed, independently bound policy."""


@dataclass(frozen=True, slots=True)
class RecoveryGrant:
    """Exact incident/scope/position authorization; no plaintext or secret keys."""

    incident_id: str
    binding_digest: str
    witness_revision: int
    witness_head: MementoCatalogHead
    candidate_head: MementoCatalogHead
    source_thread_version: int
    issued_at: int
    expires_at: int

    def __post_init__(self) -> None:
        if (not isinstance(self.incident_id, str) or not 1 <= len(self.incident_id) <= 128
                or self.incident_id != self.incident_id.strip()):
            raise MementoRecoveryDenied("invalid recovery incident")
        if (not isinstance(self.binding_digest, str) or len(self.binding_digest) != 64
                or any(c not in "0123456789abcdef" for c in self.binding_digest)):
            raise MementoRecoveryDenied("invalid recovery scope digest")
        if not isinstance(self.witness_head, MementoCatalogHead) or not isinstance(
            self.candidate_head, MementoCatalogHead
        ):
            raise MementoRecoveryDenied("recovery heads are malformed")
        if self.candidate_head.serial != self.witness_head.serial + 1:
            raise MementoRecoveryDenied("recovery may reconcile only one verified successor")
        for name in ("witness_revision", "source_thread_version", "issued_at", "expires_at"):
            value = getattr(self, name)
            if type(value) is not int or value < 1:
                raise MementoRecoveryDenied("invalid recovery version or clock bound")
        if self.expires_at <= self.issued_at or self.expires_at - self.issued_at > _MAX_TTL:
            raise MementoRecoveryDenied("recovery grant lifespan is invalid")

    def signed_bytes(self) -> bytes:
        from skeleton.context.sealed_memento import encode_catalog_head

        body = {
            "incident_id": self.incident_id,
            "binding_digest": self.binding_digest,
            "witness_revision": self.witness_revision,
            "witness_head": encode_catalog_head(self.witness_head).decode("ascii"),
            "candidate_head": encode_catalog_head(self.candidate_head).decode("ascii"),
            "source_thread_version": self.source_thread_version,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
        }
        return _DOMAIN + json.dumps(
            body, sort_keys=True, separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")


@dataclass(frozen=True, slots=True)
class RecoverySignature:
    signer_id: str
    signature: bytes

    def __post_init__(self) -> None:
        if (not isinstance(self.signer_id, str) or not 1 <= len(self.signer_id) <= 128
                or self.signer_id != self.signer_id.strip()
                or not isinstance(self.signature, bytes) or len(self.signature) != 64):
            raise MementoRecoveryDenied("invalid recovery signer identity or signature")


@dataclass(frozen=True, slots=True)
class ReconciledWitnessReceipt:
    incident_id: str
    binding_digest: str
    previous_revision: int
    committed_revision: int
    committed_head: MementoCatalogHead
    source_thread_version: int


class SignedMementoReconciler:
    """Operator-only control; not exposed to model prompts or chat endpoints.

    Exactly two independently keyed Ed25519 approvals are required. A durable
    operational ledger must record the resulting receipt externally, and the
    signing principals must be provisioned by a distinct trusted control plane.
    """

    def __init__(
        self, *, public_keys: Mapping[str, bytes], journal: IndependentRecoveryJournal,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not isinstance(public_keys, Mapping) or len(public_keys) < 2:
            raise MementoRecoveryDenied("two trusted independent recovery keys required")
        self._keys: dict[str, Ed25519PublicKey] = {}
        seen: set[bytes] = set()
        for identity, raw in public_keys.items():
            if (not isinstance(identity, str) or not 1 <= len(identity) <= 128
                    or identity != identity.strip() or not isinstance(raw, bytes)
                    or len(raw) != 32 or raw in seen):
                raise MementoRecoveryDenied("operator keys must be uniquely provisioned")
            seen.add(raw)
            self._keys[identity] = Ed25519PublicKey.from_public_bytes(raw)
        if not all(callable(getattr(journal, name, None)) for name in (
            "reserve", "read", "complete"
        )):
            raise MementoRecoveryDenied("external recovery incident journal required")
        self._journal = journal
        if not callable(clock):
            raise MementoRecoveryDenied("trusted recovery clock required")
        self._clock = clock

    def _approve(self, grant: RecoveryGrant, signatures: tuple[RecoverySignature, ...]) -> None:
        now = int(self._clock())
        if not grant.issued_at <= now < grant.expires_at:
            raise MementoRecoveryDenied("recovery authorization is expired or not yet active")
        if (not isinstance(signatures, tuple) or len(signatures) != 2
                or len({item.signer_id for item in signatures}) != 2):
            raise MementoRecoveryDenied("two distinct operator signatures are mandatory")
        message = grant.signed_bytes()
        for item in signatures:
            key = self._keys.get(item.signer_id)
            if key is None:
                raise MementoRecoveryDenied("operator is not provisioned for recovery")
            try:
                key.verify(item.signature, message)
            except InvalidSignature as exc:
                raise MementoRecoveryDenied("operator recovery signature failed verification") from exc

    async def reconcile_one(
        self, *, archive: SealedMementoArchive, mongo: Any,
        witness: IndependentMementoWitness, grant: RecoveryGrant,
        signatures: tuple[RecoverySignature, ...],
    ) -> ReconciledWitnessReceipt:
        """Never repair a fork/rollback/tombstone, and never auto-advance heads."""
        if not isinstance(grant, RecoveryGrant) or grant.binding_digest != _binding_digest(archive):
            raise MementoRecoveryDenied("grant is not bound to the canonical archive")
        self._approve(grant, signatures)
        try:
            pinned = await witness.read(binding_digest=grant.binding_digest)
        except Exception as exc:
            raise MementoWitnessUnavailable("external witness unavailable for reconciliation") from exc
        if (not isinstance(pinned, WitnessPosition) or pinned.retired
                or pinned.binding_digest != grant.binding_digest
                or pinned.revision != grant.witness_revision
                or pinned.head != grant.witness_head):
            raise MementoWitnessDivergence("recovery witness changed or has been retired")
        inspection = await inspect_memento_recovery(
            archive=archive, mongo=mongo, witness=witness,
        )
        if (inspection.classification != "single_verified_unwitnessed_commit"
                or inspection.witness_revision != grant.witness_revision
                or inspection.witness_serial != grant.witness_head.serial
                or inspection.candidate_serial != grant.candidate_head.serial
                or inspection.source_thread_version != grant.source_thread_version):
            raise MementoRecoveryDenied("incident no longer matches a single authenticated successor")
        # The canonical conversation version can change without advancing the
        # archive head. Repeat suffix verification before the external CAS.
        recheck = await inspect_memento_recovery(
            archive=archive, mongo=mongo, witness=witness,
        )
        if recheck != inspection or await mongo.trusted_head(archive=archive) != grant.candidate_head:
            raise MementoWitnessDivergence("recovery source changed before authorization commit")
        # Repeat the human signature and clock checks before external mutation.
        self._approve(grant, signatures)
        claim = claim_record(grant, tuple(item.signer_id for item in signatures))
        try:
            reserved = await self._journal.reserve(record=claim)
            confirmed_claim = await self._journal.read(
                binding_digest=claim.binding_digest, incident_id=claim.incident_id,
            )
        except Exception as exc:
            raise RecoveryJournalError("durable recovery incident reservation unavailable") from exc
        if reserved is not True or confirmed_claim != claim:
            raise RecoveryJournalError("incident already consumed or reservation unconfirmed")
        # Reservation is permanent, even if a subsequent step fails. Never
        # replay an indeterminate incident or issue a second grant under its ID.
        successor = WitnessPosition(
            grant.binding_digest, pinned.revision + 1, grant.candidate_head,
        )
        try:
            accepted = await witness.compare_and_set(
                binding_digest=grant.binding_digest, previous=pinned,
                successor=successor,
            )
        except Exception as exc:
            raise MementoWitnessIndeterminate("recovery CAS acknowledgement unavailable") from exc
        if accepted is not True:
            raise MementoWitnessIndeterminate("recovery CAS not durably acknowledged")
        try:
            observed = await witness.read(binding_digest=grant.binding_digest)
            db_head = await mongo.trusted_head(archive=archive)
        except Exception as exc:
            raise MementoWitnessIndeterminate("recovery post-commit confirmation unavailable") from exc
        if observed != successor or db_head != grant.candidate_head:
            raise MementoWitnessIndeterminate("reconciled authority changed after witness CAS")
        receipt = ReconciledWitnessReceipt(
            grant.incident_id, grant.binding_digest, pinned.revision,
            successor.revision, successor.head, grant.source_thread_version,
        )
        from skeleton.context.sealed_memento import encode_catalog_head

        receipt_bytes = _DOMAIN + json.dumps({
            "incident": receipt.incident_id, "binding": receipt.binding_digest,
            "previous_revision": receipt.previous_revision,
            "committed_revision": receipt.committed_revision,
            "head": encode_catalog_head(receipt.committed_head).decode("ascii"),
            "source_thread_version": receipt.source_thread_version,
        }, sort_keys=True, separators=(",", ":")).encode("utf-8")
        completed = completed_record(claim, receipt_bytes)
        try:
            finalized = await self._journal.complete(previous=claim, successor=completed)
            confirmation = await self._journal.read(
                binding_digest=claim.binding_digest, incident_id=claim.incident_id,
            )
        except Exception as exc:
            raise MementoWitnessIndeterminate("recovery committed but journal completion unavailable") from exc
        if finalized is not True or confirmation != completed:
            raise MementoWitnessIndeterminate("recovery committed without durable final journal receipt")
        return receipt
