"""Deterministic workflow optimization and recovery proposals.

Only exact, source-bound pure computations can share a candidate result.
Semantic resemblance is a review suggestion, never execution suppression.
Compensation and replanning require existing owner authorization and evidence.
"""
from __future__ import annotations

from collections.abc import Sequence, Mapping
from dataclasses import dataclass
from graphlib import CycleError, TopologicalSorter
from fractions import Fraction
from hashlib import sha256
import json

from .dispatch_policy import DispatchPolicyError, bounded_int, identifier
from .dispatch_cognitive import digest, labels

MAX_NODES = 4096
MAX_EDGES = 65536


@dataclass(frozen=True, slots=True)
class WorkflowNode:
    task_id: str
    tenant_id: str
    operation: str
    input_sha256: str
    source_sha256: str
    policy_sha256: str
    context_sha256: str
    dependencies: tuple[str, ...]
    estimated_ms: int
    output_bytes: int
    effect: str = "unknown"
    semantic_labels: frozenset[str] = frozenset()
    compensation_id: str | None = None

    def __post_init__(self) -> None:
        for value in (self.task_id, self.tenant_id, self.operation):
            identifier(value)
        for value in (self.input_sha256, self.source_sha256, self.policy_sha256, self.context_sha256):
            digest(value)
        if type(self.dependencies) is not tuple or len(self.dependencies) > 256:
            raise DispatchPolicyError("invalid dependency list")
        for dep in self.dependencies:
            identifier(dep)
        if len(set(self.dependencies)) != len(self.dependencies):
            raise DispatchPolicyError("duplicate predecessor")
        bounded_int(self.estimated_ms, "duration", 1)
        bounded_int(self.output_bytes, "output bytes")
        if self.effect not in {"pure", "read", "write", "unknown"}:
            raise DispatchPolicyError("invalid effect category")
        labels(self.semantic_labels)
        if self.compensation_id is not None:
            identifier(self.compensation_id)
            if self.effect != "write":
                raise DispatchPolicyError("compensation requires a write operation")


def _graph(nodes: Sequence[WorkflowNode]) -> tuple[dict[str, WorkflowNode], tuple[str, ...]]:
    if not 1 <= len(nodes) <= MAX_NODES or any(not isinstance(n, WorkflowNode) for n in nodes):
        raise DispatchPolicyError("invalid workflow graph")
    by_id = {n.task_id: n for n in nodes}
    if len(by_id) != len(nodes) or sum(len(n.dependencies) for n in nodes) > MAX_EDGES:
        raise DispatchPolicyError("duplicate workflow identity or edge limit")
    for n in nodes:
        if any(d not in by_id or by_id[d].tenant_id != n.tenant_id for d in n.dependencies):
            raise DispatchPolicyError("unknown or cross-tenant dependency")
    try:
        order = tuple(TopologicalSorter({
            k: tuple(sorted(by_id[k].dependencies)) for k in sorted(by_id)
        }).static_order())
    except CycleError as exc:
        raise DispatchPolicyError("workflow dependency cycle") from exc
    return by_id, order


@dataclass(frozen=True, slots=True)
class ReductionProposal:
    order: tuple[str, ...]
    aliases: tuple[tuple[str, str], ...]
    rewritten_dependencies: tuple[tuple[str, tuple[str, ...]], ...]
    estimated_saved_ms: int
    graph_sha256: str


def reduce_pure_graph(nodes: Sequence[WorkflowNode]) -> ReductionProposal:
    """Propose common-subexpression reuse only for byte-identical pure identities.

    Dependency representatives are part of the identity, including original
    signed input/implementation/policy/context digests. Never mutate a supplied
    graph or auto-publish aliases. The caller must validate purity, result
    custody, exact predecessor output identity and authorization before reuse.
    """
    by_id, order = _graph(nodes)
    representative: dict[str, str] = {}
    seen: dict[tuple, str] = {}
    aliases = []
    rewrites = []
    saved = 0
    payload = []
    for key in order:
        n = by_id[key]
        # Preserve the original predecessor order and multiplicity. Dependency
        # position may be semantically meaningful to the consuming operation.
        parents = tuple(representative[d] for d in n.dependencies)
        identity = (n.tenant_id, n.operation, n.input_sha256, n.source_sha256,
                    n.policy_sha256, n.context_sha256, parents)
        prior = seen.get(identity) if n.effect == "pure" else None
        representative[key] = prior or key
        if prior is not None:
            aliases.append((key, prior))
            saved += n.estimated_ms
        else:
            rewrites.append((key, parents))
            if n.effect == "pure":
                seen[identity] = key
        payload.append((key, identity, n.effect, n.estimated_ms, n.output_bytes,
                        sorted(n.semantic_labels), n.compensation_id))
    proof = sha256(json.dumps(["graph-reduction-v1", payload, aliases, rewrites],
                             separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()
    return ReductionProposal(tuple(key for key in order if representative[key] == key),
                             tuple(aliases), tuple(rewrites), saved, proof)


@dataclass(frozen=True, slots=True)
class SemanticPair:
    left: str
    right: str
    similarity: Fraction


def semantic_review_pairs(nodes: Sequence[WorkflowNode], *, minimum_ppm: int = 800_000,
                          pair_budget: int = 100_000, maximum_results: int = 512) -> tuple[SemanticPair, ...]:
    """Bound inverted-index comparison to tenant/policy/context/operation scope.

    Labels must be supplied by an existing classifier. Exact Jaccard similarity
    is not semantic equivalence; the result ONLY requests human/owner review.
    """
    bounded_int(minimum_ppm, "similarity", 1, 1_000_000)
    bounded_int(pair_budget, "pair budget", 1, 1_000_000)
    bounded_int(maximum_results, "results", 1, 4096)
    by_id, _ = _graph(nodes)
    postings: dict[tuple, list[str]] = {}
    for n in sorted(nodes, key=lambda n: n.task_id):
        if n.effect != "pure" or not n.semantic_labels:
            continue
        scope = (n.tenant_id, n.policy_sha256, n.context_sha256, n.operation)
        for label in sorted(n.semantic_labels):
            postings.setdefault(scope + (label,), []).append(n.task_id)
    compared: set[tuple[str, str]] = set()
    results = []
    work = 0
    for ids in postings.values():
        for i, left in enumerate(ids):
            for j in range(i + 1, len(ids)):
                work += 1
                if work > pair_budget:
                    raise DispatchPolicyError("semantic review comparison budget exhausted")
                pair = (left, ids[j])
                if pair in compared:
                    continue
                compared.add(pair)
                a, b = (by_id[key].semantic_labels for key in pair)
                score = Fraction(len(a & b), len(a | b))
                if score >= Fraction(minimum_ppm, 1_000_000):
                    results.append(SemanticPair(*pair, score))
    results.sort(key=lambda p: (-p.similarity, p.left, p.right))
    return tuple(results[:maximum_results])


@dataclass(frozen=True, slots=True)
class EffectObservation:
    task_id: str
    disposition: str
    receipt_sha256: str

    def __post_init__(self) -> None:
        identifier(self.task_id)
        digest(self.receipt_sha256)
        if self.disposition not in {"committed", "no-effect", "unknown"}:
            raise DispatchPolicyError("invalid effect observation")


@dataclass(frozen=True, slots=True)
class RecoveryProposal:
    hold_tasks: tuple[str, ...]
    compensation_order: tuple[tuple[str, str, str], ...]
    rerunnable: tuple[str, ...]


def plan_recovery(nodes: Sequence[WorkflowNode], observations: Sequence[EffectObservation],
                  *, approved_compensations: frozenset[str]) -> RecoveryProposal:
    """Reverse committed dependency order; unknown effects stop compensation.

    No inverse is synthesized. Each compensation must be explicitly registered
    and approved by the owner, and independently verified before execution.
    Missing receipts for write/unknown operations are conservatively held.
    """
    by_id, order = _graph(nodes)
    labels(approved_compensations)
    if len(observations) > len(nodes) or any(not isinstance(o, EffectObservation) for o in observations):
        raise DispatchPolicyError("invalid recovery evidence")
    records = {o.task_id: o for o in observations}
    if len(records) != len(observations) or not set(records) <= set(by_id):
        raise DispatchPolicyError("duplicate or unknown receipt")
    holds: list[str] = []
    actions: list[tuple[str, str, str]] = []
    rerunnable: list[str] = []
    for key in reversed(order):
        node = by_id[key]
        record = records.get(key)
        if record is not None and record.disposition == "unknown":
            holds.append(key)
            continue
        if node.effect == "pure":
            rerunnable.append(key)
            continue
        if record is None:
            holds.append(key)
        elif record.disposition == "no-effect":
            rerunnable.append(key)
        elif node.effect == "write" and node.compensation_id in approved_compensations:
            actions.append((key, node.compensation_id, record.receipt_sha256))
        elif node.effect != "read":
            holds.append(key)
    if holds:
        # Conservative global barrier: a missed unknown can invalidate reverse
        # ordering or cause a conflicting compensation.
        actions.clear()
        rerunnable.clear()
    return RecoveryProposal(tuple(sorted(holds)), tuple(actions), tuple(reversed(rerunnable)))


@dataclass(frozen=True, slots=True)
class WaitEdge:
    waiter: str
    holder: str
    resource: str
    generation: int

    def __post_init__(self) -> None:
        for value in (self.waiter, self.holder, self.resource):
            identifier(value)
        bounded_int(self.generation, "generation")


def wait_cycles(edges: Sequence[WaitEdge], *, generation: int) -> tuple[tuple[str, ...], ...]:
    """Detect strongly connected wait-for components in a coherent snapshot.

    A cycle is a deadlock *candidate*. Actual distributed deadlock needs
    resource multiplicity, expiry, alternative holders and owner evidence.
    Never kill a worker or release a reservation based on this function.
    """
    bounded_int(generation, "generation")
    if len(edges) > MAX_EDGES or any(not isinstance(e, WaitEdge) for e in edges):
        raise DispatchPolicyError("invalid wait graph")
    if any(e.generation != generation for e in edges):
        raise DispatchPolicyError("mixed wait graph generation")
    vertices = {name for e in edges for name in (e.waiter, e.holder)}
    if len(vertices) > MAX_NODES:
        raise DispatchPolicyError("wait graph vertex limit")
    outgoing = {v: set() for v in vertices}
    incoming = {v: set() for v in vertices}
    for e in edges:
        outgoing[e.waiter].add(e.holder)
        incoming[e.holder].add(e.waiter)
    visited: set[str] = set()
    finish: list[str] = []
    for start in sorted(vertices):
        if start in visited:
            continue
        visited.add(start)
        stack = [(start, iter(sorted(outgoing[start])))]
        while stack:
            vertex, children = stack[-1]
            child = next(children, None)
            if child is None:
                finish.append(vertex)
                stack.pop()
            elif child not in visited:
                visited.add(child)
                stack.append((child, iter(sorted(outgoing[child]))))
    visited.clear()
    cycles = []
    for start in reversed(finish):
        if start in visited:
            continue
        component = []
        stack = [start]
        visited.add(start)
        while stack:
            vertex = stack.pop()
            component.append(vertex)
            for child in sorted(incoming[vertex]):
                if child not in visited:
                    visited.add(child)
                    stack.append(child)
        if len(component) > 1 or start in outgoing[start]:
            cycles.append(tuple(sorted(component)))
    return tuple(sorted(cycles))


@dataclass(frozen=True, slots=True)
class HedgeObservation:
    task_id: str
    effect: str
    elapsed_ms: int
    tail_ms: int
    alternative_ms: int
    transfer_ms: int
    deadline_remaining_ms: int
    reservation_units: int
    spare_units: int
    primary_domain: str
    alternative_domain: str

    def __post_init__(self) -> None:
        for value in (self.task_id, self.primary_domain, self.alternative_domain):
            identifier(value)
        if self.effect not in {"pure", "read", "write", "unknown"}:
            raise DispatchPolicyError("invalid hedge effect")
        for name in ("elapsed_ms", "tail_ms", "alternative_ms", "transfer_ms",
                     "deadline_remaining_ms", "reservation_units", "spare_units"):
            bounded_int(getattr(self, name), name)
        if not self.tail_ms or not self.alternative_ms or not self.reservation_units:
            raise DispatchPolicyError("positive hedge service and reservation required")


def propose_hedge(observation: HedgeObservation, *, minimum_gain_ms: int = 1) -> bool:
    """Allow at most a proposal for pure work on an independent failure domain.

    The owner must reserve duplicate cost, execution, output and cancellation
    capacity; the losing outcome cannot publish and must be reconciled.
    """
    bounded_int(minimum_gain_ms, "minimum gain", 1)
    if not isinstance(observation, HedgeObservation):
        raise DispatchPolicyError("invalid hedge observation")
    o = observation
    alternative = o.alternative_ms + o.transfer_ms
    return (o.effect == "pure" and o.primary_domain != o.alternative_domain
            and o.reservation_units <= o.spare_units
            and o.elapsed_ms > 0 and alternative <= o.deadline_remaining_ms
            and o.tail_ms - o.elapsed_ms - alternative >= minimum_gain_ms)
