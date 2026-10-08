"""Regressions for immutable preregistered mechanic trials."""
import sqlite3,pytest
from skeleton.ai.webcrawler.dragon_trial_ledger import (
 DragonTrialLedger,TrialAssignment,TrialObservation)
from skeleton.ai.webcrawler.dragon_mechanic_causal_analysis import analyze_mechanic_trials


def registered():
    l=DragonTrialLedger(sqlite3.connect(":memory:"))
    a=tuple(TrialAssignment(f"t{i}",i%2==0,"ctx",f"s{i%2}") for i in range(20))
    p=l.preregister("u",hypothesis_id="h",mechanic="jump",assignments=a,
        outcome_definition="binary displacement threshold",registered_at=10,authorized=True)
    return l,p,a


def test_outcome_cannot_predate_preregistration():
    l,p,_=registered()
    with pytest.raises(ValueError,match="follow preregistration"):
        l.observe("u",p.protocol_id,TrialObservation("t0",True,9,"a"*64),authorized=True)


def test_unassigned_trial_cannot_be_injected():
    l,p,_=registered()
    with pytest.raises(ValueError,match="no preregistered"):
        l.observe("u",p.protocol_id,TrialObservation("evil",True,11,"a"*64),authorized=True)


def test_observation_is_immutable():
    l,p,_=registered(); o=TrialObservation("t0",True,11,"a"*64)
    l.observe("u",p.protocol_id,o,authorized=True)
    with pytest.raises(ValueError,match="immutable"):
        l.observe("u",p.protocol_id,TrialObservation("t0",False,12,"b"*64),authorized=True)


def test_complete_ledger_materializes_verified_protocol():
    l,p,a=registered()
    for i,x in enumerate(a):
        l.observe("u",p.protocol_id,TrialObservation(x.trial_id,x.intervention,
            11+i,"a"*64),authorized=True)
    trials,protocol=l.materialize("u",p.protocol_id,authorized=True)
    effect=analyze_mechanic_trials(trials,authorized=True,protocol=protocol)
    assert protocol.attrition_accounted and protocol.interference_assessed
    assert effect.randomized_effect_estimate_eligible
    assert effect.causal_claim_permitted


def test_incomplete_outcomes_do_not_verify_protocol():
    l,p,_=registered()
    l.observe("u",p.protocol_id,TrialObservation("t0",True,11,"a"*64),authorized=True)
    trials,protocol=l.materialize("u",p.protocol_id,authorized=True)
    assert not protocol.attrition_accounted
    assert not protocol.interference_assessed
