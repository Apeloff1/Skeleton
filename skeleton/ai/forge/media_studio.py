"""Media studio — asset pipelines as sagas + LAFS publish.

Port of gameforge-rs ``crates/gf-gameforge/src/media_studio.rs``. Every media
job (ingest, transcode, thumbnail, waveform, publish) is a saga: visible in
the ledger, compensatable when a stage fails, and recorded on LAFS at
completion. The studio owns no heavy codecs — it orchestrates stages and
records provenance; rendering is delegated elsewhere. That separation is the
point: the studio decides *what* must happen, the swarm decides *who* does
it, and LAFS remembers *that* it happened.

Uses existing ``skeleton.kernel.saga.SagaLedger`` (begin / single-step
advance / abort) and ``skeleton.forge.lafs.Lafs`` (put_chunk / pin_manifest)
only — extend-only; no DAG, outbox, or verify-loop rewrite.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from skeleton.forge.lafs import Lafs, Manifest
from skeleton.kernel.errors import SkeletonError
from skeleton.kernel.saga import (
    Saga,
    SagaLedger,
    Status as SagaStatus,
    Step,
    StepRecord,
)

# Canonical stage names from the RS studio module docstring.
DEFAULT_PIPELINE: tuple[str, ...] = (
    "ingest",
    "transcode",
    "thumbnail",
    "waveform",
    "publish",
)


class MediaStudioError(SkeletonError):
    """Studio refuse — unknown job, wrong status, empty pipeline."""

    code = "FORGE.MEDIA_STUDIO"
    http_status = 400


class JobStatus(str, Enum):
    STAGED = "staged"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    COMPENSATED = "compensated"


@dataclass
class StudioJob:
    """One media pipeline run. ``asset`` is a LAFS manifest name or external ref."""

    id: str
    asset: str
    pipeline: list[str]
    saga_id: str
    status: JobStatus = JobStatus.STAGED
    created: float = field(default_factory=time.time)
    output: Optional[str] = None  # LAFS manifest of the finished asset

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "asset": self.asset,
            "pipeline": list(self.pipeline),
            "saga_id": self.saga_id,
            "status": self.status.value,
            "created": self.created,
            "output": self.output,
        }


def decide_pipeline(
    asset: str,
    *,
    kind: str | None = None,
) -> list[str]:
    """Decide which stages an asset needs — the studio's *what*.

    ``kind`` selects a shorter path for stills / audio-only; unknown kinds
    get the full RS default ladder. ``asset`` is reserved for future
    name-based heuristics and is validated non-empty.
    """
    if not asset or not str(asset).strip():
        raise MediaStudioError("asset ref required to decide a pipeline")
    k = (kind or "full").strip().lower()
    if k in ("image", "still", "promo"):
        return ["ingest", "thumbnail", "publish"]
    if k in ("audio", "waveform", "voice"):
        return ["ingest", "waveform", "publish"]
    if k in ("video", "clip", "full", "default"):
        return list(DEFAULT_PIPELINE)
    return list(DEFAULT_PIPELINE)


def _stage_step(name: str) -> Step:
    """Build a ledger Step that records stage progress in saga context."""

    def action(ctx: dict[str, Any]) -> str:
        done = ctx.setdefault("completed_stages", [])
        done.append(name)
        return name

    def compensation(ctx: dict[str, Any]) -> str:
        undone = ctx.setdefault("compensated_stages", [])
        undone.append(name)
        return name

    return Step(name=name, action=action, compensation=compensation)


def _clone_job(job: StudioJob) -> StudioJob:
    return StudioJob(
        id=job.id,
        asset=job.asset,
        pipeline=list(job.pipeline),
        saga_id=job.saga_id,
        status=job.status,
        created=job.created,
        output=job.output,
    )


class MediaStudio:
    """In-process media job ledger + LAFS publish port.

    Thread-safe via a single RLock (mirrors the RS RwLock covering job
    mutation so observers never see a half-written studio).
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._jobs: dict[str, StudioJob] = {}

    def submit(
        self,
        ledger: SagaLedger,
        asset: str,
        pipeline: list[str] | None = None,
        *,
        kind: str | None = None,
    ) -> StudioJob:
        """Stage a job: register it and open its saga in one move."""
        stages = list(pipeline) if pipeline is not None else decide_pipeline(asset, kind=kind)
        if not stages:
            raise MediaStudioError("pipeline needs at least one stage")
        if not asset or not str(asset).strip():
            raise MediaStudioError("asset ref required")

        steps = tuple(_stage_step(s) for s in stages)
        saga = ledger.begin(
            steps,
            context={"asset": asset, "studio": "media"},
            saga_id=f"studio:{uuid.uuid4().hex[:12]}",
        )
        job = StudioJob(
            id=str(uuid.uuid4()),
            asset=asset,
            pipeline=stages,
            saga_id=saga.saga_id,
            status=JobStatus.STAGED,
            created=time.time(),
            output=None,
        )
        with self._lock:
            self._jobs[job.id] = job
            return _clone_job(job)

    def advance(self, ledger: SagaLedger, job_id: str) -> StudioJob | None:
        """Complete the current stage. Saga is the ledger; the job mirrors it.

        One-step drive using the same Step / StepRecord shapes
        ``SagaLedger.run`` uses — no saga module rewrite.
        """
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            if job.status in (
                JobStatus.DONE,
                JobStatus.FAILED,
                JobStatus.COMPENSATED,
            ):
                return None
            try:
                saga = ledger.get(job.saga_id)
            except Exception:
                return None
            advanced = self._advance_unlocked(ledger, job, saga)
            return _clone_job(advanced) if advanced is not None else None

    def run(self, ledger: SagaLedger, job_id: str) -> StudioJob | None:
        """Drive every remaining stage via ``SagaLedger.run`` (batch path)."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            if job.status in (
                JobStatus.DONE,
                JobStatus.FAILED,
                JobStatus.COMPENSATED,
            ):
                return None
            try:
                saga = ledger.get(job.saga_id)
            except Exception:
                return None
            # If advance() already progressed some steps, resume by running
            # remaining via ledger only when still PENDING (cursor 0).
            # Otherwise finish remaining stages with advance-equivalent loop.
            if saga.status is SagaStatus.PENDING and saga.cursor == 0:
                terminal = ledger.run(saga)
            else:
                # Resume mid-pipeline without double-firing completed steps.
                while saga.cursor < len(saga.steps) and saga.status in (
                    SagaStatus.PENDING,
                    SagaStatus.RUNNING,
                ):
                    advanced = self._advance_unlocked(ledger, job, saga)
                    if advanced is None:
                        break
                    if job.status in (
                        JobStatus.DONE,
                        JobStatus.FAILED,
                        JobStatus.COMPENSATED,
                    ):
                        return _clone_job(job)
                return _clone_job(job)

            if terminal is SagaStatus.COMPLETED:
                job.status = JobStatus.DONE
            elif terminal is SagaStatus.COMPENSATED:
                job.status = JobStatus.COMPENSATED
            else:
                job.status = JobStatus.FAILED
            return _clone_job(job)

    def _advance_unlocked(
        self, ledger: SagaLedger, job: StudioJob, saga: Saga
    ) -> StudioJob | None:
        """Internal one-step advance; caller holds the lock."""
        # Re-enter advance path by temporarily releasing is awkward; inline.
        if saga.status not in (SagaStatus.PENDING, SagaStatus.RUNNING):
            return None
        saga.status = SagaStatus.RUNNING
        if saga.cursor >= len(saga.steps):
            saga.status = SagaStatus.COMPLETED
            job.status = JobStatus.DONE
            return job
        step = saga.steps[saga.cursor]
        record = StepRecord(
            name=step.name, index=saga.cursor, started_at=time.monotonic()
        )
        saga.records.append(record)
        try:
            record.result = step.action(saga.context)
        except Exception as exc:
            record.error = f"{type(exc).__name__}: {exc}"
            record.finished_at = time.monotonic()
            ledger.abort(saga)
            job.status = (
                JobStatus.FAILED
                if saga.status is SagaStatus.FAILED
                else JobStatus.COMPENSATED
            )
            return job
        record.finished_at = time.monotonic()
        saga.cursor += 1
        if saga.cursor >= len(saga.steps):
            saga.status = SagaStatus.COMPLETED
            job.status = JobStatus.DONE
        else:
            job.status = JobStatus.RUNNING
        return job

    def fail(self, ledger: SagaLedger, job_id: str) -> StudioJob | None:
        """Fail the job — the saga compensates every completed stage in reverse."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            if job.status in (
                JobStatus.DONE,
                JobStatus.FAILED,
                JobStatus.COMPENSATED,
            ):
                return None
            try:
                saga = ledger.get(job.saga_id)
            except Exception:
                return None
            ledger.abort(saga)
            job.status = (
                JobStatus.FAILED
                if saga.status is SagaStatus.FAILED
                else JobStatus.COMPENSATED
            )
            return _clone_job(job)

    def publish(self, job_id: str, output_manifest: str) -> StudioJob | None:
        """Attach the output manifest name once the pipeline finishes (RS)."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            if job.status is not JobStatus.DONE:
                return None
            if not output_manifest or not str(output_manifest).strip():
                raise MediaStudioError("output manifest name required")
            job.output = output_manifest
            return _clone_job(job)

    def publish_to_lafs(
        self,
        job_id: str,
        lafs: Lafs,
        data: bytes,
        *,
        name: str | None = None,
    ) -> tuple[StudioJob, Manifest] | None:
        """Publish finished asset bytes into LAFS and pin the job output.

        Studio decides the manifest name (default: ``job.asset``); LAFS
        records the content-addressed chunks. Only valid when status is Done.
        """
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            if job.status is not JobStatus.DONE:
                return None
            manifest_name = (name or job.asset).strip()
            if not manifest_name:
                raise MediaStudioError("manifest name required for LAFS publish")
            digest = lafs.put_chunk(data)
            manifest = lafs.pin_manifest(manifest_name, [digest])
            job.output = manifest.name
            return _clone_job(job), manifest

    def get(self, job_id: str) -> StudioJob | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return _clone_job(job) if job is not None else None

    def list(self) -> list[StudioJob]:
        with self._lock:
            return [_clone_job(j) for j in self._jobs.values()]


# RS-facing alias
Studio = MediaStudio
