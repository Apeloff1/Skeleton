"""Bridge the unified semantic lens registry into Jeeves scientific governance.

Jeeves historically grew two lens surfaces:
* semantic_lenses.SemanticLensSpec for high-dimensional interpretation; and
* lens_system.LensDefinition for authority, calibration, and permissions.

This module makes the boundary explicit instead of allowing semantic routing to
bypass scientific governance. It converts a semantic selection into governed
lens activations without ever upgrading a semantic lens into evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from .lens_governance import (
    LensGovernanceDecision,
    LensPermission,
    LensScienceRegistry,
)
from .lens_system import (
    LensActivation,
    LensAuthority,
    LensBundle,
    LensDefinition,
    LensFamily as GovernedLensFamily,
)
from .semantic_extreme_lenses import LensMaturity, rare_semantic_definitions
from .semantic_depth_lenses import depth_semantic_definitions
from .semantic_lenses import (
    LensFamily,
    LensSelection,
    SemanticLensSpec,
    SemanticObservation,
)
from .semantic_plane_lenses import plane_semantic_definitions
from .semantic_research_lenses import research_semantic_definitions
from .types import stable_fingerprint


_FAMILY_MAP: Mapping[LensFamily, GovernedLensFamily] = {
    LensFamily.FILM: GovernedLensFamily.CINEMA,
    LensFamily.LITERATURE: GovernedLensFamily.LITERARY,
    LensFamily.GAME: GovernedLensFamily.LUDIC,
    LensFamily.NARRATIVE: GovernedLensFamily.LITERARY,
    LensFamily.SEMIOTIC: GovernedLensFamily.SEMIOTIC,
    LensFamily.COGNITIVE: GovernedLensFamily.METACOGNITIVE,
    LensFamily.RHETORIC: GovernedLensFamily.PRAGMATIC,
    LensFamily.SOCIAL: GovernedLensFamily.SOCIAL,
    LensFamily.TEMPORAL: GovernedLensFamily.PREDICTIVE,
    LensFamily.SYSTEM: GovernedLensFamily.COMPUTATIONAL,
    LensFamily.CAUSAL: GovernedLensFamily.CAUSAL,
    LensFamily.INFORMATION: GovernedLensFamily.INFORMATION,
    LensFamily.COMPUTATIONAL: GovernedLensFamily.COMPUTATIONAL,
    LensFamily.METACOGNITIVE: GovernedLensFamily.METACOGNITIVE,
    LensFamily.PROBABILITY: GovernedLensFamily.PROBABILITY,
    LensFamily.PREDICTIVE: GovernedLensFamily.PREDICTIVE,
}


_AUTHORITY_MAP: Mapping[LensMaturity, LensAuthority] = {
    LensMaturity.FORMAL: LensAuthority.FORMAL,
    LensMaturity.EMPIRICAL: LensAuthority.EMPIRICAL,
    LensMaturity.MIXED: LensAuthority.EMPIRICAL,
    LensMaturity.CONCEPTUAL: LensAuthority.INTERPRETIVE,
    LensMaturity.HEURISTIC: LensAuthority.HEURISTIC,
}


def semantic_maturity_index() -> Mapping[str, LensMaturity]:
    """Return known maturity metadata for semantic lenses that declare it."""
    result: dict[str, LensMaturity] = {}
    # Later catalogs intentionally win only when a key was not already assigned;
    # duplicate semantic keys are historical aliases, not competing authority.
    for definitions in (
        rare_semantic_definitions(),
        research_semantic_definitions(),
        plane_semantic_definitions(),
        depth_semantic_definitions(),
    ):
        for definition in definitions:
            result.setdefault(definition.spec.key, definition.maturity)
    return result


def governed_family(family: LensFamily) -> GovernedLensFamily:
    return _FAMILY_MAP[family]


def semantic_spec_to_definition(
    spec: SemanticLensSpec,
    *,
    maturity: LensMaturity | None = None,
) -> LensDefinition:
    """Project a semantic spec into the authority-aware lens contract."""
    maturity = maturity or semantic_maturity_index().get(spec.key)
    authority = (
        _AUTHORITY_MAP[maturity]
        if maturity is not None
        else LensAuthority.INTERPRETIVE
    )
    return LensDefinition(
        lens_id=spec.key,
        name=spec.key.replace("_", " ").title(),
        family=governed_family(spec.family),
        authority=authority,
        description=spec.description,
        cues=spec.activation_cues,
        outputs=("hypothesis", "forecast", "counterreading", "tangent"),
        preserves_source_truth=True,
        metadata={
            "semantic_family": spec.family.value,
            "semantic_role": spec.role.value,
            "lineage_year": spec.lineage_year,
            "minimum_observations": spec.minimum_observations,
            "pairwise": spec.pairwise,
            "sequential": spec.sequential,
            "rare": spec.rare,
            "maturity": maturity.value if maturity else "undeclared",
            "semantic_plane_bridge": True,
        },
    )


@dataclass(frozen=True, slots=True)
class SemanticGovernanceSnapshot:
    decisions: tuple[LensGovernanceDecision, ...]
    predictive_weights: tuple[tuple[str, float], ...]
    forecast_blocked_lens_keys: tuple[str, ...]
    decision_blocked_lens_keys: tuple[str, ...]
    factual_assertion_authorized: bool
    causal_assertion_authorized: bool
    fingerprint: str

    def weight_for(self, lens_key: str, default: float = 0.0) -> float:
        key = str(lens_key).strip().casefold()
        return dict(self.predictive_weights).get(key, default)

    def decision_for(self, lens_key: str) -> LensGovernanceDecision | None:
        key = str(lens_key).strip().casefold()
        return next((item for item in self.decisions if item.lens_id == key), None)


class SemanticGovernanceBridge:
    """Apply LensScienceRegistry governance to SemanticLensSpec selections."""

    def __init__(self, registry: LensScienceRegistry | None = None) -> None:
        self.registry = registry or LensScienceRegistry()
        self._maturity = dict(semantic_maturity_index())

    @staticmethod
    def _text(observations: Sequence[SemanticObservation]) -> str:
        return " ".join(
            f"{item.content} {' '.join(item.tags)}"
            for item in observations
        ).casefold()

    def activation_for(
        self,
        spec: SemanticLensSpec,
        *,
        score: float,
        observations: Sequence[SemanticObservation],
    ) -> LensActivation:
        text = self._text(observations)
        matched = tuple(
            cue for cue in spec.activation_cues
            if cue and cue in text
        )
        cue_score = (
            min(1.0, len(matched) / max(1, min(6, len(spec.activation_cues))))
            if spec.activation_cues
            else 0.0
        )
        relation_score = min(
            1.0,
            (0.35 if spec.pairwise and len(observations) >= 2 else 0.0)
            + (0.35 if spec.sequential and len(observations) >= 3 else 0.0),
        )
        novelty_score = 0.75 if spec.rare else 0.35
        definition = semantic_spec_to_definition(
            spec,
            maturity=self._maturity.get(spec.key),
        )
        return LensActivation(
            lens=definition,
            score=score,
            cue_score=cue_score,
            relation_score=relation_score,
            novelty_score=novelty_score,
            matched_cues=matched,
            rationale=(
                f"semantic-plane bridge: family={spec.family.value}; "
                f"role={spec.role.value}; cue_support={cue_score:.3f}; "
                f"relation_support={relation_score:.3f}"
            ),
        )

    def assess(
        self,
        selection: LensSelection,
        *,
        observations: Sequence[SemanticObservation] = (),
    ) -> SemanticGovernanceSnapshot:
        activations = tuple(
            self.activation_for(
                spec,
                score=selection.activation_scores.get(spec.key, 0.0),
                observations=observations,
            )
            for spec in selection.lenses
        )
        bundle = LensBundle(
            query=self._text(observations),
            activations=activations,
            families=tuple(
                sorted(
                    {activation.lens.family for activation in activations},
                    key=lambda family: family.value,
                )
            ),
            fingerprint=stable_fingerprint(
                {
                    "selection": [
                        (
                            spec.key,
                            selection.activation_scores.get(spec.key, 0.0),
                        )
                        for spec in selection.lenses
                    ],
                    "observations": [item.fingerprint for item in observations],
                }
            ),
        )
        decisions = self.registry.assess_bundle(bundle)
        weights = tuple(
            sorted(
                (decision.lens_id, decision.predictive_weight)
                for decision in decisions
            )
        )
        forecast_blocked = tuple(
            sorted(
                decision.lens_id
                for decision in decisions
                if LensPermission.FORECAST_GENERATION not in decision.permissions
            )
        )
        decision_blocked = tuple(
            sorted(
                decision.lens_id
                for decision in decisions
                if not decision.decision_feature_authorized
            )
        )
        # The bridge invariant is stricter than any individual lens profile:
        # semantic activations never directly authorize factual/causal claims.
        factual = any(item.factual_assertion_authorized for item in decisions)
        causal = any(item.causal_assertion_authorized for item in decisions)
        fingerprint = stable_fingerprint(
            {
                "bundle": bundle.fingerprint,
                "decisions": [item.fingerprint for item in decisions],
                "weights": weights,
                "forecast_blocked": forecast_blocked,
                "decision_blocked": decision_blocked,
                "factual": factual,
                "causal": causal,
            }
        )
        return SemanticGovernanceSnapshot(
            decisions=decisions,
            predictive_weights=weights,
            forecast_blocked_lens_keys=forecast_blocked,
            decision_blocked_lens_keys=decision_blocked,
            factual_assertion_authorized=factual,
            causal_assertion_authorized=causal,
            fingerprint=fingerprint,
        )
