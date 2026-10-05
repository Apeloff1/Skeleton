"""Pipeline runner — generic stage orchestration for Skeleton pipelines.

Stages are pure callables: ``(PipelineContext) -> Any``. The runner
topologically sorts the DAG before execution, so every stage sees the
outputs of all its dependencies in the shared context.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from skeleton.kernel.errors import PipelineError


class StageError(PipelineError):
    code = "PPL.STAGE"


class PipelineConfigError(PipelineError):
    code = "PPL.CONFIG"


@dataclass(frozen=True)
class Stage:
    name: str
    run: Callable[["PipelineContext"], Any]
    depends_on: Tuple[str, ...] = ()


@dataclass
class StageResult:
    stage: str
    started_at: float
    finished_at: float
    output: Any = None
    error: Optional[Exception] = None


@dataclass
class PipelineContext:
    inputs: Dict[str, Any] = field(default_factory=dict)
    outputs: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def get(self, name: str, default: Any = None) -> Any:
        return self.outputs.get(name, self.inputs.get(name, default))


class PipelineRunner:
    """Dependency-aware stage execution."""

    def __init__(self, *, fail_fast: bool = True) -> None:
        self.fail_fast = fail_fast
        self._stages: Dict[str, Stage] = {}

    def register(self, stage: Stage) -> None:
        if stage.name in self._stages:
            raise PipelineConfigError(
                "stage already registered", context={"stage": stage.name}
            )
        self._stages[stage.name] = stage

    def run(self, **inputs: Any) -> Tuple[StageResult, ...]:
        context = PipelineContext(inputs=inputs)
        order = self._topo_sort()
        results: List[StageResult] = []
        for name in order:
            stage = self._stages[name]
            start = time.time()
            try:
                output = stage.run(context)
                context.outputs[name] = output
                results.append(StageResult(name, start, time.time(), output=output))
            except Exception as exc:
                results.append(StageResult(name, start, time.time(), error=exc))
                if self.fail_fast:
                    break
        return tuple(results)

    def _topo_sort(self) -> List[str]:
        visited, temp, order = set(), set(), []

        def visit(name: str) -> None:
            if name in temp:
                raise PipelineConfigError(
                    "dependency cycle detected",
                    context={"path": list(temp)},
                )
            if name in visited:
                return
            temp.add(name)
            for dep in self._stages[name].depends_on:
                if dep not in self._stages:
                    raise PipelineConfigError(
                        "missing dependency",
                        context={"stage": name, "missing": dep},
                    )
                visit(dep)
            temp.remove(name)
            visited.add(name)
            order.append(name)

        for name in self._stages:
            visit(name)
        return order

    def plan(self) -> List[str]:
        return self._topo_sort()
