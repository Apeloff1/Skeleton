"""Fail-closed maturity reconciliation for masterplan volume claims.

The reconciler is intentionally non-authoritative: it computes explainable
promotion candidates from masterplan fields and signed accountability state.
It never mutates either source and never signs or applies a maturity change.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from typing import Any, Mapping, Sequence


class MaturityReconciliationError(ValueError):
    """Input to maturity reconciliation is malformed."""


class MaturityState(str, Enum):
    SPECIFIED = "specified"
    SCAFFOLDED = "scaffolded"
    IMPLEMENTED = "implemented"
    INTEGRATED = "integrated"
    VERIFIED = "verified"
    HARDENED = "hardened"
    PRODUCTION = "production"


MATURITY_ORDER: tuple[MaturityState, ...] = (
    MaturityState.SPECIFIED,
    MaturityState.SCAFFOLDED,
    MaturityState.IMPLEMENTED,
    MaturityState.INTEGRATED,
    MaturityState.VERIFIED,
    MaturityState.HARDENED,
    MaturityState.PRODUCTION,
)
_MATURITY_INDEX = {state.value: index for index, state in enumerate(MATURITY_ORDER)}
_PLANNED_PREFIX = "planned:"


def _canonical_digest(value: object) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _nonempty_sequence(value: object) -> bool:
    return isinstance(value, Sequence) and not isinstance(
        value, (str, bytes)
    ) and bool(value)


def _materialized_sequence(value: object) -> bool:
    if not _nonempty_sequence(value):
        return False
    for item in value:
        if not isinstance(item, str) or not item.strip():
            return False
        if item.startswith(_PLANNED_PREFIX):
            return False
    return True


def _signed(signoff: object) -> bool:
    return isinstance(signoff, Mapping) and signoff.get("signed") is True


def _accountability_rank(status: object) -> int:
    """Return rank only for explicit maturity-bearing accountability states.

    Generic lifecycle terminals such as passing/done/closed/accepted_risk are
    intentionally not aliases for maturity. Completion, risk disposition, and
    production qualification are different claims and must remain separate.
    """
    if not isinstance(status, str):
        return -1
    return _MATURITY_INDEX.get(status.lower(), -1)


@dataclass(frozen=True, slots=True)
class MaturityEvaluation:
    state: str
    eligible: bool
    blockers: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "eligible": self.eligible,
            "blockers": list(self.blockers),
        }


@dataclass(frozen=True, slots=True)
class MaturityReconciliation:
    volume_key: str
    current_status: str
    current_implementation_status: str
    accountability_id: str
    accountability_status: str
    accountability_maturity_status: str | None
    implementation_status_candidate: str | None
    target_floor: str
    highest_eligible_status: str
    promotion_candidate: str | None
    current_claim_valid: bool
    current_claim_blockers: tuple[str, ...]
    target_floor_eligible: bool
    implementation_signed: bool
    verification_signed: bool
    source_digest: str
    evaluations: tuple[MaturityEvaluation, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "volume_key": self.volume_key,
            "current_status": self.current_status,
            "current_implementation_status": self.current_implementation_status,
            "accountability_id": self.accountability_id,
            "accountability_status": self.accountability_status,
            "accountability_maturity_status": self.accountability_maturity_status,
            "implementation_status_candidate": self.implementation_status_candidate,
            "target_floor": self.target_floor,
            "highest_eligible_status": self.highest_eligible_status,
            "promotion_candidate": self.promotion_candidate,
            "current_claim_valid": self.current_claim_valid,
            "current_claim_blockers": list(self.current_claim_blockers),
            "target_floor_eligible": self.target_floor_eligible,
            "implementation_signed": self.implementation_signed,
            "verification_signed": self.verification_signed,
            "source_digest": self.source_digest,
            "evaluations": [item.as_dict() for item in self.evaluations],
        }


def _required_fields(
    maturity_policy: Mapping[str, Any],
    state: str,
) -> tuple[str, ...]:
    policy = maturity_policy.get(state)
    if not isinstance(policy, Mapping):
        raise MaturityReconciliationError(
            f"missing maturity policy for {state}"
        )
    fields = policy.get("required_nonempty_fields")
    if not isinstance(fields, list) or not all(
        isinstance(item, str) and item for item in fields
    ):
        raise MaturityReconciliationError(
            f"invalid required fields for {state}"
        )
    return tuple(fields)


def _field_blockers(
    volume: Mapping[str, Any],
    maturity_policy: Mapping[str, Any],
    state: str,
) -> list[str]:
    blockers: list[str] = []
    executable_fields = {
        "implementation_paths",
        "tests",
        "evaluations",
        "evidence",
    }
    for field in _required_fields(maturity_policy, state):
        value = volume.get(field)
        if field in executable_fields:
            if not _materialized_sequence(value):
                blockers.append(
                    f"{state}: {field} must contain materialized references"
                )
        elif not _nonempty_sequence(value):
            blockers.append(f"{state}: {field} must be non-empty")
    return blockers


def _accountability_blockers(
    accountability: Mapping[str, Any],
    state: str,
) -> list[str]:
    blockers: list[str] = []
    rank = _MATURITY_INDEX[state]
    status_rank = _accountability_rank(accountability.get("status"))
    impl_signed = _signed(accountability.get("implementation_signoff"))
    verify_signed = _signed(accountability.get("verification_signoff"))

    if rank >= _MATURITY_INDEX[MaturityState.IMPLEMENTED.value]:
        if not impl_signed:
            blockers.append(
                f"{state}: implementation accountability is unsigned"
            )
        if status_rank < _MATURITY_INDEX[MaturityState.IMPLEMENTED.value]:
            blockers.append(
                f"{state}: accountability status is below implemented"
            )
    if rank >= _MATURITY_INDEX[MaturityState.INTEGRATED.value]:
        if status_rank < _MATURITY_INDEX[MaturityState.INTEGRATED.value]:
            blockers.append(
                f"{state}: accountability status is below integrated"
            )
    if rank >= _MATURITY_INDEX[MaturityState.VERIFIED.value]:
        if not verify_signed:
            blockers.append(
                f"{state}: independent verification is unsigned"
            )
        if status_rank < _MATURITY_INDEX[MaturityState.VERIFIED.value]:
            blockers.append(
                f"{state}: accountability status is below verified"
            )
    if rank >= _MATURITY_INDEX[MaturityState.HARDENED.value]:
        evidence = accountability.get("evidence")
        if not _materialized_sequence(evidence):
            blockers.append(
                f"{state}: accountability evidence is not materialized"
            )
        if status_rank < _MATURITY_INDEX[MaturityState.HARDENED.value]:
            blockers.append(
                f"{state}: accountability status is below hardened"
            )
    if rank >= _MATURITY_INDEX[MaturityState.PRODUCTION.value]:
        if status_rank < _MATURITY_INDEX[MaturityState.PRODUCTION.value]:
            blockers.append(
                f"{state}: accountability status is below production"
            )
    return blockers


def reconcile_volume(
    volume: Mapping[str, Any],
    accountability: Mapping[str, Any],
    maturity_policy: Mapping[str, Any],
    *,
    target_floor: str,
) -> MaturityReconciliation:
    """Compute a non-mutating maturity candidate for one canonical volume."""

    key = volume.get("key")
    current = volume.get("status")
    current_implementation = volume.get("implementation_status")
    accountability_id = volume.get("accountability_id")
    if not isinstance(key, str) or not key:
        raise MaturityReconciliationError("volume key is required")
    if current not in _MATURITY_INDEX:
        raise MaturityReconciliationError(
            f"{key}: unsupported current maturity {current!r}"
        )
    if current_implementation == "unverified":
        current_implementation_index = -1
    elif current_implementation in _MATURITY_INDEX:
        current_implementation_index = _MATURITY_INDEX[current_implementation]
    else:
        raise MaturityReconciliationError(
            f"{key}: unsupported implementation_status "
            f"{current_implementation!r}"
        )
    if target_floor not in _MATURITY_INDEX:
        raise MaturityReconciliationError(
            f"{key}: unsupported target floor {target_floor!r}"
        )
    if not isinstance(accountability_id, str) or not accountability_id:
        raise MaturityReconciliationError(
            f"{key}: accountability_id is required"
        )
    if accountability.get("id") != accountability_id:
        raise MaturityReconciliationError(
            f"{key}: accountability record identity mismatch"
        )

    accountability_status = str(accountability.get("status") or "")
    accountability_rank = _accountability_rank(accountability_status)
    accountability_maturity_status = (
        MATURITY_ORDER[accountability_rank].value
        if accountability_rank >= 0
        else None
    )
    if (
        current_implementation_index >= 0
        and accountability_rank < current_implementation_index
    ):
        raise MaturityReconciliationError(
            f"{key}: implementation_status {current_implementation!r} "
            "exceeds explicit accountability maturity"
        )

    implementation_candidate: str | None = None
    for state in MATURITY_ORDER[
        _MATURITY_INDEX[MaturityState.IMPLEMENTED.value]:
    ]:
        state_name = state.value
        if _accountability_blockers(accountability, state_name):
            break
        state_index = _MATURITY_INDEX[state_name]
        if state_index > current_implementation_index:
            implementation_candidate = state_name

    source_digest = _canonical_digest(
        {
            "volume": dict(volume),
            "accountability": dict(accountability),
            "target_floor": target_floor,
        }
    )
    evaluations: list[MaturityEvaluation] = []
    highest_index = _MATURITY_INDEX[current]
    current_index = highest_index

    for state in MATURITY_ORDER:
        state_name = state.value
        index = _MATURITY_INDEX[state_name]
        blockers = _field_blockers(volume, maturity_policy, state_name)
        blockers.extend(_accountability_blockers(accountability, state_name))

        if index >= _MATURITY_INDEX[MaturityState.HARDENED.value]:
            gaps = volume.get("gaps")
            if _nonempty_sequence(gaps):
                blockers.append(
                    f"{state_name}: unresolved volume gaps remain"
                )

        eligible = not blockers
        evaluations.append(
            MaturityEvaluation(
                state=state_name,
                eligible=eligible,
                blockers=tuple(sorted(set(blockers))),
            )
        )
        if eligible and index >= highest_index:
            highest_index = index

    evaluation_by_state = {
        item.state: item
        for item in evaluations
    }
    current_eval = evaluation_by_state[current]
    highest_index = current_index
    if current_eval.eligible:
        for index in range(current_index + 1, len(MATURITY_ORDER)):
            next_state = MATURITY_ORDER[index].value
            if not evaluation_by_state[next_state].eligible:
                break
            highest_index = index

    highest = MATURITY_ORDER[highest_index].value
    candidate = (
        highest
        if current_eval.eligible and highest_index > current_index
        else None
    )
    target_eval = evaluation_by_state[target_floor]
    floor_reachable = (
        current_eval.eligible
        and _MATURITY_INDEX[target_floor] <= highest_index
        and target_eval.eligible
    )

    return MaturityReconciliation(
        volume_key=key,
        current_status=current,
        current_implementation_status=str(current_implementation),
        accountability_id=accountability_id,
        accountability_status=accountability_status,
        accountability_maturity_status=accountability_maturity_status,
        implementation_status_candidate=implementation_candidate,
        target_floor=target_floor,
        highest_eligible_status=highest,
        promotion_candidate=candidate,
        current_claim_valid=current_eval.eligible,
        current_claim_blockers=current_eval.blockers,
        target_floor_eligible=floor_reachable,
        implementation_signed=_signed(
            accountability.get("implementation_signoff")
        ),
        verification_signed=_signed(
            accountability.get("verification_signoff")
        ),
        source_digest=source_digest,
        evaluations=tuple(evaluations),
    )
