"""Join the existing homebrew port blueprint with independent legal admission.

Technical feasibility and legality are separate dimensions. A rights-risk hold
must not be laundered into a buildable 'approved' artifact merely because a
deterministic technical port plan could be generated.
"""
from __future__ import annotations

from dataclasses import dataclass
from .legal_paths import (
    HomebrewLegalRequest, HomebrewLegalAssessment, HomebrewPolicyError,
    LegalDisposition, assess_homebrew,
)
from .port_planner import (
    HomebrewSource, PortBlueprint, PortMode, PortRequest, compile_port,
)
from .platform_registry import PlatformRegistry


@dataclass(frozen=True, slots=True)
class RightsAwarePortProposal:
    legal: HomebrewLegalAssessment
    technical_blueprint: PortBlueprint | None
    design_stage_admitted: bool
    release_certified: bool = False
    native_build_verified: bool = False

    @property
    def disposition(self) -> str:
        return self.legal.disposition.value


def propose_rights_aware_port(
    source: HomebrewSource, facts: HomebrewLegalRequest, *,
    mode: PortMode = PortMode.ENHANCED,
    registry: PlatformRegistry | None = None,
) -> RightsAwarePortProposal:
    """Admit design only if both rights and target identity agree, never auto-release."""
    if not isinstance(source, HomebrewSource) or not isinstance(facts, HomebrewLegalRequest):
        raise HomebrewPolicyError("typed homebrew and legal facts required")
    if source.project_id != facts.project_id:
        raise HomebrewPolicyError("rights packet cannot authorize another project")
    if source.platform_id != facts.source_platform_id:
        raise HomebrewPolicyError("source hardware identity mismatch")
    if source.evidence_sha256 != facts.rights_packet_sha256:
        raise HomebrewPolicyError("source evidence differs from legal rights packet")
    assessment = assess_homebrew(facts, registry=registry)
    if assessment.disposition is not LegalDisposition.DESIGN_ALLOWED_RELEASE_NOT_CERTIFIED:
        return RightsAwarePortProposal(assessment, None, False)
    plan = compile_port(PortRequest((source,), facts.target_platform_id, mode), registry=registry)
    return RightsAwarePortProposal(assessment, plan, True)
