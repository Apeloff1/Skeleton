"""Bounded causal modeling and *explicitly simulated* interventions (VOL-250).

An observational association is not a causal effect. Even an identified causal
model here is a research assumption, not an observed or authorized action. All
evidence must remain active in the canonical source-lineage registry.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import heapq
import json
import math
import re

from .source_lineage import ResearchLineageError, ResearchSourceRegistry, SourceStatus

_ID = re.compile(r"^[A-Za-z][A-Za-z0-9._:-]{1,127}$")
_VARIABLE = re.compile(r"^[A-Za-z][A-Za-z0-9._:-]{0,127}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")


class CausalKnowledgeError(ValueError):
    """Causal statement is invalid, stale, unidentifiable or out of bounds."""


def _identity(value: object, field: str) -> str:
    pattern = _VARIABLE if field in ("cause", "effect", "intervention variable") else _ID
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise CausalKnowledgeError(field + " requires stable bounded identity")
    return value


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 4096:
        raise CausalKnowledgeError(field + " requires bounded nonempty text")
    return value.strip()


def _finite(value: object, field: str, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CausalKnowledgeError(field + " must be finite numeric")
    try:
        number = float(value)
    except (OverflowError, ValueError) as exc:
        raise CausalKnowledgeError(field + " outside safe model bounds") from exc
    if not math.isfinite(number) or abs(number) > maximum:
        raise CausalKnowledgeError(field + " outside safe model bounds")
    return number


def _digest(data: object) -> str:
    serialized = json.dumps(data, ensure_ascii=False, allow_nan=False,
                            sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def _terms(values: tuple[str, ...], field: str, *, required: bool) -> tuple[str, ...]:
    if not isinstance(values, tuple) or len(values) > 32:
        raise CausalKnowledgeError(field + " must be bounded tuple")
    if required and not values:
        raise CausalKnowledgeError(field + " must name identification assumptions")
    result = tuple(_text(value, field) for value in values)
    if len(set(result)) != len(result):
        raise CausalKnowledgeError("duplicate " + field)
    return result


class ClaimKind(str, Enum):
    ASSOCIATION = "association"
    CAUSAL_HYPOTHESIS = "causal-hypothesis"
    IDENTIFIED_MODEL = "identified-model"


@dataclass(frozen=True, slots=True)
class CausalClaim:
    claim_id: str
    cause: str
    effect: str
    source_id: str
    source_digest: str
    method: str
    kind: ClaimKind
    assumptions: tuple[str, ...]
    unresolved_confounders: tuple[str, ...] = ()
    coefficient: float | None = None

    def __post_init__(self) -> None:
        for field in ("claim_id", "cause", "effect", "source_id"):
            _identity(getattr(self, field), field)
        if self.cause == self.effect:
            raise CausalKnowledgeError("self-causation unsupported")
        if not isinstance(self.source_digest, str) or not _SHA.fullmatch(self.source_digest):
            raise CausalKnowledgeError("source_digest must be sha256")
        object.__setattr__(self, "method", _text(self.method, "method"))
        if not isinstance(self.kind, ClaimKind):
            raise CausalKnowledgeError("kind must be typed ClaimKind")
        object.__setattr__(
            self, "assumptions", _terms(self.assumptions, "assumptions", required=True)
        )
        object.__setattr__(
            self, "unresolved_confounders",
            _terms(self.unresolved_confounders, "unresolved_confounders", required=False),
        )
        if self.kind is ClaimKind.ASSOCIATION:
            if self.coefficient is not None:
                raise CausalKnowledgeError("association cannot masquerade as causal coefficient")
        elif self.coefficient is None:
            raise CausalKnowledgeError("structural hypothesis must specify coefficient")
        else:
            _finite(self.coefficient, "coefficient", 2.0)

    @property
    def digest(self) -> str:
        return _digest({
            "schema": "skeleton.research.causal-claim.v1",
            "claim": self.claim_id, "cause": self.cause, "effect": self.effect,
            "source": self.source_id, "source_digest": self.source_digest,
            "method": self.method, "kind": self.kind.value,
            "assumptions": self.assumptions,
            "unresolved_confounders": self.unresolved_confounders,
            "coefficient": self.coefficient,
        })


@dataclass(frozen=True, slots=True)
class CausalGraphSnapshot:
    claim_ids: tuple[str, ...]
    causal_claim_ids: tuple[str, ...]
    association_claim_ids: tuple[str, ...]
    source_ids: tuple[str, ...]
    receipt_digest: str


@dataclass(frozen=True, slots=True)
class InterventionResult:
    intervened_variable: str
    intervention_delta: float
    simulated_deltas: tuple[tuple[str, float], ...]
    model_claim_ids: tuple[str, ...]
    assumptions: tuple[str, ...]
    result_kind: str
    receipt_digest: str

    @property
    def observed(self) -> bool:
        """Never represent simulated/counterfactual output as observation."""
        return False


class CausalGraph:
    """Process-local DAG of source-bound causal models plus separate associations.

    One directed structural equation per (cause, effect) prevents silently
    choosing among incompatible estimates. Association edges never propagate
    interventions. This component does not execute real-world interventions.
    """

    def __init__(
        self, sources: ResearchSourceRegistry, *,
        max_nodes: int = 128, max_claims: int = 1024,
    ) -> None:
        if not isinstance(sources, ResearchSourceRegistry):
            raise CausalKnowledgeError("canonical source registry required")
        for value, name, bound in (
            (max_nodes, "max_nodes", 4096), (max_claims, "max_claims", 16384)
        ):
            if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= bound:
                raise CausalKnowledgeError(name + " outside allowed range")
        self._sources = sources
        self._max_nodes = max_nodes
        self._max_claims = max_claims
        self._claims: dict[str, CausalClaim] = {}

    @property
    def sources(self) -> ResearchSourceRegistry:
        """Canonical shared custody owner; no authority is transferred."""
        return self._sources

    def _verify_source(self, claim: CausalClaim) -> None:
        try:
            source = self._sources.source(claim.source_id)
        except ResearchLineageError as exc:
            raise CausalKnowledgeError("unknown causal evidence source") from exc
        if source.status is not SourceStatus.ACTIVE:
            raise CausalKnowledgeError("causal claim source corrected/retracted")
        if source.content_digest != claim.source_digest:
            raise CausalKnowledgeError("causal claim source digest mismatch")

    @staticmethod
    def _directed(claims: dict[str, CausalClaim]) -> tuple[CausalClaim, ...]:
        return tuple(
            sorted((c for c in claims.values() if c.kind is not ClaimKind.ASSOCIATION),
                   key=lambda c: c.claim_id)
        )

    def _ordered_nodes(self, claims: dict[str, CausalClaim]) -> tuple[str, ...]:
        nodes = {name for c in claims.values() for name in (c.cause, c.effect)}
        if len(nodes) > self._max_nodes:
            raise CausalKnowledgeError("causal graph node capacity exceeded")
        inbound = {node: 0 for node in nodes}
        outgoing: dict[str, list[str]] = {node: [] for node in nodes}
        for claim in self._directed(claims):
            outgoing[claim.cause].append(claim.effect)
            inbound[claim.effect] += 1
        ready = [node for node, degree in inbound.items() if degree == 0]
        heapq.heapify(ready)
        order = []
        while ready:
            node = heapq.heappop(ready)
            order.append(node)
            for nxt in sorted(outgoing[node]):
                inbound[nxt] -= 1
                if inbound[nxt] == 0:
                    heapq.heappush(ready, nxt)
        if len(order) != len(nodes):
            raise CausalKnowledgeError("directed causal cycle is inadmissible")
        return tuple(order)

    def add(self, claim: CausalClaim) -> str:
        if not isinstance(claim, CausalClaim):
            raise CausalKnowledgeError("typed causal claim required")
        prior = self._claims.get(claim.claim_id)
        if prior is not None:
            if prior != claim:
                raise CausalKnowledgeError("immutable causal claim identity conflict")
            self._verify_source(claim)
            return claim.digest
        self._verify_source(claim)
        if len(self._claims) >= self._max_claims:
            raise CausalKnowledgeError("causal claim capacity exceeded")
        if claim.kind is not ClaimKind.ASSOCIATION:
            for present in self._directed(self._claims):
                if (present.cause, present.effect) == (claim.cause, claim.effect):
                    raise CausalKnowledgeError("ambiguous duplicate structural edge")
        proposed = dict(self._claims)
        proposed[claim.claim_id] = claim
        self._ordered_nodes(proposed)  # Validate BEFORE mutating.
        self._claims[claim.claim_id] = claim
        return claim.digest

    def snapshot(self) -> CausalGraphSnapshot:
        for claim in self._claims.values():
            self._verify_source(claim)  # fail closed on research retraction
        self._ordered_nodes(self._claims)
        all_claims = tuple(sorted(self._claims.values(), key=lambda c: c.claim_id))
        causal = tuple(c.claim_id for c in all_claims if c.kind is not ClaimKind.ASSOCIATION)
        assoc = tuple(c.claim_id for c in all_claims if c.kind is ClaimKind.ASSOCIATION)
        sources = tuple(sorted({c.source_id for c in all_claims}))
        digest = _digest({
            "schema": "skeleton.research.causal-graph.v1",
            "claims": [(claim.claim_id, claim.digest) for claim in all_claims],
            "sources": sources,
        })
        return CausalGraphSnapshot(tuple(c.claim_id for c in all_claims),
                                   causal, assoc, sources, digest)

    def simulate(
        self, variable: str, delta: float, *,
        allow_hypothesized: bool = False,
    ) -> InterventionResult:
        _identity(variable, "intervention variable")
        requested = _finite(delta, "intervention delta", 10.0)
        if not isinstance(allow_hypothesized, bool):
            raise CausalKnowledgeError("allow_hypothesized must be boolean")
        snapshot = self.snapshot()
        directed = self._directed(self._claims)
        out: dict[str, list[CausalClaim]] = {}
        for c in directed:
            out.setdefault(c.cause, []).append(c)
        reachable = {variable}
        queue = [variable]
        chosen: dict[str, CausalClaim] = {}
        while queue:
            node = queue.pop()
            for edge in out.get(node, ()):
                chosen[edge.claim_id] = edge
                if edge.effect not in reachable:
                    reachable.add(edge.effect)
                    queue.append(edge.effect)
        for claim in chosen.values():
            if claim.unresolved_confounders:
                raise CausalKnowledgeError("unresolved confounders prohibit model intervention")
            if claim.kind is ClaimKind.CAUSAL_HYPOTHESIS and not allow_hypothesized:
                raise CausalKnowledgeError("hypothesized edge requires explicit what-if opt-in")
        order = self._ordered_nodes(self._claims)
        if variable not in order:
            order = (variable,) + order
        effects: dict[str, float] = {variable: requested}
        # Topologically compute linear *model* deltas; no observed data is changed.
        for node in order:
            if node not in reachable or node not in effects:
                continue
            for claim in sorted(out.get(node, ()), key=lambda c: c.claim_id):
                step = effects[node] * float(claim.coefficient)
                result = effects.get(claim.effect, 0.0) + step
                if not math.isfinite(result) or abs(result) > 10000:
                    raise CausalKnowledgeError("intervention exceeds bounded model magnitude")
                effects[claim.effect] = result
        assumptions = tuple(sorted({
            value for claim in chosen.values() for value in claim.assumptions
        }))
        values = tuple(sorted(effects.items()))
        claims = tuple(sorted(chosen))
        digest = _digest({
            "schema": "skeleton.research.simulated-intervention.v1",
            "graph": snapshot.receipt_digest, "variable": variable,
            "delta": requested, "deltas": values, "model_claims": claims,
            "assumptions": assumptions,
            "allow_hypothesized": allow_hypothesized,
            "result_kind": "SIMULATION_NOT_OBSERVATION",
        })
        return InterventionResult(
            variable, requested, values, claims, assumptions,
            "SIMULATION_NOT_OBSERVATION", digest,
        )


__all__ = [
    "CausalClaim", "CausalGraph", "CausalGraphSnapshot",
    "CausalKnowledgeError", "ClaimKind", "InterventionResult",
]
