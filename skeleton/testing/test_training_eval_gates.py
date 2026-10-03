import pytest
from skeleton.learning.training_eval_gates import *
def test_independent_versioned_gate_requires_disposition_and_bounds_uncertainty():
 g=TrainingEvalGate(EvaluationSuite("suite",1,(("quality",.8),)))
 with pytest.raises(TrainingEvalError): g.evaluate(checkpoint_digest="a"*64,producer_id="p",verifier_id="p",metrics={"quality":.9},uncertainty=.1)
 with pytest.raises(TrainingEvalError): g.evaluate(checkpoint_digest="a"*64,producer_id="p",verifier_id="v",metrics={"quality":.5},uncertainty=.1)
 p=g.evaluate(checkpoint_digest="a"*64,producer_id="p",verifier_id="v",metrics={"quality":.9},uncertainty=.3); assert not p.allowed
