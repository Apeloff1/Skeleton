"""Operator-controlled, single-use journal for witnessed crash reconciliation.

The journal is a protocol, NOT an in-memory production authority. A deployment
must provide an independently administered linearizable durable store; it must
atomically reserve the exact (binding, incident) pair, disallow reuse for any
grant, and preserve records even if Mongo and the witness are restored.

A reserved, not-finalized incident is intentionally *not* automatically retried.
The operator diagnoses the indeterminate crash window independently.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
from typing import Protocol

from skeleton.context.sealed_sandwich import SealedContextBoundaryError


class RecoveryJournalError(SealedContextBoundaryError):
    """Recovery audit evidence cannot be trusted or durably committed."""


@dataclass(frozen=True, slots=True)
class RecoveryJournalRecord:
    """Bounded metadata receipt; no plaintext content or signing keys."""

    binding_digest: str
    incident_id: str
    grant_digest: str
    approvers: tuple[str, str]
    witness_revision: int
    candidate_serial: int
    candidate_commitment: str
    previous_commitment: str
    source_thread_version: int
    state: str = "reserved"
    receipt_digest: str | None = None

    def __post_init__(self) -> None:
        for value in (
            self.binding_digest, self.grant_digest, self.candidate_commitment,
            self.previous_commitment,
        ):
            if not isinstance(value, str) or len(value) != 64 or any(
                ch not in "0123456789abcdef" for ch in value
            ):
                raise RecoveryJournalError("malformed cryptographic recovery journal digest")
        if (not isinstance(self.incident_id, str) or not 1 <= len(self.incident_id) <= 128
                or self.incident_id != self.incident_id.strip()):
            raise RecoveryJournalError("malformed recovery journal incident")
        if (not isinstance(self.approvers, tuple) or len(self.approvers) != 2
                or any(not isinstance(v, str) or not 1 <= len(v) <= 128
                       for v in self.approvers) or self.approvers[0] >= self.approvers[1]):
            raise RecoveryJournalError("recovery journal approvers must be two distinct principals")
        if (type(self.witness_revision) is not int or self.witness_revision < 1
                or type(self.candidate_serial) is not int or self.candidate_serial < 1
                or type(self.source_thread_version) is not int or self.source_thread_version < 1):
            raise RecoveryJournalError("malformed recovery journal revision")
        if self.state not in {"reserved", "completed"}:
            raise RecoveryJournalError("unsupported recovery journal state")
        if self.state == "reserved" and self.receipt_digest is not None:
            raise RecoveryJournalError("reserved recovery has a false completion receipt")
        if self.state == "completed" and (
            not isinstance(self.receipt_digest, str)
            or len(self.receipt_digest) != 64
            or any(c not in "0123456789abcdef" for c in self.receipt_digest)
        ):
            raise RecoveryJournalError("completed recovery lacks receipt commitment")


class IndependentRecoveryJournal(Protocol):
    """External single-use, linearizable authorization and durable audit sink.

    reserve must reject an incident previously reserved under the same binding,
    EVEN if grant_digest differs. read and complete must use exact scoped IDs.
    complete is conditional on exactly the previously reserved record and must
    never permit receipt rewrite or reactivation.
    """

    async def reserve(self, *, record: RecoveryJournalRecord) -> bool: ...

    async def read(self, *, binding_digest: str, incident_id: str) -> RecoveryJournalRecord | None: ...

    async def complete(self, *, previous: RecoveryJournalRecord,
                       successor: RecoveryJournalRecord) -> bool: ...


def claim_record(grant: object, signer_ids: tuple[str, str]) -> RecoveryJournalRecord:
    """Hash the EXACT signed authorization; journal gets no private key material."""
    if not callable(getattr(grant, "signed_bytes", None)):
        raise RecoveryJournalError("signed recovery grant required")
    digest = hashlib.sha256(b"skeleton.memento.operator_journal.v1\x00"
                            + grant.signed_bytes()).hexdigest()
    return RecoveryJournalRecord(
        binding_digest=grant.binding_digest, incident_id=grant.incident_id,
        grant_digest=digest, approvers=tuple(sorted(signer_ids)),
        witness_revision=grant.witness_revision,
        candidate_serial=grant.candidate_head.serial,
        candidate_commitment=grant.candidate_head.commitment,
        previous_commitment=grant.witness_head.commitment,
        source_thread_version=grant.source_thread_version,
    )


def completed_record(previous: RecoveryJournalRecord, signed_receipt: bytes) -> RecoveryJournalRecord:
    if not isinstance(signed_receipt, bytes) or not signed_receipt:
        raise RecoveryJournalError("recovery completion must bind immutable receipt bytes")
    digest = hashlib.sha256(b"skeleton.memento.operator_receipt.v1\x00"
                            + signed_receipt).hexdigest()
    return replace(previous, state="completed", receipt_digest=digest)


@dataclass(frozen=True, slots=True)
class RecoveryIncidentInspection:
    """Non-privileged incident metadata; classification never authorizes repair."""

    incident_id: str
    classification: str
    journal_state: str
    witness_revision: int
    mongo_serial: int
    manual_intervention_required: bool


async def inspect_recovery_incident(
    *, archive: object, incident_id: str, mongo: object,
    witness: object, journal: IndependentRecoveryJournal,
) -> RecoveryIncidentInspection:
    """Classify an incomplete recovery without promoting any state.

    The separately durable journal and witness must be rechecked after a
    cryptographic one-frame suffix replay. The caller never supplies their
    own head, checkpoint or signing policy. No operations are auto-retried.
    """
    from skeleton.persistence.sealed_memento_witness import (
        MementoWitnessDivergence, MementoWitnessUnavailable,
        WitnessPosition, _binding_digest,
    )

    if not isinstance(incident_id, str) or not 1 <= len(incident_id) <= 128:
        raise RecoveryJournalError("invalid recovery incident query")
    scope = _binding_digest(archive)
    try:
        record = await journal.read(binding_digest=scope, incident_id=incident_id)
        pinned = await witness.read(binding_digest=scope)
        head = await mongo.trusted_head(archive=archive)
    except Exception as exc:
        raise RecoveryJournalError("independent recovery inspection unavailable") from exc
    if (not isinstance(record, RecoveryJournalRecord) or record.binding_digest != scope
            or record.incident_id != incident_id):
        raise RecoveryJournalError("recovery incident missing or outside authorized scope")
    if (not isinstance(pinned, WitnessPosition) or pinned.binding_digest != scope
            or pinned.retired):
        raise MementoWitnessUnavailable("witness missing or permanently retired")
    if (head.serial != record.candidate_serial
            or head.commitment != record.candidate_commitment):
        raise MementoWitnessDivergence("incident candidate is absent or changed in Mongo")
    if (pinned.revision == record.witness_revision
            and pinned.recovery_incident_id is None
            and pinned.head.serial == record.candidate_serial - 1
            and pinned.head.commitment == record.previous_commitment
            and record.state == "reserved"):
        state = "reserved_unwitnessed"
    elif (pinned.revision == record.witness_revision + 1
          and pinned.recovery_incident_id == incident_id
          and pinned.head == head):
        state = "completed_verified" if record.state == "completed" else "receipt_missing"
    else:
        raise MementoWitnessDivergence("incident witness/journal positions do not reconcile")
    try:
        page = await mongo.read_window(
            archive=archive, after_serial=record.candidate_serial - 1,
            limit=1,
        )
        if (page.starting_head.serial != record.candidate_serial - 1
                or page.starting_head.commitment != record.previous_commitment
                or page.verified_head != head or page.authoritative_head != head
                or page.source_thread_version != record.source_thread_version
                or len(page.records) != 1
                or page.records[0].serial != record.candidate_serial):
            raise MementoWitnessDivergence("incident ciphertext or source version mismatch")
        after_record = await journal.read(binding_digest=scope, incident_id=incident_id)
        after_witness = await witness.read(binding_digest=scope)
        after_head = await mongo.trusted_head(archive=archive)
    except MementoWitnessDivergence:
        raise
    except Exception as exc:
        raise RecoveryJournalError("recovery incident proof unavailable") from exc
    if (after_record != record or after_witness != pinned or after_head != head):
        raise MementoWitnessDivergence("recovery incident changed during inspection")
    return RecoveryIncidentInspection(
        incident_id, state, record.state, pinned.revision, head.serial,
        state != "completed_verified",
    )
