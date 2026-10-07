import pytest
from skeleton.eval.evaluation_farm import *
def test_result_binds_worker_environment_scorer():assert run(EvaluationFarmJob("j","m","d","e"),EvalWorker("w","env","s1",True),lambda j:1).scorer_version=="s1"
def test_unattested_worker_rejected():
 with pytest.raises(PermissionError):run(EvaluationFarmJob("j","m","d","e"),EvalWorker("w","e","s",False),lambda j:1)

def test_nonfinite_and_duplicate_results_rejected():
 import pytest,math
 j=EvaluationFarmJob("j","m","d","e");w=EvalWorker("w","env","s",True)
 with pytest.raises(ValueError):run(j,w,lambda x:math.nan)
 r=EvaluationFarmResult("j","w","env","s",1)
 with pytest.raises(ValueError):aggregate((r,r))
