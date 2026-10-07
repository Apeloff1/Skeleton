"""Execution-event adapter for measured local inference telemetry."""
from __future__ import annotations

from dataclasses import dataclass

from .serving_telemetry import RequestTelemetry


@dataclass(frozen=True, slots=True)
class ExecutionTiming:
    request_id: str
    started_ns: int
    first_token_ns: int
    completed_ns: int
    output_tokens: int
    prompt_tokens: int
    prefix_reused_tokens: int = 0

    def __post_init__(self) -> None:
        if not self.request_id:
            raise ValueError("request_id required")
        for name in ("started_ns", "first_token_ns", "completed_ns", "output_tokens",
                     "prompt_tokens", "prefix_reused_tokens"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"invalid {name}")
        if not self.started_ns <= self.first_token_ns <= self.completed_ns:
            raise ValueError("execution timestamps out of order")
        if self.output_tokens <= 0:
            raise ValueError("positive output_tokens required")
        if self.prefix_reused_tokens > self.prompt_tokens:
            raise ValueError("prefix reuse exceeds prompt")

    def telemetry(self) -> RequestTelemetry:
        ttft_ms = (self.first_token_ns - self.started_ns) // 1_000_000
        e2e_ms = (self.completed_ns - self.started_ns) // 1_000_000
        decode_ns = self.completed_ns - self.first_token_ns
        intervals = max(1, self.output_tokens - 1)
        inter_token_ms = (decode_ns // intervals) // 1_000_000
        return RequestTelemetry(
            self.request_id,
            ttft_ms,
            inter_token_ms,
            e2e_ms,
            self.prompt_tokens,
            self.output_tokens,
            self.prefix_reused_tokens,
        )


__all__ = ["ExecutionTiming"]
