"""Canonical export envelopes for reverse-engineering reports."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .contracts import ReverseEngineeringError, canonical_json, is_sha256_digest, stable_digest


@dataclass(frozen=True)
class ReportEnvelope:
    schema_version: str
    report_kind: str
    report_digest: str
    payload: Mapping[str, Any]
    envelope_digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "report_kind": self.report_kind,
            "report_digest": self.report_digest,
            "payload": dict(self.payload),
            "envelope_digest": self.envelope_digest,
        }

    def to_json(self) -> str:
        return canonical_json(self.as_dict())


def build_report_envelope(
    report_kind: str,
    report_digest: str,
    payload: Mapping[str, Any],
    *,
    schema_version: str = "reverse-engineering.report.v1",
) -> ReportEnvelope:
    if not report_kind or not schema_version:
        raise ReverseEngineeringError("report envelope identity is required")
    if not is_sha256_digest(report_digest):
        raise ReverseEngineeringError("report_digest must be sha256 hex")
    payload_digest = stable_digest(payload)
    envelope_payload = {
        "schema_version": schema_version,
        "report_kind": report_kind,
        "report_digest": report_digest,
        "payload_digest": payload_digest,
    }
    return ReportEnvelope(
        schema_version=schema_version,
        report_kind=report_kind,
        report_digest=report_digest,
        payload=dict(payload),
        envelope_digest=stable_digest(envelope_payload),
    )


def verify_report_envelope(envelope: ReportEnvelope) -> bool:
    try:
        if not is_sha256_digest(envelope.report_digest):
            return False
        payload_digest = stable_digest(envelope.payload)
        expected = stable_digest(
            {
                "schema_version": envelope.schema_version,
                "report_kind": envelope.report_kind,
                "report_digest": envelope.report_digest,
                "payload_digest": payload_digest,
            }
        )
    except ReverseEngineeringError:
        return False
    return expected == envelope.envelope_digest
