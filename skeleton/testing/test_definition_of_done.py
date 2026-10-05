from __future__ import annotations
import hashlib
from skeleton.automation.definition_of_done import *
S=lambda x:hashlib.sha256(x.encode()).hexdigest()
def ev(k,actor="ACTOR.BUILDER"):return CompletionEvidence("EVID."+k.name,k,S(k.value),actor)
def test_low_impact_requires_implementation_test_and_ownership():
 p=canonical_policy();ok,missing=p.evaluate(Impact.LOW,(ev(EvidenceKind.IMPLEMENTATION),ev(EvidenceKind.TEST),ev(EvidenceKind.OWNERSHIP)),"ACTOR.BUILDER");assert ok and not missing
def test_medium_impact_adds_failure_and_observability():
 p=canonical_policy();e=(ev(EvidenceKind.IMPLEMENTATION),ev(EvidenceKind.TEST),ev(EvidenceKind.OWNERSHIP));ok,missing=p.evaluate(Impact.MEDIUM,e,"ACTOR.BUILDER");assert not ok and set(missing)=={"failure","observability"}
def test_high_impact_requires_recovery_rollback_and_independent_verification():
 p=canonical_policy();e=tuple(ev(k,"ACTOR.VERIFIER" if k is EvidenceKind.VERIFICATION else "ACTOR.BUILDER") for k in EvidenceKind);assert p.evaluate(Impact.HIGH,e,"ACTOR.BUILDER")[0]
def test_implementation_actor_cannot_supply_high_impact_verification():
 p=canonical_policy();e=tuple(ev(k) for k in EvidenceKind);assert p.evaluate(Impact.HIGH,e,"ACTOR.BUILDER")== (False,("verification_not_independent",))
def test_missing_evidence_downgrades_completion():
 p=canonical_policy();e=tuple(ev(k,"ACTOR.VERIFIER" if k is EvidenceKind.VERIFICATION else "ACTOR.BUILDER") for k in EvidenceKind if k is not EvidenceKind.ROLLBACK);ok,missing=p.evaluate(Impact.HIGH,e,"ACTOR.BUILDER");assert not ok and missing==("rollback",)
