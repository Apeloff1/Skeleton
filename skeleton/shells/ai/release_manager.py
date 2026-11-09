"""Release manager that gates signed AI releases before policy rollout."""

from __future__ import annotations

from dataclasses import dataclass

from skeleton.shells.ai.policy import AIShellPolicy
from skeleton.shells.ai.policy_rollout import AIPolicyRollout
from skeleton.shells.ai.release_gate import AIReleaseGate, ReleaseGateDecision, ReleaseGateResult
from skeleton.shells.ai.release_registry import AIReleaseRegistry, RegisteredRelease
from skeleton.shells.ai.governance import AIShellGovernance
from skeleton.shells.ai.release_evidence import ReleaseEvidence


@dataclass(frozen=True)
class PreparedAIRelease:
    registered: RegisteredRelease
    gate: ReleaseGateResult
    rollout: AIPolicyRollout | None

    def to_dict(self) -> dict[str, object]:
        return {
            "registered": self.registered.to_dict(),
            "gate": self.gate.to_dict(),
            "rollout": None if self.rollout is None else self.rollout.to_dict(),
        }


class AIReleaseManager:
    """Signed evidence must pass the release gate before autonomy rollout."""

    def __init__(
        self,
        registry: AIReleaseRegistry,
        governance: AIShellGovernance,
        *,
        gate: AIReleaseGate | None = None,
        expected_tool_catalog_digest: str | None = None,
        expected_effect_digest: str | None = None,
        expected_code_revision: str | None = None,
    ) -> None:
        for name, value in (
            ("expected_tool_catalog_digest", expected_tool_catalog_digest),
            ("expected_effect_digest", expected_effect_digest),
        ):
            if value is not None and len(value) != 64:
                raise ValueError(f"{name} must be SHA-256 hex")
        if expected_code_revision is not None and not expected_code_revision:
            raise ValueError("expected_code_revision may not be empty")
        self.registry = registry
        self.governance = governance
        self.gate = gate or AIReleaseGate()
        self.expected_tool_catalog_digest = expected_tool_catalog_digest
        self.expected_effect_digest = expected_effect_digest
        self.expected_code_revision = expected_code_revision

    def prepare(
        self,
        evidence: ReleaseEvidence,
        *,
        target_policy: AIShellPolicy | None = None,
        canary_percent: int = 10,
        rollout_reason: str = "",
    ) -> PreparedAIRelease:
        current_policy = self.governance.current_policy()
        gate = self.gate.inspect(
            evidence,
            expected_tool_catalog_digest=self.expected_tool_catalog_digest,
            expected_effect_digest=self.expected_effect_digest,
            expected_code_revision=self.expected_code_revision,
        )
        if target_policy is None:
            if evidence.policy_fingerprint != current_policy.fingerprint:
                gate = ReleaseGateResult(
                    ReleaseGateDecision.DENY,
                    evidence.release_id,
                    evidence.digest,
                    gate.reasons + ("release policy does not match active policy",),
                )
        else:
            if evidence.policy_fingerprint != target_policy.fingerprint:
                gate = ReleaseGateResult(
                    ReleaseGateDecision.DENY,
                    evidence.release_id,
                    evidence.digest,
                    gate.reasons + ("release evidence does not match target policy",),
                )
        if not gate.allowed:
            raise RuntimeError("; ".join(gate.reasons))
        registered = self.registry.register(evidence)
        rollout = None
        if target_policy is not None and target_policy.fingerprint != current_policy.fingerprint:
            rollout = self.governance.prepare_policy_rollout(
                f"release:{evidence.release_id}",
                target_policy,
                canary_percent=canary_percent,
                reason=rollout_reason,
            )
        return PreparedAIRelease(registered, gate, rollout)

    def activate(self, release_id: str) -> RegisteredRelease:
        return self.registry.activate(release_id)
