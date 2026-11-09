"""Actual usage metering adapters for skill/tool execution.

This module intentionally does not execute skills. It gives every skill/tool
execution boundary a small, deterministic adapter into the shared
:class:`AdmissionRuntime` budget ledger so retries do not double-charge and
unknown usage cannot be silently treated as zero.
"""

from __future__ import annotations

import hashlib

from skeleton.intelligence.admission import UsageEstimate
from skeleton.intelligence.admission_runtime import (
    AdmissionRuntime,
    UnknownUsageMarker,
)
from skeleton.intelligence.quota import QuotaUsageEvent


def _event_id(kind: str, *parts: str) -> str:
    normalized = [str(part).strip() for part in parts]
    if any(not part for part in normalized):
        raise ValueError("usage event identity parts are required")
    material = "\x1f".join((kind, *normalized)).encode("utf-8")
    return kind + "-" + hashlib.sha256(material).hexdigest()[:24]


class SkillUsageMeter:
    """Charge actual skill/tool calls against an admitted operation."""

    def __init__(self, runtime: AdmissionRuntime) -> None:
        if not isinstance(runtime, AdmissionRuntime):
            raise TypeError("runtime must be an AdmissionRuntime")
        self.runtime = runtime

    def meter_execution(
        self,
        operation_id: str,
        skill_id: str,
        execution_id: str,
        *,
        calls: int = 1,
        now_wall: float | None = None,
    ) -> QuotaUsageEvent:
        return self.runtime.meter_tool_call(
            operation_id,
            _event_id("skill", skill_id, execution_id),
            calls=calls,
            now_wall=now_wall,
        )

    def mark_unknown(
        self,
        operation_id: str,
        skill_id: str,
        execution_id: str,
        reason: str,
        *,
        now_wall: float | None = None,
    ) -> UnknownUsageMarker:
        return self.runtime.mark_usage_unknown(
            operation_id,
            _event_id("skill", skill_id, execution_id),
            "tool",
            reason,
            now_wall=now_wall,
        )

    def resolve_unknown(
        self,
        operation_id: str,
        skill_id: str,
        execution_id: str,
        *,
        calls: int,
        now_wall: float | None = None,
    ) -> QuotaUsageEvent:
        if isinstance(calls, bool) or not isinstance(calls, int) or calls <= 0:
            raise ValueError("calls must be a positive integer")
        return self.runtime.resolve_unknown_usage(
            operation_id,
            _event_id("skill", skill_id, execution_id),
            UsageEstimate(tool_calls=calls),
            now_wall=now_wall,
        )


__all__ = ["SkillUsageMeter"]
