from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from skeleton.persistence.spine_runtime_transition_permit import (
    SpineRuntimeTransitionPermitError,
    SpineRuntimeTransitionPermitLedger,
)
from skeleton.persistence.spine_runtime_transition_permit_verify import SpineRuntimeTransitionPermitVerify
from skeleton.persistence.spine_runtime_transition_consumption_verify import (
    SpineRuntimeTransitionConsumptionVerify,
)


NOW=datetime(2026,10,1,16,40,tzinfo=timezone.utc)


def _rehearsal() -> dict[str, object]:
    return {
        "kind":"spine_runtime_transition_rehearsal","digest":"r"*64,"transition_id":"t"*64,
        "deployment_id":"deploy-a","target_driver":"pymongo-async","transition_rehearsed":True,
        "transition_attempted":False,"transition_executed":False,"runtime_driver_selected":True,
        "runtime_object_replaced":False,"dispatcher_called":False,"dispatcher_running":False,
        "fence_moved":False,"runtime_activated":False,
    }


def _rehearsal_verify() -> dict[str, object]:
    return {
        "kind":"spine_runtime_transition_rehearsal_verify","rehearsal_digest":"r"*64,
        "transition_id":"t"*64,"verified":True,"transition_rehearsed":True,
        "transition_attempted":False,"transition_executed":False,
        "runtime_driver_selected":True,"runtime_activated":False,
    }


def _receipt() -> dict[str, object]:
    return {
        "kind":"spine_runtime_transition_execution_receipt","authority_domain":"runtime-transition-execution",
        "decision":"permit-transition","rehearsal_digest":"r"*64,"transition_id":"t"*64,
        "deployment_id":"deploy-a","target_driver":"pymongo-async","execution_nonce":"n"*64,
        "issued_at":(NOW-timedelta(seconds=10)).isoformat(),
        "expires_at":(NOW+timedelta(seconds=60)).isoformat(),"attestation_digest":"a"*64,
    }


def _permit(ledger: SpineRuntimeTransitionPermitLedger) -> dict[str, object]:
    return ledger.issue(
        rehearsal=_rehearsal(),rehearsal_verify=_rehearsal_verify(),receipt=_receipt(),
        authenticate=lambda receipt: True,now=NOW,
    )


def test_transition_permit_is_consumed_exactly_once_without_attempt() -> None:
    ledger=SpineRuntimeTransitionPermitLedger()
    try:
        permit=_permit(ledger)
        permit_verify=SpineRuntimeTransitionPermitVerify().verify(permit)
        consumed=ledger.consume(
            permit=permit,permit_verify=permit_verify,now=NOW+timedelta(seconds=1)
        )
        verified=SpineRuntimeTransitionConsumptionVerify().verify(consumed)
        assert ledger.count()==1
        assert ledger.consumed_count()==1
        assert consumed["transition_authorized"] is True
        assert consumed["permit_consumed"] is True
        assert consumed["transition_attempted"] is False
        assert consumed["transition_executed"] is False
        assert consumed["runtime_activated"] is False
        assert verified["verified"] is True

        with pytest.raises(SpineRuntimeTransitionPermitError,match="replay refused"):
            ledger.consume(
                permit=permit,permit_verify=permit_verify,now=NOW+timedelta(seconds=2)
            )
    finally:
        ledger.close()


def test_transition_permit_cannot_be_consumed_after_expiry() -> None:
    ledger=SpineRuntimeTransitionPermitLedger()
    try:
        permit=_permit(ledger)
        permit_verify=SpineRuntimeTransitionPermitVerify().verify(permit)
        with pytest.raises(SpineRuntimeTransitionPermitError,match="expired before consumption"):
            ledger.consume(
                permit=permit,permit_verify=permit_verify,now=NOW+timedelta(minutes=3)
            )
        assert ledger.consumed_count()==0
    finally:
        ledger.close()
