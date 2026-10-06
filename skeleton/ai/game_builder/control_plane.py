"""Integrated deterministic control plane for the overengineered game-builder forge."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .contracts import Candidate, Challenge, GateResult, PromotionReceipt, canonical_digest
from .dual_rival_forge import DualRivalForge, ForgeStatus
from .evaluation import EvaluationPanel, PanelDecision
from .quality_debt import QualityDebtLedger
from .resource_governor import ResourceDelta, ResourceGovernor, ResourceSnapshot


class ControlPlaneError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ControlledStatus:
    forge: ForgeStatus
    resources: ResourceSnapshot
    quality_debt_score: int
    protected_quality_debt_score: int
    quality_debt_allows_promotion: bool

    def to_payload(self) -> dict[str, object]:
        return {
            "forge": self.forge.to_payload(),
            "protected_quality_debt_score": self.protected_quality_debt_score,
            "quality_debt_allows_promotion": self.quality_debt_allows_promotion,
            "quality_debt_score": self.quality_debt_score,
            "resources": self.resources.to_payload(),
        }


class ForgeControlPlane:
    """Compose duel order, evaluator quorum, resource limits and debt ratchet."""

    SCHEMA = "skeleton.ai_game_builder.control_plane.v1"

    def __init__(
        self,
        *,
        forge: DualRivalForge,
        evaluation_panel: EvaluationPanel,
        resource_governor: ResourceGovernor,
        quality_debt: QualityDebtLedger,
    ) -> None:
        self.forge = forge
        self.evaluation_panel = evaluation_panel
        self.resource_governor = resource_governor
        self.quality_debt = quality_debt

    @property
    def status(self) -> ControlledStatus:
        return ControlledStatus(
            forge=self.forge.status,
            resources=self.resource_governor.snapshot,
            quality_debt_score=self.quality_debt.total_score,
            protected_quality_debt_score=self.quality_debt.protected_score,
            quality_debt_allows_promotion=self.quality_debt.promotion_allowed(),
        )

    def submit_construct(
        self,
        candidate: Candidate,
        *,
        resources: ResourceDelta,
    ) -> ControlledStatus:
        self.resource_governor.charge(resources)
        self.forge.submit_construct(candidate)
        return self.status

    def submit_attack(
        self,
        challenge: Challenge,
        *,
        resources: ResourceDelta,
    ) -> ControlledStatus:
        self.resource_governor.charge(resources)
        self.forge.submit_attack(challenge)
        return self.status

    def reconcile(
        self,
        *,
        submitted: Candidate | None,
        panel_decision: PanelDecision | None,
        gate_results: Sequence[GateResult],
        resources: ResourceDelta,
    ) -> PromotionReceipt:
        self.resource_governor.charge(resources)
        gates = list(gate_results)

        if submitted is None:
            if panel_decision is not None:
                raise ControlPlaneError(
                    "panel decision must be absent when no candidate is submitted"
                )
            evaluator_id = "control-plane-retain"
        else:
            if panel_decision is None:
                raise ControlPlaneError(
                    "submitted candidate requires independent evaluator panel decision"
                )
            if panel_decision.candidate_digest != submitted.digest:
                raise ControlPlaneError(
                    "evaluator panel decision does not match submitted candidate"
                )
            gates.append(
                GateResult(
                    "evaluator_panel",
                    panel_decision.eligible,
                    panel_decision.decision_digest,
                    non_compensable=True,
                )
            )
            debt_payload = self.quality_debt.snapshot()
            gates.append(
                GateResult(
                    "quality_debt",
                    self.quality_debt.promotion_allowed(),
                    str(debt_payload["debt_digest"]),
                    non_compensable=True,
                )
            )
            evaluator_id = (
                "panel:"
                + canonical_digest(
                    {
                        "decision": panel_decision.decision_digest,
                        "evaluators": list(panel_decision.evaluator_ids),
                        "methods": list(panel_decision.method_ids),
                    }
                )[:32]
            )

        return self.forge.reconcile(
            submitted=submitted,
            evaluator_id=evaluator_id,
            gate_results=tuple(gates),
        )

    def checkpoint_bundle(self) -> dict[str, object]:
        core: dict[str, object] = {
            "forge": self.forge.checkpoint(),
            "quality_debt": self.quality_debt.snapshot(),
            "resources": self.resource_governor.to_checkpoint(),
            "schema": self.SCHEMA,
        }
        return {**core, "bundle_digest": canonical_digest(core)}
