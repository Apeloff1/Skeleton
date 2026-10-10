import pytest
from skeleton.eval.evaluation_sdk import *
def test_result_captures_hidden_context_identity():
 r=EvaluationSDK("m","c","env").run(Scorer("acc","v1",("dataset:v1",)),[1],lambda x:1);assert (r.model_id,r.config_id,r.environment_id)==("m","c","env")
def test_bad_scorer_output_rejected():
 with pytest.raises(TypeError):EvaluationSDK("m","c","e").run(Scorer("s","1",()),[],lambda x:"1")

def test_nonfinite_score_rejected():
 import pytest,math
 with pytest.raises(TypeError):EvaluationSDK("m","c","e").run(Scorer("s","v",()),(),lambda x:math.nan)
