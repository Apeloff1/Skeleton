"""Deterministic reliability profiles for the in-process API gateway.

The profile deliberately avoids external network and provider dependencies. It
uses a real thread pool so shared gateway state is exercised under concurrent
callers while keeping pass/fail invariants independent of machine speed.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from typing import Sequence

from skeleton.api.gateway import APIGateway, GatewayRequest


@dataclass(frozen=True, slots=True)
class APIProfileResult:
    """Aggregate result for one concurrent API-gateway pressure profile."""

    requests: int
    concurrency: int
    completed: int
    failed: int
    body_mismatches: int
    route_calls: int
    route_errors: int
    p50_ms: float
    p95_ms: float
    max_ms: float
    wall_ms: float
    requests_per_second: float
    python_version: str
    python_implementation: str
    platform_system: str
    machine: str
    cpu_count: int | None
    invariants_passed: bool

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _positive_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < 1:
        raise ValueError(f"{name} must be at least 1")
    return value


def _percentile(values: Sequence[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * fraction) - 1)
    return ordered[index]


def run_api_gateway_throughput_profile(
    *,
    requests: int = 5_000,
    concurrency: int = 32,
) -> APIProfileResult:
    """Drive one gateway route concurrently and report comparable metrics.

    The route has no cache, rate limit, network access, or external provider so
    the profile measures gateway dispatch/middleware overhead. Machine-specific
    timing is reported for baseline capture, while correctness gates only on
    deterministic request/response and accounting invariants.
    """

    requests = _positive_int(requests, "requests")
    concurrency = _positive_int(concurrency, "concurrency")
    workers = min(concurrency, requests)

    gateway = APIGateway()
    gateway.route("/reliability/echo", lambda payload: {"index": payload["index"]})

    def one_request(index: int) -> tuple[int, bool, float]:
        response = gateway.handle(
            GatewayRequest(
                "/reliability/echo",
                actor=f"load-worker-{index % workers}",
                payload={"index": index},
            )
        )
        body_matches = response.body == {"index": index}
        return response.status, body_matches, response.duration_ms

    wall_started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="gateway-load") as pool:
        outcomes = list(pool.map(one_request, range(requests)))
    wall_s = max(time.perf_counter() - wall_started, 1e-12)

    statuses = [status for status, _, _ in outcomes]
    body_matches = [matches for _, matches, _ in outcomes]
    durations = [duration for _, _, duration in outcomes]
    completed = sum(status == 200 for status in statuses)
    failed = requests - completed
    mismatches = sum(not matches for matches in body_matches)

    route = gateway._routes["/reliability/echo"]
    invariants_passed = (
        completed == requests
        and failed == 0
        and mismatches == 0
        and route.calls == requests
        and route.errors == 0
    )

    return APIProfileResult(
        requests=requests,
        concurrency=workers,
        completed=completed,
        failed=failed,
        body_mismatches=mismatches,
        route_calls=route.calls,
        route_errors=route.errors,
        p50_ms=round(_percentile(durations, 0.50), 3),
        p95_ms=round(_percentile(durations, 0.95), 3),
        max_ms=round(max(durations, default=0.0), 3),
        wall_ms=round(wall_s * 1000.0, 3),
        requests_per_second=round(requests / wall_s, 3),
        python_version=platform.python_version(),
        python_implementation=platform.python_implementation(),
        platform_system=platform.system(),
        machine=platform.machine(),
        cpu_count=os.cpu_count(),
        invariants_passed=invariants_passed,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run deterministic concurrent API-gateway reliability pressure."
    )
    parser.add_argument("--requests", type=int, default=5_000)
    parser.add_argument("--concurrency", type=int, default=32)
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    result = run_api_gateway_throughput_profile(
        requests=args.requests,
        concurrency=args.concurrency,
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
