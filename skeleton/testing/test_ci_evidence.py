import pytest
from skeleton.automation.ci_evidence import Gate,CIEvidence,from_workflow_runs
def test_green_exact_head():
 e=CIEvidence("a"*40,(Gate("CI/CD","completed","success",1),),("CI/CD",));assert e.green() and len(e.digest())==64
def test_pending_not_green():
 assert not CIEvidence("a"*40,(Gate("CI/CD","pending",None,1),),("CI/CD",)).green()
def test_missing_required_fails():
 with pytest.raises(ValueError):CIEvidence("a"*40,(),("CI/CD",)).green()

def test_latest_run_wins_per_gate():
 runs=(
  {"id":1,"name":"CI/CD","status":"completed","conclusion":"failure"},
  {"id":2,"name":"CI/CD","status":"completed","conclusion":"success"},
 )
 e=from_workflow_runs("a"*40,runs,("CI/CD",))
 assert e.green() and e.gates[0].run_id==2
