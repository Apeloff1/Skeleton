"""Parallel pipeline execution — run independent stages concurrently.

PipelineRunner is sequential; ParallelRunner groups the topological
order into dependency levels and executes each level's stages
concurrently in a thread pool, preserving fail-fast semantics.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple

from skeleton.pipelines.core import (
    PipelineConfigError,
    PipelineContext,
    Stage,
    StageResult,
)


class ParallelRunner:
    """Level-by-level concurrent stage execution over a DAG."""

    def __init__(self, *, max_workers: int = 4, fail_fast: bool = True) -> None:
        self.max_workers = max_workers
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
        levels = self._levels()
        results: List[StageResult] = []
        for level in levels:
            with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
                future_map = {
                    name: pool.submit(self._run_stage, self._stages[name], context)
                    for name in level
                }
                for name, fut in future_map.items():
                    result = fut.result()
                    results.append(result)
                    if result.error is not None and self.fail_fast:
                        return tuple(results)
        return tuple(results)

    def _run_stage(self, stage: Stage, context: PipelineContext) -> StageResult:
        start = time.time()
        try:
            output = stage.run(context)
            context.outputs[stage.name] = output
            return StageResult(stage.name, start, time.time(), output=output)
        except Exception as exc:
            return StageResult(stage.name, start, time.time(), error=exc)

    def _levels(self) -> List[List[str]]:
        remaining = set(self._stages)
        done: set = set()
        levels: List[List[str]] = []
        while remaining:
            level = sorted(
                name
                for name in remaining
                if all(dep in done for dep in self._stages[name].depends_on)
            )
            if not level:
                raise PipelineConfigError("dependency cycle detected")
            levels.append(level)
            done.update(level)
            remaining -= set(level)
        return levels

    def plan(self) -> List[List[str]]:
        return self._levels()
