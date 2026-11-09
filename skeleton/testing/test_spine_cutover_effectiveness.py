from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone

import pytest

from skeleton.persistence.spine_cutover_effectiveness import (
    SpineCutoverEffectiveness,
    SpineCutoverEffectivenessError,
)
from skeleton.persistence.spine_cutover_effectiveness_verify import (
    SpineCutoverEffectivenessVerify,
    SpineCutoverEffectivenessVerifyError,
)


NOW = datetime(2026, 10, 1, 16, 0, tzinfo=timezone.utc)


def _authorization() -> dict[str, object]:
    return {
        "kind": "spine_cutover_authorization",
        "digest": "a" * 64,
        "dual_control_authenticated": True,
        "authorization_qualified": True,
        "authorization_effective": False,
        "selection_authorized": False,
        "runtime_driver_selected": False,
        "runtime_activated": False,
    }


def _authorization_verify() -> dict[str, object]:
    return {
        "kind": "spine_cutover_authorization_verify",
        "authorization_digest": "a" * 64,
        "verified": True,
        "authorization_effective": False,
        "selection_authorized": False,
        "runtime_driver_selected": False,
        "runtime_activated": False,
    }


def _receipt() -> dict[str, object]:
    return {
        "kind": "spine_cutover_effectiveness_receipt",
        "receipt_id": "change-control-001",
        "authorization_digest": "a" * 64,
        "decision": "make-effective",
        "authority_domain": "change-control",
        "change_window_id": "window-2026-10-01T1600Z",
        "one_time_nonce": "n" * 64,
        "issued_at": (NOW - timedelta(minutes=1)).isoformat(),
        "expires_at": (NOW + timedelta(minutes=5)).isoformat(),
        "attestation_digest": "e" * 64,
    }


def _authenticate(receipt: dict[str, object]) -> bool:
    return receipt.get("attestation_digest") == "e" * 64


def test_external_change_control_can_make_authorization_effective_only() -> None:
    card = SpineCutoverEffectiveness().qualify(
        authorization=_authorization(),
        authorization_verify=_authorization_verify(),
        receipt=_receipt(),
        authenticate=_authenticate,
        now=NOW,
    )
    verified = SpineCutoverEffectivenessVerify().verify(card)

    assert card["external_change_control_authenticated"] is True
    assert card["authorization_effective"] is True
    assert card["selection_authorized"] is False
    assert card["runtime_driver_selected"] is False
    assert card["runtime_activated"] is False
    assert len(card["digest"]) == 64
    assert verified["verified"] is True
    assert verified["authorization_effective"] is True
    assert verified["selection_authorized"] is False
    assert verified["one_time_nonce"] == "n" * 64


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        ("authority_domain", "operations", "change-control"),
        ("decision", "approve", "make-effective"),
        ("authorization_digest", "b" * 64, "scope mismatch"),
        ("expires_at", (NOW - timedelta(seconds=1)).isoformat(), "expired"),
        ("one_time_nonce", "short", "64-character"),
    ],
)
def test_effectiveness_fails_closed_on_bad_external_receipt(
    field: str,
    value: object,
    match: str,
) -> None:
    receipt = _receipt()
    receipt[field] = value

    with pytest.raises(SpineCutoverEffectivenessError, match=match):
        SpineCutoverEffectiveness().qualify(
            authorization=_authorization(),
            authorization_verify=_authorization_verify(),
            receipt=receipt,
            authenticate=_authenticate,
            now=NOW,
        )


def test_effectiveness_fails_closed_when_external_authenticator_rejects() -> None:
    with pytest.raises(SpineCutoverEffectivenessError, match="not externally authenticated"):
        SpineCutoverEffectiveness().qualify(
            authorization=_authorization(),
            authorization_verify=_authorization_verify(),
            receipt=_receipt(),
            authenticate=lambda receipt: False,
            now=NOW,
        )


def test_effectiveness_verifier_rejects_runtime_authority_or_tamper() -> None:
    card = SpineCutoverEffectiveness().qualify(
        authorization=_authorization(),
        authorization_verify=_authorization_verify(),
        receipt=_receipt(),
        authenticate=_authenticate,
        now=NOW,
    )

    selected = copy.deepcopy(card)
    selected["selection_authorized"] = True
    with pytest.raises(
        SpineCutoverEffectivenessVerifyError,
        match="gained runtime authority",
    ):
        SpineCutoverEffectivenessVerify().verify(selected)

    tampered = copy.deepcopy(card)
    tampered["effectiveness_receipt"]["change_window_id"] = "window-tampered"
    with pytest.raises(
        SpineCutoverEffectivenessVerifyError,
        match="digest mismatch",
    ):
        SpineCutoverEffectivenessVerify().verify(tampered)
