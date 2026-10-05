from __future__ import annotations
import hashlib
import pytest
from skeleton.ai.evaluation.experiment_comparison import ExperimentComparisonError,ExperimentMetric,ExperimentSnapshot,compare_experiments

def d(x): return hashlib.sha256(x.encode()).hexdigest()
def snap(id,value,protocol="p",dataset=None):
    return ExperimentSnapshot(id,protocol,dataset or d("data"),d("bench"),(ExperimentMetric("quality",value),))

def test_experiment_comparison_computes_deltas_for_compatible_runs():
    result=compare_experiments(snap("a",0.7),snap("b",0.8))
    assert result.deltas==(("quality",pytest.approx(0.1)),)
    assert result.promotion_authority is False

def test_protocol_mismatch_is_rejected():
    with pytest.raises(ExperimentComparisonError,match="identical protocol"):
        compare_experiments(snap("a",1.0,"p1"),snap("b",1.0,"p2"))

def test_dataset_mismatch_is_rejected():
    with pytest.raises(ExperimentComparisonError,match="identical protocol"):
        compare_experiments(snap("a",1.0,dataset=d("a")),snap("b",1.0,dataset=d("b")))

def test_metric_set_mismatch_is_rejected():
    left=snap("a",1.0)
    right=ExperimentSnapshot("b","p",d("data"),d("bench"),(ExperimentMetric("latency",1.0),))
    with pytest.raises(ExperimentComparisonError,match="identical metric sets"):
        compare_experiments(left,right)
