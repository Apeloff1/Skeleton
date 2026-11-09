"""Causal epistemic control for advanced Jeeves cognition.

This module is a host-side causal reasoning and active-information layer.  It is
purposefully separated from the evidence ledger: simulated/interventional
predictions are *planning artifacts*, never facts.  Real observations may
update mechanisms only through explicit learning proposals and validation.

The implementation combines several durable ideas from classical and modern AI:

* structural causal models: directed mechanisms, interventions, counterfactual
  queries, transport/regime metadata, and mechanism drift;
* POMDP-style belief control: hidden-state distributions rather than a single
  guessed state;
* active inference / value of information: choose actions for both pragmatic
  value and uncertainty reduction;
* causal RL: distinguish observational association from effects under do();
* experimental design: select interventions expected to discriminate competing
  causal hypotheses;
* process learning: fit categorical mechanisms from verified transition data,
  score edge hypotheses, and expose uncertainty rather than silently promoting
  causal structure.

No private chain-of-thought is stored.  Reasoning artifacts are concise typed
summaries with deterministic fingerprints.
"""

from __future__ import annotations

import itertools
import math
import random
import threading
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Callable, Iterable, Mapping, Sequence

from .types import (
    AgentContractError,
    RiskTier,
    bounded_text,
    finite_number,
    json_safe,
    positive_int,
    probability,
    require_id,
    stable_fingerprint,
    stable_id,
)


_EPS = 1e-12


class CausalEpistemicError(RuntimeError):
    """Raised for invalid causal or epistemic-control operations."""


class InferenceLimit(CausalEpistemicError):
    """Raised when exact inference would exceed the configured state budget."""


class VariableRole(str, Enum):
    STATE = "state"
    LATENT = "latent"
    OBSERVATION = "observation"
    ACTION = "action"
    OUTCOME = "outcome"
    CONTEXT = "context"


class MechanismStatus(str, Enum):
    DECLARED = "declared"
    LEARNED = "learned"
    PROVISIONAL = "provisional"
    DRIFTED = "drifted"
    REJECTED = "rejected"


class QueryKind(str, Enum):
    OBSERVATIONAL = "observational"
    INTERVENTIONAL = "interventional"
    COUNTERFACTUAL = "counterfactual"


class ExperimentPurpose(str, Enum):
    DISCRIMINATE_EDGE = "discriminate_edge"
    REDUCE_STATE_UNCERTAINTY = "reduce_state_uncertainty"
    ESTIMATE_EFFECT = "estimate_effect"
    TEST_MECHANISM_DRIFT = "test_mechanism_drift"


def _finite_nonnegative(name: str, value: Any) -> float:
    result = finite_number(name, value)
    if result < 0:
        raise AgentContractError(f"{name} must be non-negative")
    return result


def _normalize(values: Mapping[str, float]) -> dict[str, float]:
    if not values:
        raise AgentContractError("probability mapping cannot be empty")
    cleaned: dict[str, float] = {}
    for key, raw in values.items():
        if not isinstance(key, str) or not key:
            raise AgentContractError("distribution keys must be non-empty strings")
        value = finite_number(f"probability[{key}]", raw)
        if value < 0:
            raise AgentContractError("probabilities must be non-negative")
        cleaned[key] = value
    total = sum(cleaned.values())
    if total <= 0:
        raise AgentContractError("probability mass must be positive")
    return {key: value / total for key, value in cleaned.items()}


def entropy_bits(values: Mapping[str, float]) -> float:
    dist = _normalize(values)
    return -sum(p * math.log2(p) for p in dist.values() if p > 0)


def kl_divergence_bits(
    left: Mapping[str, float],
    right: Mapping[str, float],
    *,
    smoothing: float = 1e-9,
) -> float:
    p = _normalize(left)
    q = _normalize(right)
    keys = set(p) | set(q)
    q_smooth = {key: q.get(key, 0.0) + smoothing for key in keys}
    q_smooth = _normalize(q_smooth)
    p_smooth = {key: p.get(key, 0.0) + smoothing for key in keys}
    p_smooth = _normalize(p_smooth)
    return sum(
        p_smooth[key] * math.log2(p_smooth[key] / q_smooth[key])
        for key in keys
        if p_smooth[key] > 0
    )


def js_divergence_bits(
    left: Mapping[str, float],
    right: Mapping[str, float],
) -> float:
    p = _normalize(left)
    q = _normalize(right)
    keys = set(p) | set(q)
    mix = {key: 0.5 * p.get(key, 0.0) + 0.5 * q.get(key, 0.0) for key in keys}
    return 0.5 * kl_divergence_bits(p, mix) + 0.5 * kl_divergence_bits(q, mix)


@dataclass(frozen=True, slots=True)
class CategoricalDistribution:
    values: Mapping[str, float]
    support: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        normalized = _normalize(dict(self.values))
        support = tuple(self.support) if self.support else tuple(sorted(normalized))
        if len(set(support)) != len(support) or any(not isinstance(item, str) or not item for item in support):
            raise AgentContractError("invalid categorical support")
        unknown = set(normalized) - set(support)
        if unknown:
            raise AgentContractError(f"distribution contains values outside support: {sorted(unknown)}")
        completed = {item: normalized.get(item, 0.0) for item in support}
        object.__setattr__(self, "values", completed)
        object.__setattr__(self, "support", support)

    @classmethod
    def uniform(cls, support: Sequence[str]) -> "CategoricalDistribution":
        values = tuple(str(item) for item in support)
        if not values:
            raise AgentContractError("uniform distribution requires support")
        mass = 1.0 / len(values)
        return cls({item: mass for item in values}, values)

    @classmethod
    def point(cls, value: str, support: Sequence[str]) -> "CategoricalDistribution":
        support_tuple = tuple(support)
        if value not in support_tuple:
            raise AgentContractError("point value outside support")
        return cls({item: 1.0 if item == value else 0.0 for item in support_tuple}, support_tuple)

    @property
    def entropy_bits(self) -> float:
        return entropy_bits(self.values)

    @property
    def maximum_probability(self) -> float:
        return max(self.values.values(), default=0.0)

    @property
    def mode(self) -> str:
        if not self.values:
            raise CausalEpistemicError("empty distribution")
        return max(self.values, key=lambda key: (self.values[key], key))

    def probability_of(self, value: str) -> float:
        return self.values.get(value, 0.0)

    def sample(self, rng: random.Random) -> str:
        threshold = rng.random()
        cumulative = 0.0
        for value in self.support:
            cumulative += self.values.get(value, 0.0)
            if threshold <= cumulative + 1e-15:
                return value
        return self.support[-1]

    def mix(
        self,
        other: "CategoricalDistribution",
        weight: float,
    ) -> "CategoricalDistribution":
        if not isinstance(other, CategoricalDistribution):
            raise TypeError("other must be CategoricalDistribution")
        weight = probability("weight", weight)
        support = tuple(sorted(set(self.support) | set(other.support)))
        return CategoricalDistribution(
            {
                value: (1.0 - weight) * self.values.get(value, 0.0)
                + weight * other.values.get(value, 0.0)
                for value in support
            },
            support,
        )

    def as_json(self) -> dict[str, Any]:
        return {
            "support": list(self.support),
            "values": {key: self.values[key] for key in self.support},
            "entropy_bits": self.entropy_bits,
        }


@dataclass(frozen=True, slots=True)
class CausalVariable:
    variable_id: str
    domain: tuple[str, ...]
    role: VariableRole = VariableRole.STATE
    prior: CategoricalDistribution | None = None
    observable: bool = True
    manipulable: bool = False
    intervention_cost: float = 0.0
    risk: RiskTier = RiskTier.READ_ONLY
    description: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "variable_id", require_id("variable_id", self.variable_id))
        domain = tuple(str(item) for item in self.domain)
        if not domain or len(set(domain)) != len(domain):
            raise AgentContractError("variable domain must be non-empty and unique")
        if any(not item or len(item) > 512 for item in domain):
            raise AgentContractError("invalid domain value")
        object.__setattr__(self, "domain", domain)
        if not isinstance(self.role, VariableRole):
            object.__setattr__(self, "role", VariableRole(str(self.role)))
        prior = self.prior or CategoricalDistribution.uniform(domain)
        if tuple(prior.support) != domain:
            raise AgentContractError("variable prior support must match domain exactly")
        object.__setattr__(self, "prior", prior)
        if not isinstance(self.observable, bool) or not isinstance(self.manipulable, bool):
            raise AgentContractError("variable observable/manipulable flags must be boolean")
        object.__setattr__(
            self,
            "intervention_cost",
            _finite_nonnegative("intervention_cost", self.intervention_cost),
        )
        if not isinstance(self.risk, RiskTier):
            object.__setattr__(self, "risk", RiskTier(str(self.risk)))
        object.__setattr__(
            self,
            "description",
            bounded_text("description", self.description, maximum=4096, allow_empty=True),
        )
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))

    def as_json(self) -> dict[str, Any]:
        return {
            "variable_id": self.variable_id,
            "domain": list(self.domain),
            "role": self.role.value,
            "prior": self.prior.as_json() if self.prior else None,
            "observable": self.observable,
            "manipulable": self.manipulable,
            "intervention_cost": self.intervention_cost,
            "risk": self.risk.value,
            "description": self.description,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class MechanismRow:
    parent_values: tuple[tuple[str, str], ...]
    distribution: CategoricalDistribution

    def __post_init__(self) -> None:
        pairs = tuple((require_id("parent", key), str(value)) for key, value in self.parent_values)
        keys = [key for key, _ in pairs]
        if len(keys) != len(set(keys)):
            raise AgentContractError("mechanism row contains duplicate parent assignments")
        object.__setattr__(self, "parent_values", tuple(sorted(pairs)))

    @property
    def key(self) -> tuple[tuple[str, str], ...]:
        return self.parent_values

    def as_json(self) -> dict[str, Any]:
        return {
            "parent_values": [[key, value] for key, value in self.parent_values],
            "distribution": self.distribution.as_json(),
        }


@dataclass(frozen=True, slots=True)
class CausalMechanism:
    child_id: str
    parent_ids: tuple[str, ...]
    rows: tuple[MechanismRow, ...]
    fallback: CategoricalDistribution
    status: MechanismStatus = MechanismStatus.DECLARED
    confidence: float = 1.0
    sample_count: int = 0
    regime: str = "default"
    provenance: tuple[str, ...] = ()
    version: int = 1
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "child_id", require_id("child_id", self.child_id))
        parents = tuple(require_id("parent_id", item) for item in self.parent_ids)
        if self.child_id in parents or len(parents) != len(set(parents)):
            raise AgentContractError("invalid mechanism parent set")
        object.__setattr__(self, "parent_ids", parents)
        rows = tuple(self.rows)
        if any(not isinstance(row, MechanismRow) for row in rows):
            raise AgentContractError("mechanism rows must contain MechanismRow")
        seen: set[tuple[tuple[str, str], ...]] = set()
        for row in rows:
            if row.key in seen:
                raise AgentContractError("duplicate mechanism row")
            seen.add(row.key)
            if set(key for key, _ in row.parent_values) != set(parents):
                raise AgentContractError("mechanism row parent keys do not match parent_ids")
        object.__setattr__(self, "rows", rows)
        if not isinstance(self.status, MechanismStatus):
            object.__setattr__(self, "status", MechanismStatus(str(self.status)))
        object.__setattr__(self, "confidence", probability("confidence", self.confidence))
        if isinstance(self.sample_count, bool) or not isinstance(self.sample_count, int) or self.sample_count < 0:
            raise AgentContractError("sample_count must be non-negative integer")
        object.__setattr__(self, "regime", require_id("regime", self.regime))
        object.__setattr__(
            self,
            "provenance",
            tuple(require_id("provenance_id", item) for item in self.provenance),
        )
        object.__setattr__(self, "version", positive_int("version", self.version, maximum=1_000_000))
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))

    def distribution_for(self, assignment: Mapping[str, str]) -> CategoricalDistribution:
        wanted = tuple(sorted((parent, str(assignment[parent])) for parent in self.parent_ids if parent in assignment))
        if len(wanted) != len(self.parent_ids):
            return self.fallback
        for row in self.rows:
            if row.key == wanted:
                return row.distribution
        return self.fallback

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(self.as_json())

    def as_json(self) -> dict[str, Any]:
        return {
            "child_id": self.child_id,
            "parent_ids": list(self.parent_ids),
            "rows": [row.as_json() for row in self.rows],
            "fallback": self.fallback.as_json(),
            "status": self.status.value,
            "confidence": self.confidence,
            "sample_count": self.sample_count,
            "regime": self.regime,
            "provenance": list(self.provenance),
            "version": self.version,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class WeightedState:
    assignment: Mapping[str, str]
    probability: float

    def __post_init__(self) -> None:
        assignment = {require_id("variable", key): str(value) for key, value in dict(self.assignment).items()}
        object.__setattr__(self, "assignment", assignment)
        value = finite_number("probability", self.probability)
        if value < 0:
            raise AgentContractError("weighted state probability must be non-negative")
        object.__setattr__(self, "probability", value)

    def as_json(self) -> dict[str, Any]:
        return {"assignment": dict(self.assignment), "probability": self.probability}


@dataclass(frozen=True, slots=True)
class InferenceResult:
    query_kind: QueryKind
    states: tuple[WeightedState, ...]
    evidence: Mapping[str, str]
    interventions: Mapping[str, str]
    normalization_constant: float
    truncated: bool
    fingerprint: str

    def marginal(
        self,
        variable_id: str,
        domain: Sequence[str] | None = None,
    ) -> CategoricalDistribution:
        variable_id = require_id("variable_id", variable_id)
        counts: defaultdict[str, float] = defaultdict(float)
        for state in self.states:
            if variable_id in state.assignment:
                counts[state.assignment[variable_id]] += state.probability
        support = tuple(domain) if domain is not None else tuple(sorted(counts))
        if not support:
            raise CausalEpistemicError(f"variable {variable_id} absent from inference result")
        if sum(counts.values()) <= 0:
            return CategoricalDistribution.uniform(support)
        return CategoricalDistribution(dict(counts), support)


@dataclass(frozen=True, slots=True)
class CounterfactualEstimate:
    query_id: str
    factual_evidence: Mapping[str, str]
    intervention: Mapping[str, str]
    target_id: str
    distribution: CategoricalDistribution
    identified: bool
    identification_note: str
    assumptions: tuple[str, ...]
    fingerprint: str


class StructuralCausalModel:
    """Finite categorical structural causal model with exact bounded inference."""

    def __init__(self, *, max_joint_states: int = 100_000) -> None:
        self.max_joint_states = positive_int(
            "max_joint_states", max_joint_states, maximum=10_000_000
        )
        self._variables: dict[str, CausalVariable] = {}
        self._mechanisms: dict[tuple[str, str], CausalMechanism] = {}
        self._active_regime = "default"
        self._lock = threading.RLock()

    @property
    def active_regime(self) -> str:
        return self._active_regime

    def set_regime(self, regime: str) -> None:
        regime = require_id("regime", regime)
        with self._lock:
            self._active_regime = regime

    def add_variable(self, variable: CausalVariable) -> None:
        if not isinstance(variable, CausalVariable):
            raise TypeError("variable must be CausalVariable")
        with self._lock:
            prior = self._variables.get(variable.variable_id)
            if prior is not None and prior != variable:
                raise CausalEpistemicError(f"variable already exists: {variable.variable_id}")
            self._variables[variable.variable_id] = variable
            self._validate_mechanism_domains()

    def set_mechanism(self, mechanism: CausalMechanism) -> None:
        if not isinstance(mechanism, CausalMechanism):
            raise TypeError("mechanism must be CausalMechanism")
        with self._lock:
            if mechanism.child_id not in self._variables:
                raise CausalEpistemicError("mechanism child variable is unknown")
            missing = [parent for parent in mechanism.parent_ids if parent not in self._variables]
            if missing:
                raise CausalEpistemicError(f"unknown mechanism parents: {missing}")
            child = self._variables[mechanism.child_id]
            if tuple(mechanism.fallback.support) != child.domain:
                raise CausalEpistemicError("mechanism fallback support differs from child domain")
            for row in mechanism.rows:
                if tuple(row.distribution.support) != child.domain:
                    raise CausalEpistemicError("mechanism row support differs from child domain")
                for parent_id, value in row.parent_values:
                    if value not in self._variables[parent_id].domain:
                        raise CausalEpistemicError("mechanism row contains invalid parent value")
            self._mechanisms[(mechanism.regime, mechanism.child_id)] = mechanism
            self._topological_order(regime=mechanism.regime)

    def variable(self, variable_id: str) -> CausalVariable:
        resolved = require_id("variable_id", variable_id)
        with self._lock:
            try:
                return self._variables[resolved]
            except KeyError as exc:
                raise CausalEpistemicError(f"unknown causal variable: {resolved}") from exc

    def variables(self) -> tuple[CausalVariable, ...]:
        with self._lock:
            return tuple(self._variables[key] for key in sorted(self._variables))

    def mechanism(
        self,
        child_id: str,
        *,
        regime: str | None = None,
    ) -> CausalMechanism | None:
        child_id = require_id("child_id", child_id)
        resolved = require_id("regime", regime or self._active_regime)
        with self._lock:
            return self._mechanisms.get((resolved, child_id)) or self._mechanisms.get(
                ("default", child_id)
            )

    def parents(self, variable_id: str, *, regime: str | None = None) -> tuple[str, ...]:
        mechanism = self.mechanism(variable_id, regime=regime)
        return mechanism.parent_ids if mechanism else ()

    def children(self, variable_id: str, *, regime: str | None = None) -> tuple[str, ...]:
        resolved = require_id("variable_id", variable_id)
        regime = require_id("regime", regime or self._active_regime)
        result = []
        for variable in self.variables():
            if resolved in self.parents(variable.variable_id, regime=regime):
                result.append(variable.variable_id)
        return tuple(sorted(result))

    def descendants(self, variable_id: str, *, regime: str | None = None) -> tuple[str, ...]:
        root = require_id("variable_id", variable_id)
        seen: set[str] = set()
        queue = list(self.children(root, regime=regime))
        while queue:
            current = queue.pop(0)
            if current in seen:
                continue
            seen.add(current)
            queue.extend(self.children(current, regime=regime))
        return tuple(sorted(seen))

    def markov_blanket(self, variable_id: str, *, regime: str | None = None) -> tuple[str, ...]:
        variable_id = require_id("variable_id", variable_id)
        parents = set(self.parents(variable_id, regime=regime))
        children = set(self.children(variable_id, regime=regime))
        co_parents: set[str] = set()
        for child in children:
            co_parents.update(self.parents(child, regime=regime))
        return tuple(sorted((parents | children | co_parents) - {variable_id}))

    def _validate_mechanism_domains(self) -> None:
        for mechanism in self._mechanisms.values():
            if mechanism.child_id not in self._variables:
                continue
            child = self._variables[mechanism.child_id]
            if tuple(mechanism.fallback.support) != child.domain:
                raise CausalEpistemicError("mechanism support no longer matches variable domain")

    def _topological_order(self, *, regime: str | None = None) -> tuple[str, ...]:
        regime = require_id("regime", regime or self._active_regime)
        nodes = set(self._variables)
        incoming: dict[str, set[str]] = {
            node: set(self.parents(node, regime=regime)) for node in nodes
        }
        order: list[str] = []
        ready = sorted(node for node, parents in incoming.items() if not parents)
        while ready:
            current = ready.pop(0)
            order.append(current)
            for node in sorted(nodes - set(order)):
                if current in incoming[node]:
                    incoming[node].remove(current)
                    if not incoming[node] and node not in ready:
                        ready.append(node)
                        ready.sort()
        if len(order) != len(nodes):
            cycle_nodes = sorted(nodes - set(order))
            raise CausalEpistemicError(
                f"causal graph contains a directed cycle: {cycle_nodes}"
            )
        return tuple(order)

    def _distribution(
        self,
        variable_id: str,
        assignment: Mapping[str, str],
        *,
        regime: str,
    ) -> CategoricalDistribution:
        mechanism = self.mechanism(variable_id, regime=regime)
        if mechanism is None:
            return self.variable(variable_id).prior or CategoricalDistribution.uniform(
                self.variable(variable_id).domain
            )
        return mechanism.distribution_for(assignment)

    def infer(
        self,
        *,
        evidence: Mapping[str, str] | None = None,
        interventions: Mapping[str, str] | None = None,
        regime: str | None = None,
    ) -> InferenceResult:
        evidence = {
            require_id("evidence variable", key): str(value)
            for key, value in dict(evidence or {}).items()
        }
        interventions = {
            require_id("intervention variable", key): str(value)
            for key, value in dict(interventions or {}).items()
        }
        regime = require_id("regime", regime or self._active_regime)
        for variable_id, value in {**evidence, **interventions}.items():
            variable = self.variable(variable_id)
            if value not in variable.domain:
                raise CausalEpistemicError(
                    f"value {value!r} outside domain for {variable_id}"
                )
        for variable_id in interventions:
            variable = self.variable(variable_id)
            if not variable.manipulable and variable.role is not VariableRole.ACTION:
                raise CausalEpistemicError(
                    f"variable is not manipulable: {variable_id}"
                )
        order = self._topological_order(regime=regime)
        states: list[tuple[dict[str, str], float]] = [({}, 1.0)]
        truncated = False
        for variable_id in order:
            next_states: list[tuple[dict[str, str], float]] = []
            for partial, weight in states:
                if variable_id in interventions:
                    candidates = {interventions[variable_id]: 1.0}
                else:
                    candidates = self._distribution(
                        variable_id, partial, regime=regime
                    ).values
                for value, p in candidates.items():
                    if p <= 0:
                        continue
                    if variable_id in evidence and evidence[variable_id] != value:
                        continue
                    updated = dict(partial)
                    updated[variable_id] = value
                    next_states.append((updated, weight * p))
                    if len(next_states) > self.max_joint_states:
                        truncated = True
                        raise InferenceLimit(
                            f"joint state enumeration exceeds {self.max_joint_states}"
                        )
            states = next_states
            if not states:
                break
        total = sum(weight for _, weight in states)
        if total <= 0:
            raise CausalEpistemicError("evidence has zero probability under causal model")
        normalized = tuple(
            WeightedState(assignment=assignment, probability=weight / total)
            for assignment, weight in states
        )
        kind = (
            QueryKind.INTERVENTIONAL
            if interventions
            else QueryKind.OBSERVATIONAL
        )
        fp = stable_fingerprint(
            {
                "kind": kind.value,
                "evidence": evidence,
                "interventions": interventions,
                "regime": regime,
                "states": [
                    {
                        "assignment": dict(state.assignment),
                        "p": state.probability,
                    }
                    for state in normalized
                ],
            }
        )
        return InferenceResult(
            query_kind=kind,
            states=normalized,
            evidence=evidence,
            interventions=interventions,
            normalization_constant=total,
            truncated=truncated,
            fingerprint=fp,
        )

    def marginal(
        self,
        variable_id: str,
        *,
        evidence: Mapping[str, str] | None = None,
        interventions: Mapping[str, str] | None = None,
        regime: str | None = None,
    ) -> CategoricalDistribution:
        variable = self.variable(variable_id)
        return self.infer(
            evidence=evidence,
            interventions=interventions,
            regime=regime,
        ).marginal(variable.variable_id, variable.domain)

    def counterfactual(
        self,
        target_id: str,
        *,
        factual_evidence: Mapping[str, str],
        intervention: Mapping[str, str],
        regime: str | None = None,
    ) -> CounterfactualEstimate:
        target = self.variable(target_id)
        self.infer(evidence=factual_evidence, regime=regime)
        posterior_context: dict[str, str] = {}
        for variable in self.variables():
            if variable.variable_id in factual_evidence:
                posterior_context[variable.variable_id] = factual_evidence[
                    variable.variable_id
                ]
        relevant_evidence = {
            key: value
            for key, value in posterior_context.items()
            if key not in intervention
        }
        result = self.infer(
            evidence=relevant_evidence,
            interventions=intervention,
            regime=regime,
        )
        distribution = result.marginal(target.variable_id, target.domain)
        note = (
            "Posterior-predictive interventional approximation. Exact "
            "individual-level counterfactuals require an identified exogenous "
            "noise coupling or stronger structural assumptions."
        )
        query_id = stable_id(
            "counterfactual",
            {
                "target": target_id,
                "factual": dict(factual_evidence),
                "intervention": dict(intervention),
                "regime": regime or self._active_regime,
            },
        )
        return CounterfactualEstimate(
            query_id=query_id,
            factual_evidence=json_safe(dict(factual_evidence)),
            intervention=json_safe(dict(intervention)),
            target_id=target_id,
            distribution=distribution,
            identified=False,
            identification_note=note,
            assumptions=(
                "mechanisms are invariant under the requested intervention",
                "posterior-predictive approximation is acceptable for planning",
            ),
            fingerprint=stable_fingerprint(
                {
                    "query_id": query_id,
                    "distribution": distribution.as_json(),
                    "identified": False,
                }
            ),
        )

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "active_regime": self._active_regime,
                "variables": [variable.as_json() for variable in self.variables()],
                "mechanisms": [
                    mechanism.as_json()
                    for _, mechanism in sorted(
                        self._mechanisms.items(), key=lambda item: item[0]
                    )
                ],
            }
        )


@dataclass(frozen=True, slots=True)
class BeliefState:
    evidence: Mapping[str, str] = field(default_factory=dict)
    marginals: Mapping[str, CategoricalDistribution] = field(default_factory=dict)
    version: int = 1
    updated_at: float = field(default_factory=time.time)
    source: str = "model"

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "evidence",
            {
                require_id("evidence variable", key): str(value)
                for key, value in dict(self.evidence).items()
            },
        )
        marginals = dict(self.marginals)
        if any(not isinstance(value, CategoricalDistribution) for value in marginals.values()):
            raise AgentContractError("belief marginals must contain CategoricalDistribution")
        object.__setattr__(self, "marginals", marginals)
        object.__setattr__(self, "version", positive_int("version", self.version, maximum=1_000_000))
        updated = finite_number("updated_at", self.updated_at)
        if updated < 0:
            raise AgentContractError("updated_at must be non-negative")
        object.__setattr__(self, "updated_at", updated)
        object.__setattr__(
            self, "source", bounded_text("source", self.source, maximum=1024)
        )

    @property
    def entropy_bits(self) -> float:
        return sum(distribution.entropy_bits for distribution in self.marginals.values())

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "evidence": dict(self.evidence),
                "marginals": {
                    key: value.as_json()
                    for key, value in sorted(self.marginals.items())
                },
                "version": self.version,
                "source": self.source,
            }
        )


class BeliefUpdater:
    def __init__(
        self,
        model: StructuralCausalModel,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.model = model
        self._clock = clock

    def from_evidence(
        self,
        evidence: Mapping[str, str],
        *,
        variables: Sequence[str] | None = None,
        source: str = "observation",
    ) -> BeliefState:
        result = self.model.infer(evidence=evidence)
        selected = (
            tuple(variables)
            if variables is not None
            else tuple(variable.variable_id for variable in self.model.variables())
        )
        marginals = {
            variable_id: result.marginal(
                variable_id, self.model.variable(variable_id).domain
            )
            for variable_id in selected
        }
        return BeliefState(
            evidence=dict(evidence),
            marginals=marginals,
            version=1,
            updated_at=self._clock(),
            source=source,
        )

    def update(
        self,
        prior: BeliefState,
        observation: Mapping[str, str],
        *,
        source: str = "observation",
    ) -> BeliefState:
        if not isinstance(prior, BeliefState):
            raise TypeError("prior must be BeliefState")
        evidence = dict(prior.evidence)
        for key, value in observation.items():
            resolved = require_id("observation variable", key)
            value = str(value)
            evidence[resolved] = value
        result = self.model.infer(evidence=evidence)
        marginals = {
            variable.variable_id: result.marginal(
                variable.variable_id, variable.domain
            )
            for variable in self.model.variables()
        }
        return BeliefState(
            evidence=evidence,
            marginals=marginals,
            version=prior.version + 1,
            updated_at=self._clock(),
            source=source,
        )


@dataclass(frozen=True, slots=True)
class Preference:
    variable_id: str
    desired: CategoricalDistribution
    weight: float = 1.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "variable_id", require_id("variable_id", self.variable_id))
        weight = _finite_nonnegative("weight", self.weight)
        object.__setattr__(self, "weight", weight)


@dataclass(frozen=True, slots=True)
class EpistemicAction:
    action_id: str
    interventions: Mapping[str, str] = field(default_factory=dict)
    observation_targets: tuple[str, ...] = ()
    base_cost: float = 0.0
    risk: RiskTier = RiskTier.READ_ONLY
    blast_radius: float = 0.0
    reversible: bool = True
    description: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "action_id", require_id("action_id", self.action_id))
        interventions = {
            require_id("intervention variable", key): str(value)
            for key, value in dict(self.interventions).items()
        }
        object.__setattr__(self, "interventions", interventions)
        object.__setattr__(
            self,
            "observation_targets",
            tuple(require_id("observation_target", item) for item in self.observation_targets),
        )
        object.__setattr__(self, "base_cost", _finite_nonnegative("base_cost", self.base_cost))
        if not isinstance(self.risk, RiskTier):
            object.__setattr__(self, "risk", RiskTier(str(self.risk)))
        object.__setattr__(self, "blast_radius", probability("blast_radius", self.blast_radius))
        if not isinstance(self.reversible, bool):
            raise AgentContractError("reversible must be boolean")
        object.__setattr__(
            self,
            "description",
            bounded_text("description", self.description, maximum=4096, allow_empty=True),
        )
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class ActionEvaluation:
    action_id: str
    pragmatic_risk_bits: float
    information_gain_bits: float
    ambiguity_bits: float
    action_cost: float
    safety_penalty: float
    expected_free_energy: float
    expected_utility: float
    predicted_outcomes: Mapping[str, CategoricalDistribution]
    fingerprint: str


class ActiveInferencePlanner:
    """Rank actions by pragmatic fit, epistemic value, ambiguity, and cost."""

    _RISK_COST = {
        RiskTier.READ_ONLY: 0.0,
        RiskTier.REVERSIBLE: 0.05,
        RiskTier.MUTATING: 0.20,
        RiskTier.EXTERNAL: 0.35,
        RiskTier.HIGH_IMPACT: 0.80,
    }

    def __init__(
        self,
        model: StructuralCausalModel,
        preferences: Sequence[Preference] = (),
        *,
        ambiguity_weight: float = 0.25,
        cost_weight: float = 0.10,
        safety_weight: float = 0.35,
    ) -> None:
        self.model = model
        self.preferences = tuple(preferences)
        if any(not isinstance(item, Preference) for item in self.preferences):
            raise TypeError("preferences must contain Preference")
        self.ambiguity_weight = _finite_nonnegative("ambiguity_weight", ambiguity_weight)
        self.cost_weight = _finite_nonnegative("cost_weight", cost_weight)
        self.safety_weight = _finite_nonnegative("safety_weight", safety_weight)

    def evaluate(
        self,
        action: EpistemicAction,
        *,
        current_evidence: Mapping[str, str] | None = None,
    ) -> ActionEvaluation:
        if not isinstance(action, EpistemicAction):
            raise TypeError("action must be EpistemicAction")
        result = self.model.infer(
            evidence=current_evidence,
            interventions=action.interventions,
        )
        predicted: dict[str, CategoricalDistribution] = {}
        pragmatic_risk = 0.0
        for preference in self.preferences:
            variable = self.model.variable(preference.variable_id)
            marginal = result.marginal(variable.variable_id, variable.domain)
            predicted[variable.variable_id] = marginal
            pragmatic_risk += preference.weight * kl_divergence_bits(
                marginal.values, preference.desired.values
            )
        for target in action.observation_targets:
            if target not in predicted:
                variable = self.model.variable(target)
                predicted[target] = result.marginal(target, variable.domain)

        info_gain = self._mutual_information(
            result,
            observed=action.observation_targets,
        )
        ambiguity = sum(
            predicted[target].entropy_bits
            for target in action.observation_targets
            if target in predicted
        )
        intervention_cost = action.base_cost
        for variable_id in action.interventions:
            intervention_cost += self.model.variable(variable_id).intervention_cost
        safety_penalty = (
            self._RISK_COST[action.risk]
            + action.blast_radius * 0.5
            + (0.0 if action.reversible else 0.35)
        )
        efe = (
            pragmatic_risk
            + self.ambiguity_weight * ambiguity
            + self.cost_weight * intervention_cost
            + self.safety_weight * safety_penalty
            - info_gain
        )
        expected_utility = -efe
        fp = stable_fingerprint(
            {
                "action": action.action_id,
                "pragmatic_risk": pragmatic_risk,
                "information_gain": info_gain,
                "ambiguity": ambiguity,
                "cost": intervention_cost,
                "safety": safety_penalty,
                "efe": efe,
                "model": self.model.fingerprint,
            }
        )
        return ActionEvaluation(
            action_id=action.action_id,
            pragmatic_risk_bits=pragmatic_risk,
            information_gain_bits=info_gain,
            ambiguity_bits=ambiguity,
            action_cost=intervention_cost,
            safety_penalty=safety_penalty,
            expected_free_energy=efe,
            expected_utility=expected_utility,
            predicted_outcomes=predicted,
            fingerprint=fp,
        )

    def rank(
        self,
        actions: Sequence[EpistemicAction],
        *,
        current_evidence: Mapping[str, str] | None = None,
        maximum_risk: RiskTier = RiskTier.HIGH_IMPACT,
    ) -> tuple[ActionEvaluation, ...]:
        risk_order = {
            RiskTier.READ_ONLY: 0,
            RiskTier.REVERSIBLE: 1,
            RiskTier.MUTATING: 2,
            RiskTier.EXTERNAL: 3,
            RiskTier.HIGH_IMPACT: 4,
        }
        allowed = [
            action
            for action in actions
            if risk_order[action.risk] <= risk_order[maximum_risk]
        ]
        evaluations = [
            self.evaluate(action, current_evidence=current_evidence)
            for action in allowed
        ]
        evaluations.sort(
            key=lambda item: (
                item.expected_free_energy,
                -item.information_gain_bits,
                item.action_cost,
                item.action_id,
            )
        )
        return tuple(evaluations)

    @staticmethod
    def _mutual_information(
        result: InferenceResult,
        *,
        observed: Sequence[str],
    ) -> float:
        observed = tuple(observed)
        if not observed or not result.states:
            return 0.0
        observation_mass: defaultdict[tuple[tuple[str, str], ...], float] = defaultdict(float)
        hidden_mass: defaultdict[tuple[tuple[str, str], ...], float] = defaultdict(float)
        joint_mass: defaultdict[
            tuple[
                tuple[tuple[str, str], ...],
                tuple[tuple[str, str], ...],
            ],
            float,
        ] = defaultdict(float)
        for state in result.states:
            obs_key = tuple(
                sorted(
                    (key, state.assignment[key])
                    for key in observed
                    if key in state.assignment
                )
            )
            hidden_key = tuple(
                sorted(
                    (key, value)
                    for key, value in state.assignment.items()
                    if key not in observed
                )
            )
            p = state.probability
            observation_mass[obs_key] += p
            hidden_mass[hidden_key] += p
            joint_mass[(obs_key, hidden_key)] += p
        mi = 0.0
        for (obs_key, hidden_key), joint in joint_mass.items():
            if joint <= 0:
                continue
            denominator = observation_mass[obs_key] * hidden_mass[hidden_key]
            if denominator > 0:
                mi += joint * math.log2(joint / denominator)
        return max(0.0, mi)


@dataclass(frozen=True, slots=True)
class TransitionSample:
    sample_id: str
    before: Mapping[str, str]
    interventions: Mapping[str, str]
    after: Mapping[str, str]
    verified: bool
    weight: float = 1.0
    regime: str = "default"
    source_run_id: str | None = None
    observed_at: float = field(default_factory=time.time)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "sample_id", require_id("sample_id", self.sample_id))
        for name in ("before", "interventions", "after"):
            mapping = {
                require_id("variable", key): str(value)
                for key, value in dict(getattr(self, name)).items()
            }
            object.__setattr__(self, name, mapping)
        if not isinstance(self.verified, bool):
            raise AgentContractError("verified must be boolean")
        object.__setattr__(self, "weight", _finite_nonnegative("weight", self.weight))
        object.__setattr__(self, "regime", require_id("regime", self.regime))
        if self.source_run_id is not None:
            object.__setattr__(
                self,
                "source_run_id",
                require_id("source_run_id", self.source_run_id),
            )
        observed = finite_number("observed_at", self.observed_at)
        if observed < 0:
            raise AgentContractError("observed_at must be non-negative")
        object.__setattr__(self, "observed_at", observed)
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class LearnedMechanismProposal:
    proposal_id: str
    mechanism: CausalMechanism
    training_sample_ids: tuple[str, ...]
    heldout_log_loss: float | None
    confidence: float
    accepted_for_review: bool
    reasons: tuple[str, ...]
    fingerprint: str


class MechanismLearner:
    """Fit categorical conditional mechanisms from verified transition samples."""

    def __init__(
        self,
        model: StructuralCausalModel,
        *,
        laplace: float = 1.0,
        minimum_samples: int = 4,
    ) -> None:
        self.model = model
        self.laplace = _finite_nonnegative("laplace", laplace)
        self.minimum_samples = positive_int(
            "minimum_samples", minimum_samples, maximum=1_000_000
        )

    def fit(
        self,
        child_id: str,
        parent_ids: Sequence[str],
        samples: Sequence[TransitionSample],
        *,
        regime: str = "default",
        holdout_fraction: float = 0.2,
    ) -> LearnedMechanismProposal:
        child = self.model.variable(child_id)
        parents = tuple(require_id("parent_id", item) for item in parent_ids)
        for parent in parents:
            self.model.variable(parent)
        verified = [
            sample
            for sample in samples
            if sample.verified
            and sample.regime == regime
            and child_id in sample.after
            and all(parent in sample.before or parent in sample.after for parent in parents)
        ]
        verified.sort(key=lambda sample: (sample.observed_at, sample.sample_id))
        if len(verified) < self.minimum_samples:
            reasons = (
                f"insufficient verified samples: {len(verified)} < {self.minimum_samples}",
            )
            fallback = child.prior or CategoricalDistribution.uniform(child.domain)
            mechanism = CausalMechanism(
                child_id=child_id,
                parent_ids=parents,
                rows=(),
                fallback=fallback,
                status=MechanismStatus.PROVISIONAL,
                confidence=0.0,
                sample_count=len(verified),
                regime=regime,
                provenance=tuple(sample.sample_id for sample in verified),
            )
            pid = stable_id(
                "mechanism-proposal",
                {"child": child_id, "parents": parents, "samples": []},
            )
            return LearnedMechanismProposal(
                pid,
                mechanism,
                tuple(sample.sample_id for sample in verified),
                None,
                0.0,
                False,
                reasons,
                stable_fingerprint(
                    {"proposal": pid, "mechanism": mechanism.fingerprint, "accepted": False}
                ),
            )

        holdout_fraction = probability("holdout_fraction", holdout_fraction)
        holdout_count = (
            max(1, round(len(verified) * holdout_fraction))
            if len(verified) >= 5 and holdout_fraction > 0
            else 0
        )
        train = verified[:-holdout_count] if holdout_count else verified
        holdout = verified[-holdout_count:] if holdout_count else []

        counts: dict[
            tuple[tuple[str, str], ...],
            Counter[str],
        ] = defaultdict(Counter)
        for sample in train:
            key = tuple(
                sorted(
                    (
                        parent,
                        sample.after.get(parent, sample.before.get(parent, "")),
                    )
                    for parent in parents
                )
            )
            child_value = sample.after[child_id]
            counts[key][child_value] += sample.weight

        rows: list[MechanismRow] = []
        for parent_key, row_counts in sorted(counts.items()):
            values = {
                value: row_counts.get(value, 0.0) + self.laplace
                for value in child.domain
            }
            rows.append(
                MechanismRow(
                    parent_values=parent_key,
                    distribution=CategoricalDistribution(values, child.domain),
                )
            )
        aggregate = Counter()
        for sample in train:
            aggregate[sample.after[child_id]] += sample.weight
        fallback = CategoricalDistribution(
            {
                value: aggregate.get(value, 0.0) + self.laplace
                for value in child.domain
            },
            child.domain,
        )
        confidence = min(
            0.99,
            len(train) / (len(train) + 8.0)
            * (1.0 if rows else 0.5),
        )
        mechanism = CausalMechanism(
            child_id=child_id,
            parent_ids=parents,
            rows=tuple(rows),
            fallback=fallback,
            status=MechanismStatus.LEARNED,
            confidence=confidence,
            sample_count=len(train),
            regime=regime,
            provenance=tuple(sample.sample_id for sample in train),
            metadata={"laplace": self.laplace},
        )
        heldout_loss = (
            self._log_loss(mechanism, holdout, child_id, parents)
            if holdout
            else None
        )
        reasons = [
            f"fit from {len(train)} verified samples",
            f"{len(rows)} conditional rows",
        ]
        accepted = confidence >= 0.35
        if heldout_loss is not None:
            reasons.append(f"heldout log-loss={heldout_loss:.6f}")
            if not math.isfinite(heldout_loss) or heldout_loss > 8.0:
                accepted = False
                reasons.append("heldout loss exceeds guard")
        proposal_id = stable_id(
            "mechanism-proposal",
            {
                "child": child_id,
                "parents": parents,
                "mechanism": mechanism.fingerprint,
                "train": [sample.sample_id for sample in train],
                "holdout": [sample.sample_id for sample in holdout],
            },
        )
        return LearnedMechanismProposal(
            proposal_id=proposal_id,
            mechanism=mechanism,
            training_sample_ids=tuple(sample.sample_id for sample in train),
            heldout_log_loss=heldout_loss,
            confidence=confidence,
            accepted_for_review=accepted,
            reasons=tuple(reasons),
            fingerprint=stable_fingerprint(
                {
                    "proposal": proposal_id,
                    "mechanism": mechanism.fingerprint,
                    "heldout_loss": heldout_loss,
                    "accepted": accepted,
                }
            ),
        )

    @staticmethod
    def _log_loss(
        mechanism: CausalMechanism,
        samples: Sequence[TransitionSample],
        child_id: str,
        parent_ids: Sequence[str],
    ) -> float:
        if not samples:
            return 0.0
        weighted_loss = 0.0
        total_weight = 0.0
        for sample in samples:
            assignment = {
                parent: sample.after.get(parent, sample.before.get(parent, ""))
                for parent in parent_ids
            }
            distribution = mechanism.distribution_for(assignment)
            p = max(_EPS, distribution.probability_of(sample.after[child_id]))
            weighted_loss += -math.log(p) * sample.weight
            total_weight += sample.weight
        return weighted_loss / max(_EPS, total_weight)


@dataclass(frozen=True, slots=True)
class EdgeHypothesis:
    hypothesis_id: str
    source_id: str
    target_id: str
    observational_mutual_information_bits: float
    interventional_effect: float
    intervention_support: int
    observation_support: int
    confidence: float
    direction_score: float
    reasons: tuple[str, ...]
    fingerprint: str


class CausalDiscoveryEngine:
    """Conservative pairwise causal-edge scorer using verified transitions."""

    def __init__(self, model: StructuralCausalModel) -> None:
        self.model = model

    def score_edge(
        self,
        source_id: str,
        target_id: str,
        samples: Sequence[TransitionSample],
    ) -> EdgeHypothesis:
        source = self.model.variable(source_id)
        target = self.model.variable(target_id)
        verified = [sample for sample in samples if sample.verified]
        observational_pairs: Counter[tuple[str, str]] = Counter()
        source_counts: Counter[str] = Counter()
        target_counts: Counter[str] = Counter()
        interventions_by_value: defaultdict[str, Counter[str]] = defaultdict(Counter)
        intervention_support = 0

        for sample in verified:
            source_value = sample.before.get(source_id, sample.after.get(source_id))
            target_value = sample.after.get(target_id)
            if target_value is None:
                continue
            if source_id in sample.interventions:
                intervention_value = sample.interventions[source_id]
                interventions_by_value[intervention_value][target_value] += sample.weight
                intervention_support += 1
            elif source_value is not None:
                observational_pairs[(source_value, target_value)] += sample.weight
                source_counts[source_value] += sample.weight
                target_counts[target_value] += sample.weight

        total = sum(observational_pairs.values())
        mi = 0.0
        if total > 0:
            for (source_value, target_value), count in observational_pairs.items():
                pxy = count / total
                px = source_counts[source_value] / total
                py = target_counts[target_value] / total
                if pxy > 0 and px > 0 and py > 0:
                    mi += pxy * math.log2(pxy / (px * py))

        effect = 0.0
        distributions: list[CategoricalDistribution] = []
        for value in source.domain:
            counts = interventions_by_value.get(value)
            if counts and sum(counts.values()) > 0:
                distributions.append(
                    CategoricalDistribution(dict(counts), target.domain)
                )
        for left, right in itertools.combinations(distributions, 2):
            effect = max(effect, js_divergence_bits(left.values, right.values))

        observation_support = int(round(total))
        support_score = 1.0 - math.exp(-(observation_support + 2 * intervention_support) / 20.0)
        confidence = min(
            0.99,
            support_score
            * (0.35 + 0.35 * min(1.0, mi) + 0.30 * min(1.0, effect)),
        )
        direction_score = min(
            1.0,
            effect * 0.70 + min(1.0, mi) * 0.30,
        )
        reasons = [
            f"observational MI={mi:.6f} bits",
            f"interventional JS effect={effect:.6f} bits",
            f"observational support={observation_support}",
            f"intervention support={intervention_support}",
        ]
        if intervention_support == 0:
            reasons.append("no direct intervention support; causality remains weakly identified")
        hypothesis_id = stable_id(
            "edge",
            {
                "source": source_id,
                "target": target_id,
                "mi": mi,
                "effect": effect,
                "intervention_support": intervention_support,
                "observation_support": observation_support,
            },
        )
        return EdgeHypothesis(
            hypothesis_id=hypothesis_id,
            source_id=source_id,
            target_id=target_id,
            observational_mutual_information_bits=max(0.0, mi),
            interventional_effect=max(0.0, effect),
            intervention_support=intervention_support,
            observation_support=observation_support,
            confidence=confidence,
            direction_score=direction_score,
            reasons=tuple(reasons),
            fingerprint=stable_fingerprint(
                {
                    "hypothesis": hypothesis_id,
                    "confidence": confidence,
                    "direction": direction_score,
                }
            ),
        )

    def rank_candidate_edges(
        self,
        samples: Sequence[TransitionSample],
        *,
        minimum_confidence: float = 0.05,
        limit: int = 64,
    ) -> tuple[EdgeHypothesis, ...]:
        minimum_confidence = probability("minimum_confidence", minimum_confidence)
        limit = positive_int("limit", limit, maximum=10_000)
        variables = [item.variable_id for item in self.model.variables()]
        hypotheses: list[EdgeHypothesis] = []
        for source_id in variables:
            for target_id in variables:
                if source_id == target_id:
                    continue
                hypothesis = self.score_edge(source_id, target_id, samples)
                if hypothesis.confidence >= minimum_confidence:
                    hypotheses.append(hypothesis)
        hypotheses.sort(
            key=lambda item: (
                item.confidence,
                item.interventional_effect,
                item.direction_score,
                item.hypothesis_id,
            ),
            reverse=True,
        )
        return tuple(hypotheses[:limit])


@dataclass(frozen=True, slots=True)
class MechanismDrift:
    drift_id: str
    child_id: str
    baseline_version: int
    candidate_version: int
    mean_js_divergence_bits: float
    maximum_js_divergence_bits: float
    changed_rows: int
    drift_detected: bool
    threshold_bits: float
    fingerprint: str


class MechanismDriftDetector:
    def compare(
        self,
        baseline: CausalMechanism,
        candidate: CausalMechanism,
        *,
        threshold_bits: float = 0.10,
    ) -> MechanismDrift:
        if baseline.child_id != candidate.child_id or baseline.parent_ids != candidate.parent_ids:
            raise CausalEpistemicError("mechanisms are not structurally comparable")
        threshold = _finite_nonnegative("threshold_bits", threshold_bits)
        base_rows = {row.key: row.distribution for row in baseline.rows}
        candidate_rows = {row.key: row.distribution for row in candidate.rows}
        keys = set(base_rows) | set(candidate_rows)
        divergences: list[float] = []
        changed = 0
        for key in keys:
            left = base_rows.get(key, baseline.fallback)
            right = candidate_rows.get(key, candidate.fallback)
            js = js_divergence_bits(left.values, right.values)
            divergences.append(js)
            if js >= threshold:
                changed += 1
        if not keys:
            divergences = [
                js_divergence_bits(
                    baseline.fallback.values, candidate.fallback.values
                )
            ]
            changed = int(divergences[0] >= threshold)
        mean_js = sum(divergences) / len(divergences)
        max_js = max(divergences, default=0.0)
        detected = max_js >= threshold or mean_js >= threshold * 0.75
        drift_id = stable_id(
            "drift",
            {
                "child": baseline.child_id,
                "baseline": baseline.fingerprint,
                "candidate": candidate.fingerprint,
            },
        )
        return MechanismDrift(
            drift_id=drift_id,
            child_id=baseline.child_id,
            baseline_version=baseline.version,
            candidate_version=candidate.version,
            mean_js_divergence_bits=mean_js,
            maximum_js_divergence_bits=max_js,
            changed_rows=changed,
            drift_detected=detected,
            threshold_bits=threshold,
            fingerprint=stable_fingerprint(
                {
                    "drift": drift_id,
                    "mean": mean_js,
                    "max": max_js,
                    "changed": changed,
                    "detected": detected,
                }
            ),
        )


@dataclass(frozen=True, slots=True)
class ExperimentCandidate:
    experiment_id: str
    purpose: ExperimentPurpose
    action: EpistemicAction
    target_hypothesis_ids: tuple[str, ...]
    expected_information_gain_bits: float
    expected_cost: float
    safety_penalty: float
    score: float
    rationale: tuple[str, ...]
    fingerprint: str


class CausalExperimentPlanner:
    """Rank safe discriminating experiments for uncertain causal structure."""

    _RISK = {
        RiskTier.READ_ONLY: 0.00,
        RiskTier.REVERSIBLE: 0.10,
        RiskTier.MUTATING: 0.30,
        RiskTier.EXTERNAL: 0.50,
        RiskTier.HIGH_IMPACT: 1.00,
    }

    def __init__(self, model: StructuralCausalModel) -> None:
        self.model = model

    def propose_for_edges(
        self,
        hypotheses: Sequence[EdgeHypothesis],
        *,
        maximum_risk: RiskTier = RiskTier.REVERSIBLE,
        limit: int = 12,
    ) -> tuple[ExperimentCandidate, ...]:
        limit = positive_int("limit", limit, maximum=1000)
        risk_order = {
            RiskTier.READ_ONLY: 0,
            RiskTier.REVERSIBLE: 1,
            RiskTier.MUTATING: 2,
            RiskTier.EXTERNAL: 3,
            RiskTier.HIGH_IMPACT: 4,
        }
        candidates: list[ExperimentCandidate] = []
        for hypothesis in hypotheses:
            variable = self.model.variable(hypothesis.source_id)
            if not variable.manipulable:
                continue
            if risk_order[variable.risk] > risk_order[maximum_risk]:
                continue
            uncertainty = 1.0 - hypothesis.confidence
            for value in variable.domain:
                action = EpistemicAction(
                    action_id=stable_id(
                        "experiment-action",
                        {
                            "source": hypothesis.source_id,
                            "value": value,
                            "target": hypothesis.target_id,
                        },
                    ),
                    interventions={hypothesis.source_id: value},
                    observation_targets=(hypothesis.target_id,),
                    base_cost=variable.intervention_cost,
                    risk=variable.risk,
                    blast_radius=0.1 if variable.risk is RiskTier.READ_ONLY else 0.25,
                    reversible=variable.risk in {
                        RiskTier.READ_ONLY,
                        RiskTier.REVERSIBLE,
                    },
                    description=f"Intervene on {hypothesis.source_id}={value} and observe {hypothesis.target_id}",
                )
                predicted = self.model.marginal(
                    hypothesis.target_id,
                    interventions=action.interventions,
                )
                information = predicted.entropy_bits * uncertainty
                safety = self._RISK[action.risk] + action.blast_radius * 0.25
                cost = action.base_cost + variable.intervention_cost
                score = information - 0.15 * cost - 0.50 * safety
                experiment_id = stable_id(
                    "experiment",
                    {
                        "hypothesis": hypothesis.hypothesis_id,
                        "action": action.action_id,
                        "score": score,
                    },
                )
                candidates.append(
                    ExperimentCandidate(
                        experiment_id=experiment_id,
                        purpose=ExperimentPurpose.DISCRIMINATE_EDGE,
                        action=action,
                        target_hypothesis_ids=(hypothesis.hypothesis_id,),
                        expected_information_gain_bits=information,
                        expected_cost=cost,
                        safety_penalty=safety,
                        score=score,
                        rationale=(
                            f"edge confidence={hypothesis.confidence:.3f}",
                            f"predicted target entropy={predicted.entropy_bits:.3f} bits",
                            f"intervention value={value}",
                        ),
                        fingerprint=stable_fingerprint(
                            {
                                "experiment": experiment_id,
                                "information": information,
                                "cost": cost,
                                "safety": safety,
                                "score": score,
                            }
                        ),
                    )
                )
        candidates.sort(
            key=lambda item: (
                item.score,
                item.expected_information_gain_bits,
                -item.expected_cost,
                item.experiment_id,
            ),
            reverse=True,
        )
        return tuple(candidates[:limit])


@dataclass(frozen=True, slots=True)
class SimulationRecord:
    simulation_id: str
    action_id: str
    model_fingerprint: str
    predicted_states: tuple[WeightedState, ...]
    created_at: float
    query_kind: QueryKind
    is_simulation: bool = True
    note: str = "Simulation only; never promote directly to evidence."

    def __post_init__(self) -> None:
        object.__setattr__(self, "simulation_id", require_id("simulation_id", self.simulation_id))
        object.__setattr__(self, "action_id", require_id("action_id", self.action_id))
        if not isinstance(self.is_simulation, bool) or not self.is_simulation:
            raise AgentContractError("SimulationRecord must remain explicitly simulated")
        created = finite_number("created_at", self.created_at)
        if created < 0:
            raise AgentContractError("created_at must be non-negative")
        object.__setattr__(self, "created_at", created)
        if not isinstance(self.query_kind, QueryKind):
            object.__setattr__(self, "query_kind", QueryKind(str(self.query_kind)))
        object.__setattr__(
            self,
            "note",
            bounded_text("note", self.note, maximum=4096),
        )


@dataclass(frozen=True, slots=True)
class DecisionRegretAudit:
    audit_id: str
    chosen_action_id: str
    chosen_expected_utility: float
    best_alternative_id: str | None
    best_alternative_utility: float | None
    counterfactual_regret: float
    evaluations: tuple[ActionEvaluation, ...]
    fingerprint: str


class CausalEpistemicKernel:
    """High-level facade for causal belief control and safe learning proposals."""

    def __init__(
        self,
        model: StructuralCausalModel | None = None,
        *,
        preferences: Sequence[Preference] = (),
        clock: Callable[[], float] = time.time,
        transition_limit: int = 50_000,
    ) -> None:
        self.model = model or StructuralCausalModel()
        self.planner = ActiveInferencePlanner(self.model, preferences)
        self.discovery = CausalDiscoveryEngine(self.model)
        self.experiments = CausalExperimentPlanner(self.model)
        self.drift = MechanismDriftDetector()
        self._clock = clock
        self._transitions: list[TransitionSample] = []
        self._simulations: list[SimulationRecord] = []
        self._proposal_history: list[LearnedMechanismProposal] = []
        self._transition_limit = positive_int(
            "transition_limit", transition_limit, maximum=10_000_000
        )
        self._lock = threading.RLock()

    def record_transition(self, sample: TransitionSample) -> None:
        if not isinstance(sample, TransitionSample):
            raise TypeError("sample must be TransitionSample")
        with self._lock:
            if any(existing.sample_id == sample.sample_id for existing in self._transitions):
                return
            self._transitions.append(sample)
            if len(self._transitions) > self._transition_limit:
                self._transitions = self._transitions[-self._transition_limit :]

    def transitions(
        self,
        *,
        verified_only: bool = False,
        regime: str | None = None,
    ) -> tuple[TransitionSample, ...]:
        with self._lock:
            values = tuple(self._transitions)
        if verified_only:
            values = tuple(item for item in values if item.verified)
        if regime is not None:
            regime = require_id("regime", regime)
            values = tuple(item for item in values if item.regime == regime)
        return values

    def recommend(
        self,
        actions: Sequence[EpistemicAction],
        *,
        evidence: Mapping[str, str] | None = None,
        maximum_risk: RiskTier = RiskTier.HIGH_IMPACT,
    ) -> tuple[ActionEvaluation, ...]:
        return self.planner.rank(
            actions,
            current_evidence=evidence,
            maximum_risk=maximum_risk,
        )

    def simulate(
        self,
        action: EpistemicAction,
        *,
        evidence: Mapping[str, str] | None = None,
    ) -> SimulationRecord:
        result = self.model.infer(
            evidence=evidence,
            interventions=action.interventions,
        )
        record = SimulationRecord(
            simulation_id=stable_id(
                "simulation",
                {
                    "action": action.action_id,
                    "model": self.model.fingerprint,
                    "evidence": dict(evidence or {}),
                    "result": result.fingerprint,
                    "sequence": len(self._simulations),
                },
            ),
            action_id=action.action_id,
            model_fingerprint=self.model.fingerprint,
            predicted_states=result.states,
            created_at=self._clock(),
            query_kind=QueryKind.INTERVENTIONAL,
        )
        with self._lock:
            self._simulations.append(record)
            if len(self._simulations) > 10_000:
                self._simulations = self._simulations[-10_000:]
        return record

    def counterfactual(
        self,
        target_id: str,
        *,
        factual_evidence: Mapping[str, str],
        intervention: Mapping[str, str],
    ) -> CounterfactualEstimate:
        return self.model.counterfactual(
            target_id,
            factual_evidence=factual_evidence,
            intervention=intervention,
        )

    def learn_mechanism(
        self,
        child_id: str,
        parent_ids: Sequence[str],
        *,
        regime: str = "default",
        minimum_samples: int = 4,
    ) -> LearnedMechanismProposal:
        learner = MechanismLearner(
            self.model, minimum_samples=minimum_samples
        )
        proposal = learner.fit(
            child_id,
            parent_ids,
            self.transitions(verified_only=True, regime=regime),
            regime=regime,
        )
        with self._lock:
            self._proposal_history.append(proposal)
        return proposal

    def promote_mechanism(
        self,
        proposal: LearnedMechanismProposal,
        *,
        minimum_confidence: float = 0.50,
        maximum_heldout_log_loss: float = 4.0,
        drift_guard_bits: float = 0.50,
    ) -> CausalMechanism:
        if not isinstance(proposal, LearnedMechanismProposal):
            raise TypeError("proposal must be LearnedMechanismProposal")
        minimum_confidence = probability("minimum_confidence", minimum_confidence)
        max_loss = _finite_nonnegative(
            "maximum_heldout_log_loss", maximum_heldout_log_loss
        )
        if not proposal.accepted_for_review:
            raise CausalEpistemicError("proposal did not pass learner review gate")
        if proposal.confidence < minimum_confidence:
            raise CausalEpistemicError("proposal confidence below promotion threshold")
        if (
            proposal.heldout_log_loss is not None
            and proposal.heldout_log_loss > max_loss
        ):
            raise CausalEpistemicError("proposal heldout loss exceeds promotion threshold")
        current = self.model.mechanism(
            proposal.mechanism.child_id,
            regime=proposal.mechanism.regime,
        )
        if current is not None:
            drift = self.drift.compare(
                current,
                proposal.mechanism,
                threshold_bits=drift_guard_bits,
            )
            if (
                drift.drift_detected
                and proposal.confidence < max(0.80, minimum_confidence)
            ):
                raise CausalEpistemicError(
                    "large mechanism drift requires high-confidence proposal"
                )
        promoted = replace(
            proposal.mechanism,
            status=MechanismStatus.LEARNED,
            version=(current.version + 1 if current else proposal.mechanism.version),
        )
        self.model.set_mechanism(promoted)
        return promoted

    def audit_decision(
        self,
        chosen_action_id: str,
        evaluations: Sequence[ActionEvaluation],
    ) -> DecisionRegretAudit:
        chosen_action_id = require_id("chosen_action_id", chosen_action_id)
        values = tuple(evaluations)
        chosen = next(
            (item for item in values if item.action_id == chosen_action_id),
            None,
        )
        if chosen is None:
            raise CausalEpistemicError("chosen action absent from evaluations")
        alternatives = [item for item in values if item.action_id != chosen_action_id]
        best = max(
            alternatives,
            key=lambda item: (item.expected_utility, item.action_id),
            default=None,
        )
        regret = (
            max(0.0, best.expected_utility - chosen.expected_utility)
            if best is not None
            else 0.0
        )
        audit_id = stable_id(
            "decision-audit",
            {
                "chosen": chosen.action_id,
                "chosen_utility": chosen.expected_utility,
                "best": best.action_id if best else None,
                "best_utility": best.expected_utility if best else None,
                "model": self.model.fingerprint,
            },
        )
        return DecisionRegretAudit(
            audit_id=audit_id,
            chosen_action_id=chosen.action_id,
            chosen_expected_utility=chosen.expected_utility,
            best_alternative_id=best.action_id if best else None,
            best_alternative_utility=best.expected_utility if best else None,
            counterfactual_regret=regret,
            evaluations=values,
            fingerprint=stable_fingerprint(
                {
                    "audit": audit_id,
                    "regret": regret,
                    "evaluations": [item.fingerprint for item in values],
                }
            ),
        )

    def discover_edges(
        self,
        *,
        minimum_confidence: float = 0.05,
        limit: int = 64,
    ) -> tuple[EdgeHypothesis, ...]:
        return self.discovery.rank_candidate_edges(
            self.transitions(verified_only=True),
            minimum_confidence=minimum_confidence,
            limit=limit,
        )

    def propose_experiments(
        self,
        *,
        maximum_risk: RiskTier = RiskTier.REVERSIBLE,
        limit: int = 12,
    ) -> tuple[ExperimentCandidate, ...]:
        hypotheses = self.discover_edges(
            minimum_confidence=0.05, limit=max(limit * 4, 16)
        )
        return self.experiments.propose_for_edges(
            hypotheses, maximum_risk=maximum_risk, limit=limit
        )

    @property
    def fingerprint(self) -> str:
        with self._lock:
            transitions = tuple(self._transitions)
            simulations = tuple(self._simulations)
            proposals = tuple(self._proposal_history)
        return stable_fingerprint(
            {
                "model": self.model.fingerprint,
                "transitions": [
                    {
                        "id": item.sample_id,
                        "verified": item.verified,
                        "weight": item.weight,
                        "regime": item.regime,
                    }
                    for item in transitions
                ],
                "simulations": [
                    {
                        "id": item.simulation_id,
                        "model": item.model_fingerprint,
                    }
                    for item in simulations
                ],
                "proposals": [
                    {
                        "id": item.proposal_id,
                        "fingerprint": item.fingerprint,
                    }
                    for item in proposals
                ],
            }
        )

    def summary(self) -> dict[str, Any]:
        with self._lock:
            transitions = tuple(self._transitions)
            simulations = tuple(self._simulations)
            proposals = tuple(self._proposal_history)
        return {
            "variables": len(self.model.variables()),
            "verified_transitions": sum(1 for item in transitions if item.verified),
            "transitions": len(transitions),
            "simulations": len(simulations),
            "mechanism_proposals": len(proposals),
            "active_regime": self.model.active_regime,
            "model_fingerprint": self.model.fingerprint,
            "kernel_fingerprint": self.fingerprint,
        }
