"""Canonical protocol manifests and tamper verification."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .contracts import ReverseEngineeringError, stable_digest


@dataclass(frozen=True)
class ProtocolManifest:
    protocol_id: str
    version: str
    parameters: Mapping[str, Any]
    protocol_digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "protocol_id": self.protocol_id,
            "version": self.version,
            "parameters": dict(self.parameters),
            "protocol_digest": self.protocol_digest,
        }


def build_protocol_manifest(
    protocol_id: str,
    version: str,
    parameters: Mapping[str, Any],
) -> ProtocolManifest:
    if not protocol_id or not version:
        raise ReverseEngineeringError("protocol identity and version are required")
    payload = {
        "protocol_id": protocol_id,
        "version": version,
        "parameters": dict(parameters),
    }
    return ProtocolManifest(
        protocol_id=protocol_id,
        version=version,
        parameters=dict(parameters),
        protocol_digest=stable_digest(payload),
    )


def verify_protocol_manifest(manifest: ProtocolManifest) -> bool:
    try:
        expected = stable_digest(
            {
                "protocol_id": manifest.protocol_id,
                "version": manifest.version,
                "parameters": dict(manifest.parameters),
            }
        )
    except ReverseEngineeringError:
        return False
    return expected == manifest.protocol_digest
