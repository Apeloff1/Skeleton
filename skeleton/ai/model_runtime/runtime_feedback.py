"""Deterministic bounded feedback controller for local LLM serving."""
from __future__ import annotations

from dataclasses import dataclass
from collections import deque
import hashlib
import json

from .serving_telemetry import RequestTelemetry
from .slo_planner import RuntimeEstimate


@dataclass(frozen=True, slots=True)
class FeedbackLimits:
    min_samples: int = 4
    max_samples: int = 256
    max_observation_ms: int = 120_000
    smoothing_numerator: int = 1
    smoothing_denominator: int = 4

    def __post_init__(self) -> None:
        for name in ("min_samples", "max_samples", "max_observation_ms",
                     "smoothing_numerator", "smoothing_denominator"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"positive {name} required")
        if self.min_samples > self.max_samples:
            raise ValueError("min_samples exceeds max_samples")
        if self.smoothing_numerator > self.smoothing_denominator:
            raise ValueError("smoothing ratio exceeds one")


@dataclass(frozen=True, slots=True)
class FeedbackReceipt:
    samples: int
    ready: bool
    estimate: RuntimeEstimate
    clipped_observations: int
    digest: str


class DeterministicRuntimeEstimator:
    """Integer-only EWMA estimator with bounded history and outlier clipping."""

    def __init__(
        self,
        initial: RuntimeEstimate,
        limits: FeedbackLimits | None = None,
    ) -> None:
        if not isinstance(initial, RuntimeEstimate):
            raise ValueError("RuntimeEstimate required")
        self.limits = limits or FeedbackLimits()
        self._estimate = initial
        self._samples = 0
        self._clipped = 0
        # Bounded request identities prevent replays from skewing an EWMA.
        # This is an in-memory recent-identity fence, not durable exactly-once
        # accounting; a caller requiring persistence must dedupe upstream.
        self._recent_ids: deque[str] = deque()
        self._recent_id_set: set[str] = set()

    @property
    def estimate(self) -> RuntimeEstimate:
        return self._estimate

    @property
    def ready(self) -> bool:
        return self._samples >= self.limits.min_samples

    def _clip_ms(self, value: int) -> int:
        if value > self.limits.max_observation_ms:
            self._clipped += 1
            return self.limits.max_observation_ms
        return value

    def _ewma(self, old: int, observed: int) -> int:
        n = self.limits.smoothing_numerator
        d = self.limits.smoothing_denominator
        return max(0, ((d - n) * old + n * observed + d // 2) // d)

    def observe(self, telemetry: RequestTelemetry, *, kv_bytes_per_token: int) -> FeedbackReceipt:
        if not isinstance(telemetry, RequestTelemetry):
            raise ValueError("RequestTelemetry required")
        if isinstance(kv_bytes_per_token, bool) or not isinstance(kv_bytes_per_token, int) or kv_bytes_per_token < 0:
            raise ValueError("non-negative kv_bytes_per_token required")
        if telemetry.request_id in self._recent_id_set:
            raise ValueError("duplicate runtime feedback request identity")

        prefill = self._clip_ms(telemetry.ttft_ms)
        decode = self._clip_ms(telemetry.inter_token_ms)
        output = telemetry.output_tokens
        kv = kv_bytes_per_token

        self._estimate = RuntimeEstimate(
            self._ewma(self._estimate.prefill_ms, prefill),
            self._ewma(self._estimate.decode_token_ms, decode),
            self._ewma(self._estimate.predicted_output_tokens, output),
            self._ewma(self._estimate.kv_bytes_per_token, kv),
        )
        self._samples = min(self._samples + 1, self.limits.max_samples)
        self._recent_ids.append(telemetry.request_id)
        self._recent_id_set.add(telemetry.request_id)
        if len(self._recent_ids) > self.limits.max_samples:
            evicted = self._recent_ids.popleft()
            self._recent_id_set.remove(evicted)
        return self.receipt()

    def receipt(self) -> FeedbackReceipt:
        body = {
            "schema": "skeleton.ai.runtime-feedback.v1",
            "samples": self._samples,
            "ready": self.ready,
            "estimate": {
                "prefill_ms": self._estimate.prefill_ms,
                "decode_token_ms": self._estimate.decode_token_ms,
                "predicted_output_tokens": self._estimate.predicted_output_tokens,
                "kv_bytes_per_token": self._estimate.kv_bytes_per_token,
            },
            "clipped_observations": self._clipped,
            "limits": {
                "min_samples": self.limits.min_samples,
                "max_samples": self.limits.max_samples,
                "max_observation_ms": self.limits.max_observation_ms,
                "smoothing_numerator": self.limits.smoothing_numerator,
                "smoothing_denominator": self.limits.smoothing_denominator,
            },
        }
        digest = hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return FeedbackReceipt(
            self._samples, self.ready, self._estimate, self._clipped, digest
        )


__all__ = ["DeterministicRuntimeEstimator", "FeedbackLimits", "FeedbackReceipt"]
