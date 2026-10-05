"""Storage/locality and distributed compute fabric VOL-395,396,400-402."""
from dataclasses import dataclass
from enum import Enum
class StorageTier(str,Enum): HOT="hot"; WARM="warm"; COLD="cold"
@dataclass(frozen=True,slots=True)
class TieringPolicy: critical_replicas:int; allowed:tuple[StorageTier,...]
@dataclass(frozen=True,slots=True)
class TierMove: artifact_id:str; source:StorageTier; target:StorageTier; digest_before:str; digest_after:str; metadata_preserved:bool; replicas_after:int
def tier_move_valid(m,p):return m.target in p.allowed and m.digest_before==m.digest_after and m.metadata_preserved and m.replicas_after>=p.critical_replicas
@dataclass(frozen=True,slots=True)
class DataLocation: artifact_id:str; zone:str; freshness_watermark:int
@dataclass(frozen=True,slots=True)
class LocalityConstraint: allowed_zones:frozenset[str]; authority_ok:bool; security_ok:bool
@dataclass(frozen=True,slots=True)
class TransferPlan: source:DataLocation; target_zone:str; transfer_cost:float; admitted:bool
def plan_transfer(source,target_zone,constraint,cost):
 ok=constraint.authority_ok and constraint.security_ok and target_zone in constraint.allowed_zones
 return TransferPlan(source,target_zone,cost,ok)
@dataclass(frozen=True,slots=True)
class BuildWorker: worker_id:str; environment_id:str; attested:bool
@dataclass(frozen=True,slots=True)
class BuildFarmJob: job_id:str; source_digest:str; build_input_digest:str
@dataclass(frozen=True,slots=True)
class BuildFarmArtifact: job_id:str; worker_id:str; environment_id:str; artifact_digest:str; log_digest:str; attested:bool
def build_artifact(job,worker,artifact_digest,log_digest):
 if not worker.attested:raise ValueError("worker not attested")
 return BuildFarmArtifact(job.job_id,worker.worker_id,worker.environment_id,artifact_digest,log_digest,True)
@dataclass(frozen=True,slots=True)
class EvalWorker: worker_id:str; environment_id:str; attested:bool
@dataclass(frozen=True,slots=True)
class EvaluationFarmJob: job_id:str; eval_digest:str; model_digest:str; dataset_digest:str; scorer_version:str
@dataclass(frozen=True,slots=True)
class EvaluationFarmResult: job_id:str; worker_id:str; environment_id:str; scorer_version:str; metric:str; value:float
def aggregate_results(results):
 return tuple(sorted(results,key=lambda x:(x.metric,x.worker_id,x.environment_id,x.value)))
class ResearchPriority(int,Enum): BACKGROUND=1; NORMAL=2; URGENT=3
@dataclass(frozen=True,slots=True)
class ResearchComputeJob: job_id:str; priority:ResearchPriority; quota:int; provenance:str
@dataclass(frozen=True,slots=True)
class ResearchQueue: jobs:tuple[ResearchComputeJob,...]; production_pressure:bool
@dataclass(frozen=True,slots=True)
class ResearchAllocation: job_id:str; admitted:bool; reason:str
def allocate_research(q):
 if not q.jobs:return ResearchAllocation("",False,"empty")
 ordered=sorted(q.jobs,key=lambda x:(-int(x.priority),x.job_id))
 for j in ordered:
  if j.quota<=0:continue
  if q.production_pressure and j.priority is not ResearchPriority.URGENT:continue
  return ResearchAllocation(j.job_id,True,"policy admitted")
 return ResearchAllocation("",False,"production/quota protected")
