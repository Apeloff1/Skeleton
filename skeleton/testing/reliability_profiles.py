"""Deterministic reliability profiles for canonical orchestration.

The profiles deliberately avoid external providers and wall-clock sleeps so they
can run in CI and on developer machines with reproducible failure patterns.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import time
from dataclasses import asdict, dataclass
from typing import Sequence

from skeleton.frontier.orchestration import (
    CanonicalOrchestrator,
    RetryBudget,
    RunStatus,
    StepKind,
    ToolInvocation,
    ToolRegistry,
    TransientToolError,
    TurnOutcome,
)


@dataclass(frozen=True, slots=True)
class ProfileResult:
    """Aggregate result for one deterministic orchestration profile."""

    runs: int
    concurrency: int
    completed: int
    failed: int
    total_tool_attempts: int
    max_tool_attempts: int
    p50_ms: float
    p95_ms: float
    max_ms: float

    def as_dict(self) -> dict[str, int | float]:
        return asdict(self)


class _SingleToolDriver:
    def __init__(self) -> None:
        self.requested = False

    async def next_turn(self, *, run, tool_results):
        del run
        if not self.requested:
            self.requested = True
            return TurnOutcome(
                tool_calls=(ToolInvocation("chaos-call", "flaky", {}),)
            )
        if len(tool_results) != 1:
            raise RuntimeError("successful tool execution must yield one result")
        return TurnOutcome(output=tool_results[0].output, terminal=True)


class _FlakyTool:
    def __init__(self, failures_before_success: int) -> None:
        self.failures_before_success = failures_before_success
        self.calls = 0

    async def __call__(self, arguments):
        del arguments
        self.calls += 1
        if self.calls <= self.failures_before_success:
            raise TransientToolError("injected transient failure")
        return "recovered"


def _positive_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < 1:
        raise ValueError(f"{name} must be at least 1")
    return value


def _non_negative_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < 0:
        raise ValueError(f"{name} must not be negative")
    return value


def _percentile(values: Sequence[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * fraction) - 1)
    return ordered[index]


async def run_orchestration_retry_profile(
    *,
    runs: int = 250,
    concurrency: int = 16,
    transient_failures: int = 2,
    max_attempts: int = 3,
) -> ProfileResult:
    """Run concurrent orchestration with a deterministic transient-failure pattern.

    Each run owns its driver, tool, registry, and orchestrator. When
    ``transient_failures < max_attempts`` every run must recover. Otherwise the
    canonical retry budget must terminate every run as failed after exactly
    ``max_attempts`` tool attempts.
    """

    runs = _positive_int(runs, "runs")
    concurrency = _positive_int(concurrency, "concurrency")
    transient_failures = _non_negative_int(transient_failures, "transient_failures")
    max_attempts = _positive_int(max_attempts, "max_attempts")

    semaphore = asyncio.Semaphore(min(concurrency, runs))

    async def one_run(index: int) -> tuple[RunStatus, int, float]:
        async with semaphore:
            tool = _FlakyTool(transient_failures)
            registry = ToolRegistry()
            registry.register("flaky", tool)
            orchestrator = CanonicalOrchestrator(
                tools=registry,
                tool_retry_budget=RetryBudget(max_attempts=max_attempts),
            )
            started = time.perf_counter()
            record = await orchestrator.run(
                _SingleToolDriver(),
                run_id=f"reliability-{index}",
            )
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            tool_steps = [step for step in record.steps if step.kind is StepKind.TOOL]
            attempts = tool_steps[-1].attempt if tool_steps else 0
            return record.status, attempts, elapsed_ms

    outcomes = await asyncio.gather(*(one_run(index) for index in range(runs)))
    statuses = [status for status, _, _ in outcomes]
    attempts = [attempt for _, attempt, _ in outcomes]
    durations = [duration for _, _, duration in outcomes]

    return ProfileResult(
        runs=runs,
        concurrency=min(concurrency, runs),
        completed=sum(status is RunStatus.COMPLETED for status in statuses),
        failed=sum(status is RunStatus.FAILED for status in statuses),
        total_tool_attempts=sum(attempts),
        max_tool_attempts=max(attempts, default=0),
        p50_ms=round(_percentile(durations, 0.50), 3),
        p95_ms=round(_percentile(durations, 0.95), 3),
        max_ms=round(max(durations, default=0.0), 3),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run deterministic canonical-orchestration reliability pressure."
    )
    parser.add_argument("--runs", type=int, default=250)
    parser.add_argument("--concurrency", type=int, default=16)
    parser.add_argument("--transient-failures", type=int, default=2)
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    result = asyncio.run(
        run_orchestration_retry_profile(
            runs=args.runs,
            concurrency=args.concurrency,
            transient_failures=args.transient_failures,
            max_attempts=args.max_attempts,
        )
    )

    expected_completed = args.transient_failures < args.max_attempts
    healthy = (
        result.completed == result.runs and result.failed == 0
        if expected_completed
        else result.failed == result.runs and result.completed == 0
    )
    healthy = healthy and result.max_tool_attempts <= args.max_attempts

    payload = result.as_dict()
    payload["expected_outcome"] = "completed" if expected_completed else "failed"
    payload["invariants_passed"] = healthy
    if args.as_json:
        print(json.dumps(payload, sort_keys=True))
    else:
        for key, value in payload.items():
            print(f"{key}: {value}")
    return 0 if healthy else 1


if __name__ == "__main__":
    raise SystemExit(main())
