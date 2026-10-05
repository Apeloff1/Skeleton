from skeleton.observability.reasoning_cost import *
def test_cost_is_attributed_without_reasoning_content():
 r=attribute("op",ReasoningStage("plan","s","m","v1"),2);assert r.operation_id=="op" and not hasattr(r,"content")
def test_report_sums_stage_cost_once():
 r=attribute("op",ReasoningStage("a","s","m","v"),2);assert report((r,))==2

def test_nonfinite_and_duplicate_cost_rejected():
 import pytest,math
 s=ReasoningStage("s","x","m","v")
 with pytest.raises(ValueError):attribute("o",s,math.nan)
 a=attribute("o",s,1)
 with pytest.raises(ValueError):report((a,a))

def test_incomplete_stage_identity_rejected():
 import pytest
 with pytest.raises(ValueError):attribute("o",ReasoningStage("s","","m","v"),1)
