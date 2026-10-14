import math
import pytest
from skeleton.eval.evaluation_farm import *


def test_result_binds_worker_environment_scorer():
    result = run(
        EvaluationFarmJob("j", "m", "d", "e"),
        EvalWorker("w", "env", "s1", True),
        lambda job: 1,
    )
    assert result.scorer_version == "s1"


def test_unattested_worker_rejected():
    with pytest.raises(PermissionError):
        run(
            EvaluationFarmJob("j", "m", "d", "e"),
            EvalWorker("w", "e", "s", False),
            lambda job: 1,
        )


def test_nonfinite_and_duplicate_results_rejected():
    job = EvaluationFarmJob("j", "m", "d", "e")
    worker = EvalWorker("w", "env", "s", True)
    with pytest.raises(ValueError):
        run(job, worker, lambda item: math.nan)
    result = EvaluationFarmResult("j", "w", "env", "s", 1)
    with pytest.raises(ValueError):
        aggregate((result, result))


def test_aggregate_rejects_mixed_jobs_and_scorer_versions():
    with pytest.raises(ValueError):
        aggregate(
            (
                EvaluationFarmResult("a", "w1", "env", "s1", 1),
                EvaluationFarmResult("b", "w2", "env", "s1", 1),
            )
        )
    with pytest.raises(ValueError):
        aggregate(
            (
                EvaluationFarmResult("a", "w1", "env", "s1", 1),
                EvaluationFarmResult("a", "w2", "env", "s2", 1),
            )
        )


def test_boolean_score_is_not_numeric_evidence():
    job = EvaluationFarmJob("j", "m", "d", "e")
    worker = EvalWorker("w", "env", "s", True)
    with pytest.raises(ValueError):
        run(job, worker, lambda item: True)
