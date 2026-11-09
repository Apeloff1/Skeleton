"""Versioned provider capability attestations for model rollout control."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from types import MappingProxyType
from typing import Mapping

from skeleton.shells.ai.model_port import ModelCapabilities


@dataclass(frozen=True)
class ProviderAttestation:
    provider_id: str
    model_id: str
    model_version: str
    adapter_version: str
    capabilities: ModelCapabilities
    protocol_versions: tuple[int, ...]
    tool_catalog_digest: str
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("provider_id", "model_id", "model_version", "adapter_version"):
            value = getattr(self, name)
            if not value or len(value) > 256:
                raise ValueError(f"invalid {name}")
        versions = tuple(int(item) for item in self.protocol_versions)
        if not versions or any(item <= 0 for item in versions):
            raise ValueError("provider attestation protocol versions invalid")
        if len(self.tool_catalog_digest) != 64:
            raise ValueError("tool_catalog_digest must be SHA-256 hex")
        metadata = dict(self.metadata)
        if len(metadata) > 64:
            raise ValueError("too many provider attestation metadata fields")
        object.__setattr__(self, "protocol_versions", versions)
        object.__setattr__(self, "metadata", MappingProxyType(metadata))

    def to_dict(self) -> dict[str, object]:
        return {
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "model_version": self.model_version,
            "adapter_version": self.adapter_version,
            "capabilities": {
                "structured_output": self.capabilities.structured_output,
                "tool_use": self.capabilities.tool_use,
                "critique": self.capabilities.critique,
                "parallel_candidates": self.capabilities.parallel_candidates,
                "max_input_bytes": self.capabilities.max_input_bytes,
                "max_output_bytes": self.capabilities.max_output_bytes,
            },
            "protocol_versions": list(self.protocol_versions),
            "tool_catalog_digest": self.tool_catalog_digest,
            "metadata": dict(self.metadata),
        }

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class AttestationRequirement:
    require_structured_output: bool = True
    require_tool_use: bool = True
    require_critique: bool = False
    require_parallel_candidates: bool = False
    min_input_bytes: int = 0
    min_output_bytes: int = 0
    protocol_version: int = 1


@dataclass(frozen=True)
class AttestationReport:
    compatible: bool
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {"compatible": self.compatible, "reasons": list(self.reasons)}


class ProviderAttestationVerifier:
    def inspect(
        self,
        attestation: ProviderAttestation,
        requirement: AttestationRequirement,
        *,
        expected_tool_catalog_digest: str,
    ) -> AttestationReport:
        reasons = []
        caps = attestation.capabilities
        if requirement.require_structured_output and not caps.structured_output:
            reasons.append("provider lacks structured output")
        if requirement.require_tool_use and not caps.tool_use:
            reasons.append("provider lacks tool use")
        if requirement.require_critique and not caps.critique:
            reasons.append("provider lacks critique capability")
        if requirement.require_parallel_candidates and not caps.parallel_candidates:
            reasons.append("provider lacks parallel candidate capability")
        if caps.max_input_bytes < requirement.min_input_bytes:
            reasons.append("provider input byte capacity below requirement")
        if caps.max_output_bytes < requirement.min_output_bytes:
            reasons.append("provider output byte capacity below requirement")
        if requirement.protocol_version not in attestation.protocol_versions:
            reasons.append("provider does not attest required AI protocol version")
        if attestation.tool_catalog_digest != expected_tool_catalog_digest:
            reasons.append("provider attestation tool catalog digest mismatch")
        return AttestationReport(not reasons, tuple(reasons))
