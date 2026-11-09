"""Scientific authority and permission governance for Jeeves semantic lenses.

This module complements interpretive_science.

LensAuthority answers what kind of operator a lens is.
ScientificLensLab answers how well a lens has predicted in recorded trials.
This module combines those facts into an explicit permission decision.

Crucial invariant
-----------------
No semantic lens is evidence. Even a mathematically formal lens may transform,
query, score, or organize source-backed evidence, but a lens activation alone
can never authorize a factual or causal assertion.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from .interpretive_science import ScientificLensLab, ScientificLensStatus
from .lens_system import LensActivation, LensAuthority, LensBundle, LensDefinition
from .types import AgentContractError, bounded_text, json_safe, probability, stable_fingerprint


class ScientificGrade(str, Enum):
    FORMAL = "formal"
    STRONG_EMPIRICAL = "strong_empirical"
    EMPIRICAL = "empirical"
    THEORY = "theory"
    HEURISTIC = "heuristic"
    INTERPRETIVE = "interpretive"


class LensPermission(str, Enum):
    QUERY_SELECTION = "query_selection"
    HYPOTHESIS_GENERATION = "hypothesis_generation"
    FORECAST_GENERATION = "forecast_generation"
    DECISION_FEATURE = "decision_feature"
    FACTUAL_ASSERTION = "factual_assertion"
    CAUSAL_ASSERTION = "causal_assertion"


@dataclass(frozen=True, slots=True)
class ResearchReference:
    title: str
    year: int
    locator: str
    supports: str
    limitations: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "title", bounded_text("reference title", self.title, maximum=1024))
        if isinstance(self.year, bool) or not isinstance(self.year, int) or not -5000 <= self.year <= 3000:
            raise AgentContractError("reference year is invalid")
        object.__setattr__(self, "locator", bounded_text("reference locator", self.locator, maximum=1024))
        object.__setattr__(self, "supports", bounded_text("reference supports", self.supports, maximum=4096))
        object.__setattr__(self, "limitations", bounded_text("reference limitations", self.limitations, maximum=4096))


@dataclass(frozen=True, slots=True)
class LensScienceProfile:
    lens_id: str
    grade: ScientificGrade
    baseline_permissions: tuple[LensPermission, ...]
    decision_requires_active_calibration: bool = True
    domain_specific: bool = True
    evidence_ceiling: str = "lens_never_evidence"
    references: tuple[ResearchReference, ...] = ()
    assumptions: tuple[str, ...] = ()
    prohibited_inferences: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        key = str(self.lens_id).strip().casefold()
        if not key:
            raise AgentContractError("lens_id is required")
        object.__setattr__(self, "lens_id", key)
        if not isinstance(self.grade, ScientificGrade):
            object.__setattr__(self, "grade", ScientificGrade(str(self.grade)))
        permissions = tuple(
            permission if isinstance(permission, LensPermission) else LensPermission(str(permission))
            for permission in self.baseline_permissions
        )
        if LensPermission.FACTUAL_ASSERTION in permissions or LensPermission.CAUSAL_ASSERTION in permissions:
            raise AgentContractError("a lens profile cannot grant factual or causal assertion authority")
        object.__setattr__(self, "baseline_permissions", tuple(dict.fromkeys(permissions)))
        object.__setattr__(self, "references", tuple(self.references))
        object.__setattr__(
            self,
            "assumptions",
            tuple(bounded_text("lens assumption", value, maximum=2048) for value in self.assumptions),
        )
        object.__setattr__(
            self,
            "prohibited_inferences",
            tuple(bounded_text("prohibited inference", value, maximum=2048) for value in self.prohibited_inferences),
        )
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "lens": self.lens_id,
                "grade": self.grade.value,
                "permissions": [item.value for item in self.baseline_permissions],
                "decision_requires_active_calibration": self.decision_requires_active_calibration,
                "domain_specific": self.domain_specific,
                "evidence_ceiling": self.evidence_ceiling,
                "references": [
                    (item.title, item.year, item.locator, item.supports, item.limitations)
                    for item in self.references
                ],
                "assumptions": self.assumptions,
                "prohibited": self.prohibited_inferences,
            }
        )


@dataclass(frozen=True, slots=True)
class LensGovernanceDecision:
    lens_id: str
    grade: ScientificGrade
    scientific_status: ScientificLensStatus
    permissions: tuple[LensPermission, ...]
    predictive_weight: float
    decision_feature_authorized: bool
    factual_assertion_authorized: bool
    causal_assertion_authorized: bool
    reasons: tuple[str, ...]
    evidence_ceiling: str
    profile_fingerprint: str
    fingerprint: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "predictive_weight", probability("predictive_weight", self.predictive_weight))
        if self.factual_assertion_authorized or self.causal_assertion_authorized:
            raise AgentContractError("lens governance must never authorize standalone factual/causal assertions")

    def as_json(self) -> dict[str, Any]:
        return {
            "lens_id": self.lens_id,
            "grade": self.grade.value,
            "scientific_status": self.scientific_status.value,
            "permissions": [item.value for item in self.permissions],
            "predictive_weight": self.predictive_weight,
            "decision_feature_authorized": self.decision_feature_authorized,
            "factual_assertion_authorized": False,
            "causal_assertion_authorized": False,
            "reasons": list(self.reasons),
            "evidence_ceiling": self.evidence_ceiling,
            "fingerprint": self.fingerprint,
        }


def _ref(title: str, year: int, locator: str, supports: str, limitations: str) -> ResearchReference:
    return ResearchReference(title, year, locator, supports, limitations)


def _baseline_for(definition: LensDefinition) -> LensScienceProfile:
    common = (
        LensPermission.QUERY_SELECTION,
        LensPermission.HYPOTHESIS_GENERATION,
        LensPermission.FORECAST_GENERATION,
    )
    if definition.authority is LensAuthority.FORMAL:
        return LensScienceProfile(
            definition.lens_id,
            ScientificGrade.FORMAL,
            common + (LensPermission.DECISION_FEATURE,),
            decision_requires_active_calibration=False,
            domain_specific=False,
            assumptions=("formal assumptions and input contracts must be satisfied",),
            prohibited_inferences=("formal validity does not establish source truth",),
        )
    if definition.authority is LensAuthority.EMPIRICAL:
        return LensScienceProfile(
            definition.lens_id,
            ScientificGrade.EMPIRICAL,
            common + (LensPermission.DECISION_FEATURE,),
            decision_requires_active_calibration=True,
            assumptions=("target domain must match or be transfer-validated",),
            prohibited_inferences=("association or prediction alone does not establish causation",),
        )
    if definition.authority is LensAuthority.HEURISTIC:
        return LensScienceProfile(
            definition.lens_id,
            ScientificGrade.HEURISTIC,
            common,
            decision_requires_active_calibration=True,
            prohibited_inferences=("heuristic coherence is not empirical validation",),
        )
    return LensScienceProfile(
        definition.lens_id,
        ScientificGrade.INTERPRETIVE,
        common,
        decision_requires_active_calibration=True,
        prohibited_inferences=(
            "interpretive coherence is not factual evidence",
            "authorial intent is not inferred without independent evidence",
            "symbolic or narrative relation is not a causal mechanism",
        ),
    )


def explicit_profiles() -> Mapping[str, LensScienceProfile]:
    kuleshov = LensScienceProfile(
        "kuleshov_juxtaposition",
        ScientificGrade.EMPIRICAL,
        (
            LensPermission.QUERY_SELECTION,
            LensPermission.HYPOTHESIS_GENERATION,
            LensPermission.FORECAST_GENERATION,
            LensPermission.DECISION_FEATURE,
        ),
        decision_requires_active_calibration=True,
        domain_specific=True,
        references=(
            _ref(
                "Reexamining the Kuleshov effect: Behavioral and neural evidence from authentic film experiments",
                2024,
                "doi:10.1371/journal.pone.0308295",
                "context can systematically alter interpretation of an unchanged neutral face in a face-scene-face sequence",
                "supports a bounded contextual-framing effect; it does not prove arbitrary montage meanings, authorial intent, or causal claims outside the studied paradigm",
            ),
        ),
        assumptions=(
            "comparison target is materially unchanged across contexts",
            "adjacent context is the manipulated or discriminating variable",
            "domain transfer requires separate calibration",
        ),
        prohibited_inferences=(
            "do not infer that every juxtaposition changes meaning",
            "do not treat perceived meaning as an objective property of either isolated item",
            "do not infer authorial intent from the effect alone",
        ),
    )

    mda = LensScienceProfile(
        "mechanics_dynamics_aesthetics",
        ScientificGrade.THEORY,
        (
            LensPermission.QUERY_SELECTION,
            LensPermission.HYPOTHESIS_GENERATION,
            LensPermission.FORECAST_GENERATION,
        ),
        references=(
            _ref(
                "MDA: A Formal Approach to Game Design and Game Research",
                2004,
                "AAAI WS-04-04-001",
                "a decomposition framework connecting mechanics, emergent dynamics, and player aesthetics",
                "a design/research framework rather than a calibrated predictive law",
            ),
        ),
        prohibited_inferences=("MDA labels alone do not establish player response or causal mechanism",),
    )

    procedural = LensScienceProfile(
        "procedural_rhetoric",
        ScientificGrade.INTERPRETIVE,
        (
            LensPermission.QUERY_SELECTION,
            LensPermission.HYPOTHESIS_GENERATION,
            LensPermission.FORECAST_GENERATION,
        ),
        prohibited_inferences=(
            "a rule system does not prove designer intent",
            "a simulated relation does not prove the same relation in the world",
        ),
    )

    partial_observability = LensScienceProfile(
        "partial_observability",
        ScientificGrade.FORMAL,
        (
            LensPermission.QUERY_SELECTION,
            LensPermission.HYPOTHESIS_GENERATION,
            LensPermission.FORECAST_GENERATION,
            LensPermission.DECISION_FEATURE,
        ),
        decision_requires_active_calibration=False,
        domain_specific=False,
        assumptions=("hidden-state and observation models are explicitly represented",),
        prohibited_inferences=("belief state is not ground-truth state",),
    )

    game_formalism = LensScienceProfile(
        "state_abstraction",
        ScientificGrade.FORMAL,
        (
            LensPermission.QUERY_SELECTION,
            LensPermission.HYPOTHESIS_GENERATION,
            LensPermission.FORECAST_GENERATION,
            LensPermission.DECISION_FEATURE,
        ),
        decision_requires_active_calibration=False,
        references=(
            _ref(
                "Modeling Game Mechanics With Ceptre",
                2024,
                "doi:10.1109/TG.2023.3292982",
                "formal executable game-mechanics specifications can support simulation, querying, and verification",
                "verification applies to encoded mechanics and properties, not unmodeled player psychology or narrative interpretation",
            ),
        ),
        assumptions=("state equivalence must preserve decision-relevant transitions or values",),
    )

    strategy = {
        key: LensScienceProfile(
            key,
            ScientificGrade.FORMAL,
            (
                LensPermission.QUERY_SELECTION,
                LensPermission.HYPOTHESIS_GENERATION,
                LensPermission.FORECAST_GENERATION,
                LensPermission.DECISION_FEATURE,
            ),
            decision_requires_active_calibration=False,
            domain_specific=False,
            assumptions=("payoffs, action sets, and information structure are correctly specified",),
            prohibited_inferences=("formal optimality is conditional on the supplied game model",),
        )
        for key in ("dominant_strategy", "mixed_strategy", "risk_reward")
    }

    values = (kuleshov, mda, procedural, partial_observability, game_formalism, *strategy.values())
    return {profile.lens_id: profile for profile in values}


class LensScienceRegistry:
    """Combine lens type, research lineage, and measured calibration."""

    def __init__(
        self,
        *,
        lab: ScientificLensLab | None = None,
        profiles: Mapping[str, LensScienceProfile] | None = None,
    ) -> None:
        self.lab = lab or ScientificLensLab()
        self._profiles = dict(explicit_profiles())
        if profiles:
            for key, profile in profiles.items():
                if not isinstance(profile, LensScienceProfile):
                    raise TypeError("profiles must contain LensScienceProfile values")
                self._profiles[str(key).casefold()] = profile

    def profile(self, definition: LensDefinition) -> LensScienceProfile:
        return self._profiles.get(definition.lens_id.casefold(), _baseline_for(definition))

    def assess(self, activation: LensActivation) -> LensGovernanceDecision:
        definition = activation.lens
        profile = self.profile(definition)
        reasons: list[str] = []
        try:
            report = self.lab.report(definition.lens_id)
        except AgentContractError:
            report = None

        if report is None:
            status = ScientificLensStatus.SHADOW
            measured_weight = 0.10
            reasons.append("no replicated calibration ledger is available for this lens")
        else:
            status = report.status
            measured_weight = report.predictive_weight
            reasons.extend(report.reasons)

        baseline = list(profile.baseline_permissions)
        if status is ScientificLensStatus.REJECTED:
            baseline = [LensPermission.QUERY_SELECTION, LensPermission.HYPOTHESIS_GENERATION]
            measured_weight = 0.0
            reasons.append("rejected lenses may inspect or generate counter-hypotheses but cannot contribute forecasts")
        elif status is ScientificLensStatus.RESTRICTED:
            baseline = [item for item in baseline if item is not LensPermission.DECISION_FEATURE]
            reasons.append("restricted calibration blocks decision influence")

        if profile.grade is ScientificGrade.FORMAL:
            predictive_weight = min(1.0, max(measured_weight, activation.score))
        else:
            predictive_weight = min(activation.score, measured_weight)

        decision_authorized = LensPermission.DECISION_FEATURE in baseline
        if profile.decision_requires_active_calibration and status is not ScientificLensStatus.ACTIVE:
            decision_authorized = False
            baseline = [item for item in baseline if item is not LensPermission.DECISION_FEATURE]
            reasons.append("decision use requires ACTIVE domain-calibrated status")

        reasons.append("lens activations never authorize standalone factual or causal assertions")
        permissions = tuple(dict.fromkeys(baseline))
        fingerprint = stable_fingerprint(
            {
                "activation": definition.lens_id,
                "activation_score": activation.score,
                "profile": profile.fingerprint,
                "status": status.value,
                "permissions": [item.value for item in permissions],
                "predictive_weight": predictive_weight,
                "decision_authorized": decision_authorized,
                "factual": False,
                "causal": False,
            }
        )
        return LensGovernanceDecision(
            lens_id=definition.lens_id,
            grade=profile.grade,
            scientific_status=status,
            permissions=permissions,
            predictive_weight=predictive_weight,
            decision_feature_authorized=decision_authorized,
            factual_assertion_authorized=False,
            causal_assertion_authorized=False,
            reasons=tuple(dict.fromkeys(reasons)),
            evidence_ceiling=profile.evidence_ceiling,
            profile_fingerprint=profile.fingerprint,
            fingerprint=fingerprint,
        )

    def assess_bundle(self, bundle: LensBundle) -> tuple[LensGovernanceDecision, ...]:
        return tuple(self.assess(activation) for activation in bundle.activations)

    def payload(self, bundle: LensBundle) -> list[dict[str, Any]]:
        return [decision.as_json() for decision in self.assess_bundle(bundle)]

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "profiles": [(key, value.fingerprint) for key, value in sorted(self._profiles.items())],
                "lab": self.lab.fingerprint,
            }
        )


__all__ = [
    "LensGovernanceDecision",
    "LensPermission",
    "LensScienceProfile",
    "LensScienceRegistry",
    "ResearchReference",
    "ScientificGrade",
    "explicit_profiles",
]
