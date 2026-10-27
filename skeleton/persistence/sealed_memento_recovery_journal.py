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
    state: str = "reserved"
    receipt_digest: str | None = None

    def __post_init__(self) -> None:
        for value in (self.binding_digest, self.grant_digest, self.candidate_commitment):
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
                or type(self.candidate_serial) is not int or self.candidate_serial < 1):
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
    )


def completed_record(previous: RecoveryJournalRecord, signed_receipt: bytes) -> RecoveryJournalRecord:
    if not isinstance(signed_receipt, bytes) or not signed_receipt:
        raise RecoveryJournalError("recovery completion must bind immutable receipt bytes")
    digest = hashlib.sha256(b"skeleton.memento.operator_receipt.v1\x00"
                            + signed_receipt).hexdigest()
    return replace(previous, state="completed", receipt_digest=digest)
