"""Perpendicular semantic expansion for Jeeves.

The planner converts "do not lose tangents" into a deterministic contract.
It searches the registered semantic lens space for cue-supported directions that
are structurally different from the readings already in use.

Perpendicularity is diversity, not randomness:
- prefer unused lens families;
- prefer unused semantic roles;
- retain an adversarial/counter-reading axis when supported;
- reward lenses that make a discriminating prediction;
- never force an exotic lens with zero cue support merely to fill a quota;
- preserve every proposed axis as a research tangent, not evidence.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Sequence

from .semantic_lenses import (
    LensFamily,
    SemanticFinding,
    SemanticLensRegistry,
    SemanticLensSpec,
    SemanticObservation,
    SemanticRole,
)
from .types import AgentContractError, positive_int, probability, stable_fingerprint


@dataclass(frozen=True, slots=True)
class PerpendicularPolicy:
    maximum_axes: int = 12
    maximum_per_family: int = 2
    minimum_cue_support: float = 0.08
    family_novelty_weight: float = 0.28
    role_novelty_weight: float = 0.17
    cue_support_weight: float = 0.30
    discrimination_weight: float = 0.15
    ambiguity_weight: float = 0.10
    adversarial_bonus: float = 0.08

    def __post_init__(self) -> None:
        for name in ("maximum_axes", "maximum_per_family"):
            object.__setattr__(self, name, positive_int(name, getattr(self, name), maximum=1000))
        object.__setattr__(self, "minimum_cue_support", probability("minimum_cue_support", self.minimum_cue_support))
        names = (
            "family_novelty_weight",
            "role_novelty_weight",
            "cue_support_weight",
            "discrimination_weight",
            "ambiguity_weight",
        )
        values = [float(getattr(self, name)) for name in names]
        if any(value < 0.0 for value in values) or sum(values) <= 0:
            raise AgentContractError("perpendicular planner weights must be non-negative and non-zero")
        total = sum(values)
        for name, value in zip(names, values):
            object.__setattr__(self, name, value / total)
        if self.adversarial_bonus < 0:
            raise AgentContractError("adversarial_bonus must be non-negative")


@dataclass(frozen=True, slots=True)
class PerpendicularAxisCandidate:
    lens_key: str
    family: LensFamily
    role: SemanticRole
    support: float
    family_novelty: float
    role_novelty: float
    discrimination: float
    ambiguity_value: float
    expected_value: float
    evidence_gap: float
    direction: str
    rationale: str
    prediction: str
    failure_mode: str
    trigger_terms: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in (
            "support",
            "family_novelty",
            "role_novelty",
            "discrimination",
            "ambiguity_value",
            "expected_value",
            "evidence_gap",
        ):
            object.__setattr__(self, name, probability(name, getattr(self, name)))


@dataclass(frozen=True, slots=True)
class PerpendicularExpansionPlan:
    candidates: tuple[PerpendicularAxisCandidate, ...]
    covered_families: tuple[LensFamily, ...]
    covered_roles: tuple[SemanticRole, ...]
    omitted_lens_keys: tuple[str, ...]
    adversarial_included: bool
    fingerprint: str


class PerpendicularExpansionPlanner:
    """Select orthogonal, cue-supported semantic research directions."""

    def __init__(
        self,
        registry: SemanticLensRegistry,
        *,
        policy: PerpendicularPolicy | None = None,
    ) -> None:
        if not isinstance(registry, SemanticLensRegistry):
            raise TypeError("registry must be SemanticLensRegistry")
        self.registry = registry
        self.policy = policy or PerpendicularPolicy()

    @staticmethod
    def _text(observations: Sequence[SemanticObservation]) -> str:
        return " ".join(
            f"{item.content} {' '.join(item.tags)}"
            for item in observations
        ).casefold()

    @staticmethod
    def _cue_support(spec: SemanticLensSpec, text: str) -> tuple[float, tuple[str, ...]]:
        if not spec.activation_cues:
            return 0.0, ()
        matched = tuple(cue for cue in spec.activation_cues if cue and cue in text)
        if not matched:
            return 0.0, ()
        # Saturate repeated/synonymous cue evidence so huge cue lists do not
        # unfairly penalize a narrow but diagnostic match.
        ratio = len(matched) / max(1, min(6, len(spec.activation_cues)))
        return min(1.0, ratio), matched

    @staticmethod
    def _mean_ambiguity(findings: Sequence[SemanticFinding]) -> float:
        if not findings:
            return 0.5
        return sum(item.ambiguity for item in findings) / len(findings)

    @staticmethod
    def _discrimination(spec: SemanticLensSpec) -> float:
        prediction = bool(spec.predicts.strip())
        failure = bool(spec.failure_mode.strip())
        questions = bool(spec.asks)
        if prediction and failure and questions:
            return 1.0
        if prediction and (failure or questions):
            return 0.75
        if prediction:
            return 0.55
        return 0.25

    def plan(
        self,
        observations: Sequence[SemanticObservation],
        *,
        findings: Sequence[SemanticFinding] = (),
        selected_lens_keys: Sequence[str] = (),
        maximum_axes: int | None = None,
    ) -> PerpendicularExpansionPlan:
        maximum = self.policy.maximum_axes if maximum_axes is None else positive_int(
            "maximum_axes", maximum_axes, maximum=1000
        )
        if not observations:
            return PerpendicularExpansionPlan(
                (),
                (),
                (),
                (),
                False,
                stable_fingerprint({"observations": (), "candidates": ()}),
            )

        text = self._text(observations)
        selected = {str(item).strip().casefold() for item in selected_lens_keys if str(item).strip()}
        selected.update(item.lens_key for item in findings)
        covered_families = {item.family for item in findings}
        covered_roles: set[SemanticRole] = set()

        # Selected lenses count as covered even before a model returns findings:
        # this prevents restart expansion from proposing the same reasoning mode
        # that was already on the active context.
        for key in selected:
            try:
                spec = self.registry.get(key)
            except KeyError:
                continue
            covered_families.add(spec.family)
            covered_roles.add(spec.role)
        for finding in findings:
            try:
                covered_roles.add(self.registry.get(finding.lens_key).role)
            except KeyError:
                pass

        ambiguity = self._mean_ambiguity(findings)
        scored: list[tuple[float, SemanticLensSpec, tuple[str, ...], tuple[float, ...]]] = []
        for spec in self.registry.all():
            if spec.key in selected or len(observations) < spec.minimum_observations:
                continue
            support, matched = self._cue_support(spec, text)
            if support < self.policy.minimum_cue_support:
                continue
            family_novelty = 1.0 if spec.family not in covered_families else 0.20
            role_novelty = 1.0 if spec.role not in covered_roles else 0.25
            discrimination = self._discrimination(spec)
            ambiguity_value = min(1.0, ambiguity + (0.12 if spec.role is SemanticRole.ADVERSARIAL_READING else 0.0))
            value = (
                self.policy.family_novelty_weight * family_novelty
                + self.policy.role_novelty_weight * role_novelty
                + self.policy.cue_support_weight * support
                + self.policy.discrimination_weight * discrimination
                + self.policy.ambiguity_weight * ambiguity_value
            )
            if spec.role is SemanticRole.ADVERSARIAL_READING:
                value = min(1.0, value + self.policy.adversarial_bonus)
            evidence_gap = min(
                1.0,
                0.45
                + 0.35 * ambiguity_value
                + 0.20 * (1.0 - support),
            )
            scored.append(
                (
                    value,
                    spec,
                    matched,
                    (
                        support,
                        family_novelty,
                        role_novelty,
                        discrimination,
                        ambiguity_value,
                        evidence_gap,
                    ),
                )
            )

        scored.sort(key=lambda item: (-item[0], item[1].family.value, item[1].role.value, item[1].key))

        chosen: list[PerpendicularAxisCandidate] = []
        family_counts: defaultdict[LensFamily, int] = defaultdict(int)
        omitted: list[str] = []

        # First pass: maximize family breadth.
        seen_families = set(covered_families)
        for value, spec, matched, parts in scored:
            if len(chosen) >= maximum:
                break
            if spec.family in seen_families:
                continue
            support, family_novelty, role_novelty, discrimination, ambiguity_value, evidence_gap = parts
            chosen.append(
                self._candidate(
                    spec,
                    value,
                    matched,
                    support,
                    family_novelty,
                    role_novelty,
                    discrimination,
                    ambiguity_value,
                    evidence_gap,
                )
            )
            family_counts[spec.family] += 1
            seen_families.add(spec.family)

        chosen_keys = {item.lens_key for item in chosen}

        # Ensure a supported adversarial reading is not crowded out by breadth.
        adversarial = next(
            (
                row
                for row in scored
                if row[1].role is SemanticRole.ADVERSARIAL_READING
                and row[1].key not in chosen_keys
            ),
            None,
        )
        if adversarial is not None and len(chosen) < maximum:
            value, spec, matched, parts = adversarial
            if family_counts[spec.family] < self.policy.maximum_per_family:
                chosen.append(self._candidate(spec, value, matched, *parts))
                chosen_keys.add(spec.key)
                family_counts[spec.family] += 1

        # Second pass: depth, still bounded per family.
        for value, spec, matched, parts in scored:
            if len(chosen) >= maximum:
                break
            if spec.key in chosen_keys:
                continue
            if family_counts[spec.family] >= self.policy.maximum_per_family:
                omitted.append(spec.key)
                continue
            chosen.append(self._candidate(spec, value, matched, *parts))
            chosen_keys.add(spec.key)
            family_counts[spec.family] += 1

        omitted.extend(
            spec.key
            for _, spec, _, _ in scored
            if spec.key not in chosen_keys and spec.key not in omitted
        )
        adversarial_included = any(
            item.role is SemanticRole.ADVERSARIAL_READING for item in chosen
        )
        fingerprint = stable_fingerprint(
            {
                "observations": [item.fingerprint for item in observations],
                "findings": [item.fingerprint for item in findings],
                "selected": sorted(selected),
                "candidates": [
                    (
                        item.lens_key,
                        item.family.value,
                        item.role.value,
                        round(item.support, 12),
                        round(item.expected_value, 12),
                        round(item.evidence_gap, 12),
                    )
                    for item in chosen
                ],
                "omitted": omitted,
            }
        )
        return PerpendicularExpansionPlan(
            candidates=tuple(chosen),
            covered_families=tuple(sorted(covered_families, key=lambda item: item.value)),
            covered_roles=tuple(sorted(covered_roles, key=lambda item: item.value)),
            omitted_lens_keys=tuple(omitted),
            adversarial_included=adversarial_included,
            fingerprint=fingerprint,
        )

    @staticmethod
    def _candidate(
        spec: SemanticLensSpec,
        value: float,
        matched: Sequence[str],
        support: float,
        family_novelty: float,
        role_novelty: float,
        discrimination: float,
        ambiguity_value: float,
        evidence_gap: float,
    ) -> PerpendicularAxisCandidate:
        question = spec.asks[0] if spec.asks else f"Test the {spec.key} interpretation."
        direction = f"{question} Prediction to discriminate: {spec.predicts}"
        rationale = (
            f"Perpendicular lens={spec.key}; family={spec.family.value}; role={spec.role.value}; "
            f"cue_support={support:.3f}; family_novelty={family_novelty:.3f}; "
            f"role_novelty={role_novelty:.3f}; failure_condition={spec.failure_mode}"
        )
        return PerpendicularAxisCandidate(
            lens_key=spec.key,
            family=spec.family,
            role=spec.role,
            support=support,
            family_novelty=family_novelty,
            role_novelty=role_novelty,
            discrimination=discrimination,
            ambiguity_value=ambiguity_value,
            expected_value=max(0.0, min(1.0, value)),
            evidence_gap=evidence_gap,
            direction=direction,
            rationale=rationale,
            prediction=spec.predicts,
            failure_mode=spec.failure_mode,
            trigger_terms=tuple(sorted(set(matched))),
        )
