"""Deterministic provider-stream load and failure profiles.

The profile exercises the canonical ModelRuntime streaming boundary with no
network dependency. Each run owns a provider that can fail a configurable
number of times before emitting any stream event, making retry accounting and
stream integrity deterministic under concurrent pressure.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import time
from dataclasses import asdict, dataclass
from typing import Sequence

from skeleton.frontier import model_runtime as runtime


@dataclass(frozen=True, slots=True)
class ProviderStreamProfileResult:
    runs: int
    concurrency: int
    chunks_per_run: int
    completed: int
    failed: int
    total_provider_attempts: int
    max_provider_attempts: int
    total_events: int
    p50_first_event_ms: float
    p95_completion_ms: float
    max_completion_ms: float
    invariants_passed: bool

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


class _FlakyStreamingProvider:
    name = "stream-pressure"
    capabilities = frozenset(
        {runtime.ModelCapability.CHAT, runtime.ModelCapability.STREAMING}
    )

    def __init__(self, *, transient_failures: int, chunks: int) -> None:
        self.transient_failures = transient_failures
        self.chunks = chunks
        self.calls = 0

    async def chat(self, request):
        return runtime.ChatResponse(model=request.model, text="fallback")

    async def embed(self, request):
        raise AssertionError("embedding is outside this reliability profile")

    async def stream_chat(self, request):
        self.calls += 1
        await asyncio.sleep(0)
        if self.calls <= self.transient_failures:
            raise runtime.TransientProviderError("injected pre-emission failure")
        text_parts: list[str] = []
        for index in range(self.chunks):
            await asyncio.sleep(0)
            chunk = f"{index},"
            text_parts.append(chunk)
            yield runtime.StreamEvent(kind="text_delta", text_delta=chunk)
        yield runtime.StreamEvent(
            kind="completed",
            response=runtime.ChatResponse(
                model=request.model,
                text="".join(text_parts),
            ),
        )


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


async def run_provider_stream_profile(
    *,
    runs: int = 128,
    concurrency: int = 16,
    chunks_per_run: int = 4,
    transient_failures: int = 1,
    max_attempts: int = 2,
) -> ProviderStreamProfileResult:
    runs = _positive_int(runs, "runs")
    concurrency = _positive_int(concurrency, "concurrency")
    chunks_per_run = _positive_int(chunks_per_run, "chunks_per_run")
    transient_failures = _non_negative_int(transient_failures, "transient_failures")
    max_attempts = _positive_int(max_attempts, "max_attempts")
    workers = min(concurrency, runs)
    semaphore = asyncio.Semaphore(workers)

    async def one_run(index: int) -> tuple[bool, int, int, float, float]:
        async with semaphore:
            provider = _FlakyStreamingProvider(
                transient_failures=transient_failures,
                chunks=chunks_per_run,
            )
            model_runtime = runtime.ModelRuntime()
            model_runtime.register(provider)
            request = runtime.ChatRequest(
                model="profile-model",
                messages=(runtime.ModelMessage("user", f"run-{index}"),),
            )
            started = time.perf_counter()
            first_event_ms = 0.0
            event_count = 0
            try:
                async for _event in model_runtime.stream_chat(
                    provider.name,
                    request,
                    retry_policy=runtime.RetryPolicy(max_attempts=max_attempts),
                ):
                    event_count += 1
                    if event_count == 1:
                        first_event_ms = (time.perf_counter() - started) * 1000.0
            except runtime.TransientProviderError:
                completion_ms = (time.perf_counter() - started) * 1000.0
                return False, provider.calls, event_count, first_event_ms, completion_ms
            completion_ms = (time.perf_counter() - started) * 1000.0
            return True, provider.calls, event_count, first_event_ms, completion_ms

    outcomes = await asyncio.gather(*(one_run(index) for index in range(runs)))
    completed = sum(success for success, *_ in outcomes)
    failed = runs - completed
    attempts = [attempt_count for _, attempt_count, _, _, _ in outcomes]
    event_counts = [count for _, _, count, _, _ in outcomes]
    first_event_durations = [
        first_ms for success, _, _, first_ms, _ in outcomes if success
    ]
    completion_durations = [completion_ms for *_, completion_ms in outcomes]

    expected_success = transient_failures < max_attempts
    expected_attempts = (
        transient_failures + 1 if expected_success else max_attempts
    )
    expected_events = chunks_per_run + 1 if expected_success else 0
    invariants_passed = (
        (completed == runs and failed == 0)
        if expected_success
        else (failed == runs and completed == 0)
    )
    invariants_passed = invariants_passed and all(
        attempt_count == expected_attempts for attempt_count in attempts
    )
    invariants_passed = invariants_passed and all(
        count == expected_events for count in event_counts
    )

    return ProviderStreamProfileResult(
        runs=runs,
        concurrency=workers,
        chunks_per_run=chunks_per_run,
        completed=completed,
        failed=failed,
        total_provider_attempts=sum(attempts),
        max_provider_attempts=max(attempts, default=0),
        total_events=sum(event_counts),
        p50_first_event_ms=round(_percentile(first_event_durations, 0.50), 3),
        p95_completion_ms=round(_percentile(completion_durations, 0.95), 3),
        max_completion_ms=round(max(completion_durations, default=0.0), 3),
        invariants_passed=invariants_passed,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run deterministic concurrent provider-stream reliability pressure."
    )
    parser.add_argument("--runs", type=int, default=128)
    parser.add_argument("--concurrency", type=int, default=16)
    parser.add_argument("--chunks", type=int, default=4)
    parser.add_argument("--transient-failures", type=int, default=1)
    parser.add_argument("--max-attempts", type=int, default=2)
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    result = asyncio.run(
        run_provider_stream_profile(
            runs=args.runs,
            concurrency=args.concurrency,
            chunks_per_run=args.chunks,
            transient_failures=args.transient_failures,
            max_attempts=args.max_attempts,
        )
    )
    payload = result.as_dict()
    if args.as_json:
        print(json.dumps(payload, sort_keys=True))
    else:
        for key, value in payload.items():
            print(f"{key}: {value}")
    return 0 if result.invariants_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
