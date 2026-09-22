"""Frontier-style inference orchestration for Jeeves.

Jeeves already has strong specialist components: adaptive deliberation, semantic
lenses, adversarial verification, rational metareasoning, uncertainty models,
and guarded execution.  The missing piece is an explicit host-side contract for
composing those signals at inference time.

This module supplies that contract.  It never asks for, stores, or exposes
private chain-of-thought.  It operates on concise candidate proposals,
host-computed scores, calibrated/empirical metareasoning opportunities,
dependency-aware lens signals, and verification council verdicts.

The coordinator is deliberately conservative:

* search confidence is separated from relative candidate preference;
* disagreement and entropy remain first-class instead of being averaged away;
* semantic lenses can trigger more reasoning but cannot manufacture evidence;
* positive value-of-computation can postpone an otherwise acceptable answer;
* mutating/high-impact decisions require an explicit verification boundary;
* verifier rejection can never be overruled by model confidence;
* every decision receives a deterministic replay fingerprint.

The result is closer to modern frontier inference patterns without pretending
that orchestration alone turns the underlying model into a frontier model.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Sequence

from .adversarial_verification import CouncilVerdict, Verdict
from .deliberation import CandidateProposal, CandidateScore, SearchResult
from .frontier_consensus import ConsensusResult, ConsensusSelector, promote_consensus
from .lens_fusion import (
    LensDependence,
    LensFusionEngine,
    LensFusionPolicy,
    LensFusionResult,
    LensSignal,
)
from .rational_metareasoning import (
    ComputationAction,
    MetaActionKind,
    MetaDecision as RationalMetaDecision,
    MetaState as RationalMetaState,
    RationalMetareasoner,
)
from .types import (
    AgentContractError,
    RiskTier,
    finite_number,
    json_safe,
    positive_int,
    probability,
    stable_fingerprint,
)


class FrontierReasoningError(RuntimeError):
    """Raised when frontier reasoning inputs violate orchestration contracts."""


class InferenceDisposition(str, Enum):
    """Host-side next step selected from observable inference state."""

    COMMIT = "commit"
    DELIBERATE = "deliberate"
    VERIFY = "verify"
    SEEK_EVIDENCE = "seek_evidence"
    ABSTAIN = "abstain"


class EscalationCause(str, Enum):
    NO_CANDIDATE = "no_candidate"
    LOW_ABSOLUTE_QUALITY = "low_absolute_quality"
    LOW_CHOICE_CONFIDENCE = "low_choice_confidence"
    LOW_MARGIN = "low_margin"
    HIGH_ENTROPY = "high_entropy"
    ACTION_DISAGREEMENT = "action_disagreement"
    OUTCOME_DISAGREEMENT = "outcome_disagreement"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    LENS_CONFLICT = "lens_conflict"
    LENS_SENSITIVITY = "lens_sensitivity"
    VERIFICATION_REQUIRED = "verification_required"
    VERIFICATION_ABSTAINED = "verification_abstained"
    VERIFICATION_REJECTED = "verification_rejected"
    VERIFICATION_WEAK_BOUND = "verification_weak_bound"
    POSITIVE_VALUE_OF_COMPUTATION = "positive_value_of_computation"
    CONSENSUS_WEAK = "consensus_weak"


_RISK_ORDER = {
    RiskTier.READ_ONLY: 0,
    RiskTier.REVERSIBLE: 1,
    RiskTier.MUTATING: 2,
    RiskTier.EXTERNAL: 3,
    RiskTier.HIGH_IMPACT: 4,
}


@dataclass(frozen=True, slots=True)
class FrontierReasoningPolicy:
    """Thresholds for committing versus spending more inference-time compute."""

    maximum_candidates: int = 12
    softmax_temperature: float = 0.70
    minimum_absolute_quality: float = 0.62
    minimum_choice_probability: float = 0.52
    minimum_choice_margin: float = 0.08
    maximum_normalized_entropy: float = 0.78
    maximum_action_disagreement: float = 0.42
    maximum_outcome_disagreement: float = 0.52
    minimum_evidence_quality: float = 0.25
    maximum_lens_sensitivity_width: float = 0.58
    maximum_lens_conflict: float = 0.55
    verification_required_at: RiskTier = RiskTier.MUTATING
    minimum_verification_lower_bound: float = 0.68
    block_on_verifier_abstention: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "maximum_candidates",
            positive_int("maximum_candidates", self.maximum_candidates, maximum=10_000),
        )
        temperature = finite_number("softmax_temperature", self.softmax_temperature)
        if temperature <= 0.0 or temperature > 100.0:
            raise AgentContractError("softmax_temperature must be in (0, 100]")
        object.__setattr__(self, "softmax_temperature", temperature)
        for name in (
            "minimum_absolute_quality",
            "minimum_choice_probability",
            "minimum_choice_margin",
            "maximum_normalized_entropy",
            "maximum_action_disagreement",
            "maximum_outcome_disagreement",
            "minimum_evidence_quality",
            "maximum_lens_sensitivity_width",
            "maximum_lens_conflict",
            "minimum_verification_lower_bound",
        ):
            object.__setattr__(self, name, probability(name, getattr(self, name)))
        if not isinstance(self.verification_required_at, RiskTier):
            object.__setattr__(
                self,
                "verification_required_at",
                RiskTier(str(self.verification_required_at)),
            )


@dataclass(frozen=True, slots=True)
class CandidateAssessment:
    """Absolute and relative support for one deliberation candidate."""

    candidate_id: str
    rank: int
    absolute_quality: float
    choice_probability: float
    score_total: float
    candidate_confidence: float
    evidence_quality: float
    verifier_score: float
    risk_penalty: float
    evidence_count: int
    action_signature: str
    outcome_signature: str
    fingerprint: str

    def __post_init__(self) -> None:
        if not self.candidate_id:
            raise AgentContractError("candidate assessment requires candidate_id")
        object.__setattr__(
            self, "rank", positive_int("candidate rank", self.rank, maximum=1_000_000)
        )
        for name in (
            "absolute_quality",
            "choice_probability",
            "candidate_confidence",
            "evidence_quality",
            "verifier_score",
            "risk_penalty",
        ):
            object.__setattr__(self, name, probability(name, getattr(self, name)))
        total = finite_number("score_total", self.score_total)
        object.__setattr__(self, "score_total", max(-1.0, min(1.0, total)))
        if isinstance(self.evidence_count, bool) or self.evidence_count < 0:
            raise AgentContractError("evidence_count must be non-negative integer")


@dataclass(frozen=True, slots=True)
class InferenceDiagnostics:
    """Uncertainty diagnostics over the current candidate set."""

    normalized_entropy: float
    choice_margin: float
    action_disagreement: float
    outcome_disagreement: float
    maximum_evidence_overlap: float
    effective_candidate_count: float
    fingerprint: str

    def __post_init__(self) -> None:
        for name in (
            "normalized_entropy",
            "choice_margin",
            "action_disagreement",
            "outcome_disagreement",
            "maximum_evidence_overlap",
        ):
            object.__setattr__(self, name, probability(name, getattr(self, name)))
        effective = finite_number(
            "effective_candidate_count", self.effective_candidate_count
        )
        if effective < 0.0:
            raise AgentContractError("effective_candidate_count cannot be negative")
        object.__setattr__(self, "effective_candidate_count", effective)


@dataclass(frozen=True, slots=True)
class FrontierReasoningDecision:
    """Auditable output of a single inference orchestration pass."""

    disposition: InferenceDisposition
    leading_candidate: CandidateProposal | None
    assessments: tuple[CandidateAssessment, ...]
    diagnostics: InferenceDiagnostics
    causes: tuple[EscalationCause, ...]
    lens_fusion: LensFusionResult | None
    consensus: ConsensusResult | None
    metareasoning: RationalMetaDecision | None
    verification: CouncilVerdict | None
    next_computation_action_id: str | None
    risk: RiskTier
    metadata: Mapping[str, Any]
    fingerprint: str

    def __post_init__(self) -> None:
        if not isinstance(self.disposition, InferenceDisposition):
            object.__setattr__(
                self, "disposition", InferenceDisposition(str(self.disposition))
            )
        if not isinstance(self.risk, RiskTier):
            object.__setattr__(self, "risk", RiskTier(str(self.risk)))
        if self.leading_candidate is not None and not isinstance(
            self.leading_candidate, CandidateProposal
        ):
            raise TypeError("leading_candidate must be CandidateProposal or None")
        if any(not isinstance(item, CandidateAssessment) for item in self.assessments):
            raise TypeError("assessments must contain CandidateAssessment")
        if any(not isinstance(item, EscalationCause) for item in self.causes):
            raise TypeError("causes must contain EscalationCause")
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))

    @property
    def committed_candidate(self) -> CandidateProposal | None:
        return (
            self.leading_candidate
            if self.disposition is InferenceDisposition.COMMIT
            else None
        )


def _normalized_text(value: str) -> str:
    return " ".join(str(value).casefold().split())


def _signature(value: str) -> str:
    return stable_fingerprint(_normalized_text(value))


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _softmax(values: Sequence[float]) -> tuple[float, ...]:
    if not values:
        return ()
    peak = max(values)
    exps = [math.exp(max(-80.0, min(80.0, value - peak))) for value in values]
    total = sum(exps)
    if total <= 0.0:
        return tuple(1.0 / len(values) for _ in values)
    return tuple(value / total for value in exps)


def _normalized_entropy(probabilities: Sequence[float]) -> float:
    if len(probabilities) <= 1:
        return 0.0
    entropy = -sum(
        value * math.log(value)
        for value in probabilities
        if value > 0.0
    )
    maximum = math.log(len(probabilities))
    return _clamp(entropy / maximum) if maximum > 0.0 else 0.0


def _effective_count(probabilities: Sequence[float]) -> float:
    denominator = sum(value * value for value in probabilities)
    return 0.0 if denominator <= 0.0 else 1.0 / denominator


def _weighted_disagreement(
    values: Sequence[str],
    probabilities: Sequence[float],
) -> float:
    if not values:
        return 0.0
    mass: dict[str, float] = {}
    for value, weight in zip(values, probabilities):
        key = _signature(value)
        mass[key] = mass.get(key, 0.0) + weight
    return _clamp(1.0 - max(mass.values(), default=1.0))


def _jaccard(left: Sequence[str], right: Sequence[str]) -> float:
    a = {str(item) for item in left if str(item)}
    b = {str(item) for item in right if str(item)}
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


class FrontierReasoningCoordinator:
    """Compose deliberation, lens fusion, metareasoning, and verification.

    The coordinator is pure orchestration.  It does not execute a model, tool,
    verifier, or retriever.  Callers supply the outputs of those systems and the
    coordinator returns the next justified host-side disposition.
    """

    def __init__(
        self,
        *,
        policy: FrontierReasoningPolicy | None = None,
        lens_fusion: LensFusionEngine | None = None,
        metareasoner: RationalMetareasoner | None = None,
        consensus_selector: ConsensusSelector | None = None,
    ) -> None:
        self.policy = policy or FrontierReasoningPolicy()
        self.lens_fusion = lens_fusion or LensFusionEngine(LensFusionPolicy())
        self.metareasoner = metareasoner or RationalMetareasoner()
        self.consensus_selector = consensus_selector or ConsensusSelector()

    def decide(
        self,
        search: SearchResult,
        *,
        risk: RiskTier = RiskTier.READ_ONLY,
        lens_signals: Sequence[LensSignal] = (),
        explicit_lens_dependencies: Sequence[LensDependence] = (),
        meta_state: RationalMetaState | None = None,
        computation_actions: Sequence[ComputationAction] = (),
        verification: CouncilVerdict | None = None,
    ) -> FrontierReasoningDecision:
        if not isinstance(search, SearchResult):
            raise TypeError("search must be SearchResult")
        if not isinstance(risk, RiskTier):
            risk = RiskTier(str(risk))
        if any(not isinstance(item, LensSignal) for item in lens_signals):
            raise TypeError("lens_signals must contain LensSignal")
        if any(
            not isinstance(item, LensDependence)
            for item in explicit_lens_dependencies
        ):
            raise TypeError(
                "explicit_lens_dependencies must contain LensDependence"
            )
        if meta_state is None and computation_actions:
            raise FrontierReasoningError(
                "computation_actions require an explicit rational meta_state"
            )
        if meta_state is not None and not isinstance(meta_state, RationalMetaState):
            raise TypeError("meta_state must be rational_metareasoning.MetaState")
        if any(not isinstance(item, ComputationAction) for item in computation_actions):
            raise TypeError("computation_actions must contain ComputationAction")
        if verification is not None and not isinstance(verification, CouncilVerdict):
            raise TypeError("verification must be CouncilVerdict or None")

        consensus = self.consensus_selector.select(search)
        search = promote_consensus(search, consensus)
        ranked = tuple(search.ranking[: self.policy.maximum_candidates])
        assessments, candidates = self._assess_candidates(ranked)
        diagnostics = self._diagnostics(assessments, candidates)
        leading = candidates[0] if candidates else None

        fusion: LensFusionResult | None = None
        if lens_signals:
            base_rate = (
                assessments[0].absolute_quality if assessments else 0.5
            )
            fusion = self.lens_fusion.fuse(
                lens_signals,
                base_rate=base_rate,
                explicit_dependencies=explicit_lens_dependencies,
            )

        meta: RationalMetaDecision | None = None
        if meta_state is not None:
            meta = self.metareasoner.choose(meta_state, tuple(computation_actions))

        causes = self._causes(
            assessments,
            diagnostics,
            fusion=fusion,
            verification=verification,
            metareasoning=meta,
            consensus=consensus,
            risk=risk,
        )
        disposition, next_action = self._disposition(
            assessments,
            causes,
            metareasoning=meta,
            computation_actions=tuple(computation_actions),
            verification=verification,
            risk=risk,
        )

        payload = {
            "search": search.trace_fingerprint,
            "mode": search.mode.value,
            "leading": leading.candidate_id if leading else None,
            "assessments": [item.fingerprint for item in assessments],
            "diagnostics": diagnostics.fingerprint,
            "lens": fusion.fingerprint if fusion else None,
            "consensus": consensus.fingerprint,
            "meta": meta.fingerprint if meta else None,
            "verification": verification.fingerprint if verification else None,
            "risk": risk.value,
            "causes": [item.value for item in causes],
            "disposition": disposition.value,
            "next_action": next_action,
        }
        fingerprint = stable_fingerprint(payload)
        metadata = {
            "search_mode": search.mode.value,
            "search_stop_reason": search.stopped_reason,
            "search_trace": search.trace_fingerprint,
            "candidate_count": len(assessments),
            "consensus_agreement": consensus.agreement,
            "consensus_entropy": consensus.normalized_entropy,
            "consensus_requires_more_sampling": consensus.requires_more_sampling,
            "lens_signal_count": len(lens_signals),
            "metareasoning_considered": len(meta.considered) if meta else 0,
            "verification_present": verification is not None,
        }
        return FrontierReasoningDecision(
            disposition=disposition,
            leading_candidate=leading,
            assessments=assessments,
            diagnostics=diagnostics,
            causes=causes,
            lens_fusion=fusion,
            consensus=consensus,
            metareasoning=meta,
            verification=verification,
            next_computation_action_id=next_action,
            risk=risk,
            metadata=metadata,
            fingerprint=fingerprint,
        )

    def _assess_candidates(
        self,
        ranked: Sequence[tuple[CandidateProposal, CandidateScore]],
    ) -> tuple[tuple[CandidateAssessment, ...], tuple[CandidateProposal, ...]]:
        if any(
            not isinstance(candidate, CandidateProposal)
            or not isinstance(score, CandidateScore)
            for candidate, score in ranked
        ):
            raise FrontierReasoningError(
                "search ranking must contain CandidateProposal/CandidateScore pairs"
            )
        candidates = tuple(candidate for candidate, _ in ranked)
        if len({candidate.candidate_id for candidate in candidates}) != len(candidates):
            raise FrontierReasoningError("search ranking contains duplicate candidate ids")

        logits: list[float] = []
        absolute: list[float] = []
        for candidate, score in ranked:
            score_unit = _clamp((score.total + 1.0) * 0.5)
            evidence_presence = 1.0 if candidate.evidence else 0.0
            quality = _clamp(
                0.30 * score_unit
                + 0.24 * candidate.confidence
                + 0.18 * score.evidence_quality
                + 0.20 * score.verifier_score
                + 0.08 * evidence_presence
                - 0.12 * score.risk_penalty
            )
            absolute.append(quality)
            preference = (
                score.total
                + 0.30 * candidate.confidence
                + 0.16 * score.evidence_quality
                + 0.18 * score.verifier_score
                - 0.12 * score.risk_penalty
                - 0.05 * score.cost_penalty
            )
            logits.append(preference / self.policy.softmax_temperature)

        choice = _softmax(logits)
        assessments: list[CandidateAssessment] = []
        for index, ((candidate, score), quality, preference) in enumerate(
            zip(ranked, absolute, choice), start=1
        ):
            evidence_ids = tuple(
                sorted({reference.evidence_id for reference in candidate.evidence})
            )
            action_signature = _signature(candidate.proposed_action)
            outcome_signature = _signature(candidate.predicted_outcome)
            fingerprint = stable_fingerprint(
                {
                    "candidate": candidate.fingerprint,
                    "rank": index,
                    "quality": quality,
                    "choice_probability": preference,
                    "score": score.total,
                    "confidence": candidate.confidence,
                    "evidence_quality": score.evidence_quality,
                    "verifier": score.verifier_score,
                    "risk": score.risk_penalty,
                    "evidence": evidence_ids,
                    "action": action_signature,
                    "outcome": outcome_signature,
                }
            )
            assessments.append(
                CandidateAssessment(
                    candidate_id=candidate.candidate_id,
                    rank=index,
                    absolute_quality=quality,
                    choice_probability=preference,
                    score_total=score.total,
                    candidate_confidence=candidate.confidence,
                    evidence_quality=score.evidence_quality,
                    verifier_score=score.verifier_score,
                    risk_penalty=score.risk_penalty,
                    evidence_count=len(evidence_ids),
                    action_signature=action_signature,
                    outcome_signature=outcome_signature,
                    fingerprint=fingerprint,
                )
            )
        return tuple(assessments), candidates

    def _diagnostics(
        self,
        assessments: Sequence[CandidateAssessment],
        candidates: Sequence[CandidateProposal],
    ) -> InferenceDiagnostics:
        probabilities = tuple(item.choice_probability for item in assessments)
        entropy = _normalized_entropy(probabilities)
        if not probabilities:
            margin = 0.0
        elif len(probabilities) == 1:
            margin = probabilities[0]
        else:
            ordered = sorted(probabilities, reverse=True)
            margin = _clamp(ordered[0] - ordered[1])

        actions = tuple(candidate.proposed_action for candidate in candidates)
        outcomes = tuple(candidate.predicted_outcome for candidate in candidates)
        action_disagreement = _weighted_disagreement(actions, probabilities)
        outcome_disagreement = _weighted_disagreement(outcomes, probabilities)

        maximum_overlap = 0.0
        for index, left in enumerate(candidates):
            left_ids = tuple(reference.evidence_id for reference in left.evidence)
            for right in candidates[index + 1 :]:
                right_ids = tuple(reference.evidence_id for reference in right.evidence)
                maximum_overlap = max(
                    maximum_overlap, _jaccard(left_ids, right_ids)
                )

        effective = _effective_count(probabilities)
        fingerprint = stable_fingerprint(
            {
                "entropy": entropy,
                "margin": margin,
                "action_disagreement": action_disagreement,
                "outcome_disagreement": outcome_disagreement,
                "evidence_overlap": maximum_overlap,
                "effective_candidates": effective,
            }
        )
        return InferenceDiagnostics(
            normalized_entropy=entropy,
            choice_margin=margin,
            action_disagreement=action_disagreement,
            outcome_disagreement=outcome_disagreement,
            maximum_evidence_overlap=maximum_overlap,
            effective_candidate_count=effective,
            fingerprint=fingerprint,
        )

    def _causes(
        self,
        assessments: Sequence[CandidateAssessment],
        diagnostics: InferenceDiagnostics,
        *,
        fusion: LensFusionResult | None,
        verification: CouncilVerdict | None,
        metareasoning: RationalMetaDecision | None,
        consensus: ConsensusResult | None,
        risk: RiskTier,
    ) -> tuple[EscalationCause, ...]:
        causes: list[EscalationCause] = []
        if not assessments:
            causes.append(EscalationCause.NO_CANDIDATE)
        else:
            lead = assessments[0]
            consensus_resolves_relative = self._consensus_resolves_relative_uncertainty(
                consensus,
                lead,
            )
            if lead.absolute_quality < self.policy.minimum_absolute_quality:
                causes.append(EscalationCause.LOW_ABSOLUTE_QUALITY)
            if (
                not consensus_resolves_relative
                and lead.choice_probability < self.policy.minimum_choice_probability
            ):
                causes.append(EscalationCause.LOW_CHOICE_CONFIDENCE)
            if (
                not consensus_resolves_relative
                and len(assessments) > 1
                and diagnostics.choice_margin < self.policy.minimum_choice_margin
            ):
                causes.append(EscalationCause.LOW_MARGIN)
            if (
                not consensus_resolves_relative
                and len(assessments) > 1
                and diagnostics.normalized_entropy
                > self.policy.maximum_normalized_entropy
            ):
                causes.append(EscalationCause.HIGH_ENTROPY)
            if (
                not consensus_resolves_relative
                and diagnostics.action_disagreement
                > self.policy.maximum_action_disagreement
            ):
                causes.append(EscalationCause.ACTION_DISAGREEMENT)
            if (
                not consensus_resolves_relative
                and diagnostics.outcome_disagreement
                > self.policy.maximum_outcome_disagreement
            ):
                causes.append(EscalationCause.OUTCOME_DISAGREEMENT)
            if lead.evidence_quality < self.policy.minimum_evidence_quality:
                causes.append(EscalationCause.INSUFFICIENT_EVIDENCE)

        if fusion is not None:
            if (
                fusion.abstain
                or fusion.conflict_strength > self.policy.maximum_lens_conflict
            ):
                causes.append(EscalationCause.LENS_CONFLICT)
            if (
                fusion.sensitivity_high - fusion.sensitivity_low
                > self.policy.maximum_lens_sensitivity_width
            ):
                causes.append(EscalationCause.LENS_SENSITIVITY)

        requires_verification = self._risk_requires_verification(risk)
        if requires_verification and verification is None:
            causes.append(EscalationCause.VERIFICATION_REQUIRED)
        elif verification is not None:
            if verification.verdict is Verdict.REJECT:
                causes.append(EscalationCause.VERIFICATION_REJECTED)
            elif verification.verdict is Verdict.ABSTAIN:
                if self.policy.block_on_verifier_abstention or requires_verification:
                    causes.append(EscalationCause.VERIFICATION_ABSTAINED)
            elif (
                verification.verdict is Verdict.ACCEPT
                and verification.lower_bound
                < self.policy.minimum_verification_lower_bound
            ):
                causes.append(EscalationCause.VERIFICATION_WEAK_BOUND)

        if consensus is not None and consensus.requires_more_sampling and len(assessments) > 1:
            causes.append(EscalationCause.CONSENSUS_WEAK)

        if (
            metareasoning is not None
            and metareasoning.selected_action_id is not None
        ):
            causes.append(EscalationCause.POSITIVE_VALUE_OF_COMPUTATION)

        return tuple(dict.fromkeys(causes))

    @staticmethod
    def _consensus_resolves_relative_uncertainty(
        consensus: ConsensusResult | None,
        lead: CandidateAssessment,
    ) -> bool:
        if (
            consensus is None
            or consensus.requires_more_sampling
            or consensus.selected_candidate_id != lead.candidate_id
        ):
            return False
        winner = next(
            (
                cluster
                for cluster in consensus.clusters
                if cluster.best_candidate_id == consensus.selected_candidate_id
            ),
            None,
        )
        return winner is not None and len(winner.candidate_ids) >= 2

    def _disposition(
        self,
        assessments: Sequence[CandidateAssessment],
        causes: Sequence[EscalationCause],
        *,
        metareasoning: RationalMetaDecision | None,
        computation_actions: Sequence[ComputationAction],
        verification: CouncilVerdict | None,
        risk: RiskTier,
    ) -> tuple[InferenceDisposition, str | None]:
        cause_set = set(causes)

        if EscalationCause.VERIFICATION_REJECTED in cause_set:
            mapped = self._meta_disposition(metareasoning, computation_actions)
            if mapped is not None:
                return mapped
            return InferenceDisposition.ABSTAIN, None

        if (
            EscalationCause.VERIFICATION_REQUIRED in cause_set
            or EscalationCause.VERIFICATION_ABSTAINED in cause_set
            or EscalationCause.VERIFICATION_WEAK_BOUND in cause_set
        ):
            return InferenceDisposition.VERIFY, (
                metareasoning.selected_action_id
                if metareasoning is not None
                and metareasoning.selected_kind is MetaActionKind.VERIFY
                else None
            )

        mapped = self._meta_disposition(metareasoning, computation_actions)
        if mapped is not None:
            return mapped

        if not assessments:
            return InferenceDisposition.ABSTAIN, None

        if EscalationCause.INSUFFICIENT_EVIDENCE in cause_set:
            return InferenceDisposition.SEEK_EVIDENCE, None

        nonterminal = {
            EscalationCause.LOW_ABSOLUTE_QUALITY,
            EscalationCause.LOW_CHOICE_CONFIDENCE,
            EscalationCause.LOW_MARGIN,
            EscalationCause.HIGH_ENTROPY,
            EscalationCause.ACTION_DISAGREEMENT,
            EscalationCause.OUTCOME_DISAGREEMENT,
            EscalationCause.LENS_CONFLICT,
            EscalationCause.LENS_SENSITIVITY,
            EscalationCause.CONSENSUS_WEAK,
        }
        if cause_set & nonterminal:
            return InferenceDisposition.DELIBERATE, None

        if self._risk_requires_verification(risk):
            if verification is None or verification.verdict is not Verdict.ACCEPT:
                return InferenceDisposition.VERIFY, None

        return InferenceDisposition.COMMIT, None

    def _meta_disposition(
        self,
        metareasoning: RationalMetaDecision | None,
        computation_actions: Sequence[ComputationAction],
    ) -> tuple[InferenceDisposition, str | None] | None:
        if metareasoning is None or metareasoning.selected_action_id is None:
            return None
        selected = next(
            (
                action
                for action in computation_actions
                if action.action_id == metareasoning.selected_action_id
            ),
            None,
        )
        action_id = metareasoning.selected_action_id
        if metareasoning.selected_kind is MetaActionKind.VERIFY:
            return InferenceDisposition.VERIFY, action_id
        if (
            selected is not None
            and selected.evidence_producing
            and metareasoning.selected_kind
            in {MetaActionKind.SEARCH, MetaActionKind.EXPERIMENT, MetaActionKind.TOOL}
        ):
            return InferenceDisposition.SEEK_EVIDENCE, action_id
        return InferenceDisposition.DELIBERATE, action_id

    def _risk_requires_verification(self, risk: RiskTier) -> bool:
        return (
            _RISK_ORDER[risk]
            >= _RISK_ORDER[self.policy.verification_required_at]
        )


__all__ = [
    "CandidateAssessment",
    "EscalationCause",
    "FrontierReasoningCoordinator",
    "FrontierReasoningDecision",
    "FrontierReasoningError",
    "FrontierReasoningPolicy",
    "InferenceDiagnostics",
    "InferenceDisposition",
]
