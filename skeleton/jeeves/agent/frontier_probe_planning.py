"""Falsification and evidence-probe planning for Jeeves frontier reasoning.

A frontier reasoning decision can say that more evidence or deliberation is
needed, but that signal is only useful if the runtime can turn it into a
specific, auditable knowledge obligation. This module bridges the reasoning
coordinator to Jeeves' existing epistemic-frontier engine.

The planner is deliberately host-side and non-executing. It derives measurable
gap signals from an existing FrontierReasoningDecision, asks
EpistemicFrontierEngine to rank bounded probes, and returns a deterministic plan
for the replanner/context system. It does not call models, retrieval systems, or
tools and therefore cannot bypass runtime authorization.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .epistemic_frontier import (
    EpistemicFrontierEngine,
    EpistemicGap,
    FrontierSnapshot,
    KnowledgeObligation,
    ProbeCandidate,
)
from .frontier_reasoning import (
    EscalationCause,
    FrontierReasoningDecision,
)
from .types import AgentContractError, RiskTier, json_safe, positive_int, stable_fingerprint, stable_id


_RISK_IMPACT = {
    RiskTier.READ_ONLY: 0.25,
    RiskTier.REVERSIBLE: 0.40,
    RiskTier.MUTATING: 0.65,
    RiskTier.EXTERNAL: 0.80,
    RiskTier.HIGH_IMPACT: 1.00,
}


@dataclass(frozen=True, slots=True)
class FrontierProbePolicy:
    """Controls how many ranked epistemic probes are exposed to replanning."""

    maximum_probes: int = 6

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "maximum_probes",
            positive_int("maximum_probes", self.maximum_probes, maximum=64),
        )


@dataclass(frozen=True, slots=True)
class FrontierProbePlan:
    """Auditable evidence-seeking plan derived from one frontier decision."""

    decision_fingerprint: str
    obligation: KnowledgeObligation
    gaps: tuple[EpistemicGap, ...]
    probes: tuple[ProbeCandidate, ...]
    frontier_pressure: float
    unresolved_decision_value: float
    metadata: Mapping[str, Any]
    fingerprint: str

    def __post_init__(self) -> None:
        if not self.decision_fingerprint:
            raise AgentContractError("decision_fingerprint must be non-empty")
        if not isinstance(self.obligation, KnowledgeObligation):
            raise TypeError("obligation must be KnowledgeObligation")
        if any(not isinstance(item, EpistemicGap) for item in self.gaps):
            raise TypeError("gaps must contain EpistemicGap")
        if any(not isinstance(item, ProbeCandidate) for item in self.probes):
            raise TypeError("probes must contain ProbeCandidate")
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))

    @property
    def selected_probe(self) -> ProbeCandidate | None:
        return self.probes[0] if self.probes else None

    def as_json(self) -> dict[str, Any]:
        return {
            "decision_fingerprint": self.decision_fingerprint,
            "obligation": self.obligation.as_json(),
            "gaps": [item.as_json() for item in self.gaps],
            "probes": [item.as_json() for item in self.probes],
            "frontier_pressure": self.frontier_pressure,
            "unresolved_decision_value": self.unresolved_decision_value,
            "metadata": dict(self.metadata),
            "fingerprint": self.fingerprint,
        }


class FrontierProbePlanner:
    """Translate unresolved frontier reasoning into falsifiable probe options."""

    def __init__(
        self,
        *,
        engine: EpistemicFrontierEngine | None = None,
        policy: FrontierProbePolicy | None = None,
    ) -> None:
        self.engine = engine or EpistemicFrontierEngine()
        self.policy = policy or FrontierProbePolicy()

    def plan(self, decision: FrontierReasoningDecision) -> FrontierProbePlan:
        if not isinstance(decision, FrontierReasoningDecision):
            raise TypeError("decision must be FrontierReasoningDecision")

        obligation = self._obligation(decision)
        snapshot = self.engine.discover((obligation,))
        probes = tuple(snapshot.probes[: self.policy.maximum_probes])
        metadata = {
            "disposition": decision.disposition.value,
            "risk": decision.risk.value,
            "causes": [cause.value for cause in decision.causes],
            "diagnostics": {
                "entropy": decision.diagnostics.normalized_entropy,
                "action_disagreement": decision.diagnostics.action_disagreement,
                "outcome_disagreement": decision.diagnostics.outcome_disagreement,
                "evidence_overlap": decision.diagnostics.maximum_evidence_overlap,
                "effective_candidates": decision.diagnostics.effective_candidate_count,
            },
            "consensus": (
                {
                    "agreement": decision.consensus.agreement,
                    "entropy": decision.consensus.normalized_entropy,
                    "requires_more_sampling": decision.consensus.requires_more_sampling,
                }
                if decision.consensus is not None
                else None
            ),
        }
        fingerprint = stable_fingerprint(
            {
                "decision": decision.fingerprint,
                "obligation": obligation.fingerprint,
                "snapshot": snapshot.fingerprint,
                "probes": [probe.fingerprint for probe in probes],
                "metadata": metadata,
            }
        )
        return FrontierProbePlan(
            decision_fingerprint=decision.fingerprint,
            obligation=obligation,
            gaps=snapshot.gaps,
            probes=probes,
            frontier_pressure=snapshot.frontier_pressure,
            unresolved_decision_value=snapshot.unresolved_decision_value,
            metadata=metadata,
            fingerprint=fingerprint,
        )

    def _obligation(self, decision: FrontierReasoningDecision) -> KnowledgeObligation:
        lead = decision.leading_candidate
        assessment = decision.assessments[0] if decision.assessments else None
        evidence_refs = (
            tuple(ref.evidence_id for ref in lead.evidence)
            if lead is not None
            else ()
        )
        assumptions = tuple(lead.assumptions) if lead is not None else ()

        confidence = assessment.absolute_quality if assessment is not None else 0.0
        evidence_coverage = assessment.evidence_quality if assessment is not None else 0.0

        disagreement = max(
            decision.diagnostics.normalized_entropy,
            decision.diagnostics.action_disagreement,
            decision.diagnostics.outcome_disagreement,
        )
        if decision.consensus is not None:
            disagreement = max(
                disagreement,
                decision.consensus.normalized_entropy,
                1.0 - decision.consensus.agreement,
            )

        contradiction = 0.0
        if decision.lens_fusion is not None:
            contradiction = max(
                contradiction,
                decision.lens_fusion.conflict_strength,
            )
        if EscalationCause.VERIFICATION_REJECTED in decision.causes:
            contradiction = 1.0
        elif EscalationCause.VERIFICATION_ABSTAINED in decision.causes:
            contradiction = max(contradiction, 0.50)

        assumption_load = min(
            1.0,
            max(
                len(assumptions) / 4.0,
                0.25 if EscalationCause.LENS_SENSITIVITY in decision.causes else 0.0,
            ),
        )

        if lead is None:
            question = (
                "What decision-relevant evidence is missing before Jeeves can "
                "justify a candidate action?"
            )
            candidate_id = None
            action = None
            outcome = None
        else:
            question = (
                "What evidence would most strongly confirm or falsify candidate "
                f"{lead.candidate_id} before proceeding with action: "
                f"{lead.proposed_action[:2048]}"
            )
            candidate_id = lead.candidate_id
            action = lead.proposed_action
            outcome = lead.predicted_outcome

        obligation_id = stable_id(
            "frontier-obligation",
            {
                "decision": decision.fingerprint,
                "candidate": candidate_id,
                "risk": decision.risk.value,
            },
            length=30,
        )
        return KnowledgeObligation(
            obligation_id=obligation_id,
            question=question,
            decision_impact=_RISK_IMPACT[decision.risk],
            confidence=confidence,
            evidence_coverage=evidence_coverage,
            freshness=1.0,
            contradiction_strength=max(0.0, min(1.0, contradiction)),
            model_disagreement=max(0.0, min(1.0, disagreement)),
            assumption_load=assumption_load,
            novelty=0.0,
            evidence_refs=evidence_refs,
            assumptions=assumptions,
            metadata={
                "decision_fingerprint": decision.fingerprint,
                "candidate_id": candidate_id,
                "proposed_action": action,
                "predicted_outcome": outcome,
                "disposition": decision.disposition.value,
                "causes": [cause.value for cause in decision.causes],
            },
        )


__all__ = [
    "FrontierProbePlan",
    "FrontierProbePlanner",
    "FrontierProbePolicy",
]
