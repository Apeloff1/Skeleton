from __future__ import annotations
import hashlib,pytest
from skeleton.ai.providers.provider_risk import ProviderDependency,ProviderRiskError,ProviderRiskAssessment,assess_provider_risk
def d(x): return hashlib.sha256(x.encode()).hexdigest()
def dims(v=100000): return {"availability":v,"security":v,"privacy":v,"regulatory":v,"lock_in":v}
def test_provider_risk_derives_failover_requirement():
    dep=ProviderDependency("p","chat",True,d("contract"))
    result=assess_provider_risk(dependency=dep,dimension_risk_ppm=dims(800000),evidence_digest=d("e"))
    assert result.failover_required is True and result.max_risk_ppm==800000
def test_missing_dimension_fails_closed():
    dep=ProviderDependency("p","chat",True,d("c"))
    with pytest.raises(ProviderRiskError,match="all provider risk dimensions"):
        assess_provider_risk(dependency=dep,dimension_risk_ppm={"availability":1},evidence_digest=d("e"))
def test_risk_assessment_cannot_route():
    with pytest.raises(ProviderRiskError,match="routing authority"):
        ProviderRiskAssessment("p","c",tuple((k,0) for k in ("availability","security","privacy","regulatory","lock_in")),0,False,d("e"),True)
