"""Compatibility checks for AI shell clients and provider adapters."""

from __future__ import annotations

from dataclasses import dataclass

from skeleton.shells.ai.catalog import AIToolCatalog
from skeleton.shells.ai.model_port import AIModelPort
from skeleton.shells.ai.protocol import AI_MODEL_PROTOCOL_VERSION


@dataclass(frozen=True)
class AICompatibilityRequirement:
    min_protocol_version: int = 1
    max_protocol_version: int = 1
    required_tools: frozenset[str] = frozenset()
    require_structured_output: bool = True
    require_tool_use: bool = True
    require_critique: bool = False

    def __post_init__(self) -> None:
        if self.min_protocol_version <= 0:
            raise ValueError("minimum protocol version must be positive")
        if self.max_protocol_version < self.min_protocol_version:
            raise ValueError("maximum protocol version precedes minimum")


@dataclass(frozen=True)
class AICompatibilityReport:
    compatible: bool
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {"compatible": self.compatible, "reasons": list(self.reasons)}


class AICompatibility:
    def check(
        self,
        catalog: AIToolCatalog,
        model: AIModelPort,
        requirement: AICompatibilityRequirement,
    ) -> AICompatibilityReport:
        reasons = []
        if not (
            requirement.min_protocol_version
            <= AI_MODEL_PROTOCOL_VERSION
            <= requirement.max_protocol_version
        ):
            reasons.append("AI shell protocol version is outside required range")
        names = {item.name for item in catalog.cards()}
        missing = requirement.required_tools - names
        if missing:
            reasons.append("required tools are missing: " + ", ".join(sorted(missing)))
        capabilities = model.capabilities
        if requirement.require_structured_output and not capabilities.structured_output:
            reasons.append("model lacks structured-output capability")
        if requirement.require_tool_use and not capabilities.tool_use:
            reasons.append("model lacks tool-use capability")
        if requirement.require_critique and not capabilities.critique:
            reasons.append("model lacks critique capability")
        return AICompatibilityReport(not reasons, tuple(reasons))
