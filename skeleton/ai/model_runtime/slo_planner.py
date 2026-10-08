"""SLO-aware resource planning for local LLM serving.

Implements bounded planning concepts derived from modern serving systems without
assuming a particular accelerator backend.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math


@dataclass(frozen=True, slots=True)
class SLOTarget:
    ttft_ms: int
    inter_token_ms: int
    end_to_end_ms: int

    def __post_init__(self) -> None:
        for name in ("ttft_ms", "inter_token_ms", "end_to_end_ms"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"positive {name} required")
        if self.end_to_end_ms < self.ttft_ms:
            raise ValueError("end-to-end SLO cannot be below TTFT SLO")


@dataclass(frozen=True, slots=True)
class RuntimeEstimate:
    prefill_ms: int
    decode_token_ms: int
    predicted_output_tokens: int
    kv_bytes_per_token: int

    def __post_init__(self) -> None:
        for name in ("prefill_ms", "decode_token_ms", "predicted_output_tokens", "kv_bytes_per_token"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"non-negative {name} required")


@dataclass(frozen=True, slots=True)
class ResourcePlan:
    admitted: bool
    reason: str
    prefill_chunks: tuple[int, ...]
    reserved_kv_bytes: int
    predicted_ttft_ms: int
    predicted_e2e_ms: int
    slo_compliant: bool
    digest: str


class SLOResourcePlanner:
    def __init__(self, *, prefill_chunk_tokens: int = 512, overload_reject_pct: int = 98) -> None:
        if prefill_chunk_tokens <= 0:
            raise ValueError("positive prefill chunk size required")
        if not 1 <= overload_reject_pct <= 100:
            raise ValueError("overload rejection percentage outside range")
        self.prefill_chunk_tokens = prefill_chunk_tokens
        self.overload_reject_pct = overload_reject_pct

    def plan(
        self,
        *,
        prompt_tokens: int,
        estimate: RuntimeEstimate,
        slo: SLOTarget,
        kv_capacity_bytes: int,
        kv_used_bytes: int,
        queue_pressure_pct: int,
    ) -> ResourcePlan:
        for name, value in (
            ("prompt_tokens", prompt_tokens),
            ("kv_capacity_bytes", kv_capacity_bytes),
            ("kv_used_bytes", kv_used_bytes),
            ("queue_pressure_pct", queue_pressure_pct),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"invalid {name}")
        if kv_used_bytes > kv_capacity_bytes or queue_pressure_pct > 100:
            raise ValueError("invalid runtime pressure state")

        chunks: list[int] = []
        remaining = prompt_tokens
        while remaining:
            chunk = min(remaining, self.prefill_chunk_tokens)
            chunks.append(chunk)
            remaining -= chunk

        total_tokens = prompt_tokens + estimate.predicted_output_tokens
        reserve = total_tokens * estimate.kv_bytes_per_token
        predicted_ttft = estimate.prefill_ms
        predicted_e2e = predicted_ttft + estimate.decode_token_ms * estimate.predicted_output_tokens
        slo_ok = (
            predicted_ttft <= slo.ttft_ms
            and estimate.decode_token_ms <= slo.inter_token_ms
            and predicted_e2e <= slo.end_to_end_ms
        )

        reason = "admitted"
        admitted = True
        if reserve > kv_capacity_bytes - kv_used_bytes:
            admitted, reason = False, "insufficient_predicted_kv_capacity"
        elif queue_pressure_pct >= self.overload_reject_pct and not slo_ok:
            admitted, reason = False, "overload_predicted_slo_miss"

        body = {
            "schema": "skeleton.ai.slo-resource-plan.v1",
            "admitted": admitted,
            "reason": reason,
            "prefill_chunks": chunks,
            "reserved_kv_bytes": reserve,
            "predicted_ttft_ms": predicted_ttft,
            "predicted_e2e_ms": predicted_e2e,
            "slo_compliant": slo_ok,
        }
        digest = hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return ResourcePlan(
            admitted, reason, tuple(chunks), reserve, predicted_ttft,
            predicted_e2e, slo_ok, digest
        )


__all__ = ["ResourcePlan", "RuntimeEstimate", "SLOResourcePlanner", "SLOTarget"]
