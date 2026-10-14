from __future__ import annotations
import hashlib,pytest
from skeleton.ai.providers.failover import ProviderCompatibility,ProviderFailoverError,ProviderHealth,choose_failover
def d(x): return hashlib.sha256(x.encode()).hexdigest()
def test_failover_selects_lowest_risk_compatible_provider():
    requested=ProviderCompatibility("p0","chat",("vision","tools"),100000)
    candidates=(ProviderCompatibility("p1","chat",("vision","tools"),100000),ProviderCompatibility("p2","chat",("vision","tools"),100000))
    health=(ProviderHealth("p1",True,d("h1"),200000),ProviderHealth("p2",True,d("h2"),100000))
    decision=choose_failover(requested=requested,candidates=candidates,health=health,required_features=("vision","tools"),required_context_tokens=50000)
    assert decision.selected_provider_id=="p2" and decision.capability_expansion is False
def test_incompatible_providers_fail_closed():
    requested=ProviderCompatibility("p0","chat",("tools",),1000)
    decision=choose_failover(requested=requested,candidates=(ProviderCompatibility("p1","chat",("text",),1000),),health=(ProviderHealth("p1",True,d("h"),0),),required_features=("tools",),required_context_tokens=100)
    assert decision.selected_provider_id is None
def test_failover_cannot_expand_capability():
    from skeleton.ai.providers.failover import FailoverDecision
    with pytest.raises(ProviderFailoverError,match="expand capability"):
        FailoverDecision("p0","p1","chat",(),True)
