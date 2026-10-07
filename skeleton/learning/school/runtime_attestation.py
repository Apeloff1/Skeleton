"""Deterministic attestation chain for Jeeves runtime provenance."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import importlib
import json

from skeleton.learning.school.decision_ledger import (
    DecisionDisposition,
    DecisionLedger,
)
from skeleton.learning.school.runtime_capsule import (
    RuntimeIntegrityCapsule,
)
from skeleton.learning.school.runtime_replay import (
    RuntimeReplaySnapshot,
    audit_runtime,
    replay_digest,
)
from skeleton.learning.school.session_audit import (
    audit_session,
)


def _trusted_twin_instance(
    value: object,
    canonical_type: type[object],
    *,
    twin_module: str,
    twin_name: str,
) -> bool:
    """Accept only a canonical runtime type or its governed AI-tree twin."""

    if isinstance(value, canonical_type):
        return True
    try:
        module = importlib.import_module(twin_module)
        twin_type = getattr(module, twin_name)
    except (ImportError, AttributeError):
        return False
    return isinstance(twin_type, type) and isinstance(value, twin_type)


def _is_decision_ledger(value: object) -> bool:
    return _trusted_twin_instance(
        value,
        DecisionLedger,
        twin_module="skeleton.ai.learning.school.decision_ledger",
        twin_name="DecisionLedger",
    )


def _is_runtime_snapshot(value: object) -> bool:
    return _trusted_twin_instance(
        value,
        RuntimeReplaySnapshot,
        twin_module="skeleton.ai.learning.school.runtime_replay",
        twin_name="RuntimeReplaySnapshot",
    )


def _is_runtime_attestation(value: object) -> bool:
    return _trusted_twin_instance(
        value,
        RuntimeAttestation,
        twin_module="skeleton.ai.learning.school.runtime_attestation",
        twin_name="RuntimeAttestation",
    )


def _digest(payload: object) -> str:
    try:
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "runtime attestation payload is not deterministic JSON"
        ) from exc
    return hashlib.sha256(
        encoded.encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class RuntimeAttestation:
    session_id: str
    runtime_digest: str
    replay_digest: str
    capsule_digest: str
    session_audit_digest: str
    ledger_head: str
    ledger_count: int
    session_root_decision_id: str
    selected_policy_decision_id: str | None
    accepted_decision_ids: tuple[str, ...]
    rejected_decision_ids: tuple[str, ...]
    session_record_hashes: tuple[str, ...]
    attestation_digest: str
    evidence_root: str = ""
    ledger_identity: str = ""
    checkpoint_digest: str = ""

    @classmethod
    def capture(
        cls,
        snapshot: RuntimeReplaySnapshot,
        ledger: DecisionLedger,
    ) -> "RuntimeAttestation":
        if not _is_runtime_snapshot(snapshot):
            raise TypeError(
                "snapshot must be trusted RuntimeReplaySnapshot"
            )
        if not _is_decision_ledger(ledger):
            raise TypeError("ledger must be trusted DecisionLedger")

        runtime_audit = audit_runtime(snapshot, ledger)
        session_audit = audit_session(
            ledger,
            snapshot.session_id,
        )
        if not runtime_audit.valid:
            raise ValueError(
                "cannot attest an invalid runtime snapshot"
            )
        if not session_audit.valid:
            raise ValueError(
                "cannot attest an invalid session audit"
            )

        capsule = RuntimeIntegrityCapsule.capture(
            snapshot,
            ledger,
        )
        capsule_audit = capsule.verify(ledger)
        if not capsule_audit.valid:
            raise ValueError(
                "cannot attest an invalid integrity capsule"
            )

        records = ledger.session(snapshot.session_id)
        if not records:
            raise ValueError("cannot attest an empty session")
        roots = tuple(
            record
            for record in records
            if not record.predecessors
        )
        if len(roots) != 1:
            raise ValueError(
                "session must have exactly one causal root"
            )
        root = roots[0]

        accepted = tuple(
            record.decision_id
            for record in records
            if record.disposition
            == DecisionDisposition.ACCEPTED
        )
        rejected = tuple(
            record.decision_id
            for record in records
            if record.disposition
            == DecisionDisposition.REJECTED
        )
        record_hashes = tuple(
            record.record_hash
            for record in records
        )
        selected = (
            snapshot.selected_policy_decision_id
            or None
        )
        if selected is not None:
            selected_record = next(
                (
                    record
                    for record in records
                    if record.decision_id == selected
                ),
                None,
            )
            if (
                selected_record is None
                or selected_record.disposition
                != DecisionDisposition.ACCEPTED
            ):
                raise ValueError(
                    "selected policy decision is not an accepted session record"
                )
            if selected_record.action != snapshot.selected_policy:
                raise ValueError(
                    "selected policy decision does not match selected policy"
                )

        checkpoint = ledger.checkpoint()
        payload = {
            "schema_version": "skeleton.runtime_attestation.v2",
            "session_id": snapshot.session_id,
            "runtime_digest": snapshot.runtime_digest,
            "replay_digest": replay_digest(snapshot),
            "capsule_digest": capsule.capsule_digest,
            "session_audit_digest": session_audit.digest,
            "ledger_head": ledger.head_hash,
            "ledger_count": len(ledger.records),
            "evidence_root": ledger.evidence_root,
            "ledger_identity": ledger.ledger_identity,
            "checkpoint_digest": checkpoint.digest,
            "session_root_decision_id": root.decision_id,
            "selected_policy_decision_id": selected,
            "accepted_decision_ids": list(accepted),
            "rejected_decision_ids": list(rejected),
            "session_record_hashes": list(record_hashes),
        }
        return cls(
            session_id=snapshot.session_id,
            runtime_digest=snapshot.runtime_digest,
            replay_digest=payload["replay_digest"],
            capsule_digest=capsule.capsule_digest,
            session_audit_digest=session_audit.digest,
            ledger_head=ledger.head_hash,
            ledger_count=len(ledger.records),
            session_root_decision_id=root.decision_id,
            selected_policy_decision_id=selected,
            accepted_decision_ids=accepted,
            rejected_decision_ids=rejected,
            session_record_hashes=record_hashes,
            attestation_digest=_digest(payload),
            evidence_root=ledger.evidence_root,
            ledger_identity=ledger.ledger_identity,
            checkpoint_digest=checkpoint.digest,
        )

    def identity_payload(self) -> dict[str, object]:
        return {
            "schema_version": "skeleton.runtime_attestation.v2",
            "session_id": self.session_id,
            "runtime_digest": self.runtime_digest,
            "replay_digest": self.replay_digest,
            "capsule_digest": self.capsule_digest,
            "session_audit_digest": self.session_audit_digest,
            "ledger_head": self.ledger_head,
            "ledger_count": self.ledger_count,
            "evidence_root": self.evidence_root,
            "ledger_identity": self.ledger_identity,
            "checkpoint_digest": self.checkpoint_digest,
            "session_root_decision_id": self.session_root_decision_id,
            "selected_policy_decision_id": self.selected_policy_decision_id,
            "accepted_decision_ids": list(self.accepted_decision_ids),
            "rejected_decision_ids": list(self.rejected_decision_ids),
            "session_record_hashes": list(self.session_record_hashes),
        }

    def verify_identity(self) -> bool:
        try:
            return (
                self.attestation_digest
                == _digest(self.identity_payload())
            )
        except ValueError:
            return False


def verify_attestation(
    attestation: RuntimeAttestation,
    snapshot: RuntimeReplaySnapshot,
    ledger: DecisionLedger,
) -> tuple[str, ...]:
    """Return deterministic integrity violations for an attestation."""
    if not _is_runtime_attestation(attestation):
        raise TypeError(
            "attestation must be trusted RuntimeAttestation"
        )
    if not _is_runtime_snapshot(snapshot):
        raise TypeError(
            "snapshot must be trusted RuntimeReplaySnapshot"
        )
    if not _is_decision_ledger(ledger):
        raise TypeError("ledger must be trusted DecisionLedger")

    failures: list[str] = []
    runtime = audit_runtime(snapshot, ledger)
    session = audit_session(
        ledger,
        snapshot.session_id,
    )
    try:
        expected = RuntimeAttestation.capture(
            snapshot,
            ledger,
        )
        capsule = RuntimeIntegrityCapsule.capture(
            snapshot,
            ledger,
        )
        capsule_audit = capsule.verify(ledger)
    except ValueError as exc:
        failures.append(str(exc))
        expected = None
        capsule = None
        capsule_audit = None

    if not runtime.valid:
        failures.append("runtime audit is invalid")
    if not session.valid:
        failures.append("session audit is invalid")
    if (
        capsule_audit is not None
        and not capsule_audit.valid
    ):
        failures.append("integrity capsule is invalid")
    if attestation.session_id != snapshot.session_id:
        failures.append(
            "attestation session identity diverges"
        )
    if attestation.runtime_digest != snapshot.runtime_digest:
        failures.append(
            "attestation runtime digest diverges"
        )
    if attestation.replay_digest != replay_digest(snapshot):
        failures.append(
            "attestation replay digest diverges"
        )
    if (
        capsule is not None
        and attestation.capsule_digest
        != capsule.capsule_digest
    ):
        failures.append(
            "attestation capsule digest diverges"
        )
    if attestation.session_audit_digest != session.digest:
        failures.append(
            "attestation session audit digest diverges"
        )
    if (
        attestation.ledger_head != ledger.head_hash
        or attestation.ledger_count != len(ledger.records)
    ):
        failures.append(
            "attestation ledger identity diverges"
        )
    if attestation.evidence_root != ledger.evidence_root:
        failures.append(
            "attestation evidence root diverges"
        )
    if attestation.ledger_identity != ledger.ledger_identity:
        failures.append(
            "attestation ledger content identity diverges"
        )
    checkpoint = ledger.checkpoint()
    if attestation.checkpoint_digest != checkpoint.digest:
        failures.append(
            "attestation ledger checkpoint diverges"
        )

    if (
        attestation.session_root_decision_id
        != (
            expected.session_root_decision_id
            if expected
            else ""
        )
    ):
        failures.append(
            "attestation causal root diverges"
        )
    if (
        attestation.selected_policy_decision_id
        != (
            expected.selected_policy_decision_id
            if expected
            else None
        )
    ):
        failures.append(
            "attestation selected policy identity diverges"
        )
    if (
        attestation.accepted_decision_ids
        != (
            expected.accepted_decision_ids
            if expected
            else ()
        )
    ):
        failures.append(
            "attestation accepted decision identities diverge"
        )
    if (
        attestation.rejected_decision_ids
        != (
            expected.rejected_decision_ids
            if expected
            else ()
        )
    ):
        failures.append(
            "attestation rejected decision identities diverge"
        )
    if (
        attestation.session_record_hashes
        != (
            expected.session_record_hashes
            if expected
            else ()
        )
    ):
        failures.append(
            "attestation session record hashes diverge"
        )
    if not attestation.verify_identity():
        failures.append(
            "attestation digest diverges"
        )
    if (
        expected is not None
        and attestation.attestation_digest
        != expected.attestation_digest
    ):
        failures.append(
            "attestation digest diverges"
        )
    return tuple(dict.fromkeys(failures))


__all__ = ["RuntimeAttestation", "verify_attestation"]
