"""HTTP and streaming reliability profile for deployed Skeleton surfaces.

This profile intentionally uses only the Python standard library so it can run
against local, staging, or production-like endpoints without adding load-test
dependencies to the application.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping, Sequence


@dataclass(frozen=True, slots=True)
class RequestSample:
    status: int | None
    elapsed_ms: float
    ttfb_ms: float | None
    bytes_read: int
    chunks: int
    error_kind: str | None = None


@dataclass(frozen=True, slots=True)
class LatencySummary:
    p50_ms: float
    p95_ms: float
    p99_ms: float
    max_ms: float

    def as_dict(self) -> dict[str, float]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class HTTPProfileResult:
    url: str
    method: str
    requests: int
    concurrency: int
    stream: bool
    completed: int
    failed: int
    transport_errors: int
    unexpected_statuses: int
    error_rate: float
    wall_ms: float
    throughput_rps: float
    latency: LatencySummary
    ttfb: LatencySummary
    bytes_read: int
    chunks: int
    status_counts: dict[str, int]
    error_counts: dict[str, int]

    def as_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["latency"] = self.latency.as_dict()
        payload["ttfb"] = self.ttfb.as_dict()
        return payload


def _positive_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < 1:
        raise ValueError(f"{name} must be at least 1")
    return value


def _positive_float(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a number")
    if value <= 0:
        raise ValueError(f"{name} must be greater than 0")
    return float(value)


def _percentile(values: Sequence[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * fraction) - 1)
    return ordered[index]


def _summarize(values: Sequence[float]) -> LatencySummary:
    if not values:
        return LatencySummary(0.0, 0.0, 0.0, 0.0)
    return LatencySummary(
        p50_ms=round(_percentile(values, 0.50), 3),
        p95_ms=round(_percentile(values, 0.95), 3),
        p99_ms=round(_percentile(values, 0.99), 3),
        max_ms=round(max(values), 3),
    )


def _display_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    hostname = parsed.hostname or ""
    if parsed.port is not None:
        hostname = f"{hostname}:{parsed.port}"
    return urllib.parse.urlunsplit((parsed.scheme, hostname, parsed.path, "", ""))


def _error_kind(exc: BaseException) -> str:
    if isinstance(exc, TimeoutError):
        return "timeout"
    if isinstance(exc, urllib.error.URLError):
        return f"url_error:{type(exc.reason).__name__}"
    return type(exc).__name__


def _read_response(response, *, started: float, stream: bool, chunk_size: int) -> tuple[float, int, int]:
    first = response.read(chunk_size)
    ttfb_ms = (time.perf_counter() - started) * 1000.0
    total = len(first)
    chunks = 1 if first else 0
    if stream:
        while True:
            chunk = response.read(chunk_size)
            if not chunk:
                break
            total += len(chunk)
            chunks += 1
    else:
        remainder = response.read()
        if remainder:
            total += len(remainder)
            chunks += 1
    return ttfb_ms, total, chunks


def _request_once(
    url: str,
    *,
    method: str,
    headers: Mapping[str, str],
    body: bytes | None,
    timeout_s: float,
    stream: bool,
    chunk_size: int,
) -> RequestSample:
    request = urllib.request.Request(url=url, data=body, headers=dict(headers), method=method)
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            status = int(response.getcode())
            ttfb_ms, total, chunks = _read_response(
                response, started=started, stream=stream, chunk_size=chunk_size
            )
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            return RequestSample(status, elapsed_ms, ttfb_ms, total, chunks)
    except urllib.error.HTTPError as exc:
        with exc:
            ttfb_ms, total, chunks = _read_response(
                exc, started=started, stream=stream, chunk_size=chunk_size
            )
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        return RequestSample(int(exc.code), elapsed_ms, ttfb_ms, total, chunks)
    except Exception as exc:  # noqa: BLE001
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        return RequestSample(None, elapsed_ms, None, 0, 0, _error_kind(exc))


def _status_expected(status: int | None, expected_statuses: Sequence[int]) -> bool:
    if status is None:
        return False
    if expected_statuses:
        return status in expected_statuses
    return 200 <= status < 300


def run_http_profile(
    url: str,
    *,
    requests: int = 100,
    concurrency: int = 10,
    method: str = "GET",
    headers: Mapping[str, str] | None = None,
    body: bytes | None = None,
    timeout_s: float = 10.0,
    stream: bool = False,
    chunk_size: int = 16_384,
    expected_statuses: Sequence[int] = (),
) -> HTTPProfileResult:
    requests = _positive_int(requests, "requests")
    concurrency = _positive_int(concurrency, "concurrency")
    chunk_size = _positive_int(chunk_size, "chunk_size")
    timeout_s = _positive_float(timeout_s, "timeout_s")
    workers = min(concurrency, requests)
    normalized_method = method.strip().upper()
    if not normalized_method:
        raise ValueError("method must not be empty")
    headers = headers or {}

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="skeleton-http-profile") as pool:
        futures = [
            pool.submit(
                _request_once,
                url,
                method=normalized_method,
                headers=headers,
                body=body,
                timeout_s=timeout_s,
                stream=stream,
                chunk_size=chunk_size,
            )
            for _ in range(requests)
        ]
        samples = [future.result() for future in as_completed(futures)]
    wall_ms = (time.perf_counter() - started) * 1000.0

    status_counts = Counter(str(sample.status) for sample in samples if sample.status is not None)
    error_counts = Counter(sample.error_kind for sample in samples if sample.error_kind)
    transport_errors = sum(sample.status is None for sample in samples)
    unexpected_statuses = sum(
        sample.status is not None and not _status_expected(sample.status, expected_statuses)
        for sample in samples
    )
    failed = transport_errors + unexpected_statuses
    ttfb_values = [sample.ttfb_ms for sample in samples if sample.ttfb_ms is not None]
    wall_s = wall_ms / 1000.0

    return HTTPProfileResult(
        url=_display_url(url),
        method=normalized_method,
        requests=requests,
        concurrency=workers,
        stream=stream,
        completed=requests - failed,
        failed=failed,
        transport_errors=transport_errors,
        unexpected_statuses=unexpected_statuses,
        error_rate=round(failed / requests, 6),
        wall_ms=round(wall_ms, 3),
        throughput_rps=round(requests / wall_s, 3) if wall_s > 0 else 0.0,
        latency=_summarize([sample.elapsed_ms for sample in samples]),
        ttfb=_summarize(ttfb_values),
        bytes_read=sum(sample.bytes_read for sample in samples),
        chunks=sum(sample.chunks for sample in samples),
        status_counts=dict(sorted(status_counts.items())),
        error_counts=dict(sorted(error_counts.items())),
    )


def evaluate_gates(
    result: HTTPProfileResult,
    *,
    max_error_rate: float = 0.0,
    min_rps: float | None = None,
    max_p95_ms: float | None = None,
    max_p95_ttfb_ms: float | None = None,
) -> list[str]:
    violations: list[str] = []
    if not 0.0 <= max_error_rate <= 1.0:
        raise ValueError("max_error_rate must be between 0 and 1")
    if result.error_rate > max_error_rate:
        violations.append(f"error_rate {result.error_rate:.6f} > {max_error_rate:.6f}")
    if min_rps is not None and result.throughput_rps < min_rps:
        violations.append(f"throughput_rps {result.throughput_rps:.3f} < {min_rps:.3f}")
    if max_p95_ms is not None and result.latency.p95_ms > max_p95_ms:
        violations.append(f"p95_ms {result.latency.p95_ms:.3f} > {max_p95_ms:.3f}")
    if max_p95_ttfb_ms is not None and result.ttfb.p95_ms > max_p95_ttfb_ms:
        violations.append(f"p95_ttfb_ms {result.ttfb.p95_ms:.3f} > {max_p95_ttfb_ms:.3f}")
    return violations


def _header_env(values: Sequence[str]) -> dict[str, str]:
    headers: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ValueError("--header-env entries must use HEADER=ENV_VAR")
        header, env_name = value.split("=", 1)
        header = header.strip()
        env_name = env_name.strip()
        if not header or not env_name:
            raise ValueError("--header-env entries must use non-empty HEADER=ENV_VAR")
        if env_name not in os.environ:
            raise ValueError(f"environment variable {env_name!r} is not set")
        headers[header] = os.environ[env_name]
    return headers


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run concurrent HTTP/streaming reliability pressure against a deployed endpoint."
    )
    parser.add_argument("url")
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--method", default="GET")
    parser.add_argument("--timeout-s", type=float, default=10.0)
    parser.add_argument("--stream", action="store_true")
    parser.add_argument("--chunk-size", type=int, default=16_384)
    parser.add_argument("--expect-status", type=int, action="append", default=[])
    parser.add_argument("--header-env", action="append", default=[], metavar="HEADER=ENV_VAR")
    parser.add_argument("--data-file", type=Path)
    parser.add_argument("--max-error-rate", type=float, default=0.0)
    parser.add_argument("--min-rps", type=float)
    parser.add_argument("--max-p95-ms", type=float)
    parser.add_argument("--max-p95-ttfb-ms", type=float)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        headers = _header_env(args.header_env)
        body = args.data_file.read_bytes() if args.data_file else None
        result = run_http_profile(
            args.url,
            requests=args.requests,
            concurrency=args.concurrency,
            method=args.method,
            headers=headers,
            body=body,
            timeout_s=args.timeout_s,
            stream=args.stream,
            chunk_size=args.chunk_size,
            expected_statuses=args.expect_status,
        )
        violations = evaluate_gates(
            result,
            max_error_rate=args.max_error_rate,
            min_rps=args.min_rps,
            max_p95_ms=args.max_p95_ms,
            max_p95_ttfb_ms=args.max_p95_ttfb_ms,
        )
    except (OSError, TypeError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc

    payload = result.as_dict()
    payload["invariants_passed"] = not violations
    payload["violations"] = violations
    rendered = json.dumps(payload, indent=2 if args.as_json else None, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    if args.as_json:
        print(rendered)
    else:
        for key, value in payload.items():
            print(f"{key}: {value}")
    return 0 if not violations else 1


if __name__ == "__main__":
    raise SystemExit(main())
