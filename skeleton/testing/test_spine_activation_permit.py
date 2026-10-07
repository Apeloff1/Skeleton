from __future__ import annotations

from datetime import datetime, timedelta, timezone
import pytest

from skeleton.persistence.spine_activation_permit import SpineActivationPermitError, SpineActivationPermitLedger
from skeleton.persistence.spine_activation_permit_verify import SpineActivationPermitVerify

NOW=datetime(2026,10,1,16,30,tzinfo=timezone.utc)

def _gate():
    return {"kind":"spine_runtime_activation_gate","digest":"g"*64,"activation_eligible":True,
            "runtime_driver_selected":True,"runtime_object_replaced":False,"dispatcher_started":False,"runtime_activated":False}

def _verify():
    return {"kind":"spine_runtime_activation_gate_verify","activation_gate_digest":"g"*64,"verified":True,
            "activation_eligible":True,"runtime_driver_selected":True,"runtime_object_replaced":False,
            "dispatcher_started":False,"runtime_activated":False}

def _receipt():
    return {"kind":"spine_activation_control_receipt","authority_domain":"activation-control","decision":"permit-activation",
            "activation_gate_digest":"g"*64,"target_driver":"pymongo-async","activation_nonce":"n"*64,
            "issued_at":(NOW-timedelta(seconds=30)).isoformat(),"expires_at":(NOW+timedelta(minutes=2)).isoformat(),
            "attestation_digest":"a"*64}

def test_external_activation_control_issues_nonactivating_permit():
    ledger=SpineActivationPermitLedger()
    try:
        card=ledger.issue(activation_gate=_gate(),activation_gate_verify=_verify(),receipt=_receipt(),
                          authenticate=lambda r:r["attestation_digest"]=="a"*64,now=NOW)
        verified=SpineActivationPermitVerify().verify(card)
        assert ledger.count()==1
        assert card["activation_authorized"] is True
        assert card["permit_consumed"] is False
        assert card["runtime_activated"] is False
        assert verified["verified"] is True
    finally: ledger.close()

def test_activation_permit_replay_and_auth_fail_closed():
    ledger=SpineActivationPermitLedger()
    try:
        ledger.issue(activation_gate=_gate(),activation_gate_verify=_verify(),receipt=_receipt(),authenticate=lambda r:True,now=NOW)
        with pytest.raises(SpineActivationPermitError,match="replay or nonce reuse"):
            ledger.issue(activation_gate=_gate(),activation_gate_verify=_verify(),receipt=_receipt(),authenticate=lambda r:True,now=NOW)
    finally: ledger.close()
    ledger=SpineActivationPermitLedger()
    try:
        with pytest.raises(SpineActivationPermitError,match="not externally authenticated"):
            ledger.issue(activation_gate=_gate(),activation_gate_verify=_verify(),receipt=_receipt(),authenticate=lambda r:False,now=NOW)
    finally: ledger.close()
