#!/usr/bin/env python3
"""Benchmark Skeleton's optional Java batch accelerators.

This script is intentionally diagnostic, not a CI performance gate. Shared CI
runners are too noisy for stable speed assertions. Use it on representative
deployment hardware to tune the minimum batch/candidate thresholds.

Examples:
    PYTHONPATH=. python scripts/benchmark_java_accelerators.py
    PYTHONPATH=. python scripts/benchmark_java_accelerators.py \
        --hist-values 250000 --vectors 10000 --dims 256 --batch-queries 16 --repeats 7
"""
from __future__ import annotations

import argparse
import math
import statistics
import time
from dataclasses import dataclass
from typing import Callable, Sequence, TypeVar

from skeleton.memory.jvm_vector_accelerator import JvmVectorAccelerator
from skeleton.observability.jvm_accelerator import JvmObservabilityAccelerator

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class Timing:
    label: str
    samples_ms: tuple[float, ...]

    @property
    def median_ms(self) -> float:
        return statistics.median(self.samples_ms)

    @property
    def minimum_ms(self) -> float:
        return min(self.samples_ms)

    @property
    def maximum_ms(self) -> float:
        return max(self.samples_ms)


def _measure(label: str, repeats: int, fn: Callable[[], T]) -> tuple[Timing, T]:
    samples: list[float] = []
    result: T | None = None
    for _ in range(repeats):
        started = time.perf_counter()
        result = fn()
        samples.append((time.perf_counter() - started) * 1000.0)
    assert result is not None
    return Timing(label, tuple(samples)), result


def _hist_values(count: int) -> list[float]:
    return [
        math.sin(index * 0.011) * 25.0
        + math.cos(index * 0.0037) * 5.0
        + (index % 97) * 0.01
        for index in range(count)
    ]


def _python_histogram(values: Sequence[float]) -> tuple[int, float, float, float, float, float]:
    ordered = sorted(values)
    count = len(ordered)
    middle = count // 2
    p50 = (
        ordered[middle]
        if count % 2
        else (ordered[middle - 1] + ordered[middle]) / 2.0
    )
    p99 = ordered[min(count - 1, int(count * 0.99))]
    return (
        count,
        min(ordered),
        max(ordered),
        statistics.mean(ordered),
        p50,
        p99,
    )


def _vector(index: int, dims: int) -> list[float]:
    raw = [
        math.sin((index + 1) * (dim + 3) * 0.0017)
        + math.cos((index + 7) * (dim + 1) * 0.0009)
        for dim in range(dims)
    ]
    norm = math.sqrt(sum(value * value for value in raw)) or 1.0
    return [value / norm for value in raw]


def _vector_fixture(count: int, dims: int) -> tuple[list[float], list[tuple[list[float], float]]]:
    query = _vector(1_000_003, dims)
    candidates: list[tuple[list[float], float]] = []
    for index in range(count):
        vector = _vector(index, dims)
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        candidates.append((vector, norm))
    return query, candidates


def _python_top_k(
    query: Sequence[float],
    candidates: Sequence[tuple[Sequence[float], float]],
    top_k: int,
) -> list[tuple[int, float]]:
    query_norm = math.sqrt(sum(value * value for value in query)) or 1.0
    scored: list[tuple[int, float]] = []
    for index, (vector, norm) in enumerate(candidates):
        dot = sum(q * value for q, value in zip(query, vector))
        scored.append((index, dot / (query_norm * norm)))
    scored.sort(key=lambda item: (-item[1], item[0]))
    return scored[:top_k]



def _query_batch(count: int, dims: int) -> list[list[float]]:
    return [_vector(2_000_000 + index, dims) for index in range(count)]


def _python_top_k_many(
    queries: Sequence[Sequence[float]],
    candidates: Sequence[tuple[Sequence[float], float]],
    top_k: int,
) -> list[list[tuple[int, float]]]:
    return [_python_top_k(query, candidates, top_k) for query in queries]


def _check_vector_batch_parity(
    python_batches: Sequence[Sequence[tuple[int, float]]],
    java_batches: Sequence[Sequence[object]],
) -> None:
    if len(python_batches) != len(java_batches):
        raise RuntimeError("vector batch query count mismatch")
    for python_hits, java_hits in zip(python_batches, java_batches):
        _check_vector_parity(python_hits, java_hits)


def _speedup(python: Timing, java: Timing) -> float:
    if java.median_ms <= 0:
        return float("inf")
    return python.median_ms / java.median_ms


def _print_timing(timing: Timing) -> None:
    print(
        f"{timing.label:28s} "
        f"median={timing.median_ms:9.3f} ms "
        f"min={timing.minimum_ms:9.3f} ms "
        f"max={timing.maximum_ms:9.3f} ms"
    )


def _check_histogram_parity(
    python_result: tuple[int, float, float, float, float, float],
    java_result: object,
) -> None:
    fields = (
        java_result.count,
        java_result.minimum,
        java_result.maximum,
        java_result.mean,
        java_result.p50,
        java_result.p99,
    )
    if python_result[0] != fields[0]:
        raise RuntimeError("histogram count mismatch")
    for expected, actual in zip(python_result[1:], fields[1:]):
        if not math.isclose(expected, actual, rel_tol=1e-11, abs_tol=1e-11):
            raise RuntimeError(
                f"histogram parity mismatch: expected {expected}, got {actual}"
            )


def _check_vector_parity(
    python_hits: Sequence[tuple[int, float]],
    java_hits: Sequence[object],
) -> None:
    if [index for index, _ in python_hits] != [hit.index for hit in java_hits]:
        raise RuntimeError("vector top-k ordering mismatch")
    for (_, expected), hit in zip(python_hits, java_hits):
        if not math.isclose(expected, hit.similarity, rel_tol=1e-10, abs_tol=1e-10):
            raise RuntimeError(
                f"vector similarity mismatch: expected {expected}, got {hit.similarity}"
            )


def run(args: argparse.Namespace) -> int:
    if args.hist_values < 1:
        raise SystemExit("--hist-values must be positive")
    if args.vectors < 1:
        raise SystemExit("--vectors must be positive")
    if not 1 <= args.dims <= 4096:
        raise SystemExit("--dims must be in [1, 4096]")
    if args.vectors * args.dims > 4_000_000:
        raise SystemExit("vector fixture exceeds the accelerator 4,000,000-element bound")
    if not 1 <= args.top_k <= args.vectors:
        raise SystemExit("--top-k must be in [1, vectors]")
    if not 1 <= args.batch_queries <= 512:
        raise SystemExit("--batch-queries must be in [1, 512]")
    if (args.vectors + args.batch_queries) * args.dims > 4_000_000:
        raise SystemExit("batch vector fixture exceeds the accelerator 4,000,000-element bound")
    if args.repeats < 1:
        raise SystemExit("--repeats must be positive")

    hist = _hist_values(args.hist_values)
    query, candidates = _vector_fixture(args.vectors, args.dims)
    query_norm = math.sqrt(sum(value * value for value in query)) or 1.0
    batch_queries = _query_batch(args.batch_queries, args.dims)
    batch_query_payload = [
        (
            item,
            math.sqrt(sum(value * value for value in item)) or 1.0,
        )
        for item in batch_queries
    ]

    print("Skeleton Java accelerator benchmark")
    print(f"histogram values : {len(hist):,}")
    print(f"vector candidates: {len(candidates):,}")
    print(f"vector dimensions: {args.dims:,}")
    print(f"top_k            : {args.top_k:,}")
    print(f"batch queries    : {args.batch_queries:,}")
    print(f"repeats          : {args.repeats}")
    print()

    with JvmObservabilityAccelerator() as observability, JvmVectorAccelerator() as vector:
        # Warm source launchers, JIT paths, protocol buffers, and class loading.
        observability.summarize(hist[: min(len(hist), 4096)])
        vector.top_k(
            query,
            query_norm,
            candidates[: min(len(candidates), max(args.top_k, 32))],
            min(args.top_k, min(len(candidates), max(args.top_k, 32))),
        )

        py_hist, py_hist_result = _measure(
            "Python histogram",
            args.repeats,
            lambda: _python_histogram(hist),
        )
        java_hist, java_hist_result = _measure(
            "Java histogram",
            args.repeats,
            lambda: observability.summarize(hist),
        )
        _check_histogram_parity(py_hist_result, java_hist_result)

        py_vector, py_vector_result = _measure(
            "Python vector top-k",
            args.repeats,
            lambda: _python_top_k(query, candidates, args.top_k),
        )
        java_vector, java_vector_result = _measure(
            "Java vector top-k",
            args.repeats,
            lambda: vector.top_k(query, query_norm, candidates, args.top_k),
        )
        _check_vector_parity(py_vector_result, java_vector_result)

        py_batch, py_batch_result = _measure(
            "Python vector batch",
            args.repeats,
            lambda: _python_top_k_many(batch_queries, candidates, args.top_k),
        )
        java_batch, java_batch_result = _measure(
            "Java vector batch",
            args.repeats,
            lambda: vector.top_k_many(
                batch_query_payload,
                candidates,
                args.top_k,
            ),
        )
        _check_vector_batch_parity(py_batch_result, java_batch_result)

    _print_timing(py_hist)
    _print_timing(java_hist)
    print(f"{'Histogram speedup':28s} {_speedup(py_hist, java_hist):9.3f}x")
    print()
    _print_timing(py_vector)
    _print_timing(java_vector)
    print(f"{'Vector speedup':28s} {_speedup(py_vector, java_vector):9.3f}x")
    print()
    _print_timing(py_batch)
    _print_timing(java_batch)
    print(f"{'Vector batch speedup':28s} {_speedup(py_batch, java_batch):9.3f}x")
    print()
    print(
        "Interpretation: enable a JVM fast path only above the measured crossover "
        "point on your deployment hardware. A speedup below 1.0x means Python is "
        "faster for that fixture and the threshold should be raised."
    )
    return 0


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--hist-values", type=int, default=100_000)
    p.add_argument("--vectors", type=int, default=5_000)
    p.add_argument("--dims", type=int, default=256)
    p.add_argument("--top-k", type=int, default=10)
    p.add_argument("--batch-queries", type=int, default=8)
    p.add_argument("--repeats", type=int, default=5)
    return p


if __name__ == "__main__":
    raise SystemExit(run(parser().parse_args()))
