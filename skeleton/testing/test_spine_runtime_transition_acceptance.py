from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone

import pytest

from skeleton.persistence.spine_runtime_transition_acceptance import (
    SpineRuntimeTransitionAcceptanceError,
    SpineRuntimeTransitionAcceptanceLedger,
)
from skeleton.persistence.spine_runtime_transition_acceptance_verify import (
    SpineRuntimeTransitionAcceptanceVerify,
    SpineRuntimeTransitionAcceptanceVerifyError,
)


NOW = datetime(2026, 10, 1, 18, 0, tzinfo=timezone.utc)


def _health() -> dict[str, object]:
    return {
        "kind": "spine_runtime_transition_health",
        "digest": "h" * 64,
        "execution_id": "e" * 64,
        "deployment_id": "deploy-a",
        "target_driver": "pymongo-async",
        "health_qualified": True,
        "operation_continuity": True,
        "dispatcher_running": True,
        "fence_stable": True,
        "rollback_available": True,
        "runtime_activated": False,
    }


def _health_verify() -> dict[str, object]:
    return {
        "kind": "spine_runtime_transition_health_verify",
        "health_digest": "h" * 64,
        "execution_id": "e" * 64,
        "deployment_id": "deploy-a",
        "target_driver": "pymongo-async",
        "verified": True,
        "health_qualified": True,
        "operation_continuity": True,
        "dispatcher_running": True,
        "fence_stable": True,
        "rollback_available": True,
        "runtime_activated": False,
    }


def _receipt() -> dict[str, object]:
    return {
        "kind": "spine_runtime_transition_acceptance_receipt",
        "authority_domain": "runtime-transition-acceptance",
        "decision": "accept-transition-health",
        "health_digest": "h" * 64,
        "execution_id": "e" * 64,
        "deployment_id": "deploy-a",
        "target_driver": "pymongo-async",
        "acceptance_nonce": "n" * 64,
        "issued_at": (NOW - timedelta(seconds=10)).isoformat(),
        "expires_at": (NOW + timedelta(seconds=60)).isoformat(),
        "attestation_digest": "a" * 64,
    }


def test_external_acceptance_is_durable_but_non_authorizing() -> None:
    ledger = SpineRuntimeTransitionAcceptanceLedger()
    try:
        card = ledger.accept(
            health=_health(),
            health_verify=_health_verify(),
            receipt=_receipt(),
            authenticate=lambda receipt: receipt["attestation_digest"] == "a" * 64,
            now=NOW,
        )
        verified = SpineRuntimeTransitionAcceptanceVerify().verify(card)

        assert ledger.count() == 1
        assert card["acceptance_authenticated"] is True
        assert card["activation_accepted"] is True
        assert card["production_activation_authorized"] is False
        assert card["rollback_available"] is True
        assert card["runtime_activated"] is False
        assert verified["verified"] is True

        with pytest.raises(
            SpineRuntimeTransitionAcceptanceError,
            match="replay or nonce reuse",
        ):
            ledger.accept(
                health=_health(),
                health_verify=_health_verify(),
                receipt=_receipt(),
                authenticate=lambda receipt: True,
                now=NOW,
            )
    finally:
        ledger.close()


def test_acceptance_rejects_auth_failure_and_activation_tamper() -> None:
    ledger = SpineRuntimeTransitionAcceptanceLedger()
    try:
        with pytest.raises(
            SpineRuntimeTransitionAcceptanceError,
            match="not externally authenticated",
        ):
            ledger.accept(
                health=_health(),
                health_verify=_health_verify(),
                receipt=_receipt(),
                authenticate=lambda receipt: False,
                now=NOW,
            )

        card = ledger.accept(
            health=_health(),
            health_verify=_health_verify(),
            receipt=_receipt(),
            authenticate=lambda receipt: True,
            now=NOW,
        )
        tampered = copy.deepcopy(card)
        tampered["production_activation_authorized"] = True
        with pytest.raises(
            SpineRuntimeTransitionAcceptanceVerifyError,
            match="cannot authorize production activation",
        ):
            SpineRuntimeTransitionAcceptanceVerify().verify(tampered)
    finally:
        ledger.close()
