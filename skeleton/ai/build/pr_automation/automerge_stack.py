"""Stack topology and bounded landing plans for auto-merge.

A stacked pull request targets another pull request's head branch.  This module
models that topology without performing mutations.  Cycles, duplicate branch
owners, missing parents, and ambiguous ancestry fail closed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

from .automerge_model import (
    CandidateSnapshot,
    PullRequestIdentity,
    StackRelation,
)


@dataclass(frozen=True, slots=True)
class StackNode:
    number: int
    base_ref: str
    base_sha: str
    head_ref: str
    head_sha: str
    parent_pr: int | None
    children: tuple[int, ...]
    depth: int
    relation: StackRelation


@dataclass(frozen=True, slots=True)
class StackGraph:
    nodes: tuple[StackNode, ...]
    roots: tuple[int, ...]
    cycles: tuple[tuple[int, ...], ...]
    orphans: tuple[int, ...]
    duplicate_heads: tuple[str, ...]

    def by_number(self) -> dict[int, StackNode]:
        return {node.number: node for node in self.nodes}

    def node(self, number: int) -> StackNode | None:
        return self.by_number().get(number)


@dataclass(frozen=True, slots=True)
class LandingStep:
    pr_number: int
    target_branch: str
    parent_pr: int | None
    depth: int
    reason: str


@dataclass(frozen=True, slots=True)
class LandingPlan:
    steps: tuple[LandingStep, ...]
    blocked: tuple[int, ...]
    root_prs: tuple[int, ...]

    @property
    def empty(self) -> bool:
        return not self.steps


def _identities(
    values: Iterable[CandidateSnapshot | PullRequestIdentity],
) -> tuple[PullRequestIdentity, ...]:
    out: list[PullRequestIdentity] = []
    for value in values:
        if isinstance(value, CandidateSnapshot):
            out.append(value.identity)
        elif isinstance(value, PullRequestIdentity):
            out.append(value)
        else:
            raise TypeError("stack graph expects CandidateSnapshot or PullRequestIdentity")
    return tuple(out)


def _head_owners(
    identities: Sequence[PullRequestIdentity],
) -> tuple[dict[str, int], tuple[str, ...]]:
    owners: dict[str, int] = {}
    duplicates: set[str] = set()
    for identity in identities:
        prior = owners.get(identity.head_ref)
        if prior is not None and prior != identity.number:
            duplicates.add(identity.head_ref)
        else:
            owners[identity.head_ref] = identity.number
    for branch in duplicates:
        owners.pop(branch, None)
    return owners, tuple(sorted(duplicates))


def _parents(
    identities: Sequence[PullRequestIdentity],
    *,
    default_branch: str,
    head_owners: Mapping[str, int],
) -> tuple[dict[int, int | None], tuple[int, ...]]:
    parents: dict[int, int | None] = {}
    orphans: list[int] = []
    for identity in identities:
        if identity.base_ref == default_branch:
            parents[identity.number] = None
            continue
        parent = head_owners.get(identity.base_ref)
        if parent is None:
            parents[identity.number] = None
            orphans.append(identity.number)
            continue
        if parent == identity.number:
            parents[identity.number] = parent
            continue
        parents[identity.number] = parent
    return parents, tuple(sorted(orphans))


def _find_cycles(parents: Mapping[int, int | None]) -> tuple[tuple[int, ...], ...]:
    done: set[int] = set()
    cycles: set[tuple[int, ...]] = set()

    for start in sorted(parents):
        if start in done:
            continue
        order: list[int] = []
        positions: dict[int, int] = {}
        current: int | None = start
        while current is not None and current in parents:
            if current in positions:
                cycle = order[positions[current] :]
                if cycle:
                    smallest = min(range(len(cycle)), key=cycle.__getitem__)
                    normalized = tuple(cycle[smallest:] + cycle[:smallest])
                    cycles.add(normalized)
                break
            if current in done:
                break
            positions[current] = len(order)
            order.append(current)
            current = parents.get(current)
        done.update(order)

    return tuple(sorted(cycles))


def _cycle_members(cycles: Sequence[Sequence[int]]) -> set[int]:
    return {number for cycle in cycles for number in cycle}


def _depth(
    number: int,
    parents: Mapping[int, int | None],
    *,
    cycle_members: set[int],
    orphan_members: set[int],
) -> int:
    if number in cycle_members or number in orphan_members:
        return -1
    depth = 0
    seen: set[int] = set()
    current = number
    while True:
        if current in seen:
            return -1
        seen.add(current)
        parent = parents.get(current)
        if parent is None:
            return depth
        depth += 1
        current = parent


def build_stack_graph(
    candidates: Iterable[CandidateSnapshot | PullRequestIdentity],
    *,
    default_branch: str,
) -> StackGraph:
    identities = _identities(candidates)
    numbers = [identity.number for identity in identities]
    if len(set(numbers)) != len(numbers):
        raise ValueError("duplicate pull request number in stack inventory")

    head_owners, duplicate_heads = _head_owners(identities)
    parents, orphans = _parents(
        identities,
        default_branch=default_branch,
        head_owners=head_owners,
    )
    cycles = _find_cycles(parents)
    cycle_members = _cycle_members(cycles)
    orphan_members = set(orphans)

    children: dict[int, list[int]] = {number: [] for number in numbers}
    for number, parent in parents.items():
        if parent is not None and parent in children:
            children[parent].append(number)

    nodes: list[StackNode] = []
    roots: list[int] = []
    for identity in sorted(identities, key=lambda item: item.number):
        number = identity.number
        parent = parents.get(number)
        if number in cycle_members:
            relation = StackRelation.CYCLE
        elif number in orphan_members:
            relation = StackRelation.ORPHAN
        elif parent is None:
            relation = StackRelation.ROOT
            roots.append(number)
        else:
            relation = StackRelation.CHILD
        nodes.append(
            StackNode(
                number=number,
                base_ref=identity.base_ref,
                base_sha=identity.base_sha,
                head_ref=identity.head_ref,
                head_sha=identity.head_sha,
                parent_pr=parent,
                children=tuple(sorted(children[number])),
                depth=_depth(
                    number,
                    parents,
                    cycle_members=cycle_members,
                    orphan_members=orphan_members,
                ),
                relation=relation,
            )
        )

    return StackGraph(
        nodes=tuple(nodes),
        roots=tuple(sorted(roots)),
        cycles=cycles,
        orphans=orphans,
        duplicate_heads=duplicate_heads,
    )


def annotate_snapshot(
    snapshot: CandidateSnapshot,
    graph: StackGraph,
) -> CandidateSnapshot:
    node = graph.node(snapshot.identity.number)
    if node is None:
        raise ValueError("snapshot is absent from stack graph")
    return CandidateSnapshot(
        identity=snapshot.identity,
        diff=snapshot.diff,
        labels=snapshot.labels,
        reviews=snapshot.reviews,
        unresolved_threads=snapshot.unresolved_threads,
        workflow_runs=snapshot.workflow_runs,
        base_contains_head_parent=snapshot.base_contains_head_parent,
        head_contains_base=snapshot.head_contains_base,
        candidate_class=snapshot.candidate_class,
        stack_relation=node.relation,
        parent_pr=node.parent_pr,
        sensitive_paths=snapshot.sensitive_paths,
        risk_tier=snapshot.risk_tier,
        captured_at=snapshot.captured_at,
    )


def annotate_all(
    snapshots: Sequence[CandidateSnapshot],
    *,
    default_branch: str,
) -> tuple[CandidateSnapshot, ...]:
    graph = build_stack_graph(snapshots, default_branch=default_branch)
    return tuple(annotate_snapshot(snapshot, graph) for snapshot in snapshots)


def descendants(graph: StackGraph, number: int) -> tuple[int, ...]:
    by_number = graph.by_number()
    if number not in by_number:
        return ()
    out: list[int] = []
    queue = list(by_number[number].children)
    seen: set[int] = set()
    while queue:
        current = queue.pop(0)
        if current in seen:
            continue
        seen.add(current)
        out.append(current)
        node = by_number.get(current)
        if node is not None:
            queue.extend(node.children)
    return tuple(out)


def ancestors(graph: StackGraph, number: int) -> tuple[int, ...]:
    by_number = graph.by_number()
    node = by_number.get(number)
    if node is None:
        return ()
    out: list[int] = []
    seen: set[int] = set()
    current = node.parent_pr
    while current is not None:
        if current in seen:
            break
        seen.add(current)
        out.append(current)
        parent = by_number.get(current)
        current = parent.parent_pr if parent is not None else None
    return tuple(out)


def leaf_nodes(graph: StackGraph) -> tuple[int, ...]:
    return tuple(
        node.number
        for node in graph.nodes
        if node.relation in {StackRelation.ROOT, StackRelation.CHILD}
        and not node.children
    )


def root_for(graph: StackGraph, number: int) -> int | None:
    by_number = graph.by_number()
    node = by_number.get(number)
    if node is None or node.relation in {StackRelation.CYCLE, StackRelation.ORPHAN}:
        return None
    current = node
    seen: set[int] = set()
    while current.parent_pr is not None:
        if current.number in seen:
            return None
        seen.add(current.number)
        parent = by_number.get(current.parent_pr)
        if parent is None:
            return None
        current = parent
    return current.number


def stack_groups(graph: StackGraph) -> Mapping[int, tuple[int, ...]]:
    groups: dict[int, list[int]] = {root: [] for root in graph.roots}
    for node in graph.nodes:
        root = root_for(graph, node.number)
        if root is not None:
            groups.setdefault(root, []).append(node.number)
    return {
        root: tuple(
            sorted(
                numbers,
                key=lambda number: (
                    graph.by_number()[number].depth,
                    number,
                ),
            )
        )
        for root, numbers in groups.items()
    }


def landing_plan(
    graph: StackGraph,
    *,
    eligible: Iterable[int],
    max_stack_merges: int,
) -> LandingPlan:
    """Plan safe child-to-parent branch merges before a root lands.

    Only leaves are selected.  Merging a leaf into its parent branch changes the
    parent PR head, so the next reconciliation must re-run exact-head checks
    before another mutation.  This plan therefore deliberately emits at most
    one step per stack root per pass.
    """
    if max_stack_merges <= 0:
        raise ValueError("max_stack_merges must be positive")

    eligible_set = set(eligible)
    by_number = graph.by_number()
    blocked: set[int] = set(graph.orphans)
    blocked.update(_cycle_members(graph.cycles))

    for branch in graph.duplicate_heads:
        for node in graph.nodes:
            if node.head_ref == branch or node.base_ref == branch:
                blocked.add(node.number)

    steps: list[LandingStep] = []
    used_roots: set[int] = set()

    candidates = [
        node
        for node in graph.nodes
        if node.number in eligible_set
        and node.relation is StackRelation.CHILD
        and not node.children
        and node.number not in blocked
    ]
    candidates.sort(key=lambda node: (-node.depth, node.number))

    for node in candidates:
        if len(steps) >= max_stack_merges:
            break
        root = root_for(graph, node.number)
        if root is None or root in used_roots:
            continue
        parent = by_number.get(node.parent_pr or -1)
        if parent is None:
            blocked.add(node.number)
            continue
        used_roots.add(root)
        steps.append(
            LandingStep(
                pr_number=node.number,
                target_branch=parent.head_ref,
                parent_pr=parent.number,
                depth=node.depth,
                reason=(
                    "leaf stack child is eligible; merge into parent head branch "
                    "and force exact-head revalidation before further landing"
                ),
            )
        )

    return LandingPlan(
        steps=tuple(steps),
        blocked=tuple(sorted(blocked)),
        root_prs=graph.roots,
    )


def validate_graph(graph: StackGraph) -> tuple[str, ...]:
    reasons: list[str] = []
    if graph.cycles:
        for cycle in graph.cycles:
            reasons.append("cycle:" + "->".join(str(item) for item in cycle))
    if graph.orphans:
        reasons.append("orphans:" + ",".join(str(item) for item in graph.orphans))
    if graph.duplicate_heads:
        reasons.append("duplicate_heads:" + ",".join(graph.duplicate_heads))

    by_number = graph.by_number()
    for node in graph.nodes:
        if node.relation is StackRelation.ROOT and node.parent_pr is not None:
            reasons.append(f"root_has_parent:{node.number}")
        if node.relation is StackRelation.CHILD and node.parent_pr not in by_number:
            reasons.append(f"child_missing_parent:{node.number}")
        if node.relation is StackRelation.CHILD and node.parent_pr in by_number:
            parent = by_number[node.parent_pr]
            if node.base_sha != parent.head_sha:
                reasons.append(
                    f"child_base_sha_mismatch:{node.number}:{node.base_sha}:{parent.head_sha}"
                )
        for child in node.children:
            child_node = by_number.get(child)
            if child_node is None or child_node.parent_pr != node.number:
                reasons.append(f"child_edge_mismatch:{node.number}:{child}")

    return tuple(reasons)


__all__ = [
    "LandingPlan",
    "LandingStep",
    "StackGraph",
    "StackNode",
    "ancestors",
    "annotate_all",
    "annotate_snapshot",
    "build_stack_graph",
    "descendants",
    "landing_plan",
    "leaf_nodes",
    "root_for",
    "stack_groups",
    "validate_graph",
]
