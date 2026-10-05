from dataclasses import dataclass
@dataclass(frozen=True)
class EvalWorker: worker_id:str; environment:str; scorer_version:str; attested:bool
@dataclass(frozen=True)
class EvaluationFarmJob: job_id:str; model_digest:str; dataset_digest:str; eval_digest:str
@dataclass(frozen=True)
class EvaluationFarmResult: job_id:str; worker_id:str; environment:str; scorer_version:str; score:float
def run(job,worker,fn):
 if not worker.attested:raise PermissionError("unattested eval worker")
 return EvaluationFarmResult(job.job_id,worker.worker_id,worker.environment,worker.scorer_version,float(fn(job)))
def aggregate(results):
 xs=sorted(results,key=lambda x:(x.job_id,x.worker_id));return sum(x.score for x in xs)/len(xs) if xs else 0.0
