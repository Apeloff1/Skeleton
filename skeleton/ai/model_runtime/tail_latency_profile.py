"""Source-bound p50/p95/p99 profiling for real local model execution receipts.

The profiler consumes canonical ExecutionTiming and RequestTelemetry objects.
It does not execute a model, infer hardware capability or promote simulated
observations to device qualification.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import hmac
import json
from typing import Mapping

from .execution_telemetry import ExecutionTiming
from .serving_telemetry import RequestTelemetry, ServingTelemetryWindow


PROFILE_SCHEMA = "skeleton.ai.local-tail-profile.v1"
CHECKPOINT_SCHEMA = "skeleton.ai.local-tail-checkpoint.v1"
MAX_RECORDS = 10_000
MAX_BYTES = (1 << 63) - 1


def _digest(value: object) -> str:
    return sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False,
        ensure_ascii=True,
    ).encode("utf-8")).hexdigest()


def _number(value: object, label: str, *, maximum: int = MAX_BYTES) -> int:
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError("invalid " + label)
    return value


def _hex_digest(value: object, label: str) -> str:
    if (type(value) is not str or len(value) != 64
            or any(ch not in "0123456789abcdef" for ch in value)):
        raise ValueError("invalid " + label)
    return value


def _identity(value: object, label: str, maximum: int = 128) -> str:
    if type(value) is not str or not value:
        raise ValueError("invalid " + label)
    try:
        encoded = value.encode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise ValueError("invalid " + label) from exc
    if len(encoded) > maximum or any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise ValueError("invalid " + label)
    return value


@dataclass(frozen=True, slots=True)
class ProfileIdentity:
    model_digest: str
    tokenizer_digest: str
    workload_digest: str
    policy_digest: str
    source_sha: str
    backend: str
    device: str
    evidence: str = "measured"

    def __post_init__(self) -> None:
        for name in ("model_digest", "tokenizer_digest", "workload_digest", "policy_digest"):
            _hex_digest(getattr(self, name), name)
        if (type(self.source_sha) is not str or len(self.source_sha) not in (40, 64)
                or any(ch not in "0123456789abcdef" for ch in self.source_sha)):
            raise ValueError("invalid source_sha")
        _identity(self.backend, "backend")
        _identity(self.device, "device")
        if self.evidence not in {"measured", "simulated"}:
            raise ValueError("unsupported evidence provenance")

    def to_dict(self) -> dict[str, str]:
        return {
            "model_digest": self.model_digest,
            "tokenizer_digest": self.tokenizer_digest,
            "workload_digest": self.workload_digest,
            "policy_digest": self.policy_digest,
            "source_sha": self.source_sha,
            "backend": self.backend,
            "device": self.device,
            "evidence": self.evidence,
        }


@dataclass(frozen=True, slots=True)
class ResourceObservation:
    """Explicit per-request OS telemetry, with unknown sensors left unknown."""

    ram_available_bytes: int
    ram_total_bytes: int
    swap_free_bytes: int
    swap_total_bytes: int
    cpu_load_ppm: int
    thermal: str
    gpu_free_bytes: int | None = None
    gpu_total_bytes: int | None = None

    def __post_init__(self) -> None:
        for name in ("ram_available_bytes", "ram_total_bytes", "swap_free_bytes", "swap_total_bytes"):
            _number(getattr(self, name), name)
        _number(self.cpu_load_ppm, "cpu_load_ppm", maximum=1_000_000)
        if (self.ram_total_bytes == 0 or self.ram_available_bytes > self.ram_total_bytes
                or self.swap_free_bytes > self.swap_total_bytes):
            raise ValueError("inconsistent resource observation")
        if self.thermal not in {"unavailable", "measured_ok", "measured_hold"}:
            raise ValueError("invalid thermal observation")
        if (self.gpu_free_bytes is None) != (self.gpu_total_bytes is None):
            raise ValueError("partial GPU telemetry cannot imply capacity")
        if self.gpu_total_bytes is not None:
            _number(self.gpu_free_bytes, "gpu_free_bytes")
            _number(self.gpu_total_bytes, "gpu_total_bytes")
            if self.gpu_free_bytes > self.gpu_total_bytes:
                raise ValueError("GPU free bytes exceed capacity")

    def to_dict(self) -> dict[str, object]:
        return {
            "ram_available_bytes": self.ram_available_bytes,
            "ram_total_bytes": self.ram_total_bytes,
            "swap_free_bytes": self.swap_free_bytes,
            "swap_total_bytes": self.swap_total_bytes,
            "cpu_load_ppm": self.cpu_load_ppm,
            "thermal": self.thermal,
            "gpu_free_bytes": self.gpu_free_bytes,
            "gpu_total_bytes": self.gpu_total_bytes,
        }


@dataclass(frozen=True, slots=True)
class ProfileRecord:
    timing: ExecutionTiming
    resource: ResourceObservation


def _nearest_rank(values: list[int], percentile: int) -> int:
    if not values:
        raise ValueError("cannot profile empty observations")
    ordered = sorted(values)
    index = (percentile * len(ordered) + 99) // 100 - 1
    return ordered[max(0, index)]


class LocalTailProfiler:
    """Finite exact-observation profiler with no implicit record eviction."""

    def __init__(self, identity: ProfileIdentity, *, max_records: int = MAX_RECORDS) -> None:
        if not isinstance(identity, ProfileIdentity):
            raise ValueError("ProfileIdentity required")
        if type(max_records) is not int or not 1 <= max_records <= MAX_RECORDS:
            raise ValueError("invalid profile capacity")
        self.identity = identity
        self.max_records = max_records
        self._records: dict[str, ProfileRecord] = {}

    def record(self, timing: ExecutionTiming, resource: ResourceObservation) -> None:
        if not isinstance(timing, ExecutionTiming) or not isinstance(resource, ResourceObservation):
            raise ValueError("canonical execution timing and resource observation required")
        if timing.request_id in self._records:
            raise ValueError("duplicate profiled request")
        if len(self._records) >= self.max_records:
            raise ValueError("profile window full")
        self._records[timing.request_id] = ProfileRecord(timing, resource)

    def _ordered(self) -> tuple[ProfileRecord, ...]:
        return tuple(self._records[key] for key in sorted(self._records))

    def summary(
        self, *, ttft_slo_ms: int, inter_token_slo_ms: int, e2e_slo_ms: int,
    ) -> dict[str, object]:
        for name, value in (
            ("ttft_slo_ms", ttft_slo_ms),
            ("inter_token_slo_ms", inter_token_slo_ms),
            ("e2e_slo_ms", e2e_slo_ms),
        ):
            if type(value) is not int or not 1 <= value <= 1_000_000_000:
                raise ValueError("invalid " + name)
        ordered = self._ordered()
        if not ordered:
            raise ValueError("cannot certify empty profile")
        window = ServingTelemetryWindow(max_records=self.max_records)
        timings: list[RequestTelemetry] = []
        raw: list[dict[str, object]] = []
        for record in ordered:
            telemetry = record.timing.telemetry()
            window.record(telemetry)
            timings.append(telemetry)
            raw.append({
                "request_id": record.timing.request_id,
                "started_ns": record.timing.started_ns,
                "first_token_ns": record.timing.first_token_ns,
                "completed_ns": record.timing.completed_ns,
                "output_tokens": record.timing.output_tokens,
                "prompt_tokens": record.timing.prompt_tokens,
                "prefix_reused_tokens": record.timing.prefix_reused_tokens,
                "resource": record.resource.to_dict(),
            })
        slo = window.metrics(
            ttft_slo_ms=ttft_slo_ms,
            inter_token_slo_ms=inter_token_slo_ms,
            e2e_slo_ms=e2e_slo_ms,
        )
        tails: dict[str, dict[str, int]] = {}
        for name, values in (
            ("ttft_ms", [item.ttft_ms for item in timings]),
            ("inter_token_ms", [item.inter_token_ms for item in timings]),
            ("e2e_ms", [item.e2e_ms for item in timings]),
        ):
            tails[name] = {
                "p50": _nearest_rank(values, 50),
                "p95": _nearest_rank(values, 95),
                "p99": _nearest_rank(values, 99),
                "max": max(values),
            }
        # Throughput is the sum of observed tokens divided by total observed
        # execution time, not wall-clock concurrency throughput. Report this
        # distinction explicitly to avoid overstating multistream capacity.
        elapsed_ns = sum(
            record.timing.completed_ns - record.timing.started_ns
            for record in ordered
        )
        output_tokens = sum(record.timing.output_tokens for record in ordered)
        tokens_per_second_milli = (
            0 if elapsed_ns == 0 else output_tokens * 1_000_000_000_000 // elapsed_ns
        )
        thermal_unknown = sum(r.resource.thermal == "unavailable" for r in ordered)
        thermal_holds = sum(r.resource.thermal == "measured_hold" for r in ordered)
        min_ram = min(r.resource.ram_available_bytes for r in ordered)
        min_gpu = min(
            (r.resource.gpu_free_bytes for r in ordered if r.resource.gpu_free_bytes is not None),
            default=None,
        )
        body: dict[str, object] = {
            "schema": PROFILE_SCHEMA,
            "identity": self.identity.to_dict(),
            "requests": len(ordered),
            "minimum_tail_sample_count_met": len(ordered) >= 100,
            "observation_digest": _digest(raw),
            "slo": slo,
            "tail": tails,
            "serial_tokens_per_second_milli": tokens_per_second_milli,
            "serial_throughput_only": True,
            "resource": {
                "min_ram_available_bytes": min_ram,
                "min_gpu_free_bytes": min_gpu,
                "thermal_unavailable_samples": thermal_unknown,
                "thermal_hold_samples": thermal_holds,
                "gpu_telemetry_samples": sum(
                    r.resource.gpu_free_bytes is not None for r in ordered
                ),
            },
            "qualification": (
                "simulated" if self.identity.evidence == "simulated"
                else "insufficient_samples" if len(ordered) < 100
                else "thermal_unknown" if thermal_unknown
                else "thermal_hold" if thermal_holds
                else "measured_tail_profile"
            ),
        }
        return {**body, "digest": _digest(body)}

    def checkpoint(self) -> dict[str, object]:
        body: dict[str, object] = {
            "schema": CHECKPOINT_SCHEMA,
            "identity": self.identity.to_dict(),
            "max_records": self.max_records,
            "records": [
                {
                    "request_id": record.timing.request_id,
                    "started_ns": record.timing.started_ns,
                    "first_token_ns": record.timing.first_token_ns,
                    "completed_ns": record.timing.completed_ns,
                    "output_tokens": record.timing.output_tokens,
                    "prompt_tokens": record.timing.prompt_tokens,
                    "prefix_reused_tokens": record.timing.prefix_reused_tokens,
                    "resource": record.resource.to_dict(),
                }
                for record in self._ordered()
            ],
        }
        return {**body, "digest": _digest(body)}

    @classmethod
    def restore(cls, state: Mapping[str, object]) -> "LocalTailProfiler":
        fields = {"schema", "identity", "max_records", "records", "digest"}
        if not isinstance(state, Mapping) or set(state) != fields:
            raise ValueError("invalid tail profile checkpoint")
        if state["schema"] != CHECKPOINT_SCHEMA:
            raise ValueError("unsupported tail profile checkpoint")
        if type(state["digest"]) is not str or len(state["digest"]) != 64:
            raise ValueError("invalid tail profile digest")
        body = {key: state[key] for key in fields if key != "digest"}
        try:
            expected = _digest(body)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("invalid tail profile encoding") from exc
        if not hmac.compare_digest(expected, state["digest"]):
            raise ValueError("tail profile checkpoint integrity mismatch")
        if type(state["identity"]) is not dict or set(state["identity"]) != {
            "model_digest", "tokenizer_digest", "workload_digest", "policy_digest",
            "source_sha", "backend", "device", "evidence",
        }:
            raise ValueError("invalid profile identity")
        identity = ProfileIdentity(**state["identity"])
        profiler = cls(identity, max_records=state["max_records"])
        records = state["records"]
        if type(records) is not list or len(records) > profiler.max_records:
            raise ValueError("unbounded profile records")
        fields_record = {
            "request_id", "started_ns", "first_token_ns", "completed_ns",
            "output_tokens", "prompt_tokens", "prefix_reused_tokens", "resource",
        }
        resource_fields = {
            "ram_available_bytes", "ram_total_bytes", "swap_free_bytes",
            "swap_total_bytes", "cpu_load_ppm", "thermal",
            "gpu_free_bytes", "gpu_total_bytes",
        }
        for raw in records:
            if type(raw) is not dict or set(raw) != fields_record:
                raise ValueError("invalid profile record")
            resource = raw["resource"]
            if type(resource) is not dict or set(resource) != resource_fields:
                raise ValueError("invalid profile resource record")
            timing = ExecutionTiming(**{key: raw[key] for key in fields_record if key != "resource"})
            profiler.record(timing, ResourceObservation(**resource))
        return profiler


def compare_tail_profiles(
    baseline: Mapping[str, object],
    candidate: Mapping[str, object],
    *,
    allowed_regression_ppm: int = 50_000,
) -> dict[str, object]:
    """Compare only identical measured workloads with sufficient samples.

    The comparison never asserts model quality or full device qualification.
    """
    _number(allowed_regression_ppm, "allowed_regression_ppm", maximum=1_000_000)
    for profile in (baseline, candidate):
        if not isinstance(profile, Mapping) or profile.get("schema") != PROFILE_SCHEMA:
            raise ValueError("invalid tail profile")
        if not isinstance(profile.get("digest"), str):
            raise ValueError("tail profile digest required")
        body = {key: profile[key] for key in profile if key != "digest"}
        if not hmac.compare_digest(_digest(body), profile["digest"]):
            raise ValueError("tail profile integrity mismatch")
    if baseline["identity"] != candidate["identity"]:
        raise ValueError("different model/workload/device/policy/source cannot be compared")
    if baseline["identity"]["evidence"] != "measured":
        raise ValueError("simulated observations cannot certify regressions")
    if (baseline["qualification"] != "measured_tail_profile"
            or candidate["qualification"] != "measured_tail_profile"):
        return {"status": "pending", "reason": "insufficient_or_unqualified_samples"}
    violations: list[str] = []
    for metric in ("ttft_ms", "inter_token_ms", "e2e_ms"):
        for percentile in ("p95", "p99"):
            prior = baseline["tail"][metric][percentile]
            observed = candidate["tail"][metric][percentile]
            if type(prior) is not int or type(observed) is not int:
                raise ValueError("invalid profile percentile")
            if observed * 1_000_000 > prior * (1_000_000 + allowed_regression_ppm):
                violations.append(metric + "." + percentile)
    return {
        "status": "regression" if violations else "no_regression",
        "violations": violations,
        "baseline_digest": baseline["digest"],
        "candidate_digest": candidate["digest"],
        "allowed_regression_ppm": allowed_regression_ppm,
    }


__all__ = [
    "LocalTailProfiler", "ProfileIdentity", "ProfileRecord",
    "ResourceObservation", "compare_tail_profiles",
]
