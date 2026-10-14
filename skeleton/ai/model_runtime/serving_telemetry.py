"""Deterministic serving telemetry and goodput accounting."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import json


@dataclass(frozen=True, slots=True)
class RequestTelemetry:
    request_id: str
    ttft_ms: int
    inter_token_ms: int
    e2e_ms: int
    prompt_tokens: int
    output_tokens: int
    prefix_reused_tokens: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.request_id, str) or not 1 <= len(self.request_id) <= 256:
            raise ValueError("nonempty request_id of at most 256 characters required")
        for name in ("ttft_ms", "inter_token_ms", "e2e_ms", "prompt_tokens", "output_tokens", "prefix_reused_tokens"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"invalid {name}")
        if self.prefix_reused_tokens > self.prompt_tokens:
            raise ValueError("prefix reuse exceeds prompt")


class ServingTelemetryWindow:
    """Finite request window with deterministic metrics and no implicit eviction."""

    def __init__(self, *, max_records: int = 10_000) -> None:
        if isinstance(max_records, bool) or not isinstance(max_records, int) or max_records <= 0:
            raise ValueError("positive integer max_records required")
        self.max_records = max_records
        self._records: dict[str, RequestTelemetry] = {}

    def record(self, telemetry: RequestTelemetry) -> None:
        if not isinstance(telemetry, RequestTelemetry):
            raise ValueError("RequestTelemetry required")
        if telemetry.request_id in self._records:
            raise ValueError("duplicate telemetry request identity")
        if len(self._records) >= self.max_records:
            raise ValueError("telemetry window capacity exceeded")
        self._records[telemetry.request_id] = telemetry

    def metrics(self, *, ttft_slo_ms: int, inter_token_slo_ms: int, e2e_slo_ms: int) -> dict[str, object]:
        for name, value in (
            ("ttft_slo_ms", ttft_slo_ms),
            ("inter_token_slo_ms", inter_token_slo_ms),
            ("e2e_slo_ms", e2e_slo_ms),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"positive integer {name} required")
        records = tuple(self._records[key] for key in sorted(self._records))
        total = len(records)
        compliant = sum(
            r.ttft_ms <= ttft_slo_ms
            and r.inter_token_ms <= inter_token_slo_ms
            and r.e2e_ms <= e2e_slo_ms
            for r in records
        )
        prompt = sum(r.prompt_tokens for r in records)
        output = sum(r.output_tokens for r in records)
        reused = sum(r.prefix_reused_tokens for r in records)
        # Bind metrics to the *actual observations*, not merely equal aggregate
        # counters; otherwise distinct tail-latency traces can share a receipt.
        observations = [
            {
                "request_id": r.request_id,
                "ttft_ms": r.ttft_ms,
                "inter_token_ms": r.inter_token_ms,
                "e2e_ms": r.e2e_ms,
                "prompt_tokens": r.prompt_tokens,
                "output_tokens": r.output_tokens,
                "prefix_reused_tokens": r.prefix_reused_tokens,
            }
            for r in records
        ]
        observation_digest = hashlib.sha256(
            json.dumps(observations, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        body = {
            "schema": "skeleton.ai.serving-telemetry.v2",
            "record_digest": observation_digest,
            "slo_ms": {
                "ttft": ttft_slo_ms,
                "inter_token": inter_token_slo_ms,
                "end_to_end": e2e_slo_ms,
            },
            "requests": total,
            "slo_compliant_requests": compliant,
            "goodput_pct": 0 if total == 0 else round(compliant * 10000 / total) / 100,
            "prompt_tokens": prompt,
            "output_tokens": output,
            "prefix_reused_tokens": reused,
            "prefix_reuse_pct": 0 if prompt == 0 else round(reused * 10000 / prompt) / 100,
        }
        body["digest"] = hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return body


__all__ = ["RequestTelemetry", "ServingTelemetryWindow"]
