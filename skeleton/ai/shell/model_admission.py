"""Fail-closed admission for model/provider identities used by shell planning."""

from __future__ import annotations

from dataclasses import dataclass

from skeleton.shells.ai.model_registry import AIModelRegistry, RegisteredModel
from skeleton.shells.ai.provider_attestation import (
    AttestationRequirement,
    AttestationReport,
    ProviderAttestationVerifier,
)


@dataclass(frozen=True)
class ModelAdmissionRequirement:
    provider_id: str
    model_id: str
    tool_catalog_digest: str
    attestation: AttestationRequirement = AttestationRequirement()
    exact_model_version: str = ""
    exact_adapter_version: str = ""
    expected_attestation_digest: str = ""

    def __post_init__(self) -> None:
        if not self.provider_id or len(self.provider_id) > 256:
            raise ValueError("invalid required provider_id")
        if not self.model_id or len(self.model_id) > 256:
            raise ValueError("invalid required model_id")
        if len(self.tool_catalog_digest) != 64:
            raise ValueError("tool_catalog_digest must be SHA-256 hex")
        if len(self.exact_model_version) > 256:
            raise ValueError("exact_model_version too long")
        if len(self.exact_adapter_version) > 256:
            raise ValueError("exact_adapter_version too long")
        if self.expected_attestation_digest and len(self.expected_attestation_digest) != 64:
            raise ValueError("expected_attestation_digest must be SHA-256 hex")

    @property
    def registry_id(self) -> str:
        return f"{self.provider_id}:{self.model_id}"


@dataclass(frozen=True)
class ModelAdmissionReport:
    allowed: bool
    reasons: tuple[str, ...]
    registry_id: str
    registry_revision: int | None
    attestation_digest: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "allowed": self.allowed,
            "reasons": list(self.reasons),
            "registry_id": self.registry_id,
            "registry_revision": self.registry_revision,
            "attestation_digest": self.attestation_digest,
        }


class AIModelAdmission:
    """Verify that a model is active and attested for the exact tool surface."""

    def __init__(
        self,
        registry: AIModelRegistry,
        *,
        verifier: ProviderAttestationVerifier | None = None,
    ) -> None:
        self.registry = registry
        self.verifier = verifier or ProviderAttestationVerifier()

    def inspect(
        self,
        requirement: ModelAdmissionRequirement,
    ) -> ModelAdmissionReport:
        try:
            registered = self.registry.current(requirement.registry_id)
        except KeyError:
            return ModelAdmissionReport(
                False,
                ("model/provider identity is not registered",),
                requirement.registry_id,
                None,
            )
        reasons = []
        if not registered.active:
            reasons.append("model/provider registry entry is inactive")
        attestation = registered.attestation
        if attestation.provider_id != requirement.provider_id:
            reasons.append("registered provider identity mismatch")
        if attestation.model_id != requirement.model_id:
            reasons.append("registered model identity mismatch")
        if (
            requirement.exact_model_version
            and attestation.model_version != requirement.exact_model_version
        ):
            reasons.append("registered model version mismatch")
        if (
            requirement.exact_adapter_version
            and attestation.adapter_version != requirement.exact_adapter_version
        ):
            reasons.append("registered adapter version mismatch")
        if (
            requirement.expected_attestation_digest
            and attestation.digest != requirement.expected_attestation_digest
        ):
            reasons.append("provider attestation digest mismatch")
        attestation_report = self.verifier.inspect(
            attestation,
            requirement.attestation,
            expected_tool_catalog_digest=requirement.tool_catalog_digest,
        )
        reasons.extend(attestation_report.reasons)
        return ModelAdmissionReport(
            not reasons,
            tuple(reasons),
            requirement.registry_id,
            registered.revision,
            attestation.digest,
        )

    def require(
        self,
        requirement: ModelAdmissionRequirement,
    ) -> ModelAdmissionReport:
        report = self.inspect(requirement)
        if not report.allowed:
            raise RuntimeError("; ".join(report.reasons))
        return report
