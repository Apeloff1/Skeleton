from skeleton.simulation.plan_simulation import *
def test_receipt_is_never_production_evidence():assert not simulate(("a",),("happy",)).production_evidence
def test_failure_timeout_resource_are_exercised():
 r=simulate(("a",),("failure","timeout","resource"));assert len(r.findings)==3 and all(x.outcome=="failed" for x in r.steps)
