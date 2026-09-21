#!/usr/bin/env python3
"""Benchmark Skeleton's Assembly vector kernels against a Python reference."""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
from pathlib import Path
from typing import Callable

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from skeleton.native import AsmVectorAccelerator


def _vectors(
    *,
    dimensions: int,
    rows: int,
    queries: int,
    seed: int,
) -> tuple[list[list[float]], list[list[float]]]:
    rng = random.Random(seed)
    query_vectors = [
        [rng.uniform(-1.0, 1.0) for _ in range(dimensions)]
        for _ in range(queries)
    ]
    candidates = [
        [rng.uniform(-1.0, 1.0) for _ in range(dimensions)]
        for _ in range(rows)
    ]
    return query_vectors, candidates


def _python_scores(
    queries: list[list[float]],
    candidates: list[list[float]],
) -> list[float]:
    return [
        sum(left * right for left, right in zip(query, candidate))
        for query in queries
        for candidate in candidates
    ]


def _flatten(rows: list[list[float]]) -> list[float]:
    return [value for row in rows for value in row]


def _check_close(
    actual: list[float],
    expected: list[float],
    *,
    label: str,
) -> None:
    if len(actual) != len(expected):
        raise SystemExit(
            f"{label}: result length mismatch {len(actual)} != {len(expected)}"
        )
    for index, (left, right) in enumerate(zip(actual, expected)):
        if not math.isclose(left, right, rel_tol=8e-5, abs_tol=8e-5):
            raise SystemExit(
                f"{label}: result mismatch at {index}: {left} != {right}"
            )


def _time(
    function: Callable[[], object],
    *,
    iterations: int,
) -> float:
    started = time.perf_counter()
    for _ in range(iterations):
        function()
    elapsed = time.perf_counter() - started
    return elapsed / iterations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dimensions", type=int, default=256)
    parser.add_argument("--rows", type=int, default=2048)
    parser.add_argument("--queries", type=int, default=8)
    parser.add_argument("--iterations", type=int, default=8)
    parser.add_argument("--warmup", type=int, default=2)
    parser.add_argument("--seed", type=int, default=1337)
    parser.add_argument("--library", type=Path, default=None)
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    for name in ("dimensions", "rows", "queries", "iterations"):
        if getattr(args, name) < 1:
            parser.error(f"--{name.replace('_', '-')} must be positive")
    if args.warmup < 0:
        parser.error("--warmup must be non-negative")

    if args.library is not None and args.build:
        parser.error("--library and --build are mutually exclusive")

    if args.library is not None:
        accelerator = AsmVectorAccelerator(args.library)
    elif args.build:
        library = AsmVectorAccelerator.build(output_dir=args.output_dir)
        accelerator = AsmVectorAccelerator(library)
    else:
        accelerator = AsmVectorAccelerator()

    queries, candidates = _vectors(
        dimensions=args.dimensions,
        rows=args.rows,
        queries=args.queries,
        seed=args.seed,
    )
    matrix = _flatten(candidates)
    query_matrix = _flatten(queries)

    reference = _python_scores(queries, candidates)
    native_many = accelerator.dot_queries_matrix_f32(
        query_matrix,
        matrix,
        query_count=args.queries,
        rows=args.rows,
        dimensions=args.dimensions,
    )
    _check_close(native_many, reference, label="multi-query")

    native_repeated: list[float] = []
    for query in queries:
        native_repeated.extend(
            accelerator.dot_matrix_f32(
                query,
                matrix,
                rows=args.rows,
                dimensions=args.dimensions,
            )
        )
    _check_close(native_repeated, reference, label="repeated-query")

    for _ in range(args.warmup):
        accelerator.dot_queries_matrix_f32(
            query_matrix,
            matrix,
            query_count=args.queries,
            rows=args.rows,
            dimensions=args.dimensions,
        )
        _python_scores(queries, candidates)

    python_seconds = _time(
        lambda: _python_scores(queries, candidates),
        iterations=args.iterations,
    )
    repeated_seconds = _time(
        lambda: [
            accelerator.dot_matrix_f32(
                query,
                matrix,
                rows=args.rows,
                dimensions=args.dimensions,
            )
            for query in queries
        ],
        iterations=args.iterations,
    )
    native_seconds = _time(
        lambda: accelerator.dot_queries_matrix_f32(
            query_matrix,
            matrix,
            query_count=args.queries,
            rows=args.rows,
            dimensions=args.dimensions,
        ),
        iterations=args.iterations,
    )

    dot_products = args.rows * args.queries
    runtime = accelerator.status()
    payload = {
        "abi_version": runtime.abi_version,
        "architecture": runtime.architecture,
        "capabilities": list(runtime.capabilities),
        "matrix_backend": runtime.matrix_backend,
        "native_calls": runtime.calls,
        "native_scalar_calls": runtime.scalar_calls,
        "native_batch_calls": runtime.batch_calls,
        "native_matrix_calls": runtime.matrix_calls,
        "native_elements_processed": runtime.elements_processed,
        "native_results_emitted": runtime.results_emitted,
        "dimensions": args.dimensions,
        "rows": args.rows,
        "queries": args.queries,
        "dot_products": dot_products,
        "python_seconds": python_seconds,
        "native_repeated_seconds": repeated_seconds,
        "native_multi_seconds": native_seconds,
        "python_dots_per_second": dot_products / python_seconds,
        "native_repeated_dots_per_second": dot_products / repeated_seconds,
        "native_multi_dots_per_second": dot_products / native_seconds,
        "native_multi_vs_python": python_seconds / native_seconds,
        "native_multi_vs_repeated": repeated_seconds / native_seconds,
        "checksum": float(sum(native_many)),
    }

    if args.json_output:
        print(json.dumps(payload, sort_keys=True))
    else:
        for key, value in payload.items():
            print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
