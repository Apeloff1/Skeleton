"""Sparse factor-graph inference for Jeeves causal models.

``StructuralCausalModel.infer`` deliberately began as transparent bounded joint
enumeration.  That is useful as a reference implementation but scales
exponentially with all variables, even when evidence renders most of them
irrelevant.  This module adds a production exact-inference path based on
classical variable elimination over sparse categorical factors.

Features:

* compile SCM mechanisms into Bayesian-network factors;
* causal intervention surgery: ``do(X=x)`` replaces X's mechanism with a delta
  factor and removes its incoming causal dependence;
* early evidence conditioning;
* sparse factor multiplication and marginalization;
* min-fill/min-degree elimination-order heuristics;
* ancestor pruning so irrelevant graph regions are never materialized;
* intermediate factor-size guards and complexity diagnostics;
* exact marginals, conditional evidence likelihoods, and small joint queries;
* deterministic fingerprints suitable for replay/evaluation.

This remains exact discrete inference.  When induced width is still too large,
the caller receives an explicit complexity failure rather than an silently
wrong approximation.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping, Sequence

from .causal_epistemics import (
    CategoricalDistribution,
    CausalEpistemicError,
    StructuralCausalModel,
)
from .types import (
    AgentContractError,
    finite_number,
    positive_int,
    require_id,
    stable_fingerprint,
)


class FactorInferenceError(RuntimeError):
    pass


class FactorComplexityExceeded(FactorInferenceError):
    pass


class EliminationHeuristic(str, Enum):
    MIN_FILL = "min_fill"
    MIN_DEGREE = "min_degree"
    DECLARED = "declared"


@dataclass(frozen=True, slots=True)
class Factor:
    """Sparse non-negative factor over ordered categorical variables."""

    variables: tuple[str, ...]
    domains: Mapping[str, tuple[str, ...]]
    values: Mapping[tuple[str, ...], float]

    def __post_init__(self) -> None:
        variables = tuple(require_id("factor variable", item) for item in self.variables)
        if len(variables) != len(set(variables)):
            raise AgentContractError("factor variables must be unique")
        domains = {require_id("domain variable", key): tuple(str(value) for value in vals) for key, vals in dict(self.domains).items()}
        if set(domains) != set(variables):
            raise AgentContractError("factor domains must match variables exactly")
        for variable in variables:
            if not domains[variable] or len(domains[variable]) != len(set(domains[variable])):
                raise AgentContractError("factor domain must be non-empty and unique")
        clean: dict[tuple[str, ...], float] = {}
        for assignment, raw in dict(self.values).items():
            key = tuple(str(value) for value in assignment)
            if len(key) != len(variables):
                raise AgentContractError("factor assignment arity mismatch")
            for variable, value in zip(variables, key):
                if value not in domains[variable]:
                    raise AgentContractError("factor assignment outside domain")
            number = finite_number("factor value", raw)
            if number < 0:
                raise AgentContractError("factor values must be non-negative")
            if number > 0:
                clean[key] = number
        object.__setattr__(self, "variables", variables)
        object.__setattr__(self, "domains", domains)
        object.__setattr__(self, "values", clean)

    @classmethod
    def scalar(cls, value: float) -> "Factor":
        number = finite_number("scalar factor", value)
        if number < 0:
            raise AgentContractError("scalar factor must be non-negative")
        return cls((), {}, {(): number} if number > 0 else {})

    @property
    def entry_count(self) -> int:
        return len(self.values)

    @property
    def dense_capacity(self) -> int:
        capacity = 1
        for variable in self.variables:
            capacity *= len(self.domains[variable])
        return capacity

    @property
    def sparsity(self) -> float:
        if self.dense_capacity <= 0:
            return 0.0
        return 1.0 - self.entry_count / self.dense_capacity

    @property
    def total(self) -> float:
        return sum(self.values.values())

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint({
            "variables": self.variables,
            "domains": {key: self.domains[key] for key in self.variables},
            "values": [(key, self.values[key]) for key in sorted(self.values)],
        })

    def contains(self, variable: str) -> bool:
        return variable in self.variables

    def condition(self, evidence: Mapping[str, str]) -> "Factor":
        relevant = {key: value for key, value in evidence.items() if key in self.variables}
        if not relevant:
            return self
        for variable, value in relevant.items():
            if value not in self.domains[variable]:
                return Factor.scalar(0.0)
        keep_variables = tuple(variable for variable in self.variables if variable not in relevant)
        keep_domains = {variable: self.domains[variable] for variable in keep_variables}
        indexes = {variable: self.variables.index(variable) for variable in self.variables}
        keep_indexes = [indexes[variable] for variable in keep_variables]
        output: dict[tuple[str, ...], float] = {}
        for assignment, weight in self.values.items():
            if any(assignment[indexes[variable]] != value for variable, value in relevant.items()):
                continue
            key = tuple(assignment[index] for index in keep_indexes)
            output[key] = output.get(key, 0.0) + weight
        return Factor(keep_variables, keep_domains, output)

    def sum_out(self, variable: str) -> "Factor":
        variable = require_id("variable", variable)
        if variable not in self.variables:
            return self
        index = self.variables.index(variable)
        keep_variables = tuple(item for item in self.variables if item != variable)
        keep_domains = {item: self.domains[item] for item in keep_variables}
        output: dict[tuple[str, ...], float] = {}
        for assignment, weight in self.values.items():
            key = assignment[:index] + assignment[index + 1 :]
            output[key] = output.get(key, 0.0) + weight
        return Factor(keep_variables, keep_domains, output)

    def normalize(self) -> "Factor":
        total = self.total
        if total <= 0:
            raise FactorInferenceError("cannot normalize zero-mass factor")
        return Factor(self.variables, self.domains, {key: value / total for key, value in self.values.items()})

    def reorder(self, variables: Sequence[str]) -> "Factor":
        requested = tuple(variables)
        if set(requested) != set(self.variables) or len(requested) != len(self.variables):
            raise FactorInferenceError("reorder must contain identical factor variables")
        indexes = [self.variables.index(variable) for variable in requested]
        return Factor(
            requested,
            {variable: self.domains[variable] for variable in requested},
            {tuple(assignment[index] for index in indexes): weight for assignment, weight in self.values.items()},
        )

    def multiply(self, other: "Factor", *, max_entries: int | None = None) -> "Factor":
        if not isinstance(other, Factor):
            raise TypeError("other must be Factor")
        if not self.variables:
            scalar = self.values.get((), 0.0)
            return Factor(other.variables, other.domains, {key: scalar * value for key, value in other.values.items()})
        if not other.variables:
            scalar = other.values.get((), 0.0)
            return Factor(self.variables, self.domains, {key: scalar * value for key, value in self.values.items()})
        variables = self.variables + tuple(variable for variable in other.variables if variable not in self.variables)
        domains: dict[str, tuple[str, ...]] = dict(self.domains)
        for variable in other.variables:
            if variable in domains and domains[variable] != other.domains[variable]:
                raise FactorInferenceError(f"domain mismatch for {variable}")
            domains[variable] = other.domains[variable]
        shared = tuple(variable for variable in self.variables if variable in other.variables)
        self_index = {variable: self.variables.index(variable) for variable in self.variables}
        other_index = {variable: other.variables.index(variable) for variable in other.variables}
        output_index_self = [self_index[variable] if variable in self_index else None for variable in variables]
        output_index_other = [other_index[variable] if variable in other_index else None for variable in variables]

        # Hash-join on shared assignments instead of dense Cartesian product.
        if shared:
            bucket: dict[tuple[str, ...], list[tuple[tuple[str, ...], float]]] = {}
            shared_other_idx = [other_index[variable] for variable in shared]
            for assignment, weight in other.values.items():
                key = tuple(assignment[index] for index in shared_other_idx)
                bucket.setdefault(key, []).append((assignment, weight))
            shared_self_idx = [self_index[variable] for variable in shared]
            iterator = []
            for left_assignment, left_weight in self.values.items():
                shared_key = tuple(left_assignment[index] for index in shared_self_idx)
                for right_assignment, right_weight in bucket.get(shared_key, ()):
                    iterator.append((left_assignment, left_weight, right_assignment, right_weight))
        else:
            iterator = [
                (left_assignment, left_weight, right_assignment, right_weight)
                for left_assignment, left_weight in self.values.items()
                for right_assignment, right_weight in other.values.items()
            ]
        if max_entries is not None and len(iterator) > max_entries:
            raise FactorComplexityExceeded(f"factor multiplication would produce > {max_entries} sparse entries")
        output: dict[tuple[str, ...], float] = {}
        for left_assignment, left_weight, right_assignment, right_weight in iterator:
            key_values = []
            for variable, left_idx, right_idx in zip(variables, output_index_self, output_index_other):
                if left_idx is not None:
                    key_values.append(left_assignment[left_idx])
                elif right_idx is not None:
                    key_values.append(right_assignment[right_idx])
                else:  # pragma: no cover - construction invariant
                    raise FactorInferenceError(f"missing variable {variable} during multiplication")
            weight = left_weight * right_weight
            if weight > 0:
                key = tuple(key_values)
                output[key] = output.get(key, 0.0) + weight
        return Factor(variables, domains, output)


@dataclass(frozen=True, slots=True)
class EliminationStep:
    variable: str
    input_factor_count: int
    input_sparse_entries: int
    product_variables: tuple[str, ...]
    product_entries: int
    output_entries: int
    dense_capacity: int
    fingerprint: str


@dataclass(frozen=True, slots=True)
class InferenceDiagnostics:
    query_variables: tuple[str, ...]
    evidence_variables: tuple[str, ...]
    intervention_variables: tuple[str, ...]
    relevant_variables: tuple[str, ...]
    pruned_variables: tuple[str, ...]
    elimination_order: tuple[str, ...]
    steps: tuple[EliminationStep, ...]
    maximum_sparse_entries: int
    maximum_dense_capacity: int
    initial_factor_count: int
    final_factor_entries: int
    fingerprint: str


@dataclass(frozen=True, slots=True)
class FactorInferenceResult:
    factor: Factor
    normalization_constant: float
    diagnostics: InferenceDiagnostics
    query_fingerprint: str

    def marginal(self, variable_id: str) -> CategoricalDistribution:
        variable_id = require_id("variable_id", variable_id)
        if variable_id not in self.factor.variables:
            raise FactorInferenceError(f"{variable_id} is not in result factor")
        reduced = self.factor
        for other in tuple(reduced.variables):
            if other != variable_id:
                reduced = reduced.sum_out(other)
        reduced = reduced.normalize()
        domain = reduced.domains[variable_id]
        values = {value: reduced.values.get((value,), 0.0) for value in domain}
        return CategoricalDistribution(values, domain)


@dataclass(frozen=True, slots=True)
class InferencePolicy:
    heuristic: EliminationHeuristic = EliminationHeuristic.MIN_FILL
    maximum_sparse_entries: int = 250_000
    maximum_dense_capacity: int = 5_000_000
    normalize_intermediate_products: bool = False
    ancestor_pruning: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.heuristic, EliminationHeuristic):
            object.__setattr__(self, "heuristic", EliminationHeuristic(str(self.heuristic)))
        object.__setattr__(self, "maximum_sparse_entries", positive_int("maximum_sparse_entries", self.maximum_sparse_entries, maximum=100_000_000))
        object.__setattr__(self, "maximum_dense_capacity", positive_int("maximum_dense_capacity", self.maximum_dense_capacity, maximum=1_000_000_000))


class FactorCompiler:
    def __init__(self, model: StructuralCausalModel) -> None:
        self.model = model

    def relevant_variables(
        self,
        query_variables: Sequence[str],
        evidence: Mapping[str, str],
        interventions: Mapping[str, str],
        *,
        regime: str | None = None,
    ) -> tuple[str, ...]:
        seeds = set(query_variables) | set(evidence) | set(interventions)
        closure = set(seeds)
        queue = list(seeds)
        while queue:
            current = queue.pop(0)
            if current in interventions:
                # Incoming causal edges are cut by do().
                continue
            for parent in self.model.parents(current, regime=regime):
                if parent not in closure:
                    closure.add(parent)
                    queue.append(parent)
        return tuple(sorted(closure))

    def compile(
        self,
        *,
        variables: Sequence[str],
        evidence: Mapping[str, str],
        interventions: Mapping[str, str],
        regime: str | None = None,
    ) -> tuple[Factor, ...]:
        wanted = set(variables)
        factors: list[Factor] = []
        for variable_id in variables:
            variable = self.model.variable(variable_id)
            if variable_id in interventions:
                value = interventions[variable_id]
                factor = Factor(
                    (variable_id,),
                    {variable_id: variable.domain},
                    {(candidate,): 1.0 if candidate == value else 0.0 for candidate in variable.domain},
                )
            else:
                mechanism = self.model.mechanism(variable_id, regime=regime)
                if mechanism is None:
                    prior = variable.prior or CategoricalDistribution.uniform(variable.domain)
                    factor = Factor(
                        (variable_id,),
                        {variable_id: variable.domain},
                        {(value,): prior.values[value] for value in variable.domain},
                    )
                else:
                    parents = tuple(parent for parent in mechanism.parent_ids if parent in wanted)
                    # Relevant-variable closure should always contain mechanism
                    # parents unless do() cut the child's incoming edges.
                    if parents != mechanism.parent_ids:
                        missing = set(mechanism.parent_ids) - wanted
                        raise FactorInferenceError(f"compiler missing causal parents for {variable_id}: {sorted(missing)}")
                    scope = parents + (variable_id,)
                    domains = {parent: self.model.variable(parent).domain for parent in parents}
                    domains[variable_id] = variable.domain
                    values: dict[tuple[str, ...], float] = {}
                    parent_domains = [domains[parent] for parent in parents]
                    parent_assignments = itertools.product(*parent_domains) if parent_domains else [()]
                    for parent_values in parent_assignments:
                        assignment = dict(zip(parents, parent_values))
                        distribution = mechanism.distribution_for(assignment)
                        for child_value in variable.domain:
                            p = distribution.values[child_value]
                            if p > 0:
                                values[tuple(parent_values) + (child_value,)] = p
                    factor = Factor(scope, domains, values)
            factor = factor.condition(evidence)
            factors.append(factor)
        return tuple(factors)


class EliminationOrderer:
    def __init__(self, heuristic: EliminationHeuristic) -> None:
        self.heuristic = heuristic

    def order(
        self,
        hidden_variables: Sequence[str],
        factors: Sequence[Factor],
    ) -> tuple[str, ...]:
        remaining = set(hidden_variables)
        scopes = [set(factor.variables) for factor in factors if factor.variables]
        output: list[str] = []
        while remaining:
            if self.heuristic is EliminationHeuristic.DECLARED:
                chosen = min(remaining)
            else:
                scores = []
                for variable in remaining:
                    neighbors: set[str] = set()
                    touching = [scope for scope in scopes if variable in scope]
                    for scope in touching:
                        neighbors.update(scope - {variable})
                    if self.heuristic is EliminationHeuristic.MIN_DEGREE:
                        score = (len(neighbors), variable)
                    else:
                        existing_edges = set()
                        for scope in scopes:
                            for left, right in itertools.combinations(sorted(scope), 2):
                                existing_edges.add((left, right))
                        fill = 0
                        for left, right in itertools.combinations(sorted(neighbors), 2):
                            if (left, right) not in existing_edges:
                                fill += 1
                        score = (fill, len(neighbors), variable)
                    scores.append((score, variable))
                chosen = min(scores, key=lambda item: item[0])[1]
            output.append(chosen)
            touching = [scope for scope in scopes if chosen in scope]
            untouched = [scope for scope in scopes if chosen not in scope]
            merged = set().union(*touching) - {chosen} if touching else set()
            scopes = untouched + ([merged] if merged else [])
            remaining.remove(chosen)
        return tuple(output)


class VariableEliminationEngine:
    def __init__(
        self,
        model: StructuralCausalModel,
        *,
        policy: InferencePolicy | None = None,
    ) -> None:
        self.model = model
        self.policy = policy or InferencePolicy()
        self.compiler = FactorCompiler(model)

    def query(
        self,
        query_variables: Sequence[str],
        *,
        evidence: Mapping[str, str] | None = None,
        interventions: Mapping[str, str] | None = None,
        regime: str | None = None,
    ) -> FactorInferenceResult:
        query_variables = tuple(require_id("query variable", item) for item in query_variables)
        if not query_variables or len(query_variables) != len(set(query_variables)):
            raise FactorInferenceError("query variables must be unique and non-empty")
        evidence = {require_id("evidence variable", key): str(value) for key, value in dict(evidence or {}).items()}
        interventions = {require_id("intervention variable", key): str(value) for key, value in dict(interventions or {}).items()}
        for variable_id in set(query_variables) | set(evidence) | set(interventions):
            variable = self.model.variable(variable_id)
            value = evidence.get(variable_id, interventions.get(variable_id))
            if value is not None and value not in variable.domain:
                raise FactorInferenceError(f"value {value!r} outside domain for {variable_id}")
        if set(evidence) & set(interventions):
            for variable_id in set(evidence) & set(interventions):
                if evidence[variable_id] != interventions[variable_id]:
                    raise FactorInferenceError("evidence contradicts intervention")
        all_variables = {variable.variable_id for variable in self.model.variables()}
        if self.policy.ancestor_pruning:
            relevant = set(self.compiler.relevant_variables(query_variables, evidence, interventions, regime=regime))
        else:
            relevant = set(all_variables)
        # Evidence variables must be included so their likelihood is represented.
        relevant.update(evidence)
        relevant.update(interventions)
        pruned = tuple(sorted(all_variables - relevant))
        relevant_tuple = tuple(sorted(relevant))
        factors = list(self.compiler.compile(variables=relevant_tuple, evidence=evidence, interventions=interventions, regime=regime))
        initial_factor_count = len(factors)
        hidden = tuple(sorted(relevant - set(query_variables) - set(evidence)))
        order = EliminationOrderer(self.policy.heuristic).order(hidden, factors)
        steps: list[EliminationStep] = []
        max_sparse = max((factor.entry_count for factor in factors), default=0)
        max_dense = max((factor.dense_capacity for factor in factors), default=0)
        for variable in order:
            touching = [factor for factor in factors if factor.contains(variable)]
            if not touching:
                continue
            factors = [factor for factor in factors if not factor.contains(variable)]
            product = touching[0]
            input_entries = sum(factor.entry_count for factor in touching)
            for factor in touching[1:]:
                product = product.multiply(factor, max_entries=self.policy.maximum_sparse_entries)
                self._guard(product)
            if self.policy.normalize_intermediate_products and product.total > 0:
                product = product.normalize()
            reduced = product.sum_out(variable)
            self._guard(reduced)
            factors.append(reduced)
            max_sparse = max(max_sparse, product.entry_count, reduced.entry_count)
            max_dense = max(max_dense, product.dense_capacity, reduced.dense_capacity)
            steps.append(
                EliminationStep(
                    variable=variable,
                    input_factor_count=len(touching),
                    input_sparse_entries=input_entries,
                    product_variables=product.variables,
                    product_entries=product.entry_count,
                    output_entries=reduced.entry_count,
                    dense_capacity=product.dense_capacity,
                    fingerprint=stable_fingerprint({
                        "variable": variable,
                        "inputs": [factor.fingerprint for factor in touching],
                        "product": product.fingerprint,
                        "reduced": reduced.fingerprint,
                    }),
                )
            )
        if not factors:
            final = Factor.scalar(1.0)
        else:
            final = factors[0]
            for factor in factors[1:]:
                final = final.multiply(factor, max_entries=self.policy.maximum_sparse_entries)
                self._guard(final)
        # Sum any residual non-query variables (can happen for evidence-conditioned
        # variables removed from factors or disconnected scalar components).
        for variable in tuple(final.variables):
            if variable not in query_variables:
                final = final.sum_out(variable)
        normalization = final.total
        if normalization <= 0:
            raise FactorInferenceError("query has zero probability under the causal model")
        normalized = final.normalize()
        desired_order = tuple(variable for variable in query_variables if variable in normalized.variables)
        if set(desired_order) == set(normalized.variables) and desired_order != normalized.variables:
            normalized = normalized.reorder(desired_order)
        diagnostics = InferenceDiagnostics(
            query_variables=query_variables,
            evidence_variables=tuple(sorted(evidence)),
            intervention_variables=tuple(sorted(interventions)),
            relevant_variables=relevant_tuple,
            pruned_variables=pruned,
            elimination_order=order,
            steps=tuple(steps),
            maximum_sparse_entries=max_sparse,
            maximum_dense_capacity=max_dense,
            initial_factor_count=initial_factor_count,
            final_factor_entries=normalized.entry_count,
            fingerprint=stable_fingerprint({
                "query": query_variables,
                "evidence": evidence,
                "interventions": interventions,
                "relevant": relevant_tuple,
                "pruned": pruned,
                "order": order,
                "steps": [step.fingerprint for step in steps],
            }),
        )
        query_fp = stable_fingerprint({
            "model": self.model.fingerprint,
            "query": query_variables,
            "evidence": evidence,
            "interventions": interventions,
            "result": normalized.fingerprint,
            "diagnostics": diagnostics.fingerprint,
        })
        return FactorInferenceResult(normalized, normalization, diagnostics, query_fp)

    def marginal(
        self,
        variable_id: str,
        *,
        evidence: Mapping[str, str] | None = None,
        interventions: Mapping[str, str] | None = None,
        regime: str | None = None,
    ) -> CategoricalDistribution:
        variable_id = require_id("variable_id", variable_id)
        variable = self.model.variable(variable_id)
        if variable_id in (evidence or {}):
            return CategoricalDistribution.point(str((evidence or {})[variable_id]), variable.domain)
        result = self.query((variable_id,), evidence=evidence, interventions=interventions, regime=regime)
        return result.marginal(variable_id)

    def evidence_likelihood(
        self,
        evidence: Mapping[str, str],
        *,
        interventions: Mapping[str, str] | None = None,
        regime: str | None = None,
    ) -> float:
        evidence = dict(evidence)
        if not evidence:
            return 1.0
        # Pick one observed variable as query to retain the likelihood scale;
        # final normalization_constant is the unnormalized mass after evidence
        # conditioning before the final result normalization.
        anchor = next(iter(sorted(evidence)))
        result = self.query((anchor,), evidence=evidence, interventions=interventions, regime=regime)
        return result.normalization_constant

    def _guard(self, factor: Factor) -> None:
        if factor.entry_count > self.policy.maximum_sparse_entries:
            raise FactorComplexityExceeded(
                f"factor has {factor.entry_count} sparse entries; limit={self.policy.maximum_sparse_entries}"
            )
        if factor.dense_capacity > self.policy.maximum_dense_capacity:
            raise FactorComplexityExceeded(
                f"factor dense capacity {factor.dense_capacity}; limit={self.policy.maximum_dense_capacity}"
            )


class ScalableCausalView:
    """Thin inference facade used by high-dimensional control models."""

    def __init__(
        self,
        model: StructuralCausalModel,
        *,
        policy: InferencePolicy | None = None,
    ) -> None:
        self.model = model
        self.engine = VariableEliminationEngine(model, policy=policy)

    def marginal(
        self,
        variable_id: str,
        *,
        evidence: Mapping[str, str] | None = None,
        interventions: Mapping[str, str] | None = None,
        regime: str | None = None,
    ) -> CategoricalDistribution:
        return self.engine.marginal(variable_id, evidence=evidence, interventions=interventions, regime=regime)

    def joint(
        self,
        variables: Sequence[str],
        *,
        evidence: Mapping[str, str] | None = None,
        interventions: Mapping[str, str] | None = None,
        regime: str | None = None,
    ) -> FactorInferenceResult:
        return self.engine.query(variables, evidence=evidence, interventions=interventions, regime=regime)

    def likelihood(
        self,
        evidence: Mapping[str, str],
        *,
        interventions: Mapping[str, str] | None = None,
        regime: str | None = None,
    ) -> float:
        return self.engine.evidence_likelihood(evidence, interventions=interventions, regime=regime)
