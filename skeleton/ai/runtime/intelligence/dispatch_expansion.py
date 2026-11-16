"""Bounded decomposition, classification and tool fusion proposals for Jeeves.

No proposal grants tool authority. Inputs must come from an independently
authorized policy/registry snapshot. The canonical owner validates final
graph, costs, effect classes and receipts before executing anything.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction
from hashlib import sha256
from graphlib import TopologicalSorter, CycleError
import json

from .dispatch_policy import DispatchPolicyError, bounded_int, identifier
from .dispatch_cognitive import digest, labels, binding
from .dispatch_workflow import WorkflowNode, _graph


@dataclass(frozen=True, slots=True)
class TaskTaxon:
    name: str
    required: frozenset[str]
    optional: frozenset[str]
    prohibited: frozenset[str]

    def __post_init__(self) -> None:
        identifier(self.name)
        for group in (self.required, self.optional, self.prohibited):
            labels(group)
        if not self.required or self.required & self.prohibited or self.optional & self.prohibited:
            raise DispatchPolicyError("invalid taxonomy")


@dataclass(frozen=True, slots=True)
class Classification:
    status: str
    task_class: str | None
    matched: tuple[str, ...]
    evidence_sha256: str


def classify_labels(observed: frozenset[str], taxonomy: Sequence[TaskTaxon], *,
                    policy_sha256: str, evidence_sha256: str) -> Classification:
    """Classify verified semantic labels, not unconstrained natural language.

    Ties abstain; weak optional matches cannot override required exclusions.
    The label producer, taxonomy and evidence must be independently bound by
    the existing owner. No trained classifier is supplied by this interface.
    """
    labels(observed)
    digest(policy_sha256)
    digest(evidence_sha256)
    if not 1 <= len(taxonomy) <= 256 or any(not isinstance(t, TaskTaxon) for t in taxonomy):
        raise DispatchPolicyError("invalid taxonomy")
    if len({t.name for t in taxonomy}) != len(taxonomy):
        raise DispatchPolicyError("duplicate class")
    entries = sorted(taxonomy, key=lambda t: t.name)
    candidates = []
    for t in entries:
        if t.required <= observed and not t.prohibited & observed:
            score = (len(t.required), Fraction(len(t.optional & observed), max(1, len(t.optional))))
            candidates.append((score, t.name))
    winners = ()
    if candidates:
        score = max(row[0] for row in candidates)
        winners = tuple(sorted(name for rank, name in candidates if rank == score))
    selected = winners[0] if len(winners) == 1 else None
    disposition = "classified" if selected is not None else "hold_ambiguous" if winners else "hold_unknown"
    proof = binding("classification-v1", policy_sha256, evidence_sha256, sorted(observed),
                    [(t.name, sorted(t.required), sorted(t.optional), sorted(t.prohibited)) for t in entries],
                    winners, disposition)
    return Classification(disposition, selected, winners, proof)


@dataclass(frozen=True, slots=True)
class WorkerChoice:
    worker_id: str
    generation: int
    tenant_id: str
    task_sha256: str
    policy_sha256: str
    observation_sha256: str

    def __post_init__(self) -> None:
        identifier(self.worker_id)
        identifier(self.tenant_id)
        bounded_int(self.generation, "generation")
        for value in (self.task_sha256, self.policy_sha256, self.observation_sha256):
            digest(value)


def validate_model_choice(proposal: WorkerChoice, eligible: Sequence[WorkerChoice], *,
                          authorized_set_sha256: str) -> WorkerChoice | None:
    """Restrict a model's recommendation to a host-owned exact eligible set.

    All eligible observations must describe the same task, tenant and policy.
    The model's choice is not a credential, reservation, or capability assertion.
    """
    digest(authorized_set_sha256)
    if not isinstance(proposal, WorkerChoice) or len(eligible) > 4096:
        raise DispatchPolicyError("invalid choice")
    if any(not isinstance(row, WorkerChoice) for row in eligible):
        raise DispatchPolicyError("invalid eligible choice")
    if len({r.worker_id for r in eligible}) != len(eligible):
        raise DispatchPolicyError("duplicate worker choice")
    scope = {(r.tenant_id, r.task_sha256, r.policy_sha256) for r in eligible}
    if len(scope) > 1:
        raise DispatchPolicyError("mixed worker choice scope")
    ordered = sorted(eligible, key=lambda r: r.worker_id)
    encoded = binding("eligible-workers-v1", [
        (r.worker_id, r.generation, r.tenant_id, r.task_sha256, r.policy_sha256, r.observation_sha256)
        for r in ordered
    ])
    if encoded != authorized_set_sha256:
        raise DispatchPolicyError("eligible set binding mismatch")
    return next((r for r in ordered if r == proposal), None)


@dataclass(frozen=True, slots=True)
class DecompositionNode:
    task_id: str
    parent_id: str | None
    operation: str
    input_sha256: str
    effect: str
    tokens: int
    cost: int
    service_ms: int
    dependencies: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        identifier(self.task_id)
        identifier(self.operation)
        digest(self.input_sha256)
        if self.parent_id is not None:
            identifier(self.parent_id)
        if self.effect not in {"pure", "read", "write", "unknown"}:
            raise DispatchPolicyError("invalid effect")
        for name in ("tokens", "cost"):
            bounded_int(getattr(self, name), name)
        bounded_int(self.service_ms, "service", 1)
        if type(self.dependencies) is not tuple or len(self.dependencies) > 256:
            raise DispatchPolicyError("invalid predecessors")
        for predecessor in self.dependencies:
            identifier(predecessor)
        if len(set(self.dependencies)) != len(self.dependencies):
            raise DispatchPolicyError("duplicate predecessor")


@dataclass(frozen=True, slots=True)
class ExpansionPlan:
    root_id: str
    leaves: tuple[str, ...]
    execution_order: tuple[str, ...]
    maximum_depth: int
    token_reservation: int
    cost_reservation: int
    service_upper_ms: int
    graph_sha256: str


def validate_expansion(nodes: Sequence[DecompositionNode], *, root_id: str, tenant_id: str,
                       policy_sha256: str, approved_operations: frozenset[str],
                       max_depth: int = 8, max_nodes: int = 1024) -> ExpansionPlan:
    """Verify a bounded recursively proposed decomposition without executing it.

    Internal nodes are allocation containers, not executable work. Direct leaf
    and nested child sums cannot exceed inherited budgets; serial service
    sums are conservative. Only pure operations are accepted for automatic
    decomposition proposals. Effects require the existing explicit plan owner.
    """
    identifier(root_id)
    identifier(tenant_id)
    digest(policy_sha256)
    labels(approved_operations)
    bounded_int(max_depth, "depth", 1, 32)
    bounded_int(max_nodes, "nodes", 1, 4096)
    if not 1 <= len(nodes) <= max_nodes or any(not isinstance(n, DecompositionNode) for n in nodes):
        raise DispatchPolicyError("invalid expansion size")
    by_id = {n.task_id: n for n in nodes}
    if len(by_id) != len(nodes) or root_id not in by_id:
        raise DispatchPolicyError("duplicate or missing root")
    children: dict[str, list[str]] = defaultdict(list)
    for node in nodes:
        if node.operation not in approved_operations or node.effect != "pure":
            raise DispatchPolicyError("unapproved or effectful expansion")
        if node.task_id == root_id:
            if node.parent_id is not None:
                raise DispatchPolicyError("root has parent")
        elif node.parent_id not in by_id:
            raise DispatchPolicyError("missing parent")
        else:
            children[node.parent_id].append(node.task_id)
    depths = {root_id: 0}
    stack = [root_id]
    leaves = []
    while stack:
        key = stack.pop()
        node = by_id[key]
        descendants = sorted(children.get(key, ()))
        if not descendants:
            leaves.append(key)
            continue
        if node.dependencies:
            raise DispatchPolicyError("container cannot have runtime dependencies")
        rows = [by_id[child] for child in descendants]
        for resource in ("tokens", "cost", "service_ms"):
            if sum(getattr(row, resource) for row in rows) > getattr(node, resource):
                raise DispatchPolicyError("child budget exceeds parent")
        for child in descendants:
            if child in depths:
                raise DispatchPolicyError("decomposition cycle")
            depths[child] = depths[key] + 1
            if depths[child] > max_depth:
                raise DispatchPolicyError("decomposition depth exhausted")
            stack.append(child)
    if len(depths) != len(nodes):
        raise DispatchPolicyError("disconnected expansion")
    leaf_set = set(leaves)
    if sum(len(by_id[key].dependencies) for key in leaves) > 65536:
        raise DispatchPolicyError("expansion edge limit")
    for key in leaves:
        if not set(by_id[key].dependencies) <= leaf_set:
            raise DispatchPolicyError("leaf depends on non-executable container")
    try:
        order = tuple(TopologicalSorter({
            key: tuple(sorted(by_id[key].dependencies)) for key in sorted(leaves)
        }).static_order())
    except CycleError as exc:
        raise DispatchPolicyError("expansion dependency cycle") from exc
    proof = binding("expansion-v1", tenant_id, root_id, policy_sha256,
                    sorted(approved_operations), max_depth, max_nodes,
                    [(n.task_id, n.parent_id, n.operation, n.input_sha256, n.effect,
                      n.tokens, n.cost, n.service_ms, n.dependencies)
                     for n in sorted(nodes, key=lambda n: n.task_id)])
    return ExpansionPlan(root_id, tuple(sorted(leaves)), order, max(depths.values()),
                         sum(by_id[k].tokens for k in leaves), sum(by_id[k].cost for k in leaves),
                         sum(by_id[k].service_ms for k in leaves), proof)


@dataclass(frozen=True, slots=True)
class FusionProposal:
    tasks: tuple[str, ...]
    input_bytes_upper: int
    estimated_service_ms: int
    graph_sha256: str


def propose_fusion(nodes: Sequence[WorkflowNode], *, maximum_chain: int = 16,
                   maximum_intermediate_bytes: int = 64 * 1024**2,
                   maximum_service_ms: int = 60_000,
                   eligible_operations: frozenset[str]) -> tuple[FusionProposal, ...]:
    """Find straight-line pure chains with exact owner scope and no fanout.

    A producer's intermediate value must not be externally observable or
    independently requested; that fact and executable fusion support must
    be verified by the owner. Estimates do not assume acceleration.
    """
    bounded_int(maximum_chain, "chain", 2, 64)
    bounded_int(maximum_intermediate_bytes, "bytes", 1)
    bounded_int(maximum_service_ms, "service", 1)
    labels(eligible_operations)
    by_id, order = _graph(nodes)
    successors: dict[str, list[str]] = defaultdict(list)
    for n in nodes:
        for p in n.dependencies:
            successors[p].append(n.task_id)
    used: set[str] = set()
    results = []
    for key in order:
        n = by_id[key]
        if key in used or n.effect != "pure" or n.operation not in eligible_operations:
            continue
        chain = [key]
        duration = n.estimated_ms
        storage = 0
        while len(chain) < maximum_chain and len(successors[chain[-1]]) == 1:
            tail = by_id[chain[-1]]
            nxt = by_id[successors[tail.task_id][0]]
            if (nxt.task_id in used or nxt.effect != "pure" or nxt.operation not in eligible_operations
                    or nxt.dependencies != (tail.task_id,)
                    or (nxt.tenant_id, nxt.source_sha256, nxt.policy_sha256, nxt.context_sha256)
                       != (n.tenant_id, n.source_sha256, n.policy_sha256, n.context_sha256)
                    or duration + nxt.estimated_ms > maximum_service_ms
                    or storage + tail.output_bytes > maximum_intermediate_bytes):
                break
            chain.append(nxt.task_id)
            duration += nxt.estimated_ms
            storage += tail.output_bytes
        if len(chain) < 2:
            continue
        used.update(chain)
        proof = binding("fusion-v1", maximum_chain, maximum_intermediate_bytes, maximum_service_ms,
                        sorted(eligible_operations),
                        [(by_id[k].task_id, by_id[k].tenant_id, by_id[k].operation,
                          by_id[k].source_sha256, by_id[k].policy_sha256, by_id[k].context_sha256,
                          by_id[k].input_sha256, by_id[k].dependencies,
                          by_id[k].estimated_ms, by_id[k].output_bytes) for k in chain])
        results.append(FusionProposal(tuple(chain), storage, duration, proof))
    return tuple(results)
