from dataclasses import dataclass
import math
@dataclass(frozen=True)
class EvalWorker: worker_id:str; environment:str; scorer_version:str; attested:bool
@dataclass(frozen=True)
class EvaluationFarmJob: job_id:str; model_digest:str; dataset_digest:str; eval_digest:str
@dataclass(frozen=True)
class EvaluationFarmResult: job_id:str; worker_id:str; environment:str; scorer_version:str; score:float
def run(job,worker,fn):
 if not all((job.job_id,job.model_digest,job.dataset_digest,job.eval_digest,worker.worker_id,worker.environment,worker.scorer_version)) or not isinstance(worker.attested,bool):raise ValueError("complete evaluation farm identity required")
 if not worker.attested:raise PermissionError("unattested eval worker")
 score=float(fn(job))
 if not math.isfinite(score):raise ValueError("evaluation score must be finite")
 return EvaluationFarmResult(job.job_id,worker.worker_id,worker.environment,worker.scorer_version,score)
def aggregate(results):
 xs=tuple(results)
 keys=[(x.job_id,x.worker_id) for x in xs]
 if len(keys)!=len(set(keys)) or any(not math.isfinite(x.score) for x in xs):raise ValueError("invalid or duplicate evaluation result")
 xs=sorted(results,key=lambda x:(x.job_id,x.worker_id));return sum(x.score for x in xs)/len(xs) if xs else 0.0
