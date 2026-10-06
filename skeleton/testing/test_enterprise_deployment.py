from __future__ import annotations
import hashlib,pytest
from skeleton.ai.runtime.deployment_profiles import DeploymentProfileError,EnterpriseDeploymentProfile,EnterpriseTopology
def d(x): return hashlib.sha256(x.encode()).hexdigest()
def test_enterprise_profile_requires_isolation_audit_and_acceptance():
    topo=EnterpriseTopology("ha",("zone-a","zone-b"),2,True,True)
    p=EnterpriseDeploymentProfile("enterprise",topo,d("boundary"),d("accept"),d("admin"))
    assert p.production_authority is False and len(p.digest)==64
def test_single_zone_topology_rejected():
    with pytest.raises(DeploymentProfileError,match="at least two zones"):
        EnterpriseTopology("bad",("a",),2,True,True)
def test_profile_cannot_self_promote():
    topo=EnterpriseTopology("ha",("a","b"),2,True,True)
    with pytest.raises(DeploymentProfileError,match="cannot grant"):
        EnterpriseDeploymentProfile("e",topo,d("b"),d("a"),d("admin"),True)
