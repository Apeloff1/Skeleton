import pytest
from skeleton.eval.benchmark_plugins import *
def p(rights=True):return BenchmarkPlugin(BenchmarkManifest("b","v1","d",rights,2),"safe")
def test_identity_binds_version_and_dataset():assert admit(p(),1,{"safe"}).plugin_identity=="b@v1"
def test_controls_cannot_be_bypassed():
 for x,r,a in ((p(False),1,{"safe"}),(p(),3,{"safe"}),(p(),1,{"other"})):
  with pytest.raises(PermissionError):admit(x,r,a)

def test_boolean_or_zero_resource_request_rejected():
 import pytest
 p=BenchmarkPlugin(BenchmarkManifest("p","1","d",True,2),"ep")
 with pytest.raises(ValueError):admit(p,True,{"ep"})
 with pytest.raises(ValueError):admit(p,0,{"ep"})
