from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone

import pytest

from skeleton.persistence.spine_cutover_authorization import (
    SpineCutoverAuthorization,
    SpineCutoverAuthorizationError,
)
from skeleton.persistence.spine_cutover_authorization_verify import (
    SpineCutoverAuthorizationVerify,
    SpineCutoverAuthorizationVerifyError,
)


NOW = datetime(2026, 10, 1, 16, 0, tzinfo=timezone.utc)


def _candidate() -> dict[str, object]:
    return {
        "kind": "spine_runtime_selection_candidate",
        "digest": "a" * 64,
        "runtime_driver_selected": False,
        "selection_authorized": False,
        "runtime_activated": False,
    }


def _rehearsal() -> dict[str, object]:
    return {
        "kind": "spine_cutover_rehearsal",
        "digest": "b" * 64,
        "rehearsed": True,
        "switch_refused": True,
        "switch_reason": "switch-not-landed",
        "runtime_driver_selected": False,
        "selection_authorized": False,
        "runtime_activated": False,
    }


def _approval(
    approval_id: str,
    approver_id: str,
    authority_domain: str,
) -> dict[str, object]:
    return {
        "approval_id": approval_id,
        "approver_id": approver_id,
        "authority_domain": authority_domain,
        "decision": "approve",
        "candidate_digest": "a" * 64,
        "rehearsal_digest": "b" * 64,
        "issued_at": (NOW - timedelta(minutes=1)).isoformat(),
        "expires_at": (NOW + timedelta(minutes=10)).isoformat(),
        "attestation_digest": (approval_id[0] * 64),
    }


def _approvals() -> list[dict[str, object]]:
    return [
        _approval("approval-operations", "operator-a", "operations"),
        _approval("approval-reliability", "reliability-b", "reliability"),
    ]


def _authenticate(approval: dict[str, object]) -> bool:
    return approval.get("attestation_digest") in {"a" * 64, "r" * 64}


def test_distinct_authenticated_dual_control_is_qualified_but_not_effective() -> None:
    card = SpineCutoverAuthorization().qualify(
        candidate=_candidate(),
        rehearsal=_rehearsal(),
        approvals=_approvals(),
        authenticate=_authenticate,
        now=NOW,
    )
    verified = SpineCutoverAuthorizationVerify().verify(card)

    assert card["approver_count"] == 2
    assert card["authority_domains"] == ["operations", "reliability"]
    assert card["dual_control_authenticated"] is True
    assert card["authorization_qualified"] is True
    assert card["authorization_effective"] is False
    assert card["runtime_driver_selected"] is False
    assert card["selection_authorized"] is False
    assert card["runtime_activated"] is False
    assert len(card["digest"]) == 64
    assert verified["verified"] is True
    assert verified["authorization_effective"] is False


@pytest.mark.parametrize(
    ("mutator", "match"),
    [
        (lambda rows: rows.__setitem__(1, {**rows[1], "approver_id": "operator-a"}), "distinct approvers"),
        (lambda rows: rows.__setitem__(1, {**rows[1], "authority_domain": "operations"}), "operations and reliability"),
        (lambda rows: rows.__setitem__(1, {**rows[1], "candidate_digest": "c" * 64}), "candidate scope"),
        (lambda rows: rows.__setitem__(1, {**rows[1], "decision": "reject"}), "decision"),
        (lambda rows: rows.__setitem__(1, {**rows[1], "expires_at": (NOW - timedelta(seconds=1)).isoformat()}), "expired"),
    ],
)
def test_dual_control_fails_closed_on_invalid_receipts(mutator, match: str) -> None:
    approvals = _approvals()
    mutator(approvals)

    with pytest.raises(SpineCutoverAuthorizationError, match=match):
        SpineCutoverAuthorization().qualify(
            candidate=_candidate(),
            rehearsal=_rehearsal(),
            approvals=approvals,
            authenticate=_authenticate,
            now=NOW,
        )


def test_dual_control_fails_closed_when_external_authenticator_rejects() -> None:
    with pytest.raises(SpineCutoverAuthorizationError, match="not externally authenticated"):
        SpineCutoverAuthorization().qualify(
            candidate=_candidate(),
            rehearsal=_rehearsal(),
            approvals=_approvals(),
            authenticate=lambda approval: False,
            now=NOW,
        )


def test_verifier_rejects_effective_authority_or_digest_tamper() -> None:
    card = SpineCutoverAuthorization().qualify(
        candidate=_candidate(),
        rehearsal=_rehearsal(),
        approvals=_approvals(),
        authenticate=_authenticate,
        now=NOW,
    )

    effective = copy.deepcopy(card)
    effective["authorization_effective"] = True
    with pytest.raises(
        SpineCutoverAuthorizationVerifyError,
        match="became effective",
    ):
        SpineCutoverAuthorizationVerify().verify(effective)

    tampered = copy.deepcopy(card)
    tampered["approvals"][0]["attestation_digest"] = "f" * 64
    with pytest.raises(
        SpineCutoverAuthorizationVerifyError,
        match="digest mismatch",
    ):
        SpineCutoverAuthorizationVerify().verify(tampered)
