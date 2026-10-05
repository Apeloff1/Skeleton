from __future__ import annotations

from skeleton.ai.runtime.deferred.component_provider_assurance import build_health_score

A="a"*64
B="b"*64
C="c"*64
D="d"*64

def test_health_scorecard_is_noncompensable_and_evidence_bound()->None:
    score,evidence=build_health_score(
        component_id="retrieval",reliability=0.99,security=0.95,
        freshness=0.75,dependency_health=0.98,
        reliability_evidence_digest=A,security_evidence_digest=B,
        freshness_evidence_digest=C,dependency_evidence_digest=D,
        healthy_threshold=0.8,
    )
    assert score.total==0.75
    assert evidence.healthy is False
    assert evidence.dashboard_metric_id=="component.health.retrieval"
    assert evidence.production_authority is False

def test_health_scorecard_green_requires_every_dimension_above_threshold()->None:
    _,evidence=build_health_score(
        component_id="retrieval",reliability=0.9,security=0.9,
        freshness=0.9,dependency_health=0.9,
        reliability_evidence_digest=A,security_evidence_digest=B,
        freshness_evidence_digest=C,dependency_evidence_digest=D,
        healthy_threshold=0.8,
    )
    assert evidence.healthy is True
