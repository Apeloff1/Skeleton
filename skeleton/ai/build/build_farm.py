from dataclasses import dataclass
import hashlib,re
_HEX=re.compile(r"^[0-9a-f]{64}$")
@dataclass(frozen=True)
class WorkerAttestation: worker_id:str; environment_digest:str; evidence_id:str; verified:bool
@dataclass(frozen=True)
class BuildWorker: worker_id:str; attested:bool; environment_digest:str; attestation:WorkerAttestation|None=None
@dataclass(frozen=True)
class BuildFarmJob: job_id:str; source_digest:str; build_digest:str
@dataclass(frozen=True)
class BuildFarmArtifact: job_id:str; worker_id:str; environment_digest:str; output_digest:str; attestation_evidence:str
def execute(job,worker,builder):
 a=worker.attestation
 if a is None or a.verified is not True or a.worker_id!=worker.worker_id or a.environment_digest!=worker.environment_digest or not a.evidence_id:raise PermissionError("verified worker attestation required")
 if not job.job_id or not _HEX.fullmatch(job.source_digest) or not _HEX.fullmatch(job.build_digest) or not _HEX.fullmatch(worker.environment_digest):raise ValueError("immutable SHA-256 build identities required")
 out=builder(job.source_digest,job.build_digest,worker.environment_digest)
 if not isinstance(out,(bytes,bytearray)):raise TypeError("builder output must be bytes")
 return BuildFarmArtifact(job.job_id,worker.worker_id,worker.environment_digest,hashlib.sha256(out).hexdigest(),a.evidence_id)
