"""Source-custodied VOL-249..252 research planning for offline game design.

Pure, side-effect-free plan construction: not a model provider, runtime executor,
experiment runner, publisher or authorization oracle. A high provisional model
score and a simulation can never become an independently verified measurement.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
from itertools import islice
import json
import math
import re
from typing import Any, Iterable

from skeleton.intelligence.strategy_registry import (
    CognitiveControlDecision,
    ReasoningPolicy,
    ReasoningRisk,
    ReasoningStep,
    StopDisposition,
    StrategyCandidate,
    evaluate_cognitive_control,
)
from .causal_knowledge import CausalGraph, CausalGraphSnapshot, InterventionResult
from .hypothesis_engine import HypothesisComparison, HypothesisLedger
from .source_lineage import ResearchSourceRegistry

_TOKEN = re.compile(r"^[A-Za-z][A-Za-z0-9._:-]{0,127}$")
_MAX_CANDIDATES = 16
_SCHEMA = "skeleton.research.game-design-probe.v1"


class ProbePlanningError(ValueError):
    """Request or custody cannot be admitted to the non-authorizing planner."""


class ProbeEvidenceStatus(str, Enum):
    UNASSESSED = "unassessed"
    CONTESTED = "contested"
    TENTATIVE = "tentative-unverified"


def _token(value: object, name: str) -> str:
    if not isinstance(value, str) or not _TOKEN.fullmatch(value):
        raise ProbePlanningError(name + " must be a bounded stable identifier")
    return value


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or (
        value != value.strip()
    ) or len(value) > 1024:
        raise ProbePlanningError(name + " must be normalized bounded text")
    return value


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, ensure_ascii=False, allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class DesignProbeRequest:
    """A planned question in a named game project, never an execution request."""

    probe_id: str
    project_id: str
    question_id: str
    metric: str
    risk: ReasoningRisk
    intervention_variable: str | None = None
    intervention_delta: float | None = None
    allow_hypothesized_model: bool = False

    def __post_init__(self) -> None:
        for key in ("probe_id", "project_id", "question_id"):
            _token(getattr(self, key), key)
        object.__setattr__(self, "metric", _text(self.metric, "metric"))
        if not isinstance(self.risk, ReasoningRisk):
            raise ProbePlanningError("risk must be a typed ReasoningRisk")
        if not isinstance(self.allow_hypothesized_model, bool):
            raise ProbePlanningError("allow_hypothesized_model must be boolean")
        if (self.intervention_variable is None) != (
            self.intervention_delta is None
        ):
            raise ProbePlanningError("intervention variable and delta must be paired")
        if self.intervention_variable is None:
            if self.allow_hypothesized_model:
                raise ProbePlanningError("hypothetical model opt-in requires intervention")
        else:
            _token(self.intervention_variable, "intervention_variable")
            delta = self.intervention_delta
            if isinstance(delta, bool) or not isinstance(delta, (int, float)):
                raise ProbePlanningError("intervention delta outside bounded model range")
            try:
                bounded_delta = float(delta)
            except (OverflowError, ValueError) as exc:
                raise ProbePlanningError("intervention delta outside bounded model range") from exc
            if not math.isfinite(bounded_delta) or not -10.0 <= bounded_delta <= 10.0:
                raise ProbePlanningError("intervention delta outside bounded model range")

    def payload(self) -> dict[str, Any]:
        return {
            "probe_id": self.probe_id,
            "project_id": self.project_id,
            "question_id": self.question_id,
            "metric": self.metric,
            "risk": self.risk.value,
            "intervention_variable": self.intervention_variable,
            "intervention_delta": self.intervention_delta,
            "allow_hypothesized_model": self.allow_hypothesized_model,
        }


@dataclass(frozen=True, slots=True)
class DesignProbePlan:
    request: DesignProbeRequest
    comparison: HypothesisComparison
    causal_snapshot: CausalGraphSnapshot
    control: CognitiveControlDecision
    simulation: InterventionResult | None
    source_ids: tuple[str, ...]
    evidence_status: ProbeEvidenceStatus
    receipt_digest: str

    @property
    def executable(self) -> bool:
        """A research plan never authorizes a game, provider or world mutation."""
        return False

    @property
    def next_strategy(self) -> str | None:
        if self.control.stopping.disposition is not StopDisposition.CONTINUE:
            return None
        return (
            self.control.selection.strategy.value
            if self.control.selection is not None else None
        )

    def payload(self) -> dict[str, Any]:
        """Render-safe bounded portable receipt with no claims of observed simulation."""
        return {
            "schema": _SCHEMA,
            "request": self.request.payload(),
            "hypothesis_comparison_digest": self.comparison.receipt_digest,
            "causal_graph_digest": self.causal_snapshot.receipt_digest,
            "reasoning_control_digest": self.control.decision_digest,
            "simulation_digest": (
                self.simulation.receipt_digest if self.simulation else None
            ),
            "simulation_kind": (
                self.simulation.result_kind if self.simulation else None
            ),
            "source_ids": list(self.source_ids),
            "evidence_status": self.evidence_status.value,
            "stop_disposition": self.control.stopping.disposition.value,
            "next_strategy": self.next_strategy,
            "observation_verified": False,
            "execution_authorized": False,
            "receipt_digest": self.receipt_digest,
        }


class DesignProbePlanner:
    """Join the existing three authority-neutral contracts by one source owner.

    Refuses independently constructed registries even if IDs/digests collide.
    Re-reads all source custody before sealing the plan; receipt replay is
    deterministic, but the result is never an authorization for subsequent use.
    """

    def __init__(
        self,
        sources: ResearchSourceRegistry,
        hypotheses: HypothesisLedger,
        causal_graph: CausalGraph,
    ) -> None:
        if not isinstance(sources, ResearchSourceRegistry):
            raise ProbePlanningError("canonical source registry required")
        if not isinstance(hypotheses, HypothesisLedger) or not isinstance(
            causal_graph, CausalGraph
        ):
            raise ProbePlanningError("typed research models required")
        if hypotheses.sources is not sources or causal_graph.sources is not sources:
            raise ProbePlanningError("models must share same exact source registry instance")
        self._sources = sources
        self._hypotheses = hypotheses
        self._causal_graph = causal_graph

    def plan(
        self,
        request: DesignProbeRequest,
        policy: ReasoningPolicy,
        candidates: Iterable[StrategyCandidate],
        history: Iterable[ReasoningStep],
        *,
        decision_index: int = 1,
        previous_decision_digest: str = "0" * 64,
    ) -> DesignProbePlan:
        if not isinstance(request, DesignProbeRequest):
            raise ProbePlanningError("typed game-design probe required")
        if not isinstance(policy, ReasoningPolicy):
            raise ProbePlanningError("versioned reasoning policy required")
        candidate_rows = tuple(islice(candidates, _MAX_CANDIDATES + 1))
        if not candidate_rows or len(candidate_rows) > _MAX_CANDIDATES:
            raise ProbePlanningError("candidate set must contain 1..16 strategies")
        # Bound even adversarial / infinite iterators before calling the owner.
        history_rows = tuple(islice(history, policy.max_steps + 1))
        if not history_rows or len(history_rows) > policy.max_steps:
            raise ProbePlanningError("history outside policy step bounds")

        comparison = self._hypotheses.compare(request.question_id)
        snapshot = self._causal_graph.snapshot()
        # The authoritative stopping/selection logic owns budget admission,
        # verification-at-risk and the next-step reservation. No alternate loop.
        decision = evaluate_cognitive_control(
            policy, candidate_rows, history_rows, risk=request.risk,
            decision_index=decision_index,
            previous_decision_digest=previous_decision_digest,
        )
        simulated = None
        if request.intervention_variable is not None:
            simulated = self._causal_graph.simulate(
                request.intervention_variable,
                float(request.intervention_delta),
                allow_hypothesized=request.allow_hypothesized_model,
            )
            if simulated.observed or simulated.result_kind != "SIMULATION_NOT_OBSERVATION":
                raise ProbePlanningError("model preview must never imply observation")
        observed_sources = {
            source_id
            for assessment in comparison.rankings
            for source_id in assessment.observed_sources
        }
        source_ids = tuple(sorted(observed_sources | set(snapshot.source_ids)))
        # Disallow a time-of-check/time-of-use promotion if a source changed
        # while plan computation was taking place. Later uses still revalidate.
        if self._hypotheses.compare(request.question_id) != comparison or (
            self._causal_graph.snapshot() != snapshot
        ):
            raise ProbePlanningError("source custody changed during planning")

        if not observed_sources:
            evidence = ProbeEvidenceStatus.UNASSESSED
        elif comparison.winner is None:
            evidence = ProbeEvidenceStatus.CONTESTED
        else:
            evidence = ProbeEvidenceStatus.TENTATIVE
        receipt = _digest({
            "schema": _SCHEMA,
            "request": request.payload(),
            "policy": policy.digest,
            "comparison": comparison.receipt_digest,
            "causal": snapshot.receipt_digest,
            "control": decision.decision_digest,
            "simulation": simulated.receipt_digest if simulated else None,
            "sources": source_ids,
            "evidence": evidence.value,
            "execution_authorized": False,
            "observation_verified": False,
        })
        return DesignProbePlan(
            request, comparison, snapshot, decision, simulated,
            source_ids, evidence, receipt,
        )


__all__ = [
    "DesignProbePlan", "DesignProbePlanner", "DesignProbeRequest",
    "ProbeEvidenceStatus", "ProbePlanningError",
]
