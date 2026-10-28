"""Portable, deterministic integrity capsules for Jeeves runtime sessions.

A capsule binds the runtime snapshot, session audit, exact decision-ledger
checkpoint, evidence root, and per-session record hashes into one portable
identity.  Verification fails if evidence content changes even when decision
ids remain unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import importlib
import json

from skeleton.learning.school.decision_ledger import (
    DecisionDisposition,
    DecisionLedger,
)
from skeleton.learning.school.runtime_replay import (
    RuntimeAudit,
    RuntimeReplaySnapshot,
    audit_runtime,
    replay_digest,
)
from skeleton.learning.school.session_audit import (
    SessionAudit,
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
            "runtime capsule payload is not deterministic JSON"
        ) from exc
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RuntimeIntegrityCapsule:
    session_id: str
    runtime: RuntimeReplaySnapshot
    session: SessionAudit
    ledger_head: str
    ledger_count: int
    root_decision_id: str
    selected_policy_decision_id: str | None
    capsule_digest: str
    evidence_root: str = ""
    ledger_identity: str = ""
    session_record_hashes: tuple[str, ...] = ()

    @classmethod
    def capture(
        cls,
        runtime: RuntimeReplaySnapshot,
        ledger: DecisionLedger,
    ) -> "RuntimeIntegrityCapsule":
        if not _is_runtime_snapshot(runtime):
            raise TypeError(
                "runtime must be trusted RuntimeReplaySnapshot"
            )
        if not _is_decision_ledger(ledger):
            raise TypeError("ledger must be trusted DecisionLedger")

        runtime_audit = audit_runtime(runtime, ledger)
        if not runtime_audit.valid:
            raise ValueError(
                "cannot capsule an invalid runtime snapshot"
            )
        session = audit_session(ledger, runtime.session_id)
        if not session.valid:
            raise ValueError(
                "cannot capsule an invalid session audit"
            )
        records = ledger.session(runtime.session_id)
        if not records:
            raise ValueError("cannot capsule an empty session")
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
        selected = runtime.selected_policy_decision_id or None
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
                or selected_record.disposition.value
                != DecisionDisposition.ACCEPTED.value
            ):
                raise ValueError(
                    "selected policy decision is not an accepted session record"
                )
            if selected_record.action != runtime.selected_policy:
                raise ValueError(
                    "selected policy decision does not match selected policy"
                )

        hashes = tuple(
            record.record_hash
            for record in records
        )
        payload = {
            "schema_version": "skeleton.runtime_integrity_capsule.v2",
            "session_id": runtime.session_id,
            "runtime_digest": runtime.runtime_digest,
            "replay_digest": replay_digest(runtime),
            "session_digest": session.digest,
            "session_valid": session.valid,
            "ledger_head": ledger.head_hash,
            "ledger_count": len(ledger.records),
            "evidence_root": ledger.evidence_root,
            "ledger_identity": ledger.ledger_identity,
            "root_decision_id": root.decision_id,
            "selected_policy_decision_id": selected,
            "session_record_hashes": list(hashes),
        }
        return cls(
            session_id=runtime.session_id,
            runtime=runtime,
            session=session,
            ledger_head=ledger.head_hash,
            ledger_count=len(ledger.records),
            root_decision_id=root.decision_id,
            selected_policy_decision_id=selected,
            capsule_digest=_digest(payload),
            evidence_root=ledger.evidence_root,
            ledger_identity=ledger.ledger_identity,
            session_record_hashes=hashes,
        )

    def identity_payload(self) -> dict[str, object]:
        return {
            "schema_version": "skeleton.runtime_integrity_capsule.v2",
            "session_id": self.session_id,
            "runtime_digest": self.runtime.runtime_digest,
            "replay_digest": replay_digest(self.runtime),
            "session_digest": self.session.digest,
            "session_valid": self.session.valid,
            "ledger_head": self.ledger_head,
            "ledger_count": self.ledger_count,
            "evidence_root": self.evidence_root,
            "ledger_identity": self.ledger_identity,
            "root_decision_id": self.root_decision_id,
            "selected_policy_decision_id": self.selected_policy_decision_id,
            "session_record_hashes": list(self.session_record_hashes),
        }

    def verify(
        self,
        ledger: DecisionLedger,
    ) -> RuntimeAudit:
        if not _is_decision_ledger(ledger):
            raise TypeError("ledger must be trusted DecisionLedger")
        runtime_audit = audit_runtime(self.runtime, ledger)
        session_audit = audit_session(
            ledger,
            self.session_id,
        )
        violations = list(runtime_audit.violations)
        try:
            expected = RuntimeIntegrityCapsule.capture(
                self.runtime,
                ledger,
            )
        except ValueError as exc:
            violations.append(str(exc))
            expected = None

        if not session_audit.valid:
            violations.extend(
                f"session audit: {item}"
                for item in session_audit.failures
            )
        if (
            self.ledger_head != ledger.head_hash
            or self.ledger_count != len(ledger.records)
        ):
            violations.append(
                "capsule-integrity divergence: ledger checkpoint has advanced"
            )
        if self.evidence_root != ledger.evidence_root:
            violations.append(
                "capsule-integrity divergence: evidence root changed"
            )
        if self.ledger_identity != ledger.ledger_identity:
            violations.append(
                "capsule-integrity divergence: ledger identity changed"
            )
        if (
            expected is not None
            and self.root_decision_id != expected.root_decision_id
        ):
            violations.append(
                "capsule-integrity divergence: causal root identity changed"
            )
        if (
            expected is not None
            and self.selected_policy_decision_id
            != expected.selected_policy_decision_id
        ):
            violations.append(
                "capsule-integrity divergence: selected policy identity changed"
            )
        if (
            expected is not None
            and self.session_record_hashes
            != expected.session_record_hashes
        ):
            violations.append(
                "capsule-integrity divergence: session record hashes changed"
            )
        try:
            own_digest = _digest(self.identity_payload())
        except ValueError:
            own_digest = ""
        if (
            (expected is not None and self.capsule_digest != expected.capsule_digest)
            or self.capsule_digest != own_digest
        ):
            violations.append(
                "capsule-integrity divergence: capsule digest does not match its bound audits"
            )
        return RuntimeAudit(
            not violations,
            tuple(dict.fromkeys(violations)),
        )


__all__ = ["RuntimeIntegrityCapsule"]
