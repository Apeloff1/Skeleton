"""Read-only CLI for source-bound local inference tail-latency receipts.

This consumes measurements emitted by an actual canonical model execution
owner; it never invokes a model, reads prompts or claims device qualification.
"""
from __future__ import annotations

import argparse
import json
import sys

from .execution_telemetry import ExecutionTiming
from .tail_latency_profile import (
    LocalTailProfiler, ProfileIdentity, ResourceObservation,
    compare_tail_profiles,
)


INPUT_SCHEMA = "skeleton.ai.tail-profile-command.v1"
OUTPUT_SCHEMA = "skeleton.ai.tail-profile-receipt.v1"
MAX_INPUT_BYTES = 524_288


def _command(raw: object) -> dict[str, object]:
    if type(raw) is not dict or set(raw) != {
        "schema", "identity", "records", "checkpoint", "slo",
        "baseline", "allowed_regression_ppm",
    }:
        raise ValueError("invalid tail profile command")
    if raw["schema"] != INPUT_SCHEMA:
        raise ValueError("unsupported tail profile command schema")
    identity = raw["identity"]
    if type(identity) is not dict or set(identity) != {
        "model_digest", "tokenizer_digest", "workload_digest", "policy_digest",
        "source_sha", "backend", "device", "evidence",
    }:
        raise ValueError("invalid profile identity")
    pinned = ProfileIdentity(**identity)
    if raw["checkpoint"] is None:
        profiler = LocalTailProfiler(pinned)
    else:
        profiler = LocalTailProfiler.restore(raw["checkpoint"])
        if profiler.identity != pinned:
            raise ValueError("checkpoint identity mismatch")
    records = raw["records"]
    if type(records) is not list or len(records) > 10_000:
        raise ValueError("unbounded profile command")
    timing_fields = {
        "request_id", "started_ns", "first_token_ns", "completed_ns",
        "output_tokens", "prompt_tokens", "prefix_reused_tokens",
    }
    resource_fields = {
        "ram_available_bytes", "ram_total_bytes", "swap_free_bytes",
        "swap_total_bytes", "cpu_load_ppm", "thermal",
        "gpu_free_bytes", "gpu_total_bytes",
    }
    for record in records:
        if type(record) is not dict or set(record) != {"timing", "resource"}:
            raise ValueError("invalid profile observation")
        timing = record["timing"]
        resource = record["resource"]
        if (type(timing) is not dict or set(timing) != timing_fields
                or type(resource) is not dict or set(resource) != resource_fields):
            raise ValueError("invalid profile observation fields")
        profiler.record(ExecutionTiming(**timing), ResourceObservation(**resource))
    slo = raw["slo"]
    if type(slo) is not dict or set(slo) != {
        "ttft_slo_ms", "inter_token_slo_ms", "e2e_slo_ms",
    }:
        raise ValueError("invalid SLO targets")
    summary = profiler.summary(**slo)
    baseline = raw["baseline"]
    comparison = None
    if baseline is not None:
        comparison = compare_tail_profiles(
            baseline, summary, allowed_regression_ppm=raw["allowed_regression_ppm"],
        )
    elif raw["allowed_regression_ppm"] is not None:
        raise ValueError("regression tolerance requires baseline")
    return {
        "schema": OUTPUT_SCHEMA,
        "summary": summary,
        "comparison": comparison,
        "checkpoint": profiler.checkpoint(),
        "device_qualified": False,
        "model_quality_qualified": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Profile measured local model timing tails from bounded JSON input"
    )
    parser.parse_args(argv)
    try:
        raw_bytes = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
        if len(raw_bytes) > MAX_INPUT_BYTES:
            raise ValueError("tail profile input exceeds byte budget")
        raw = json.loads(raw_bytes.decode("utf-8", errors="strict"))
        receipt = _command(raw)
        print(json.dumps(receipt, sort_keys=True, separators=(",", ":"), allow_nan=False))
        return 0
    except (ValueError, TypeError, UnicodeError, OSError, KeyError) as exc:
        print("tail profile denied: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
