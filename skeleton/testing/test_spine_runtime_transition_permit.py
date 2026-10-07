from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from skeleton.persistence.spine_runtime_transition_permit import (
    SpineRuntimeTransitionPermitError,
    SpineRuntimeTransitionPermitLedger,
)
from skeleton.persistence.spine_runtime_transition_permit_verify import SpineRuntimeTransitionPermitVerify


NOW=datetime(2026,10,1,16,40,tzinfo=timezone.utc)


def _rehearsal() -> dict[str, object]:
    return {
        "kind":"spine_runtime_transition_rehearsal",
        "digest":"r"*64,
        "transition_id":"t"*64,
        "deployment_id":"deploy-a",
        "target_driver":"pymongo-async",
        "transition_rehearsed":True,
        "transition_attempted":False,
        "transition_executed":False,
        "runtime_driver_selected":True,
        "runtime_object_replaced":False,
        "dispatcher_called":False,
        "dispatcher_running":False,
        "fence_moved":False,
        "runtime_activated":False,
    }


def _rehearsal_verify() -> dict[str, object]:
    return {
        "kind":"spine_runtime_transition_rehearsal_verify",
        "rehearsal_digest":"r"*64,
        "transition_id":"t"*64,
        "verified":True,
        "transition_rehearsed":True,
        "transition_attempted":False,
        "transition_executed":False,
        "runtime_driver_selected":True,
        "runtime_activated":False,
    }


def _receipt() -> dict[str, object]:
    return {
        "kind":"spine_runtime_transition_execution_receipt",
        "authority_domain":"runtime-transition-execution",
        "decision":"permit-transition",
        "rehearsal_digest":"r"*64,
        "transition_id":"t"*64,
        "deployment_id":"deploy-a",
        "target_driver":"pymongo-async",
        "execution_nonce":"n"*64,
        "issued_at":(NOW-timedelta(seconds=10)).isoformat(),
        "expires_at":(NOW+timedelta(seconds=60)).isoformat(),
        "attestation_digest":"a"*64,
    }


def test_external_execution_authority_issues_non_executing_transition_permit() -> None:
    ledger=SpineRuntimeTransitionPermitLedger()
    try:
        card=ledger.issue(
            rehearsal=_rehearsal(),
            rehearsal_verify=_rehearsal_verify(),
            receipt=_receipt(),
            authenticate=lambda receipt: receipt["attestation_digest"]=="a"*64,
            now=NOW,
        )
        verified=SpineRuntimeTransitionPermitVerify().verify(card)
        assert ledger.count()==1
        assert card["transition_authorized"] is True
        assert card["permit_consumed"] is False
        assert card["transition_attempted"] is False
        assert card["transition_executed"] is False
        assert card["runtime_activated"] is False
        assert verified["verified"] is True
    finally:
        ledger.close()


def test_transition_permit_rejects_replay_and_auth_failure() -> None:
    ledger=SpineRuntimeTransitionPermitLedger()
    try:
        ledger.issue(
            rehearsal=_rehearsal(), rehearsal_verify=_rehearsal_verify(),
            receipt=_receipt(), authenticate=lambda receipt: True, now=NOW,
        )
        with pytest.raises(SpineRuntimeTransitionPermitError,match="replay or nonce reuse"):
            ledger.issue(
                rehearsal=_rehearsal(), rehearsal_verify=_rehearsal_verify(),
                receipt=_receipt(), authenticate=lambda receipt: True, now=NOW,
            )
    finally:
        ledger.close()

    ledger=SpineRuntimeTransitionPermitLedger()
    try:
        with pytest.raises(SpineRuntimeTransitionPermitError,match="not externally authenticated"):
            ledger.issue(
                rehearsal=_rehearsal(), rehearsal_verify=_rehearsal_verify(),
                receipt=_receipt(), authenticate=lambda receipt: False, now=NOW,
            )
    finally:
        ledger.close()
