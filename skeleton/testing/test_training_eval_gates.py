from __future__ import annotations
import hashlib,pytest
from skeleton.training.eval_gates import *
S=lambda x:hashlib.sha256(x.encode()).hexdigest()
def gate():return TrainingEvalGate("GATE.1","SUITE.1",S("suite-v1"),("METRIC.ACC","METRIC.SAFE"))
def ev(results):return CheckpointEvaluation("GATE.1",S("candidate"),S("champion"),tuple(results),S("evidence"))
def test_fixed_suite_and_complete_metrics_allow_clean_promotion():assert promote(gate(),ev((("METRIC.ACC",Result.PASS),("METRIC.SAFE",Result.PASS)))).checkpoint_digest==S("candidate")
def test_missing_metric_cannot_be_averaged_away():
 with pytest.raises(GateError,match="metric set"):promote(gate(),ev((("METRIC.ACC",Result.PASS),)))
def test_regression_requires_explicit_disposition():
 e=ev((("METRIC.ACC",Result.REGRESSION),("METRIC.SAFE",Result.PASS)))
 with pytest.raises(GateError,match="disposition"):promote(gate(),e)
 assert promote(gate(),e,(("METRIC.ACC","accepted by independent risk review"),))
def test_uncertainty_requires_explicit_disposition():
 with pytest.raises(GateError,match="disposition"):promote(gate(),ev((("METRIC.ACC",Result.UNCERTAIN),("METRIC.SAFE",Result.PASS))))
def test_gate_identity_mismatch_rejected():
 e=CheckpointEvaluation("GATE.OTHER",S("candidate"),S("champion"),(("METRIC.ACC",Result.PASS),("METRIC.SAFE",Result.PASS)),S("e"))
 with pytest.raises(GateError,match="mismatch"):promote(gate(),e)
