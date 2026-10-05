from __future__ import annotations

from skeleton.ai.runtime.deferred.component_provider_assurance import assess_provider_risk
from skeleton.ai.runtime.deferred.research_evaluation import ProviderRisk

A="a"*64

def test_provider_risk_binds_dependency_map_and_failover_class()->None:
    evidence=assess_provider_risk(
        ProviderRisk("provider-a",0.2,("public",),("eu",),True),
        dependency_digests=(A,),failover_class="text-compatible",max_risk=0.3,
    )
    assert evidence.risk_acceptable is True
    assert evidence.failover_class=="text-compatible"
    assert evidence.blockers==()

def test_provider_risk_blocks_unavailable_or_over_policy_provider()->None:
    evidence=assess_provider_risk(
        ProviderRisk("provider-a",0.8,("public",),("eu",),False),
        dependency_digests=(A,),failover_class="text-compatible",max_risk=0.3,
    )
    assert evidence.risk_acceptable is False
    assert evidence.blockers==("provider-unavailable","risk-above-policy")
