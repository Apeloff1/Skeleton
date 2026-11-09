"""Cross-layer consistency checks for Dragon knowledge promotion.

Audits whether the temporal evidence, hypotheses, probabilistic belief and
analysis chain refer to the same claim. Reports missing evidence rather than
silently manufacturing certainty.
"""
from __future__ import annotations
from dataclasses import dataclass

from .dragon_analysis_chains import AnalysisLayer, LayerReceipt, validate_chain
from .dragon_analysis_quality_gates import Measurement, gate_analysis
from .dragon_probabilistic_distillation import EvidencePass, Belief, ProbabilisticKnowledgeDistiller
from .dragon_belief_stress import stress_test_belief
from .dragon_empirical_calibration import CalibrationArtifact, apply_calibrator


@dataclass(frozen=True)
class PromotionPolicy:
    minimum_independent_groups: int = 2
    maximum_source_influence: float = 0.2
    minimum_probability: float = 0.9
    require_full_analysis: bool = True
    require_empirical_calibration: bool = True


@dataclass(frozen=True)
class PromotionDecision:
    claim_id: str
    eligible: bool
    belief_probability: float
    probability_semantics: str
    calibration_artifact_fingerprint: str | None
    reasons: tuple[str, ...]
    evidence_digest: str


def assess_promotion(
    claim_id: str, readings: tuple[EvidencePass, ...],
    receipts: tuple[LayerReceipt, ...],
    measurements: tuple[Measurement, ...], *,
    authorized: bool,
    policy: PromotionPolicy = PromotionPolicy(),
    calibration: CalibrationArtifact | None = None,
) -> PromotionDecision:
    if not authorized:
        raise PermissionError("knowledge promotion requires authorization")
    if not 1 <= policy.minimum_independent_groups <= 10000:
        raise ValueError("invalid independence threshold")
    if not 0 <= policy.maximum_source_influence <= 1:
        raise ValueError("invalid influence threshold")
    if not 0.5 < policy.minimum_probability < 1:
        raise ValueError("invalid promotion probability threshold")
    distiller = ProbabilisticKnowledgeDistiller()
    belief = distiller.distill(claim_id, readings)
    stress = stress_test_belief(claim_id, readings, authorized=True)
    failures = []
    if not readings:
        failures.append("No evidence readings")
    if belief.review_required:
        failures.append("Belief requires additional review")
    if belief.conflicting:
        failures.append("Contradictory evidence remains unresolved")
    if belief.independent_groups < policy.minimum_independent_groups:
        failures.append("Insufficient independent source groups")
    promoted_probability = belief.probability
    probability_semantics = belief.probability_semantics
    calibration_fingerprint = None
    if policy.require_empirical_calibration:
        if calibration is None:
            failures.append("Eligible empirical calibration artifact required")
        elif not calibration.eligible:
            failures.append("Empirical calibration artifact is ineligible")
        else:
            calibrated = apply_calibrator(
                belief.probability, calibration, authorized=True,
            )
            promoted_probability = calibrated.calibrated_probability
            probability_semantics = "empirically_calibrated_probability"
            calibration_fingerprint = calibrated.artifact_fingerprint
    if (
        policy.require_empirical_calibration
        and probability_semantics != "empirically_calibrated_probability"
    ):
        failures.append("Promotion threshold requires calibrated probability")
    elif promoted_probability < policy.minimum_probability:
        failures.append("Belief below promotion threshold")
    if stress.maximum_probability_shift > policy.maximum_source_influence:
        failures.append("Belief depends too heavily on one source group")
    if policy.require_full_analysis:
        verdict = validate_chain(receipts, authorized=True)
        if not verdict.complete:
            failures.append("Analysis chain is incomplete")
        quality = gate_analysis(receipts, measurements, authorized=True)
        if not quality.accepted:
            failures.extend(quality.failures)
    return PromotionDecision(
        claim_id, not failures, promoted_probability,
        probability_semantics, calibration_fingerprint,
        tuple(dict.fromkeys(failures)), belief.evidence_digest,
    )
