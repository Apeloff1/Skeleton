"""Enforcement gate for AI model or autonomy releases."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from skeleton.shells.ai.release_evidence import ReleaseEvidence


class ReleaseGateDecision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"


@dataclass(frozen=True)
class ReleaseGateResult:
    decision: ReleaseGateDecision
    release_id: str
    evidence_digest: str
    reasons: tuple[str, ...]

    @property
    def allowed(self) -> bool:
        return self.decision is ReleaseGateDecision.ALLOW

    def to_dict(self) -> dict[str, object]:
        return {
            "decision": self.decision.value,
            "allowed": self.allowed,
            "release_id": self.release_id,
            "evidence_digest": self.evidence_digest,
            "reasons": list(self.reasons),
        }


class AIReleaseGate:
    def inspect(
        self,
        evidence: ReleaseEvidence,
        *,
        expected_policy_fingerprint: str | None = None,
        expected_tool_catalog_digest: str | None = None,
        expected_effect_digest: str | None = None,
        expected_code_revision: str | None = None,
    ) -> ReleaseGateResult:
        reasons = []
        if not evidence.deployable:
            reasons.append("release safety case is not deployable")
        if (
            expected_policy_fingerprint is not None
            and evidence.policy_fingerprint != expected_policy_fingerprint
        ):
            reasons.append("release policy fingerprint mismatch")
        if (
            expected_tool_catalog_digest is not None
            and evidence.tool_catalog_digest != expected_tool_catalog_digest
        ):
            reasons.append("release tool catalog digest mismatch")
        if (
            expected_effect_digest is not None
            and evidence.effect_digest != expected_effect_digest
        ):
            reasons.append("release effect digest mismatch")
        if (
            expected_code_revision is not None
            and evidence.code_revision != expected_code_revision
        ):
            reasons.append("release code revision mismatch")
        return ReleaseGateResult(
            ReleaseGateDecision.ALLOW if not reasons else ReleaseGateDecision.DENY,
            evidence.release_id,
            evidence.digest,
            tuple(reasons),
        )

    def require(self, evidence: ReleaseEvidence, **kwargs) -> ReleaseGateResult:
        result = self.inspect(evidence, **kwargs)
        if not result.allowed:
            raise RuntimeError("; ".join(result.reasons))
        return result
