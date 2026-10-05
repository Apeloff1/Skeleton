import pytest
from skeleton.artifacts.rebuild import *
def step():return RebuildStep("a","producer:v1",("in1",),"out")
def test_only_verified_inputs_and_producer_version_are_used():
 seen=[];e=execute_rebuild(RebuildPlan((step(),)),{"in1"},lambda a,v,i:(seen.append(v) or "out"));assert e[0].verified and seen==["producer:v1"]
def test_unverified_input_or_digest_mismatch_fails_closed():
 with pytest.raises(PermissionError):execute_rebuild(RebuildPlan((step(),)),set(),lambda *x:"out")
 with pytest.raises(ValueError):execute_rebuild(RebuildPlan((step(),)),{"in1"},lambda *x:"wrong")
def test_cascade_is_bounded():
 with pytest.raises(ValueError):execute_rebuild(RebuildPlan((step(),step()),1),{"in1"},lambda *x:"out")
