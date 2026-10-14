from __future__ import annotations
import hashlib,pytest
from skeleton.ai.runtime.deployment_profiles import DeploymentProfileError,EdgeDeploymentProfile,EdgeResourceTier
def d(x): return hashlib.sha256(x.encode()).hexdigest()
def test_edge_profile_binds_resource_tier_and_router_constraints():
    tier=EdgeResourceTier("edge-small",8192,65536,"cpu",32768)
    p=EdgeDeploymentProfile("edge",tier,("local-small","local-medium"),d("router"),True,True)
    assert p.resource_tier.max_context_tokens==32768 and len(p.digest)==64
def test_edge_tier_requires_positive_resources():
    with pytest.raises(DeploymentProfileError,match="positive"):
        EdgeResourceTier("bad",0,1,"cpu",1)
