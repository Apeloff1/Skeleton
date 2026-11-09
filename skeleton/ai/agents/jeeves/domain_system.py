"""Bounded domain intelligence, Jeeves custody and teaching contracts.

P3 domain intelligence must not create a parallel authority plane.  This module
therefore treats specialization as a registry of *bounded* domains whose
custody, capability envelope, evidence freshness and evaluation owner are
explicit.  Domain execution may consume simulation evidence, but simulation
never becomes real-world evidence by relabeling.  Educational recommendations
carry learner-state uncertainty instead of silently turning noisy observations
into certainty.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
import math
from typing import Mapping, Sequence

from skeleton.simulation.environment import SimulationEvidence


class DomainIntelligenceError(RuntimeError):
    """A domain request violates scope, custody, evidence or evaluation policy."""


def _text(name: str, value: object, maximum: int = 1024) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DomainIntelligenceError(f"{name} must be non-empty text")
    result = value.strip()
    if len(result) > maximum:
        raise DomainIntelligenceError(f"{name} exceeds {maximum} characters")
    return result


def _unit(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DomainIntelligenceError(f"{name} must be numeric")
    number = float(value)
    if not math.isfinite(number) or not 0.0 <= number <= 1.0:
        raise DomainIntelligenceError(f"{name} must be in [0, 1]")
    return number


def _nonnegative(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DomainIntelligenceError(f"{name} must be numeric")
    number = float(value)
    if not math.isfinite(number) or number < 0.0:
        raise DomainIntelligenceError(f"{name} must be non-negative")
    return number


def _unique(name: str, values: Sequence[str], *, minimum: int = 0) -> tuple[str, ...]:
    result: list[str] = []
    for raw in values:
        item = _text(name, raw)
        if item in result:
            raise DomainIntelligenceError(f"{name} contains duplicate {item}")
        result.append(item)
    if len(result) < minimum:
        raise DomainIntelligenceError(f"{name} requires at least {minimum} entries")
    return tuple(result)


def _digest(payload: object) -> str:
    try:
        raw = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise DomainIntelligenceError("domain payload is not deterministic JSON") from exc
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class EvidenceClass(str, Enum):
    OBSERVATION = "observation"
    RETRIEVAL = "retrieval"
    SIMULATION = "simulation"
    DERIVED = "derived"


@dataclass(frozen=True, slots=True)
class DomainDefinition:
    domain_id: str
    custody_id: str
    purpose: str
    allowed_capabilities: tuple[str, ...]
    evaluation_owner: str
    max_evidence_age_seconds: float
    out_of_domain_policy: str = "abstain"
    provenance_required: bool = True
    simulation_allowed: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "domain_id", _text("domain_id", self.domain_id, 256))
        object.__setattr__(self, "custody_id", _text("custody_id", self.custody_id, 256))
        object.__setattr__(self, "purpose", _text("purpose", self.purpose, 2048))
        object.__setattr__(
            self,
            "allowed_capabilities",
            _unique("allowed_capability", self.allowed_capabilities, minimum=1),
        )
        object.__setattr__(
            self, "evaluation_owner", _text("evaluation_owner", self.evaluation_owner, 256)
        )
        object.__setattr__(
            self,
            "max_evidence_age_seconds",
            _nonnegative("max_evidence_age_seconds", self.max_evidence_age_seconds),
        )
        if self.out_of_domain_policy not in {"abstain", "route"}:
            raise DomainIntelligenceError("out_of_domain_policy must be abstain or route")
        if not isinstance(self.provenance_required, bool):
            raise DomainIntelligenceError("provenance_required must be boolean")
        if not isinstance(self.simulation_allowed, bool):
            raise DomainIntelligenceError("simulation_allowed must be boolean")

    @property
    def digest(self) -> str:
        return _digest(
            {
                "domain_id": self.domain_id,
                "custody_id": self.custody_id,
                "purpose": self.purpose,
                "allowed_capabilities": list(self.allowed_capabilities),
                "evaluation_owner": self.evaluation_owner,
                "max_evidence_age_seconds": self.max_evidence_age_seconds,
                "out_of_domain_policy": self.out_of_domain_policy,
                "provenance_required": self.provenance_required,
                "simulation_allowed": self.simulation_allowed,
            }
        )


@dataclass(frozen=True, slots=True)
class DomainEvidence:
    evidence_id: str
    evidence_class: EvidenceClass
    observed_at: float
    source_refs: tuple[str, ...]
    provenance_refs: tuple[str, ...]
    payload_digest: str
    uncertainty: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_id", _text("evidence_id", self.evidence_id, 256))
        if not isinstance(self.evidence_class, EvidenceClass):
            object.__setattr__(
                self, "evidence_class", EvidenceClass(str(self.evidence_class))
            )
        object.__setattr__(self, "observed_at", _nonnegative("observed_at", self.observed_at))
        object.__setattr__(
            self, "source_refs", _unique("source_ref", self.source_refs, minimum=1)
        )
        object.__setattr__(
            self, "provenance_refs", _unique("provenance_ref", self.provenance_refs)
        )
        digest = _text("payload_digest", self.payload_digest, 64).lower()
        if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise DomainIntelligenceError("payload_digest must be lowercase sha256")
        object.__setattr__(self, "payload_digest", digest)
        object.__setattr__(self, "uncertainty", _unit("uncertainty", self.uncertainty))

    @classmethod
    def from_payload(
        cls,
        *,
        evidence_id: str,
        evidence_class: EvidenceClass,
        observed_at: float,
        source_refs: Sequence[str],
        provenance_refs: Sequence[str],
        payload: object,
        uncertainty: float = 0.0,
    ) -> "DomainEvidence":
        return cls(
            evidence_id=evidence_id,
            evidence_class=evidence_class,
            observed_at=observed_at,
            source_refs=tuple(source_refs),
            provenance_refs=tuple(provenance_refs),
            payload_digest=_digest(payload),
            uncertainty=uncertainty,
        )

    @classmethod
    def from_simulation(
        cls,
        evidence_id: str,
        simulation: SimulationEvidence,
        *,
        observed_at: float,
        provenance_refs: Sequence[str],
    ) -> "DomainEvidence":
        if not isinstance(simulation, SimulationEvidence):
            raise TypeError("simulation must be SimulationEvidence")
        return cls.from_payload(
            evidence_id=evidence_id,
            evidence_class=EvidenceClass.SIMULATION,
            observed_at=observed_at,
            source_refs=(f"simulation:{simulation.simulation_id}:{simulation.step_index}",),
            provenance_refs=provenance_refs,
            payload={
                "prior": simulation.prior_state_digest,
                "action": simulation.action_digest,
                "next": simulation.next_state_digest,
                "seed": simulation.seed,
            },
            uncertainty=simulation.uncertainty,
        )


@dataclass(frozen=True, slots=True)
class DomainExecutionContext:
    domain_id: str
    custody_id: str
    capability: str
    evidence: tuple[DomainEvidence, ...]
    requested_at: float
    purpose: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "domain_id", _text("domain_id", self.domain_id, 256))
        object.__setattr__(self, "custody_id", _text("custody_id", self.custody_id, 256))
        object.__setattr__(self, "capability", _text("capability", self.capability, 256))
        object.__setattr__(self, "requested_at", _nonnegative("requested_at", self.requested_at))
        object.__setattr__(self, "purpose", _text("purpose", self.purpose, 2048))
        if not self.evidence:
            raise DomainIntelligenceError("domain execution requires evidence")


@dataclass(frozen=True, slots=True)
class DomainDecision:
    domain_id: str
    capability: str
    evidence_ids: tuple[str, ...]
    evidence_digest: str
    evaluation_owner: str
    uncertainty: float
    real_world_fact_authority: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "domain_id", _text("domain_id", self.domain_id, 256))
        object.__setattr__(self, "capability", _text("capability", self.capability, 256))
        object.__setattr__(
            self, "evidence_ids", _unique("evidence_id", self.evidence_ids, minimum=1)
        )
        object.__setattr__(self, "evaluation_owner", _text("evaluation_owner", self.evaluation_owner, 256))
        object.__setattr__(self, "uncertainty", _unit("uncertainty", self.uncertainty))
        if not isinstance(self.real_world_fact_authority, bool):
            raise DomainIntelligenceError("real_world_fact_authority must be boolean")


class DomainRegistry:
    """Single custody registry for specialized intelligence domains."""

    def __init__(self) -> None:
        self._domains: dict[str, DomainDefinition] = {}

    def register(self, definition: DomainDefinition) -> DomainDefinition:
        if not isinstance(definition, DomainDefinition):
            raise TypeError("definition must be DomainDefinition")
        prior = self._domains.get(definition.domain_id)
        if prior is not None and prior != definition:
            raise DomainIntelligenceError("domain identity/custody conflict")
        self._domains[definition.domain_id] = definition
        return definition

    def definition(self, domain_id: str) -> DomainDefinition:
        try:
            return self._domains[_text("domain_id", domain_id, 256)]
        except KeyError as exc:
            raise DomainIntelligenceError("unknown domain") from exc

    def authorize(self, context: DomainExecutionContext) -> DomainDecision:
        if not isinstance(context, DomainExecutionContext):
            raise TypeError("context must be DomainExecutionContext")
        domain = self.definition(context.domain_id)
        if context.custody_id != domain.custody_id:
            raise DomainIntelligenceError("domain custody mismatch")
        if context.capability not in domain.allowed_capabilities:
            if domain.out_of_domain_policy == "route":
                raise DomainIntelligenceError("capability requires explicit domain route")
            raise DomainIntelligenceError("out-of-domain capability must abstain")
        if context.purpose != domain.purpose:
            raise DomainIntelligenceError("domain purpose mismatch")

        uncertainty = 0.0
        real_authority = True
        ids: list[str] = []
        material: list[dict[str, object]] = []
        for evidence in context.evidence:
            if context.requested_at < evidence.observed_at:
                raise DomainIntelligenceError("evidence timestamp is in the future")
            age = context.requested_at - evidence.observed_at
            if age > domain.max_evidence_age_seconds:
                raise DomainIntelligenceError("domain evidence is stale")
            if domain.provenance_required and not evidence.provenance_refs:
                raise DomainIntelligenceError("domain evidence lacks provenance")
            if evidence.evidence_class is EvidenceClass.SIMULATION:
                if not domain.simulation_allowed:
                    raise DomainIntelligenceError("simulation evidence is not allowed in domain")
                real_authority = False
            ids.append(evidence.evidence_id)
            uncertainty = max(uncertainty, evidence.uncertainty)
            material.append(
                {
                    "id": evidence.evidence_id,
                    "class": evidence.evidence_class.value,
                    "digest": evidence.payload_digest,
                    "sources": list(evidence.source_refs),
                    "provenance": list(evidence.provenance_refs),
                }
            )
        return DomainDecision(
            domain_id=domain.domain_id,
            capability=context.capability,
            evidence_ids=tuple(ids),
            evidence_digest=_digest(material),
            evaluation_owner=domain.evaluation_owner,
            uncertainty=uncertainty,
            real_world_fact_authority=real_authority,
        )


@dataclass(frozen=True, slots=True)
class LearnerState:
    learner_id: str
    skill_id: str
    mastery: float
    uncertainty: float
    evidence_ids: tuple[str, ...]
    observed_at: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "learner_id", _text("learner_id", self.learner_id, 256))
        object.__setattr__(self, "skill_id", _text("skill_id", self.skill_id, 256))
        object.__setattr__(self, "mastery", _unit("mastery", self.mastery))
        object.__setattr__(self, "uncertainty", _unit("uncertainty", self.uncertainty))
        object.__setattr__(
            self, "evidence_ids", _unique("evidence_id", self.evidence_ids, minimum=1)
        )
        object.__setattr__(self, "observed_at", _nonnegative("observed_at", self.observed_at))


@dataclass(frozen=True, slots=True)
class TeachingRecommendation:
    learner_id: str
    skill_id: str
    action: str
    target_difficulty: float
    uncertainty: float
    evaluation_owner: str
    evidence_ids: tuple[str, ...]


class TeachingPolicy:
    """Transparent uncertainty-aware educational recommendation policy."""

    def __init__(self, *, evaluation_owner: str, max_uncertainty: float = 0.45) -> None:
        self.evaluation_owner = _text("evaluation_owner", evaluation_owner, 256)
        self.max_uncertainty = _unit("max_uncertainty", max_uncertainty)

    def recommend(self, state: LearnerState) -> TeachingRecommendation:
        if not isinstance(state, LearnerState):
            raise TypeError("state must be LearnerState")
        if state.uncertainty > self.max_uncertainty:
            action = "gather_more_evidence"
            target = state.mastery
        elif state.mastery < 0.4:
            action = "scaffold"
            target = max(0.1, state.mastery)
        elif state.mastery < 0.8:
            action = "practice"
            target = min(1.0, state.mastery + 0.1)
        else:
            action = "advance"
            target = min(1.0, state.mastery + 0.15)
        return TeachingRecommendation(
            learner_id=state.learner_id,
            skill_id=state.skill_id,
            action=action,
            target_difficulty=target,
            uncertainty=state.uncertainty,
            evaluation_owner=self.evaluation_owner,
            evidence_ids=state.evidence_ids,
        )


__all__ = [
    "DomainDecision",
    "DomainDefinition",
    "DomainEvidence",
    "DomainExecutionContext",
    "DomainIntelligenceError",
    "DomainRegistry",
    "EvidenceClass",
    "LearnerState",
    "TeachingPolicy",
    "TeachingRecommendation",
]
