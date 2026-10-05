from __future__ import annotations
import hashlib,pytest
from skeleton.observability.project_metrics import *
S=lambda x:hashlib.sha256(x.encode()).hexdigest()
def definition(c=MetricClass.QUALITY):return MetricDefinition("METRIC.TEST",c,"ratio","signed-evidence")
def obs(**kw):
 v=dict(metric_id="METRIC.TEST",value=.9,numerator=9,denominator=10,source_digest=S("artifact"),observed_tick=5);v.update(kw);return MetricObservation(**v)
def test_metric_is_bound_to_authoritative_source_digest():assert MetricRegistry((definition(),)).observe(obs()).observation.source_digest==S("artifact")
def test_activity_and_outcome_classes_remain_distinct():assert definition(MetricClass.ACTIVITY).metric_class is not definition(MetricClass.OUTCOME).metric_class
def test_metrics_cannot_be_declared_completion_authority():
 with pytest.raises(MetricError,match="completion authority"):MetricDefinition("METRIC.X",MetricClass.OUTCOME,"count","events",True)
def test_stale_denominator_or_source_age_is_visible():
 r=MetricRegistry((definition(),));m=r.observe(obs());assert r.stale(m,20,10)
def test_zero_denominator_rejected():
 with pytest.raises(MetricError,match="bounds"):obs(denominator=0)
def test_definition_and_observation_identity_must_match():
 with pytest.raises(MetricError,match="mismatch"):ProjectMetric(definition(),MetricObservation("METRIC.OTHER",1,1,1,S("x"),1))
