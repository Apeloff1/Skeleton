from dataclasses import dataclass
import hashlib
import re


_HEX = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class WorkerAttestation:
    worker_id: str
    environment_digest: str
    evidence_id: str
    verified: bool

    def __post_init__(self) -> None:
        if (
            not self.worker_id
            or not _HEX.fullmatch(self.environment_digest)
            or not self.evidence_id
            or not isinstance(self.verified, bool)
        ):
            raise ValueError("valid worker attestation required")


@dataclass(frozen=True)
class BuildWorker:
    worker_id: str
    attested: bool
    environment_digest: str
    attestation: WorkerAttestation | None = None

    def __post_init__(self) -> None:
        if (
            not self.worker_id
            or not isinstance(self.attested, bool)
            or not _HEX.fullmatch(self.environment_digest)
        ):
            raise ValueError("valid build worker required")


@dataclass(frozen=True)
class BuildFarmJob:
    job_id: str
    source_digest: str
    build_digest: str

    def __post_init__(self) -> None:
        if (
            not self.job_id
            or not _HEX.fullmatch(self.source_digest)
            or not _HEX.fullmatch(self.build_digest)
        ):
            raise ValueError("immutable SHA-256 build identities required")


@dataclass(frozen=True)
class BuildFarmArtifact:
    job_id: str
    worker_id: str
    environment_digest: str
    output_digest: str
    attestation_evidence: str


def execute(job: BuildFarmJob, worker: BuildWorker, builder) -> BuildFarmArtifact:
    if not isinstance(job, BuildFarmJob) or not isinstance(worker, BuildWorker):
        raise ValueError("build job and worker required")
    attestation = worker.attestation
    if (
        worker.attested is not True
        or attestation is None
        or attestation.verified is not True
        or attestation.worker_id != worker.worker_id
        or attestation.environment_digest != worker.environment_digest
    ):
        raise PermissionError("verified worker attestation required")

    output = builder(job.source_digest, job.build_digest, worker.environment_digest)
    if not isinstance(output, (bytes, bytearray)):
        raise TypeError("builder output must be bytes")
    return BuildFarmArtifact(
        job.job_id,
        worker.worker_id,
        worker.environment_digest,
        hashlib.sha256(output).hexdigest(),
        attestation.evidence_id,
    )


def execute_reproducible(job: BuildFarmJob, workers, builder) -> tuple[BuildFarmArtifact, ...]:
    worker_items = tuple(workers)
    if len(worker_items) < 2:
        raise ValueError("reproducibility requires at least two workers")
    ids = [worker.worker_id for worker in worker_items if isinstance(worker, BuildWorker)]
    if len(ids) != len(worker_items) or len(ids) != len(set(ids)):
        raise ValueError("distinct build workers required")

    artifacts = tuple(execute(job, worker, builder) for worker in worker_items)
    digests = {artifact.output_digest for artifact in artifacts}
    if len(digests) != 1:
        raise RuntimeError("build farm reproducibility mismatch")
    return artifacts
