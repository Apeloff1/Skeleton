"""Regressions for immutable preregistered mechanic trials."""
import sqlite3,pytest
from skeleton.ai.webcrawler.dragon_trial_ledger import (
 DragonTrialLedger,TrialAssignment,TrialObservation,expected_randomized_intervention,
 cryptographic_allocation_evidence)
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


def test_complete_ledger_without_design_evidence_is_not_causal():
    l,p,a=registered()
    for i,x in enumerate(a):
        l.observe("u",p.protocol_id,TrialObservation(x.trial_id,x.intervention,
            11+i,"a"*64),authorized=True)
    trials,protocol=l.materialize("u",p.protocol_id,authorized=True)
    effect=analyze_mechanic_trials(trials,authorized=True,protocol=protocol)
    assert protocol.attrition_accounted and not protocol.interference_assessed
    assert not protocol.allocation_verified
    assert not effect.randomized_effect_estimate_eligible
    assert not effect.causal_claim_permitted


def test_incomplete_outcomes_do_not_verify_protocol():
    l,p,_=registered()
    l.observe("u",p.protocol_id,TrialObservation("t0",True,11,"a"*64),authorized=True)
    trials,protocol=l.materialize("u",p.protocol_id,authorized=True)
    assert not protocol.attrition_accounted
    assert not protocol.interference_assessed


def test_independent_design_evidence_enables_causal_eligibility():
 seed="1"*64
 l=DragonTrialLedger(sqlite3.connect(":memory:"))
 a=tuple(TrialAssignment(f"t{i}",expected_randomized_intervention(f"t{i}",seed),
  "ctx",f"s{i%2}") for i in range(40))
 assert {x.intervention for x in a}=={False,True}
 p=l.preregister("u",hypothesis_id="h",mechanic="jump",assignments=a,
  outcome_definition="binary displacement threshold",registered_at=10,authorized=True)
 evidence=cryptographic_allocation_evidence(a,seed)
 l.attest_design("u",p.protocol_id,allocation_method="cryptographic_randomization",
  allocation_evidence_digest=evidence,interference_assessment="none_detected",
  interference_evidence_digest="d"*64,assessed_at=10.5,authorized=True,
  randomization_seed=seed)
 for i,x in enumerate(a):
  l.observe("u",p.protocol_id,TrialObservation(x.trial_id,x.intervention,11+i,"a"*64),authorized=True)
 trials,protocol=l.materialize("u",p.protocol_id,authorized=True)
 effect=analyze_mechanic_trials(trials,authorized=True,protocol=protocol)
 assert protocol.allocation_verified and protocol.interference_assessed
 assert effect.randomized_effect_estimate_eligible and effect.causal_claim_permitted

def test_preregistration_alone_never_claims_randomization():
 l,p,_=registered()
 assert p.preregistered and not p.allocation_verified

def test_design_evidence_is_immutable():
 l,p,_=registered()
 kw=dict(allocation_method="external_randomization",allocation_evidence_digest="c"*64,
  interference_assessment="modeled",interference_evidence_digest="d"*64,assessed_at=10.5,authorized=True)
 l.attest_design("u",p.protocol_id,**kw)
 with pytest.raises(ValueError,match="immutable"):
  l.attest_design("u",p.protocol_id,**{**kw,"allocation_evidence_digest":"e"*64})


def test_claimed_cryptographic_randomization_must_match_assignments():
 l,p,a=registered();seed="2"*64
 with pytest.raises(ValueError,match="assignment does not match"):
  cryptographic_allocation_evidence(a,seed)
 with pytest.raises(ValueError):
  l.attest_design("u",p.protocol_id,allocation_method="cryptographic_randomization",
   allocation_evidence_digest="c"*64,interference_assessment="none_detected",
   interference_evidence_digest="d"*64,assessed_at=10.5,authorized=True,
   randomization_seed=seed)

def test_external_randomization_attestation_does_not_self_verify():
 l,p,a=registered()
 l.attest_design("u",p.protocol_id,allocation_method="external_randomization",
  allocation_evidence_digest="c"*64,interference_assessment="none_detected",
  interference_evidence_digest="d"*64,assessed_at=10.5,authorized=True)
 for i,x in enumerate(a):
  l.observe("u",p.protocol_id,TrialObservation(x.trial_id,x.intervention,11+i,"a"*64),authorized=True)
 _,protocol=l.materialize("u",p.protocol_id,authorized=True)
 assert not protocol.allocation_verified

def test_legacy_design_rows_migrate_as_unverified():
 db=sqlite3.connect(":memory:")
 db.execute("""CREATE TABLE dragon_trial_design_evidence(
  owner TEXT NOT NULL,protocol_id TEXT NOT NULL,allocation_method TEXT NOT NULL,
  allocation_evidence_digest TEXT NOT NULL,interference_assessment TEXT NOT NULL,
  interference_evidence_digest TEXT NOT NULL,assessed_at REAL NOT NULL,
  PRIMARY KEY(owner,protocol_id))""")
 l=DragonTrialLedger(db)
 a=tuple(TrialAssignment(f"t{i}",i%2==0,"ctx",f"s{i%2}") for i in range(4))
 p=l.preregister("u",hypothesis_id="h",mechanic="jump",assignments=a,
  outcome_definition="binary",registered_at=10,authorized=True)
 db.execute("""INSERT INTO dragon_trial_design_evidence(
  owner,protocol_id,allocation_method,allocation_evidence_digest,
  interference_assessment,interference_evidence_digest,assessed_at)
  VALUES(?,?,?,?,?,?,?)""",("u",p.protocol_id,"cryptographic_randomization","c"*64,
  "none_detected","d"*64,10.5));db.commit()
 for i,x in enumerate(a):
  l.observe("u",p.protocol_id,TrialObservation(x.trial_id,x.intervention,11+i,"a"*64),authorized=True)
 _,protocol=l.materialize("u",p.protocol_id,authorized=True)
 assert not protocol.allocation_verified
