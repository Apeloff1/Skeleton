"""Deterministic bounded feedback controller for local LLM serving."""
from __future__ import annotations

from dataclasses import dataclass
from collections import deque
import hashlib
import hmac
import json
from typing import Mapping

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


    def checkpoint(self) -> dict[str, object]:
        """Capture an explicit portable feedback state for operator-managed storage.

        This is an integrity checksum, not a signature or a claim that a
        checkpoint's publisher is trusted. Its digest covers the recent replay
        horizon as well as the learned estimate and bounded counters.
        """
        body: dict[str, object] = {
            "schema": "skeleton.ai.runtime-feedback-checkpoint.v1",
            "limits": {
                "min_samples": self.limits.min_samples,
                "max_samples": self.limits.max_samples,
                "max_observation_ms": self.limits.max_observation_ms,
                "smoothing_numerator": self.limits.smoothing_numerator,
                "smoothing_denominator": self.limits.smoothing_denominator,
            },
            "estimate": {
                "prefill_ms": self._estimate.prefill_ms,
                "decode_token_ms": self._estimate.decode_token_ms,
                "predicted_output_tokens": self._estimate.predicted_output_tokens,
                "kv_bytes_per_token": self._estimate.kv_bytes_per_token,
            },
            "samples": self._samples,
            "clipped_observations": self._clipped,
            "recent_request_ids": list(self._recent_ids),
        }
        digest = hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return {**body, "digest": digest}

    @classmethod
    def from_checkpoint(cls, record: Mapping[str, object]) -> "DeterministicRuntimeEstimator":
        """Restore only exact, internally consistent v1 feedback checkpoints.

        Restore has no I/O and must not be used as authorization to execute a
        model. Signature/authentication of an externally supplied snapshot and
        atomic persistence are separate responsibilities of the caller.
        """
        fields = {
            "schema", "limits", "estimate", "samples",
            "clipped_observations", "recent_request_ids", "digest",
        }
        if not isinstance(record, Mapping) or set(record) != fields:
            raise ValueError("invalid feedback checkpoint shape")
        if record["schema"] != "skeleton.ai.runtime-feedback-checkpoint.v1":
            raise ValueError("unsupported feedback checkpoint schema")
        digest = record["digest"]
        if not isinstance(digest, str) or len(digest) != 64 or any(
            ch not in "0123456789abcdef" for ch in digest
        ):
            raise ValueError("invalid feedback checkpoint digest")

        def required_int(value: object, label: str, *, positive: bool = False) -> int:
            if type(value) is not int or value < (1 if positive else 0):
                raise ValueError(f"invalid checkpoint integer {label}")
            return value

        limit_fields = {
            "min_samples", "max_samples", "max_observation_ms",
            "smoothing_numerator", "smoothing_denominator",
        }
        raw_limits = record["limits"]
        if not isinstance(raw_limits, Mapping) or set(raw_limits) != limit_fields:
            raise ValueError("invalid checkpoint feedback limits")
        limits = FeedbackLimits(**{
            key: required_int(raw_limits[key], key, positive=True) for key in limit_fields
        })
        estimate_fields = {
            "prefill_ms", "decode_token_ms",
            "predicted_output_tokens", "kv_bytes_per_token",
        }
        raw_estimate = record["estimate"]
        if not isinstance(raw_estimate, Mapping) or set(raw_estimate) != estimate_fields:
            raise ValueError("invalid checkpoint runtime estimate")
        estimate = RuntimeEstimate(**{
            key: required_int(raw_estimate[key], key) for key in estimate_fields
        })
        samples = required_int(record["samples"], "samples")
        clipped = required_int(record["clipped_observations"], "clipped_observations")
        ids = record["recent_request_ids"]
        if not isinstance(ids, list) or len(ids) > limits.max_samples:
            raise ValueError("invalid checkpoint recent request horizon")
        if any(type(key) is not str or not 1 <= len(key) <= 256 for key in ids):
            raise ValueError("invalid checkpoint request identity")
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate identities in feedback checkpoint")
        if samples != len(ids):
            raise ValueError("checkpoint sample count does not match recent request horizon")

        body = {key: record[key] for key in fields if key != "digest"}
        expected = hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        if not hmac.compare_digest(expected, digest):
            raise ValueError("feedback checkpoint digest mismatch")
        restored = cls(estimate, limits)
        restored._samples = samples
        restored._clipped = clipped
        restored._recent_ids.extend(ids)
        restored._recent_id_set.update(ids)
        return restored


__all__ = ["DeterministicRuntimeEstimator", "FeedbackLimits", "FeedbackReceipt"]
