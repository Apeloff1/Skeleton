from __future__ import annotations
import pytest
from skeleton.automation.technology_radar import *
def c():return TechnologyCandidate("TECH.1","evaluate deterministic store","BASELINE.1","OWNER.ARCH",100,20,TechnologyExitCriteria(100,5,20))
def test_candidate_must_experiment_before_adoption():
 r=TechnologyRadar((c(),))
 with pytest.raises(RadarError,match="transition"):r.decide(RadarDecision("TECH.1",RadarState.ADOPTED,("EVID.1",),"ADR.1"),1)
def test_adoption_requires_evidence_and_architecture_decision():
 with pytest.raises(RadarError,match="requires evidence"):RadarDecision("TECH.1",RadarState.ADOPTED,(),None)
def test_evidence_gated_experiment_can_be_adopted():
 r=TechnologyRadar((c(),));r.decide(RadarDecision("TECH.1",RadarState.EXPERIMENT,()),1);assert r.decide(RadarDecision("TECH.1",RadarState.ADOPTED,("EVID.1",),"ADR.1"),2) is RadarState.ADOPTED
def test_stale_experiment_cannot_become_permanent():
 r=TechnologyRadar((c(),));r.decide(RadarDecision("TECH.1",RadarState.EXPERIMENT,()),1)
 with pytest.raises(RadarError,match="horizon expired"):r.decide(RadarDecision("TECH.1",RadarState.ADOPTED,("EVID.1",),"ADR.1"),21)
def test_adopted_technology_has_retirement_path():
 r=TechnologyRadar((c(),));r.decide(RadarDecision("TECH.1",RadarState.EXPERIMENT,()),1);r.decide(RadarDecision("TECH.1",RadarState.ADOPTED,("EVID.1",),"ADR.1"),2);assert r.decide(RadarDecision("TECH.1",RadarState.RETIRED,("EVID.EXIT",)),3) is RadarState.RETIRED
