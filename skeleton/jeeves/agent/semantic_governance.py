"""Governance bridge from modern semantic lenses into Jeeves lens science.

Jeeves currently has two intentionally different lens representations:

* :mod:`semantic_lenses` carries rich, observation-bound interpretive operators
  used by the nuance runtime.
* :mod:`lens_system` / :mod:`lens_governance` carry authority, calibration,
  and permission contracts.

This module connects them without pretending that an interpretive semantic lens
is a factual source.  Semantic lenses enter governance conservatively as
INTERPRETIVE operators.  Recorded predictive outcomes may increase their
predictive weight, but governance never grants standalone factual or causal
assertion authority.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Mapping, Sequence

from .interpretive_science import ScientificLensLab
from .lens_governance import (
    LensGovernanceDecision,
    LensScienceRegistry,
    explicit_profiles,
)
from .lens_system import (
    LensActivation,
    LensAuthority,
    LensDefinition,
    LensFamily as GovernedLensFamily,
)
from .semantic_extreme_lenses import rare_semantic_definitions
from .semantic_lenses import (
    LensFamily,
    LensSelection,
    SemanticLensSpec,
    SemanticObservation,
)
from .types import AgentContractError, stable_fingerprint

_TOKEN_RE = re.compile(r"[A-Za-z0-9_'-]+")

_PROFILE_ALIASES: Mapping[str, str] = {
    # Empirical contextual-effect profile: still SHADOW until calibrated.
    "kuleshov_context": "kuleshov_juxtaposition",
    # Do not alias formal profiles here unless their mathematical input
    # assumptions can be verified from the semantic frame itself.
}

_EXTREME_DEFINITIONS = {
    definition.spec.key: definition for definition in rare_semantic_definitions()
}

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
}


@dataclass(frozen=True, slots=True)
class SemanticLensGovernanceRecord:
    lens_key: str
    activation_score: float
    matched_cues: tuple[str, ...]
    decision: LensGovernanceDecision
    declared_maturity: str | None = None
    transfer_warning: str = ""
    lineage: tuple[str, ...] = ()
    domain_predictive_weight: float | None = None
    domain_status: str = "unspecified"


@dataclass(frozen=True, slots=True)
class SemanticLensGovernanceSnapshot:
    records: tuple[SemanticLensGovernanceRecord, ...]
    fingerprint: str
    domain: str | None = None

    def record_for(self, lens_key: str) -> SemanticLensGovernanceRecord | None:
        key = str(lens_key).strip().casefold()
        return next((item for item in self.records if item.lens_key == key), None)

    def decision_for(self, lens_key: str) -> LensGovernanceDecision | None:
        record = self.record_for(lens_key)
        return None if record is None else record.decision

    @property
    def predictive_weights(self) -> Mapping[str, float]:
        return {
            item.lens_key: (
                item.domain_predictive_weight
                if item.domain_predictive_weight is not None
                else item.decision.predictive_weight
            )
            for item in self.records
        }


class SemanticLensGovernanceBridge:
    """Assess a semantic lens selection with the shared scientific lens ledger."""

    def __init__(
        self,
        *,
        lab: ScientificLensLab | None = None,
        science: LensScienceRegistry | None = None,
    ) -> None:
        if lab is not None and science is not None and science.lab is not lab:
            raise ValueError("lab and science must share the exact ScientificLensLab")
        if science is None:
            governed = explicit_profiles()
            aliases = {
                semantic_key: replace(governed[profile_key], lens_id=semantic_key)
                for semantic_key, profile_key in _PROFILE_ALIASES.items()
                if profile_key in governed
            }
            self.science = LensScienceRegistry(lab=lab, profiles=aliases)
        else:
            self.science = science
        self.lab = self.science.lab

    @staticmethod
    def _tokens(text: str) -> set[str]:
        return {token.casefold() for token in _TOKEN_RE.findall(text or "")}

    @classmethod
    def _matched_cues(
        cls,
        spec: SemanticLensSpec,
        observations: Sequence[SemanticObservation],
    ) -> tuple[str, ...]:
        observation_tokens = [cls._tokens(item.content) | set(item.tags) for item in observations]
        matched: list[str] = []
        for cue in spec.activation_cues:
            cue_tokens = cls._tokens(cue)
            if cue_tokens and any(cue_tokens.issubset(tokens) for tokens in observation_tokens):
                matched.append(cue)
        return tuple(sorted(set(matched)))

    @staticmethod
    def _definition(spec: SemanticLensSpec) -> LensDefinition:
        extreme = _EXTREME_DEFINITIONS.get(spec.key)
        return LensDefinition(
            lens_id=spec.key,
            name=spec.key.replace("_", " "),
            family=_FAMILY_MAP[spec.family],
            # A semantic interpretation remains interpretive even when its
            # intellectual lineage borrows from formal or empirical work.  A
            # host may only promote authority through an explicit governed
            # profile with verified assumptions.
            authority=LensAuthority.INTERPRETIVE,
            description=spec.description,
            cues=spec.activation_cues,
            outputs=("hypothesis", "falsifiable_prediction"),
            preserves_source_truth=True,
            metadata={
                "semantic_family": spec.family.value,
                "semantic_role": spec.role.value,
                "lineage_year": spec.lineage_year,
                "rare": spec.rare,
                "pairwise": spec.pairwise,
                "sequential": spec.sequential,
                "source": "semantic_lenses",
                "declared_maturity": (
                    extreme.maturity.value if extreme is not None else None
                ),
                "transfer_warning": (
                    extreme.transfer_warning if extreme is not None else ""
                ),
                "lineage": list(extreme.lineage) if extreme is not None else [],
            },
        )

    def assess(
        self,
        selection: LensSelection,
        observations: Sequence[SemanticObservation],
        *,
        domain: str | None = None,
    ) -> SemanticLensGovernanceSnapshot:
        normalized_domain = (
            str(domain).strip().casefold()
            if domain is not None and str(domain).strip()
            else None
        )
        records: list[SemanticLensGovernanceRecord] = []
        for spec in selection.lenses:
            matched = self._matched_cues(spec, observations)
            cue_score = len(matched) / max(1, len(spec.activation_cues))
            relation_score = 0.0
            if spec.pairwise and len(observations) >= 2:
                relation_score += 0.5
            if spec.sequential and len(observations) >= 3:
                relation_score += 0.5
            activation_score = float(selection.activation_scores.get(spec.key, 0.0))
            activation = LensActivation(
                lens=self._definition(spec),
                score=activation_score,
                cue_score=min(1.0, cue_score),
                relation_score=min(1.0, relation_score),
                novelty_score=0.15 if spec.rare else 0.0,
                matched_cues=matched,
                rationale=(
                    f"semantic-router={activation_score:.3f}; "
                    f"matched-cues={len(matched)}; "
                    f"pairwise={spec.pairwise}; sequential={spec.sequential}"
                ),
            )
            decision = self.science.assess(activation)
            domain_weight = decision.predictive_weight
            domain_status = "unspecified"
            if normalized_domain is not None:
                domain_status = "unobserved"
                try:
                    report = self.lab.report(spec.key)
                except AgentContractError:
                    report = None
                if report is not None:
                    domain_report = next(
                        (
                            item
                            for item in report.domain_calibration
                            if item.domain == normalized_domain
                        ),
                        None,
                    )
                    if domain_report is None:
                        domain_status = "unseen"
                        domain_weight = min(domain_weight, 0.10)
                    elif (
                        domain_report.count
                        < self.lab.policy.minimum_transfer_trials_per_domain
                    ):
                        domain_status = "underpowered"
                        domain_weight = min(domain_weight, 0.10)
                    else:
                        domain_status = "observed"
            extreme = _EXTREME_DEFINITIONS.get(spec.key)
            records.append(
                SemanticLensGovernanceRecord(
                    lens_key=spec.key,
                    activation_score=activation_score,
                    matched_cues=matched,
                    decision=decision,
                    declared_maturity=(
                        extreme.maturity.value if extreme is not None else None
                    ),
                    transfer_warning=(
                        extreme.transfer_warning if extreme is not None else ""
                    ),
                    lineage=(
                        tuple(extreme.lineage) if extreme is not None else ()
                    ),
                    domain_predictive_weight=domain_weight,
                    domain_status=domain_status,
                )
            )
        records.sort(key=lambda item: item.lens_key)
        fingerprint = stable_fingerprint(
            {
                "domain": normalized_domain,
                "records": [
                    (
                        item.lens_key,
                        item.activation_score,
                        item.matched_cues,
                        item.declared_maturity,
                        item.transfer_warning,
                        item.lineage,
                        item.domain_predictive_weight,
                        item.domain_status,
                        item.decision.fingerprint,
                    )
                    for item in records
                ],
            }
        )
        return SemanticLensGovernanceSnapshot(
            tuple(records),
            fingerprint,
            domain=normalized_domain,
        )

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "science": self.science.fingerprint,
                "profile_aliases": sorted(_PROFILE_ALIASES.items()),
                "extreme_definitions": [
                    (
                        key,
                        value.maturity.value,
                        value.lineage,
                        value.transfer_warning,
                    )
                    for key, value in sorted(_EXTREME_DEFINITIONS.items())
                ],
            }
        )


__all__ = [
    "SemanticLensGovernanceBridge",
    "SemanticLensGovernanceRecord",
    "SemanticLensGovernanceSnapshot",
]
