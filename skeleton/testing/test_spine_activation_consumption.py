from __future__ import annotations
from datetime import datetime, timedelta, timezone
import pytest
from skeleton.persistence.spine_activation_permit import SpineActivationPermitError, SpineActivationPermitLedger
from skeleton.persistence.spine_activation_permit_verify import SpineActivationPermitVerify
from skeleton.persistence.spine_activation_consumption_verify import SpineActivationConsumptionVerify

NOW=datetime(2026,10,1,16,30,tzinfo=timezone.utc)

def _gate():
    return {"kind":"spine_runtime_activation_gate","digest":"g"*64,"activation_eligible":True,"runtime_driver_selected":True,
            "runtime_object_replaced":False,"dispatcher_started":False,"runtime_activated":False}
def _gate_verify():
    return {"kind":"spine_runtime_activation_gate_verify","activation_gate_digest":"g"*64,"verified":True,
            "activation_eligible":True,"runtime_driver_selected":True,"runtime_object_replaced":False,
            "dispatcher_started":False,"runtime_activated":False}
def _receipt():
    return {"kind":"spine_activation_control_receipt","authority_domain":"activation-control","decision":"permit-activation",
            "activation_gate_digest":"g"*64,"target_driver":"pymongo-async","activation_nonce":"n"*64,
            "issued_at":(NOW-timedelta(seconds=30)).isoformat(),"expires_at":(NOW+timedelta(minutes=2)).isoformat(),
            "attestation_digest":"a"*64}

def _issued(ledger):
    card=ledger.issue(activation_gate=_gate(),activation_gate_verify=_gate_verify(),receipt=_receipt(),
                      authenticate=lambda r:True,now=NOW)
    return card,SpineActivationPermitVerify().verify(card)

def test_activation_permit_consumes_once_without_runtime_transition():
    ledger=SpineActivationPermitLedger()
    try:
        permit,verified=_issued(ledger)
        card=ledger.consume(permit=permit,permit_verify=verified,now=NOW+timedelta(seconds=1))
        checked=SpineActivationConsumptionVerify().verify(card)
        assert ledger.consumed_count()==1
        assert card["permit_consumed"] is True
        assert card["runtime_activated"] is False
        assert checked["verified"] is True
        with pytest.raises(SpineActivationPermitError,match="replay refused"):
            ledger.consume(permit=permit,permit_verify=verified,now=NOW+timedelta(seconds=2))
    finally: ledger.close()

def test_activation_permit_expiry_blocks_consumption():
    ledger=SpineActivationPermitLedger()
    try:
        permit,verified=_issued(ledger)
        with pytest.raises(SpineActivationPermitError,match="expired before consumption"):
            ledger.consume(permit=permit,permit_verify=verified,now=NOW+timedelta(minutes=3))
        assert ledger.consumed_count()==0
    finally: ledger.close()
