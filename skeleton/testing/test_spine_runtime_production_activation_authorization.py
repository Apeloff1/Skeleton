from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
import hashlib
import json

import pytest

from skeleton.persistence.spine_runtime_production_activation_authorization import (
    SpineRuntimeProductionActivationAuthorizationError,
    SpineRuntimeProductionActivationAuthorizationLedger,
)
from skeleton.persistence.spine_runtime_production_activation_authorization_verify import (
    SpineRuntimeProductionActivationAuthorizationVerify,
    SpineRuntimeProductionActivationAuthorizationVerifyError,
)
from skeleton.persistence.spine_runtime_transition_acceptance_verify import (
    SpineRuntimeTransitionAcceptanceVerify,
)


NOW = datetime(2026, 10, 1, 18, 10, tzinfo=timezone.utc)


def _digest(payload: dict[str, object]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _acceptance() -> dict[str, object]:
    health_digest = "h" * 64
    execution_id = "e" * 64
    deployment_id = "deploy-a"
    nonce = "n" * 64
    acceptance_id = hashlib.sha256(
        (
            f"{health_digest}|{execution_id}|{deployment_id}|"
            f"{nonce}|pymongo-async"
        ).encode("utf-8")
    ).hexdigest()
    evidence: dict[str, object] = {
        "acceptance_id": acceptance_id,
        "health_digest": health_digest,
        "execution_id": execution_id,
        "deployment_id": deployment_id,
        "acceptance_nonce": nonce,
        "target_driver": "pymongo-async",
        "accepted_at": NOW.isoformat(),
        "valid_until": (NOW + timedelta(seconds=90)).isoformat(),
        "acceptance_authenticated": True,
        "health_qualified": True,
        "operation_continuity": True,
        "activation_accepted": True,
        "production_activation_authorized": False,
        "rollback_available": True,
        "runtime_activated": False,
    }
    return {
        "kind": "spine_runtime_transition_acceptance",
        "hit": True,
        "law": "external-health-acceptance-does-not-self-authorize-activation",
        "citation": "VOL-134",
        **evidence,
        "digest": _digest(evidence),
        "stored_prose": 0,
        "completion_checkbox": False,
        "implementation_signature": False,
        "verification_signature": False,
    }


def _acceptance_verify() -> dict[str, object]:
    return SpineRuntimeTransitionAcceptanceVerify().verify(_acceptance())


def _receipt() -> dict[str, object]:
    acceptance = _acceptance()
    return {
        "kind": "spine_runtime_production_activation_receipt",
        "authority_domain": "runtime-production-activation",
        "decision": "authorize-production-activation",
        "acceptance_digest": acceptance["digest"],
        "acceptance_id": acceptance["acceptance_id"],
        "execution_id": acceptance["execution_id"],
        "deployment_id": acceptance["deployment_id"],
        "target_driver": "pymongo-async",
        "authorization_nonce": "u" * 64,
        "issued_at": (NOW - timedelta(seconds=10)).isoformat(),
        "expires_at": (NOW + timedelta(seconds=60)).isoformat(),
        "attestation_digest": "t" * 64,
    }


def test_external_authorization_is_durable_without_activation() -> None:
    ledger = SpineRuntimeProductionActivationAuthorizationLedger()
    try:
        card = ledger.authorize(
            acceptance=_acceptance(),
            acceptance_verify=_acceptance_verify(),
            receipt=_receipt(),
            authenticate=lambda receipt: receipt["attestation_digest"] == "t" * 64,
            now=NOW,
        )
        verified = SpineRuntimeProductionActivationAuthorizationVerify().verify(
            card
        )

        assert ledger.count() == 1
        assert card["authorization_authenticated"] is True
        assert card["production_activation_authorized"] is True
        assert card["rollback_available"] is True
        assert card["runtime_activated"] is False
        assert verified["verified"] is True

        with pytest.raises(
            SpineRuntimeProductionActivationAuthorizationError,
            match="replay or nonce reuse",
        ):
            ledger.authorize(
                acceptance=_acceptance(),
                acceptance_verify=_acceptance_verify(),
                receipt=_receipt(),
                authenticate=lambda receipt: True,
                now=NOW,
            )
    finally:
        ledger.close()


def test_authorization_rejects_lost_rollback_boundary() -> None:
    acceptance = _acceptance()
    acceptance["rollback_available"] = False
    ledger = SpineRuntimeProductionActivationAuthorizationLedger()
    try:
        with pytest.raises(
            SpineRuntimeProductionActivationAuthorizationError,
            match="verified transition acceptance is required",
        ):
            ledger.authorize(
                acceptance=acceptance,
                acceptance_verify=_acceptance_verify(),
                receipt=_receipt(),
                authenticate=lambda receipt: True,
                now=NOW,
            )
    finally:
        ledger.close()


def test_authorization_rejects_stale_verified_acceptance_scope() -> None:
    acceptance = _acceptance()
    acceptance["deployment_id"] = "deploy-b"
    receipt = _receipt()
    receipt["deployment_id"] = "deploy-b"
    ledger = SpineRuntimeProductionActivationAuthorizationLedger()
    try:
        with pytest.raises(
            SpineRuntimeProductionActivationAuthorizationError,
            match="current transition acceptance verification failed closed",
        ):
            ledger.authorize(
                acceptance=acceptance,
                acceptance_verify=_acceptance_verify(),
                receipt=receipt,
                authenticate=lambda receipt: True,
                now=NOW,
            )
    finally:
        ledger.close()


def test_authorization_rejects_auth_failure_and_activation_tamper() -> None:
    ledger = SpineRuntimeProductionActivationAuthorizationLedger()
    try:
        with pytest.raises(
            SpineRuntimeProductionActivationAuthorizationError,
            match="not externally authenticated",
        ):
            ledger.authorize(
                acceptance=_acceptance(),
                acceptance_verify=_acceptance_verify(),
                receipt=_receipt(),
                authenticate=lambda receipt: False,
                now=NOW,
            )

        card = ledger.authorize(
            acceptance=_acceptance(),
            acceptance_verify=_acceptance_verify(),
            receipt=_receipt(),
            authenticate=lambda receipt: True,
            now=NOW,
        )
        tampered = copy.deepcopy(card)
        tampered["runtime_activated"] = True
        with pytest.raises(
            SpineRuntimeProductionActivationAuthorizationVerifyError,
            match="cannot self-activate",
        ):
            SpineRuntimeProductionActivationAuthorizationVerify().verify(
                tampered
            )
    finally:
        ledger.close()
