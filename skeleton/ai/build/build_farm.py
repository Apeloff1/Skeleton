from dataclasses import dataclass
import hashlib
@dataclass(frozen=True)
class BuildWorker: worker_id:str; attested:bool; environment_digest:str
@dataclass(frozen=True)
class BuildFarmJob: job_id:str; source_digest:str; build_digest:str
@dataclass(frozen=True)
class BuildFarmArtifact: job_id:str; worker_id:str; environment_digest:str; output_digest:str
def execute(job,worker,builder):
 if not worker.attested:raise PermissionError("unattested build worker")
 if not job.source_digest or not job.build_digest:raise ValueError("immutable build inputs required")
 out=builder(job.source_digest,job.build_digest,worker.environment_digest)
 return BuildFarmArtifact(job.job_id,worker.worker_id,worker.environment_digest,hashlib.sha256(out).hexdigest())
