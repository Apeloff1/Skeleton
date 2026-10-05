from skeleton.reliability.compensation import *
def test_compensation_never_claims_equivalent_rollback():assert not execute(Compensation("o",(CompensationStep("s","e","refund"),)),lambda x:None).rolled_back
def test_failed_compensation_remains_explicit():
 r=execute(Compensation("o",(CompensationStep("s","e","refund"),)),lambda x:(_ for _ in ()).throw(RuntimeError()));assert r.failed==("s",)

def test_compensation_stops_after_failure_and_requires_reconciliation():
 seen=[]
 def fn(s):
  seen.append(s.step_id)
  if s.step_id=="a":raise RuntimeError()
 c=Compensation("o",(CompensationStep("a","e1","x"),CompensationStep("b","e2","y")))
 r=execute(c,fn);assert seen==["a"] and r.reconciliation_required
