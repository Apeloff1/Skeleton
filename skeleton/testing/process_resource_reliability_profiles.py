"""Deterministic process-resource soak profiles for long-lived runtime paths."""
from __future__ import annotations

import argparse
import gc
import json
import threading
import time
import tracemalloc
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

from skeleton.api.gateway import APIGateway, GatewayRequest


_GATEWAY_SOURCE_SUFFIX = "/skeleton/api/gateway.py"
_MAX_GATEWAY_RETAINED_GROWTH_BYTES = 64 * 1024


@dataclass(frozen=True, slots=True)
class ProcessResourceSoakResult:
    iterations: int
    warmup_requests: int
    completed: int
    failed: int
    route_calls: int
    route_errors: int
    rate_limit_buckets_before: int
    rate_limit_buckets_after: int
    threads_before: int
    threads_after: int
    thread_delta: int
    leaked_threads: int
    file_descriptors_before: int | None
    file_descriptors_after: int | None
    file_descriptor_delta: int | None
    traced_current_before_bytes: int
    traced_current_after_bytes: int
    traced_current_growth_bytes: int
    traced_peak_bytes: int
    gateway_source_before_bytes: int
    gateway_source_after_bytes: int
    gateway_source_growth_bytes: int
    elapsed_ms: float
    requests_per_second: float
    invariants_passed: bool

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _positive_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < 1:
        raise ValueError(f"{name} must be at least 1")
    return value


def _file_descriptor_count() -> int | None:
    proc_fds = Path("/proc/self/fd")
    if not proc_fds.is_dir():
        return None
    try:
        return sum(1 for _ in proc_fds.iterdir())
    except OSError:
        return None


def _source_bytes(snapshot: tracemalloc.Snapshot, suffix: str) -> int:
    total = 0
    normalized_suffix = suffix.replace("\\", "/")
    for statistic in snapshot.statistics("filename"):
        filename = statistic.traceback[0].filename.replace("\\", "/")
        if filename.endswith(normalized_suffix):
            total += statistic.size
    return total


def run_process_resource_soak_profile(
    *,
    iterations: int = 20_000,
    warmup_requests: int = 256,
) -> ProcessResourceSoakResult:
    """Soak the in-process API gateway and detect retained runtime resources.

    The profile intentionally uses an unlimited route with no cache or external
    dependencies. It therefore isolates process-owned request bookkeeping from
    network/provider noise while checking thread, file-descriptor, limiter-map,
    route-accounting, and retained source-allocation invariants.
    """

    iterations = _positive_int(iterations, "iterations")
    warmup_requests = _positive_int(warmup_requests, "warmup_requests")

    gateway = APIGateway()
    gateway.route("/resource-soak", lambda payload: {"index": payload["index"]})

    tracemalloc.start(25)
    try:
        for index in range(warmup_requests):
            response = gateway.handle(
                GatewayRequest(
                    "/resource-soak",
                    actor="warmup",
                    payload={"index": index},
                )
            )
            if response.status != 200:
                raise AssertionError("resource-soak warmup request failed")

        gc.collect()
        current_before, _ = tracemalloc.get_traced_memory()
        snapshot_before = tracemalloc.take_snapshot()
        gateway_source_before = _source_bytes(snapshot_before, _GATEWAY_SOURCE_SUFFIX)
        thread_ids_before = {id(thread) for thread in threading.enumerate()}
        threads_before = len(thread_ids_before)
        fds_before = _file_descriptor_count()
        buckets_before = len(gateway._buckets)

        completed = 0
        failed = 0
        started = time.perf_counter()
        for index in range(iterations):
            response = gateway.handle(
                GatewayRequest(
                    "/resource-soak",
                    actor=f"soak-{index % 32}",
                    payload={"index": index},
                )
            )
            if response.status == 200 and response.body == {"index": index}:
                completed += 1
            else:
                failed += 1
        elapsed_s = max(time.perf_counter() - started, 1e-12)

        gc.collect()
        current_after, peak = tracemalloc.get_traced_memory()
        snapshot_after = tracemalloc.take_snapshot()
        gateway_source_after = _source_bytes(snapshot_after, _GATEWAY_SOURCE_SUFFIX)
        thread_ids_after = {id(thread) for thread in threading.enumerate()}
        threads_after = len(thread_ids_after)
        leaked_threads = len(thread_ids_after - thread_ids_before)
        fds_after = _file_descriptor_count()
        buckets_after = len(gateway._buckets)
        route = gateway._routes["/resource-soak"]

        fd_delta = None
        fd_ok = True
        if fds_before is not None and fds_after is not None:
            fd_delta = fds_after - fds_before
            fd_ok = fd_delta <= 0

        thread_delta = threads_after - threads_before
        source_growth = gateway_source_after - gateway_source_before
        expected_calls = warmup_requests + iterations
        invariants_passed = (
            completed == iterations
            and failed == 0
            and route.calls == expected_calls
            and route.errors == 0
            and buckets_before == 0
            and buckets_after == 0
            and leaked_threads == 0
            and fd_ok
            and source_growth <= _MAX_GATEWAY_RETAINED_GROWTH_BYTES
        )

        return ProcessResourceSoakResult(
            iterations=iterations,
            warmup_requests=warmup_requests,
            completed=completed,
            failed=failed,
            route_calls=route.calls,
            route_errors=route.errors,
            rate_limit_buckets_before=buckets_before,
            rate_limit_buckets_after=buckets_after,
            threads_before=threads_before,
            threads_after=threads_after,
            thread_delta=thread_delta,
            leaked_threads=leaked_threads,
            file_descriptors_before=fds_before,
            file_descriptors_after=fds_after,
            file_descriptor_delta=fd_delta,
            traced_current_before_bytes=current_before,
            traced_current_after_bytes=current_after,
            traced_current_growth_bytes=current_after - current_before,
            traced_peak_bytes=peak,
            gateway_source_before_bytes=gateway_source_before,
            gateway_source_after_bytes=gateway_source_after,
            gateway_source_growth_bytes=source_growth,
            elapsed_ms=round(elapsed_s * 1000.0, 3),
            requests_per_second=round(iterations / elapsed_s, 3),
            invariants_passed=invariants_passed,
        )
    finally:
        tracemalloc.stop()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run deterministic process-level resource soak pressure."
    )
    parser.add_argument("--iterations", type=int, default=20_000)
    parser.add_argument("--warmup", type=int, default=256)
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    result = run_process_resource_soak_profile(
        iterations=args.iterations,
        warmup_requests=args.warmup,
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
