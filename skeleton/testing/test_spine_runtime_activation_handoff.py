from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone

import pytest

from skeleton.persistence.spine_runtime_activation_handoff import (
    SpineRuntimeActivationHandoff,
    SpineRuntimeActivationHandoffError,
)
from skeleton.persistence.spine_runtime_activation_handoff_verify import (
    SpineRuntimeActivationHandoffVerify,
    SpineRuntimeActivationHandoffVerifyError,
)


NOW = datetime(2026, 10, 1, 16, 40, tzinfo=timezone.utc)


def _boundary() -> dict[str, object]:
    return {
        "kind": "spine_runtime_activation_boundary_witness",
        "digest": "b" * 64,
        "commitment_id": "c" * 64,
        "activation_boundary_verified": True,
        "runtime_driver_selected": True,
        "runtime_object_replaced": False,
        "dispatcher_called": False,
        "dispatcher_running": False,
        "fence_moved": False,
        "runtime_activated": False,
    }


def _boundary_verify() -> dict[str, object]:
    return {
        "kind": "spine_runtime_activation_boundary_verify",
        "boundary_digest": "b" * 64,
        "verified": True,
        "activation_boundary_verified": True,
        "runtime_driver_selected": True,
        "dispatcher_running": False,
        "fence_moved": False,
        "runtime_object_replaced": False,
        "runtime_activated": False,
    }


def _receipt() -> dict[str, object]:
    return {
        "kind": "spine_runtime_deployment_receipt",
        "authority_domain": "runtime-deployment",
        "decision": "accept-handoff",
        "boundary_digest": "b" * 64,
        "target_driver": "pymongo-async",
        "deployment_id": "p2-runtime-deployment-001",
        "handoff_nonce": "n" * 64,
        "issued_at": (NOW - timedelta(seconds=30)).isoformat(),
        "expires_at": (NOW + timedelta(minutes=2)).isoformat(),
        "attestation_digest": "a" * 64,
    }


def test_authenticated_deployment_receipt_creates_non_activating_handoff() -> None:
    card = SpineRuntimeActivationHandoff().qualify(
        boundary=_boundary(),
        boundary_verify=_boundary_verify(),
        receipt=_receipt(),
        authenticate=lambda receipt: receipt["attestation_digest"] == "a" * 64,
        now=NOW,
    )
    verified = SpineRuntimeActivationHandoffVerify().verify(card)

    assert card["handoff_ready"] is True
    assert card["deployment_receipt_authenticated"] is True
    assert card["runtime_driver_selected"] is True
    assert card["dispatcher_started"] is False
    assert card["dispatcher_running"] is False
    assert card["fence_moved"] is False
    assert card["runtime_activated"] is False
    assert verified["verified"] is True


def test_handoff_rejects_scope_drift_or_auth_failure() -> None:
    receipt = _receipt()
    receipt["boundary_digest"] = "x" * 64
    with pytest.raises(SpineRuntimeActivationHandoffError, match="scope mismatch"):
        SpineRuntimeActivationHandoff().qualify(
            boundary=_boundary(),
            boundary_verify=_boundary_verify(),
            receipt=receipt,
            authenticate=lambda receipt: True,
            now=NOW,
        )

    with pytest.raises(SpineRuntimeActivationHandoffError, match="not externally authenticated"):
        SpineRuntimeActivationHandoff().qualify(
            boundary=_boundary(),
            boundary_verify=_boundary_verify(),
            receipt=_receipt(),
            authenticate=lambda receipt: False,
            now=NOW,
        )


def test_handoff_verifier_rejects_activation_or_digest_tamper() -> None:
    card = SpineRuntimeActivationHandoff().qualify(
        boundary=_boundary(),
        boundary_verify=_boundary_verify(),
        receipt=_receipt(),
        authenticate=lambda receipt: True,
        now=NOW,
    )

    activated = copy.deepcopy(card)
    activated["runtime_activated"] = True
    with pytest.raises(SpineRuntimeActivationHandoffVerifyError, match="runtime_activated"):
        SpineRuntimeActivationHandoffVerify().verify(activated)

    tampered = copy.deepcopy(card)
    tampered["deployment_id"] = "changed"
    with pytest.raises(SpineRuntimeActivationHandoffVerifyError, match="digest mismatch"):
        SpineRuntimeActivationHandoffVerify().verify(tampered)
