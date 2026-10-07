from dataclasses import dataclass
import math


@dataclass(frozen=True)
class EvalWorker:
    worker_id: str
    environment: str
    scorer_version: str
    attested: bool

    def __post_init__(self) -> None:
        if (
            not self.worker_id
            or not self.environment
            or not self.scorer_version
            or not isinstance(self.attested, bool)
        ):
            raise ValueError("complete evaluation worker identity required")


@dataclass(frozen=True)
class EvaluationFarmJob:
    job_id: str
    model_digest: str
    dataset_digest: str
    eval_digest: str

    def __post_init__(self) -> None:
        if not all(
            (self.job_id, self.model_digest, self.dataset_digest, self.eval_digest)
        ):
            raise ValueError("complete evaluation farm job identity required")


@dataclass(frozen=True)
class EvaluationFarmResult:
    job_id: str
    worker_id: str
    environment: str
    scorer_version: str
    score: float

    def __post_init__(self) -> None:
        if (
            not self.job_id
            or not self.worker_id
            or not self.environment
            or not self.scorer_version
            or isinstance(self.score, bool)
            or not isinstance(self.score, (int, float))
            or not math.isfinite(self.score)
        ):
            raise ValueError("valid evaluation result required")


def run(job: EvaluationFarmJob, worker: EvalWorker, fn) -> EvaluationFarmResult:
    if not isinstance(job, EvaluationFarmJob) or not isinstance(worker, EvalWorker):
        raise ValueError("evaluation job and worker required")
    if not worker.attested:
        raise PermissionError("unattested eval worker")
    score = fn(job)
    if (
        isinstance(score, bool)
        or not isinstance(score, (int, float))
        or not math.isfinite(score)
    ):
        raise ValueError("evaluation score must be finite")
    return EvaluationFarmResult(
        job.job_id,
        worker.worker_id,
        worker.environment,
        worker.scorer_version,
        float(score),
    )


def aggregate(results) -> float:
    items = tuple(results)
    if not items:
        return 0.0
    if any(not isinstance(item, EvaluationFarmResult) for item in items):
        raise ValueError("evaluation results required")

    identities = [(item.job_id, item.worker_id) for item in items]
    if len(identities) != len(set(identities)):
        raise ValueError("duplicate evaluation result")

    job_ids = {item.job_id for item in items}
    scorers = {item.scorer_version for item in items}
    if len(job_ids) != 1 or len(scorers) != 1:
        raise ValueError("aggregate requires one job and scorer version")

    ordered = sorted(items, key=lambda item: (item.job_id, item.worker_id))
    return sum(item.score for item in ordered) / len(ordered)
