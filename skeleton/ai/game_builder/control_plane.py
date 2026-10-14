"""Integrated deterministic control plane for the overengineered game-builder forge."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .contracts import (
    Candidate,
    Challenge,
    EvaluatorProvenance,
    GateResult,
    PromotionReceipt,
    canonical_digest,
)
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


def _deterministic_evaluator_provenance(
    *,
    evaluator_id: str,
    method_id: str,
    evidence_refs: tuple[str, ...],
    input_digest: str,
) -> EvaluatorProvenance:
    authority_identity = canonical_digest(
        {
            "component": "skeleton.ai.game_builder.control_plane",
            "method_id": method_id,
            "schema": "skeleton.ai_game_builder.control_plane.v1",
        }
    )
    execution_identity = canonical_digest(
        {
            "authority_identity": authority_identity,
            "evaluator_id": evaluator_id,
            "input_digest": input_digest,
            "method_id": method_id,
        }
    )
    finalization = canonical_digest(
        {
            "evidence_refs": list(evidence_refs),
            "execution_identity": execution_identity,
        }
    )
    return EvaluatorProvenance(
        evaluator_id=evaluator_id,
        operation_id=f"control-plane:{method_id}",
        execution_id=f"deterministic:{execution_identity[:32]}",
        execution_identity_digest=execution_identity,
        finalization_intent_digest=finalization,
        authority_kind="deterministic_control",
        authority_identity_digest=authority_identity,
        method_id=method_id,
        source_revision=authority_identity,
        output_evidence_refs=evidence_refs,
    )


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
            authority_evidence_digest = canonical_digest(
                {
                    "champion": self.forge.champion.digest,
                    "decision": "retain_incumbent",
                    "round_index": self.forge.round_index,
                }
            )
            evaluator_provenance = _deterministic_evaluator_provenance(
                evaluator_id=evaluator_id,
                method_id="retain-without-submission",
                evidence_refs=(authority_evidence_digest,),
                input_digest=self.forge.champion.digest,
            )
            evaluation_decision_digest = None
        else:
            if panel_decision is None:
                raise ControlPlaneError(
                    "submitted candidate requires independent evaluator panel decision"
                )
            if panel_decision.candidate_digest != submitted.digest:
                raise ControlPlaneError(
                    "evaluator panel decision does not match submitted candidate"
                )
            canonical_panel_decision = self.evaluation_panel.decide(submitted.digest)
            if canonical_panel_decision.decision_digest != panel_decision.decision_digest:
                raise ControlPlaneError(
                    "panel decision is not the canonical decision from the bound evaluator panel"
                )
            panel_decision = canonical_panel_decision
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
            evaluator_provenance = _deterministic_evaluator_provenance(
                evaluator_id=evaluator_id,
                method_id="panel-aggregation",
                evidence_refs=(
                    panel_decision.decision_digest,
                    panel_decision.evidence_root,
                ),
                input_digest=panel_decision.evidence_root,
            )
            authority_evidence_digest = panel_decision.decision_digest
            evaluation_decision_digest = panel_decision.decision_digest
            gates.append(
                GateResult(
                    "evaluator_panel",
                    panel_decision.eligible,
                    panel_decision.decision_digest,
                    evaluator_provenance=evaluator_provenance,
                    non_compensable=True,
                )
            )
            debt_payload = self.quality_debt.snapshot()
            debt_digest = str(debt_payload["debt_digest"])
            debt_provenance = _deterministic_evaluator_provenance(
                evaluator_id="control-plane:quality-debt",
                method_id="quality-debt-gate",
                evidence_refs=(debt_digest,),
                input_digest=debt_digest,
            )
            gates.append(
                GateResult(
                    "quality_debt",
                    self.quality_debt.promotion_allowed(),
                    debt_digest,
                    evaluator_provenance=debt_provenance,
                    non_compensable=True,
                )
            )
            declared = submitted.quality_map
            adjudicated = panel_decision.quality_map
            max_drift = max(
                abs(declared[axis] - adjudicated[axis])
                for axis in declared
            )
            calibration_digest = canonical_digest(
                {
                    "candidate": submitted.digest,
                    "declared": declared,
                    "adjudicated": adjudicated,
                    "max_drift": max_drift,
                    "threshold": 0.15,
                }
            )
            calibration_provenance = _deterministic_evaluator_provenance(
                evaluator_id="control-plane:quality-calibration",
                method_id="quality-calibration-gate",
                evidence_refs=(calibration_digest,),
                input_digest=submitted.digest,
            )
            gates.append(
                GateResult(
                    "quality_calibration",
                    max_drift <= 0.15,
                    calibration_digest,
                    evaluator_provenance=calibration_provenance,
                    non_compensable=True,
                )
            )

        return self.forge.reconcile(
            submitted=submitted,
            evaluator_id=evaluator_id,
            evaluator_provenance=evaluator_provenance,
            authority_evidence_digest=authority_evidence_digest,
            gate_results=tuple(gates),
            evaluated_quality=(
                panel_decision.quality_map
                if submitted is not None and panel_decision is not None
                else None
            ),
            evaluation_decision_digest=evaluation_decision_digest,
        )

    def checkpoint_bundle(self) -> dict[str, object]:
        core: dict[str, object] = {
            "forge": self.forge.checkpoint(),
            "quality_debt": self.quality_debt.snapshot(),
            "resources": self.resource_governor.to_checkpoint(),
            "schema": self.SCHEMA,
        }
        return {**core, "bundle_digest": canonical_digest(core)}
