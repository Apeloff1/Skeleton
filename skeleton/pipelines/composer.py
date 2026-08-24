"""Pipeline composer — chain generation stages into validated DAGs.

Individual pipelines generate artefacts; the composer chains them: a
description flows through NPC generation, then dialogue, then animation,
with each stage's output typed, validated, and fed to the next. A pipeline
run is a first-class object with per-stage status, so the API can report
exactly which stage failed and what was produced before the failure.

Design laws
-----------
- Stages are pure functions ``context -> partial artefact``; they read the
  accumulated context, return new keys, and never mutate prior stages'
  output.
- Validation gates run *between* stages: a gate failure halts the run
  before downstream work is wasted, and the run record says which gate.
- Retries are per-stage, bounded, and recorded; a stage that exhausts
  retries fails the run with its attempt history attached.
- The composer is deterministic given the same stage functions.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional

from skeleton.kernel.errors import StageError
from skeleton.kernel.events import DomainEvent, EventBus


class StageStatus(Enum):
    PENDING = auto()
    RUNNING = auto()
    SUCCEEDED = auto()
    FAILED = auto()
    SKIPPED = auto()


Context = Dict[str, Any]
StageFn = Callable[[Context], Dict[str, Any]]
GateFn = Callable[[Context], Optional[str]]   # None = pass, str = why it failed


@dataclass
class Stage:
    name: str
    run: StageFn
    gate: Optional[GateFn] = None
    max_attempts: int = 1
    optional: bool = False        # a failed optional stage skips, doesn't fail the run


@dataclass
class StageRecord:
    name: str
    status: StageStatus = StageStatus.PENDING
    attempts: int = 0
    duration_s: float = 0.0
    error: Optional[str] = None
    gate_failure: Optional[str] = None


@dataclass
class PipelineRun:
    run_id: str
    pipeline_name: str
    context: Context = field(default_factory=dict)
    records: List[StageRecord] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None

    @property
    def succeeded(self) -> bool:
        return self.finished_at is not None and all(
            r.status in (StageStatus.SUCCEEDED, StageStatus.SKIPPED) for r in self.records
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "pipeline": self.pipeline_name,
            "succeeded": self.succeeded,
            "stages": [
                {"name": r.name, "status": r.status.name, "attempts": r.attempts,
                 "duration_s": round(r.duration_s, 3), "error": r.error,
                 "gate_failure": r.gate_failure}
                for r in self.records
            ],
            "duration_s": round((self.finished_at or time.time()) - self.started_at, 3),
        }


class PipelineComposer:
    """Builds and executes staged pipelines."""

    def __init__(self, *, bus: Optional[EventBus] = None) -> None:
        self._bus = bus
        self._runs: List[PipelineRun] = []

    def execute(
        self,
        pipeline_name: str,
        stages: List[Stage],
        *,
        initial_context: Optional[Context] = None,
    ) -> PipelineRun:
        if not stages:
            raise StageError("a pipeline needs at least one stage")
        run = PipelineRun(
            run_id=uuid.uuid4().hex[:12],
            pipeline_name=pipeline_name,
            context=dict(initial_context or {}),
        )
        for stage in stages:
            record = StageRecord(name=stage.name)
            run.records.append(record)
            self._run_stage(run, record, stage)
            if record.status == StageStatus.FAILED and not stage.optional:
                break  # gate failure or exhausted retries halt the run
        run.finished_at = time.time()
        self._runs.append(run)
        if self._bus:
            self._bus.publish(
                DomainEvent(
                    topic="pipeline.run.finished",
                    payload=run.to_dict(),
                    correlation_id=run.run_id,
                )
            )
        return run

    def _run_stage(self, run: PipelineRun, record: StageRecord, stage: Stage) -> None:
        record.status = StageStatus.RUNNING
        start = time.time()
        last_error: Optional[str] = None
        for attempt in range(1, stage.max_attempts + 1):
            record.attempts = attempt
            try:
                output = stage.run(run.context)
                run.context.update(output)
                last_error = None
                break
            except Exception as exc:  # noqa: BLE001 - recorded, not swallowed
                last_error = f"{type(exc).__name__}: {exc}"
        record.duration_s = time.time() - start

        if last_error is not None:
            record.error = last_error
            record.status = StageStatus.SKIPPED if stage.optional else StageStatus.FAILED
            return

        if stage.gate is not None:
            failure = stage.gate(run.context)
            if failure is not None:
                record.gate_failure = failure
                record.status = StageStatus.SKIPPED if stage.optional else StageStatus.FAILED
                return

        record.status = StageStatus.SUCCEEDED

    def history(self, *, limit: int = 20) -> List[Dict[str, Any]]:
        return [r.to_dict() for r in self._runs[-limit:]]

    def stats(self) -> Dict[str, Any]:
        runs = self._runs
        return {
            "runs": len(runs),
            "succeeded": sum(1 for r in runs if r.succeeded),
            "failed": sum(1 for r in runs if not r.succeeded),
        }
