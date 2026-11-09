from skeleton.simulation.plan_simulation import *
def test_receipt_is_never_production_evidence():assert not simulate(("a",),("happy",)).production_evidence
def test_failure_timeout_resource_are_exercised():
 r=simulate(("a",),("failure","timeout","resource"));assert len(r.findings)==3 and all(x.outcome=="failed" for x in r.steps)

def test_production_evidence_cannot_be_injected():
 import pytest
 with pytest.raises(TypeError):PlanSimulation((),(),True)
def test_unknown_scenario_fails_closed():assert simulate(("a",),("novel",)).steps[0].outcome=="failed"

def test_duplicate_steps_and_empty_scenarios_rejected():
 import pytest
 with pytest.raises(ValueError):simulate(("a","a"),("success",))
 with pytest.raises(ValueError):simulate(("a",),())
