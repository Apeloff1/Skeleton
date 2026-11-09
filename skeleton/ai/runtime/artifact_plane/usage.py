"""Actual artifact/storage usage metering adapters."""

from __future__ import annotations

import hashlib

from skeleton.intelligence.admission import UsageEstimate
from skeleton.intelligence.admission_runtime import (
    AdmissionRuntime,
    UnknownUsageMarker,
)
from skeleton.intelligence.quota import QuotaUsageEvent


def _event_id(kind: str, resource_id: str, write_id: str) -> str:
    resource = str(resource_id).strip()
    write = str(write_id).strip()
    if not resource or not write:
        raise ValueError("resource_id and write_id are required")
    material = "\x1f".join((kind, resource, write)).encode("utf-8")
    return kind + "-" + hashlib.sha256(material).hexdigest()[:24]


class ArtifactUsageMeter:
    """Charge actual artifact and storage writes to one admitted operation."""

    def __init__(self, runtime: AdmissionRuntime) -> None:
        if not isinstance(runtime, AdmissionRuntime):
            raise TypeError("runtime must be an AdmissionRuntime")
        self.runtime = runtime

    def meter_artifact(
        self,
        operation_id: str,
        artifact_id: str,
        write_id: str,
        byte_count: int,
        *,
        now_wall: float | None = None,
    ) -> QuotaUsageEvent:
        return self.runtime.meter_artifact_bytes(
            operation_id,
            _event_id("artifact", artifact_id, write_id),
            byte_count,
            now_wall=now_wall,
        )

    def meter_storage(
        self,
        operation_id: str,
        resource_id: str,
        write_id: str,
        byte_count: int,
        *,
        now_wall: float | None = None,
    ) -> QuotaUsageEvent:
        return self.runtime.meter_storage_bytes(
            operation_id,
            _event_id("storage", resource_id, write_id),
            byte_count,
            now_wall=now_wall,
        )

    def mark_unknown(
        self,
        operation_id: str,
        category: str,
        resource_id: str,
        write_id: str,
        reason: str,
        *,
        now_wall: float | None = None,
    ) -> UnknownUsageMarker:
        normalized = str(category).strip().lower()
        if normalized not in {"artifact", "storage"}:
            raise ValueError("category must be artifact or storage")
        return self.runtime.mark_usage_unknown(
            operation_id,
            _event_id(normalized, resource_id, write_id),
            normalized,
            reason,
            now_wall=now_wall,
        )

    def resolve_unknown(
        self,
        operation_id: str,
        category: str,
        resource_id: str,
        write_id: str,
        byte_count: int,
        *,
        now_wall: float | None = None,
    ) -> QuotaUsageEvent:
        normalized = str(category).strip().lower()
        if normalized not in {"artifact", "storage"}:
            raise ValueError("category must be artifact or storage")
        if (
            isinstance(byte_count, bool)
            or not isinstance(byte_count, int)
            or byte_count < 0
        ):
            raise ValueError("byte_count must be a non-negative integer")
        delta = (
            UsageEstimate(artifact_bytes=byte_count)
            if normalized == "artifact"
            else UsageEstimate(storage_bytes=byte_count)
        )
        return self.runtime.resolve_unknown_usage(
            operation_id,
            _event_id(normalized, resource_id, write_id),
            delta,
            now_wall=now_wall,
        )


__all__ = ["ArtifactUsageMeter"]
