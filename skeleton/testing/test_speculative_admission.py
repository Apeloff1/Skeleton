import pytest
from skeleton.ai.speculative_inference import SpeculativePlan
from skeleton.ai.speculative_admission import SpeculationEvidence,admit_speculation
P=SpeculativePlan("draft","target",8)
def test_admits_evaluated_pair():assert admit_speculation(P,SpeculationEvidence("draft->target",True,-.01,.7),max_quality_loss=.02,max_cost_ratio=.8)==P
def test_rejects_unevaluated_pair():
 with pytest.raises(PermissionError,match="evidence"):admit_speculation(P,SpeculationEvidence("draft->target",False,0,.5),max_quality_loss=.02,max_cost_ratio=.8)
def test_rejects_quality_regression():
 with pytest.raises(PermissionError,match="quality"):admit_speculation(P,SpeculationEvidence("draft->target",True,-.2,.5),max_quality_loss=.02,max_cost_ratio=.8)
