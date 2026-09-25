"""Pipeline orchestrator — bounded DAG execution.

A stage runs only after every dependency has succeeded. Retries are real.
A cycle or an unknown dependency is rejected before any stage function is called.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List


class PipelineError(RuntimeError):
    """The pipeline graph or a stage contract is unsafe to run."""


@dataclass
class PipelineStage:
    name: str
    fn: Callable[[Any], Any]
    dependencies: List[str] = field(default_factory=list)
    retries: int = 0
    timeout_s: float = 30.0

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise PipelineError("stage name is required")
        if not callable(self.fn):
            raise PipelineError("stage function must be callable")
        if isinstance(self.retries, bool) or not isinstance(self.retries, int) or self.retries < 0:
            raise PipelineError("retries must be a non-negative integer")
        if isinstance(self.timeout_s, bool) or not isinstance(self.timeout_s, (int, float)) or not self.timeout_s > 0:
            raise PipelineError("timeout_s must be positive")
        if any(not isinstance(dep, str) or not dep for dep in self.dependencies):
            raise PipelineError("dependencies must be stage names")


@dataclass
class StageResult:
    name: str
    success: bool
    output: Any = None
    error: str | None = None
    duration_ms: float = 0.0
    timestamp_ns: int = 0
    attempts: int = 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "timestamp_ns": self.timestamp_ns,
            "attempts": self.attempts,
        }


class PipelineOrchestrator:
    """Run a stage DAG. Failed dependencies block their dependents."""

    def __init__(self, pipeline_id: str) -> None:
        if not isinstance(pipeline_id, str) or not pipeline_id.strip():
            raise PipelineError("pipeline_id is required")
        self.pipeline_id = pipeline_id
        self._stages: Dict[str, PipelineStage] = {}
        self._results: Dict[str, StageResult] = {}
        self._checkpoints: Dict[str, Any] = {}

    def add_stage(self, stage: PipelineStage) -> None:
        if not isinstance(stage, PipelineStage):
            raise TypeError("stage must be a PipelineStage")
        if stage.name in self._stages:
            raise PipelineError(f"stage {stage.name} is already registered")
        self._stages[stage.name] = stage

    def execute(self, initial_input: Any) -> Dict[str, Any]:
        self._require_acyclic()
        self._results.clear()
        self._checkpoints["start_ns"] = time.time_ns()
        self._checkpoints["input"] = initial_input
        while True:
            ready = self._ready_stages()
            if not ready:
                break
            for name in ready:
                self._run(name, initial_input)
        self._checkpoints["end_ns"] = time.time_ns()
        return self.card()

    def card(self) -> Dict[str, Any]:
        completed = len(self._results)
        successful = sum(1 for result in self._results.values() if result.success)
        blocked = tuple(sorted(name for name in self._stages if name not in self._results))
        start = self._checkpoints.get("start_ns")
        end = self._checkpoints.get("end_ns")
        if isinstance(start, bool) or isinstance(end, bool) or not isinstance(start, int) or not isinstance(end, int):
            duration = None
        else:
            duration = (end - start) / 1e6
        return {
            "kind": "pipeline-card",
            "pipeline_id": self.pipeline_id,
            "total_stages": len(self._stages),
            "completed": completed,
            "successful": successful,
            "failed": completed - successful,
            "blocked": list(blocked),
            "stages": {name: result.to_dict() for name, result in self._results.items()},
            "duration_ms": duration,
        }

    def _require_acyclic(self) -> None:
        for stage in self._stages.values():
            for dependency in stage.dependencies:
                if dependency not in self._stages:
                    raise PipelineError(f"unknown dependency {dependency}")
        visiting: set[str] = set()
        visited: set[str] = set()

        def walk(name: str) -> None:
            if name in visited:
                return
            if name in visiting:
                raise PipelineError(f"pipeline cycle includes {name}")
            visiting.add(name)
            for dependency in self._stages[name].dependencies:
                walk(dependency)
            visiting.remove(name)
            visited.add(name)

        for name in sorted(self._stages):
            walk(name)

    def _ready_stages(self) -> list[str]:
        ready: list[str] = []
        for name in sorted(self._stages):
            if name in self._results:
                continue
            stage = self._stages[name]
            if any(dep not in self._results or not self._results[dep].success for dep in stage.dependencies):
                continue
            ready.append(name)
        return ready

    def _run(self, name: str, initial_input: Any) -> None:
        stage = self._stages[name]
        attempts = stage.retries + 1
        last_error = "StageError"
        started = time.time_ns()
        for attempt in range(1, attempts + 1):
            attempt_started = time.time_ns()
            try:
                if len(stage.dependencies) == 1:
                    output = stage.fn(self._results[stage.dependencies[0]].output)
                elif stage.dependencies:
                    inputs = {dep: self._results[dep].output for dep in stage.dependencies}
                    output = stage.fn(inputs)
                else:
                    output = stage.fn(initial_input)
                elapsed_s = (time.time_ns() - attempt_started) / 1e9
                if elapsed_s > stage.timeout_s:
                    raise TimeoutError("stage exceeded timeout")
                self._results[name] = StageResult(
                    name=name,
                    success=True,
                    output=output,
                    duration_ms=(time.time_ns() - started) / 1e6,
                    timestamp_ns=time.time_ns(),
                    attempts=attempt,
                )
                return
            except Exception as exc:
                last_error = type(exc).__name__
        self._results[name] = StageResult(
            name=name,
            success=False,
            error=last_error,
            duration_ms=(time.time_ns() - started) / 1e6,
            timestamp_ns=time.time_ns(),
            attempts=attempts,
        )


__all__ = ["PipelineError", "PipelineOrchestrator", "PipelineStage", "StageResult"]
