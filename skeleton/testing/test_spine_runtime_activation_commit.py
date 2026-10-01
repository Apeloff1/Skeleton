from __future__ import annotations
from datetime import datetime,timezone
import pytest
from skeleton.persistence.spine_runtime_activation_commit import SpineRuntimeActivationCommitError,SpineRuntimeActivationCommitLedger
from skeleton.persistence.spine_runtime_activation_commit_verify import SpineRuntimeActivationCommitVerify

NOW=datetime(2026,10,1,16,31,tzinfo=timezone.utc)

def _consumption():
    return {"kind":"spine_activation_consumption","digest":"c"*64,"permit_id":"p"*64,"target_driver":"pymongo-async",
            "activation_authorized":True,"permit_consumed":True,"runtime_driver_selected":True,
            "runtime_object_replaced":False,"dispatcher_started":False,"runtime_activated":False}

def _verify():
    return {"kind":"spine_activation_consumption_verify","consumption_digest":"c"*64,"permit_id":"p"*64,
            "verified":True,"activation_authorized":True,"permit_consumed":True,"runtime_driver_selected":True,
            "runtime_object_replaced":False,"dispatcher_started":False,"runtime_activated":False}

def test_consumed_activation_permit_creates_nonactivating_commitment():
    ledger=SpineRuntimeActivationCommitLedger()
    try:
        card=ledger.commit(consumption=_consumption(),consumption_verify=_verify(),now=NOW)
        checked=SpineRuntimeActivationCommitVerify().verify(card)
        assert ledger.count()==1
        assert card["activation_committed"] is True
        assert card["runtime_activated"] is False
        assert checked["verified"] is True
    finally: ledger.close()

def test_activation_commitment_replay_and_bad_verification_fail_closed():
    ledger=SpineRuntimeActivationCommitLedger()
    try:
        ledger.commit(consumption=_consumption(),consumption_verify=_verify(),now=NOW)
        with pytest.raises(SpineRuntimeActivationCommitError,match="replay refused"):
            ledger.commit(consumption=_consumption(),consumption_verify=_verify(),now=NOW)
    finally: ledger.close()
    bad=_verify(); bad["verified"]=False
    ledger=SpineRuntimeActivationCommitLedger()
    try:
        with pytest.raises(SpineRuntimeActivationCommitError,match="independent"):
            ledger.commit(consumption=_consumption(),consumption_verify=bad,now=NOW)
    finally: ledger.close()
