import pytest
from skeleton.eval.evaluation_farm import *
def test_result_binds_worker_environment_scorer():assert run(EvaluationFarmJob("j","m","d","e"),EvalWorker("w","env","s1",True),lambda j:1).scorer_version=="s1"
def test_unattested_worker_rejected():
 with pytest.raises(PermissionError):run(EvaluationFarmJob("j","m","d","e"),EvalWorker("w","e","s",False),lambda j:1)
