from skeleton.reliability.compensation import *
def test_compensation_never_claims_equivalent_rollback():assert not execute(Compensation("o",(CompensationStep("s","e","refund"),)),lambda x:None).rolled_back
def test_failed_compensation_remains_explicit():
 r=execute(Compensation("o",(CompensationStep("s","e","refund"),)),lambda x:(_ for _ in ()).throw(RuntimeError()));assert r.failed==("s",)
