from __future__ import annotations
import hashlib,pytest
from skeleton.ai.governance.health import ComponentHealthScorecard,HealthDimension,HealthScorecardError
def d(x): return hashlib.sha256(x.encode()).hexdigest()
def test_component_health_is_weighted_and_evidence_bound():
    score=ComponentHealthScorecard.build("router",(HealthDimension("availability",950000,d("a"),500000),HealthDimension("quality",850000,d("q"),500000)))
    assert score.score_ppm==900000 and score.status=="healthy" and len(score.digest)==64
def test_forged_health_status_is_rejected():
    dims=(HealthDimension("a",500000,d("x"),1000000),)
    with pytest.raises(HealthScorecardError,match="status"):
        ComponentHealthScorecard("c",dims,500000,"healthy")
