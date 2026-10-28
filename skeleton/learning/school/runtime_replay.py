"""Deterministic runtime snapshots and semantic audit for Jeeves sessions."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import importlib
import json
import math
from typing import Sequence

from skeleton.learning.school.decision_ledger import (
    DecisionDisposition,
    DecisionLedger,
)
from skeleton.learning.school.session_runtime import (
    SessionEvent,
    SessionPhase,
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


def _is_session_event(value: object) -> bool:
    return _trusted_twin_instance(
        value,
        SessionEvent,
        twin_module="skeleton.ai.learning.school.session_runtime",
        twin_name="SessionEvent",
    )


def _is_session_phase(value: object) -> bool:
    return _trusted_twin_instance(
        value,
        SessionPhase,
        twin_module="skeleton.ai.learning.school.session_runtime",
        twin_name="SessionPhase",
    )


def _is_runtime_snapshot(value: object) -> bool:
    return _trusted_twin_instance(
        value,
        RuntimeReplaySnapshot,
        twin_module="skeleton.ai.learning.school.runtime_replay",
        twin_name="RuntimeReplaySnapshot",
    )


def _text(name: str, value: object, *, maximum: int = 4096) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    result = value.strip()
    if len(result) > maximum:
        raise ValueError(f"{name} exceeds {maximum} characters")
    return result


def _canonical(value: object) -> object:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("runtime payload contains non-finite number")
        return float(value)
    if isinstance(value, (tuple, list)):
        return [_canonical(item) for item in value]
    if isinstance(value, dict):
        result: dict[str, object] = {}
        for raw_key, item in value.items():
            key = _text("runtime payload key", raw_key, maximum=256)
            if key in result:
                raise ValueError(
                    "runtime payload keys collide after normalization"
                )
            result[key] = _canonical(item)
        return dict(sorted(result.items()))
    raise ValueError(
        f"runtime payload contains unsupported type: {type(value).__name__}"
    )


def _digest(payload: object) -> str:
    canonical = _canonical(payload)
    try:
        encoded = json.dumps(
            canonical,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("runtime payload is not deterministic JSON") from exc
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _sha(name: str, value: object, *, allow_empty: bool = False) -> str:
    if allow_empty and value == "":
        return ""
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(ch not in "0123456789abcdef" for ch in value)
    ):
        raise ValueError(f"{name} must be lowercase SHA-256")
    return value


def _normalize_event(
    event: SessionEvent,
) -> tuple[int, str, str, tuple[tuple[str, str], ...]]:
    if not _is_session_event(event):
        raise TypeError("events must contain trusted SessionEvent values")
    if (
        isinstance(event.sequence, bool)
        or not isinstance(event.sequence, int)
        or event.sequence <= 0
    ):
        raise ValueError("runtime event sequence must be positive integer")
    if not _is_session_phase(event.phase):
        raise ValueError("runtime event phase must be trusted SessionPhase")
    name = _text("runtime event", event.event)
    payload: list[tuple[str, str]] = []
    seen: set[str] = set()
    for row in event.payload:
        if not isinstance(row, tuple) or len(row) != 2:
            raise ValueError("runtime event payload must contain key/value pairs")
        key = _text("runtime event payload key", row[0], maximum=256)
        value = _text("runtime event payload value", row[1])
        if key in seen:
            raise ValueError("runtime event payload keys must be unique")
        seen.add(key)
        payload.append((key, value))
    return (
        event.sequence,
        event.phase.value,
        name,
        tuple(sorted(payload)),
    )


def _runtime_payload(
    *,
    session_id: str,
    phase: str,
    events: object,
    selected_policy: str,
    selected_policy_decision_id: str,
    rejected_policies: tuple[str, ...],
    rejected_policy_decision_ids: tuple[str, ...],
    ledger_head: str,
    ledger_count: int,
    pipeline_contract_digest: str,
    provenance_digest: str,
    evidence_root: str,
    ledger_identity: str,
) -> dict[str, object]:
    return {
        "schema_version": "skeleton.runtime_replay_snapshot.v2",
        "session_id": session_id,
        "phase": phase,
        "events": events,
        "selected_policy": selected_policy,
        "selected_policy_decision_id": selected_policy_decision_id,
        "rejected_policies": list(rejected_policies),
        "rejected_policy_decision_ids": list(
            rejected_policy_decision_ids
        ),
        "ledger_head": ledger_head,
        "ledger_count": ledger_count,
        "pipeline_contract_digest": pipeline_contract_digest,
        "provenance_digest": provenance_digest,
        "evidence_root": evidence_root,
        "ledger_identity": ledger_identity,
    }


def _runtime_digest(**kwargs: object) -> str:
    return _digest(_runtime_payload(**kwargs))


@dataclass(frozen=True)
class RuntimeReplaySnapshot:
    session_id: str
    phase: str
    event_count: int
    events: tuple[
        tuple[int, str, str, tuple[tuple[str, str], ...]],
        ...,
    ]
    selected_policy: str
    selected_policy_decision_id: str
    rejected_policies: tuple[str, ...]
    rejected_policy_decision_ids: tuple[str, ...]
    ledger_head: str
    ledger_count: int
    pipeline_contract_digest: str
    provenance_digest: str
    runtime_digest: str
    evidence_root: str = ""
    ledger_identity: str = ""

    @classmethod
    def capture(
        cls,
        *,
        session_id: str,
        phase: SessionPhase,
        events: Sequence[SessionEvent],
        selected_policy: str | None,
        selected_policy_decision_id: str | None = None,
        rejected_policies: Sequence[str],
        ledger: DecisionLedger,
        pipeline_contract_digest: str = "",
        provenance_digest: str = "",
    ) -> "RuntimeReplaySnapshot":
        if not _is_decision_ledger(ledger):
            raise TypeError("ledger must be trusted DecisionLedger")
        if not _is_session_phase(phase):
            raise TypeError("phase must be trusted SessionPhase")
        normalized_session = _text("session_id", session_id)
        normalized = tuple(_normalize_event(event) for event in events)
        selected = (
            ""
            if selected_policy is None
            else _text("selected_policy", selected_policy)
        )
        rejected = tuple(
            _text("rejected_policy", item)
            for item in rejected_policies
        )
        if len(rejected) != len(set(rejected)):
            raise ValueError("rejected policies must be unique")

        session_records = ledger.session(normalized_session)
        if selected_policy_decision_id:
            selected_id = _text(
                "selected_policy_decision_id",
                selected_policy_decision_id,
            )
        else:
            selected_records = tuple(
                record
                for record in session_records
                if (
                    selected
                    and record.action == selected
                    and record.disposition.value
                    == DecisionDisposition.ACCEPTED.value
                )
            )
            selected_id = (
                selected_records[0].decision_id
                if len(selected_records) == 1
                else ""
            )

        rejected_records = tuple(
            record
            for record in session_records
            if (
                record.action in rejected
                and record.disposition.value
                == DecisionDisposition.REJECTED.value
            )
        )
        rejected_ids = tuple(
            record.decision_id
            for record in rejected_records
        )
        head = ledger.head_hash
        evidence_root = ledger.evidence_root
        ledger_identity = ledger.ledger_identity
        pipeline = (
            ""
            if not pipeline_contract_digest
            else _text(
                "pipeline_contract_digest",
                pipeline_contract_digest,
                maximum=256,
            )
        )
        provenance = (
            ""
            if not provenance_digest
            else _text(
                "provenance_digest",
                provenance_digest,
                maximum=256,
            )
        )
        digest = _runtime_digest(
            session_id=normalized_session,
            phase=phase.value,
            events=normalized,
            selected_policy=selected,
            selected_policy_decision_id=selected_id,
            rejected_policies=rejected,
            rejected_policy_decision_ids=rejected_ids,
            ledger_head=head,
            ledger_count=len(ledger.records),
            pipeline_contract_digest=pipeline,
            provenance_digest=provenance,
            evidence_root=evidence_root,
            ledger_identity=ledger_identity,
        )
        return cls(
            session_id=normalized_session,
            phase=phase.value,
            event_count=len(normalized),
            events=normalized,
            selected_policy=selected,
            selected_policy_decision_id=selected_id,
            rejected_policies=rejected,
            rejected_policy_decision_ids=rejected_ids,
            ledger_head=head,
            ledger_count=len(ledger.records),
            pipeline_contract_digest=pipeline,
            provenance_digest=provenance,
            runtime_digest=digest,
            evidence_root=evidence_root,
            ledger_identity=ledger_identity,
        )

    @classmethod
    def capture_verified(
        cls,
        **kwargs: object,
    ) -> "RuntimeReplaySnapshot":
        snapshot = cls.capture(**kwargs)
        ledger = kwargs.get("ledger")
        if not _is_decision_ledger(ledger):
            raise TypeError("ledger must be trusted DecisionLedger")
        audit = audit_runtime(snapshot, ledger)
        if not audit.valid:
            raise ValueError(
                "cannot capture verified runtime snapshot: "
                + "; ".join(audit.violations)
            )
        return snapshot

    def identity_payload(self) -> dict[str, object]:
        return _runtime_payload(
            session_id=self.session_id,
            phase=self.phase,
            events=self.events,
            selected_policy=self.selected_policy,
            selected_policy_decision_id=self.selected_policy_decision_id,
            rejected_policies=self.rejected_policies,
            rejected_policy_decision_ids=self.rejected_policy_decision_ids,
            ledger_head=self.ledger_head,
            ledger_count=self.ledger_count,
            pipeline_contract_digest=self.pipeline_contract_digest,
            provenance_digest=self.provenance_digest,
            evidence_root=self.evidence_root,
            ledger_identity=self.ledger_identity,
        )


@dataclass(frozen=True)
class RuntimeAudit:
    valid: bool
    violations: tuple[str, ...]


def audit_runtime(
    snapshot: RuntimeReplaySnapshot,
    ledger: DecisionLedger,
) -> RuntimeAudit:
    if not _is_runtime_snapshot(snapshot):
        raise TypeError("snapshot must be trusted RuntimeReplaySnapshot")
    if not _is_decision_ledger(ledger):
        raise TypeError("ledger must be trusted DecisionLedger")

    violations: list[str] = []
    try:
        ledger.verify()
    except ValueError as exc:
        violations.append(f"ledger integrity: {exc}")

    if snapshot.ledger_head != ledger.head_hash:
        violations.append(
            "runtime snapshot ledger head diverges from ledger"
        )
    if snapshot.ledger_count != len(ledger.records):
        violations.append(
            "runtime snapshot ledger count diverges from ledger"
        )
    if snapshot.evidence_root != ledger.evidence_root:
        violations.append(
            "runtime snapshot evidence root diverges from ledger"
        )
    if snapshot.ledger_identity != ledger.ledger_identity:
        violations.append(
            "runtime snapshot ledger identity diverges from ledger"
        )

    try:
        expected_runtime_digest = _runtime_digest(
            session_id=snapshot.session_id,
            phase=snapshot.phase,
            events=snapshot.events,
            selected_policy=snapshot.selected_policy,
            selected_policy_decision_id=snapshot.selected_policy_decision_id,
            rejected_policies=snapshot.rejected_policies,
            rejected_policy_decision_ids=snapshot.rejected_policy_decision_ids,
            ledger_head=snapshot.ledger_head,
            ledger_count=snapshot.ledger_count,
            pipeline_contract_digest=snapshot.pipeline_contract_digest,
            provenance_digest=snapshot.provenance_digest,
            evidence_root=snapshot.evidence_root,
            ledger_identity=snapshot.ledger_identity,
        )
    except ValueError as exc:
        violations.append(f"runtime-integrity serialization: {exc}")
        expected_runtime_digest = None
    if (
        expected_runtime_digest is None
        or snapshot.runtime_digest != expected_runtime_digest
    ):
        violations.append(
            "runtime-integrity divergence: runtime digest does not match snapshot payload"
        )

    session_records = ledger.session(snapshot.session_id)
    by_id = {
        record.decision_id: record
        for record in ledger.records
    }
    rejected_records = tuple(
        record
        for record in session_records
        if record.disposition.value == DecisionDisposition.REJECTED.value
    )
    accepted_records = tuple(
        record
        for record in session_records
        if record.disposition.value == DecisionDisposition.ACCEPTED.value
    )

    if snapshot.event_count and not session_records:
        violations.append(
            "runtime has events but ledger has no session decisions"
        )
    if snapshot.selected_policy:
        selected_matches = tuple(
            record
            for record in accepted_records
            if record.action == snapshot.selected_policy
        )
        if not session_records:
            violations.append(
                "selected policy cannot be audited without session decisions"
            )
        elif snapshot.selected_policy not in {
            record.action for record in session_records
        }:
            violations.append(
                "selected policy is absent from session ledger"
            )
        selected_id = snapshot.selected_policy_decision_id
        if not selected_id:
            violations.append(
                "selected policy is missing a decision identity"
            )
        else:
            selected_record = by_id.get(selected_id)
            if selected_record is None:
                violations.append(
                    "selected policy decision identity is absent from ledger"
                )
            elif selected_record.session_id != snapshot.session_id:
                violations.append(
                    "selected policy decision identity crosses session boundary"
                )
            elif selected_record.action != snapshot.selected_policy:
                violations.append(
                    "selected policy decision identity does not match selected action"
                )
            elif (
                selected_record.disposition.value
                != DecisionDisposition.ACCEPTED.value
            ):
                violations.append(
                    "selected policy decision identity is not ACCEPTED"
                )
        if not selected_id and len(selected_matches) != 1:
            violations.append(
                "selected policy does not have a unique ACCEPTED ledger attribution"
            )

    expected_rejected_ids = tuple(
        record.decision_id
        for record in rejected_records
        if record.action in snapshot.rejected_policies
    )
    if set(snapshot.rejected_policy_decision_ids) != set(
        expected_rejected_ids
    ):
        violations.append(
            "rejected policy decision identities diverge from ledger"
        )
    if (
        len(snapshot.rejected_policy_decision_ids)
        != len(set(snapshot.rejected_policy_decision_ids))
    ):
        violations.append(
            "rejected policy decision identities are not unique"
        )
    for decision_id in snapshot.rejected_policy_decision_ids:
        record = by_id.get(decision_id)
        if record is None:
            violations.append(
                f"rejected policy decision {decision_id!r} is absent from ledger"
            )
        elif record.session_id != snapshot.session_id:
            violations.append(
                f"rejected policy decision {decision_id!r} crosses session boundary"
            )
        elif (
            record.disposition.value
            != DecisionDisposition.REJECTED.value
        ):
            violations.append(
                f"rejected policy decision {decision_id!r} is not REJECTED"
            )
        elif record.action not in snapshot.rejected_policies:
            violations.append(
                f"rejected policy decision {decision_id!r} is not listed in rejected policies"
            )

    for policy in sorted(
        set(snapshot.rejected_policies)
        - {record.action for record in rejected_records}
    ):
        violations.append(
            f"rejected policy {policy!r} lacks a REJECTED ledger record"
        )
    for policy in sorted(
        {record.action for record in rejected_records}
        - set(snapshot.rejected_policies)
    ):
        violations.append(
            f"ledger rejected policy {policy!r} is absent from runtime snapshot"
        )

    pipeline = snapshot.pipeline_contract_digest
    provenance = snapshot.provenance_digest
    if bool(pipeline) != bool(provenance):
        violations.append(
            "runtime provenance is incomplete: pipeline and plan digests must be paired"
        )
    for name, value in (
        ("pipeline contract", pipeline),
        ("runtime provenance", provenance),
        ("runtime evidence root", snapshot.evidence_root),
        ("runtime ledger identity", snapshot.ledger_identity),
    ):
        if value:
            if (
                len(value) != 64
                or any(
                    char not in "0123456789abcdef"
                    for char in value
                )
            ):
                violations.append(
                    f"{name} digest is not a valid lowercase SHA-256 identity"
                )

    event_sequences = [
        event[0]
        for event in snapshot.events
    ]
    if event_sequences != list(
        range(1, snapshot.event_count + 1)
    ):
        violations.append(
            "runtime event sequence is not contiguous"
        )
    if len(snapshot.events) != snapshot.event_count:
        violations.append(
            "runtime event count does not match event payload"
        )
    for event in snapshot.events:
        if (
            not isinstance(event, tuple)
            or len(event) != 4
            or not isinstance(event[0], int)
            or isinstance(event[0], bool)
        ):
            violations.append(
                "runtime event payload shape is invalid"
            )
            break

    complete_events = [
        index
        for index, event in enumerate(snapshot.events)
        if event[1] == SessionPhase.COMPLETE.value
    ]
    if complete_events:
        complete_index = complete_events[0]
        if complete_index != len(snapshot.events) - 1:
            violations.append(
                "runtime contains events after COMPLETE"
            )
        if snapshot.phase != SessionPhase.COMPLETE.value:
            violations.append(
                "runtime snapshot phase diverges from terminal COMPLETE event"
            )
    elif snapshot.phase == SessionPhase.COMPLETE.value:
        violations.append(
            "runtime snapshot claims COMPLETE without a terminal COMPLETE event"
        )

    for record in session_records:
        for predecessor in record.predecessors:
            prior = by_id.get(predecessor)
            if prior is None:
                violations.append(
                    f"decision {record.decision_id!r} references missing predecessor"
                )
            elif prior.session_id != snapshot.session_id:
                violations.append(
                    f"decision {record.decision_id!r} has a cross-session predecessor"
                )
            elif prior.sequence >= record.sequence:
                violations.append(
                    f"decision {record.decision_id!r} has a non-causal predecessor"
                )

    return RuntimeAudit(
        not violations,
        tuple(dict.fromkeys(violations)),
    )


def replay_digest(snapshot: RuntimeReplaySnapshot) -> str:
    if not _is_runtime_snapshot(snapshot):
        raise TypeError("snapshot must be trusted RuntimeReplaySnapshot")
    return _digest(
        {
            "schema_version": "skeleton.runtime_replay.v2",
            **snapshot.identity_payload(),
            "runtime_digest": snapshot.runtime_digest,
        }
    )


__all__ = [
    "RuntimeAudit",
    "RuntimeReplaySnapshot",
    "audit_runtime",
    "replay_digest",
]
