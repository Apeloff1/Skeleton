from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone

import pytest

from skeleton.persistence.spine_runtime_production_activation_authorization import (
    SpineRuntimeProductionActivationAuthorizationError,
    SpineRuntimeProductionActivationAuthorizationLedger,
)
from skeleton.persistence.spine_runtime_production_activation_authorization_verify import (
    SpineRuntimeProductionActivationAuthorizationVerify,
    SpineRuntimeProductionActivationAuthorizationVerifyError,
)


NOW = datetime(2026, 10, 1, 18, 10, tzinfo=timezone.utc)


def _acceptance() -> dict[str, object]:
    return {
        "kind": "spine_runtime_transition_acceptance",
        "digest": "d" * 64,
        "acceptance_id": "a" * 64,
        "health_digest": "h" * 64,
        "execution_id": "e" * 64,
        "deployment_id": "deploy-a",
        "target_driver": "pymongo-async",
        "acceptance_authenticated": True,
        "activation_accepted": True,
        "production_activation_authorized": False,
        "rollback_available": True,
        "runtime_activated": False,
    }


def _acceptance_verify() -> dict[str, object]:
    return {
        "kind": "spine_runtime_transition_acceptance_verify",
        "acceptance_id": "a" * 64,
        "acceptance_digest": "d" * 64,
        "execution_id": "e" * 64,
        "verified": True,
        "activation_accepted": True,
        "production_activation_authorized": False,
        "rollback_available": True,
        "runtime_activated": False,
    }


def _receipt() -> dict[str, object]:
    return {
        "kind": "spine_runtime_production_activation_receipt",
        "authority_domain": "runtime-production-activation",
        "decision": "authorize-production-activation",
        "acceptance_digest": "d" * 64,
        "acceptance_id": "a" * 64,
        "execution_id": "e" * 64,
        "deployment_id": "deploy-a",
        "target_driver": "pymongo-async",
        "authorization_nonce": "n" * 64,
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
