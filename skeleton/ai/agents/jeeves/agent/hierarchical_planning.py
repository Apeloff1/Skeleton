"""Hierarchical rolling-horizon planning for Jeeves.

Flat plans become brittle as horizons grow: distant steps are guessed before the
agent has the evidence needed to specify them, while replanning can erase work
that was already verified.  This module introduces temporal abstraction:

* strategic objectives and milestones form a macro DAG;
* only the near execution frontier is refined into executable micro steps;
* subplans own explicit compute/tool/token/risk budgets;
* constraints propagate down the hierarchy and outcomes propagate upward;
* completed verified milestones are immutable across replans by default;
* alternative macro plans can be held as a diverse portfolio;
* refinement depth is selected from uncertainty, novelty and risk;
* plan compilation produces the existing deterministic ``Plan`` contract.

This keeps long-horizon intent stable while allowing local tactics to evolve.
"""

from __future__ import annotations

import math
import threading
import time
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Callable, Mapping, Sequence

from .types import (
    AgentContractError,
    Goal,
    Plan,
    PlanStep,
    RiskTier,
    StepStatus,
    bounded_text,
    finite_number,
    json_safe,
    positive_int,
    probability,
    require_id,
    stable_fingerprint,
    stable_id,
)


class HierarchicalPlanningError(RuntimeError):
    pass


class NodeKind(str, Enum):
    OBJECTIVE = "objective"
    MILESTONE = "milestone"
    OPTION = "option"
    ACTION = "action"
    VERIFICATION = "verification"
    RECOVERY = "recovery"


class NodeState(str, Enum):
    ABSTRACT = "abstract"
    REFINED = "refined"
    READY = "ready"
    RUNNING = "running"
    VERIFIED = "verified"
    FAILED = "failed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"


class ConstraintKind(str, Enum):
    HARD = "hard"
    SOFT = "soft"
    RESOURCE = "resource"
    SAFETY = "safety"
    TEMPORAL = "temporal"
    QUALITY = "quality"


@dataclass(frozen=True, slots=True)
class ResourceEnvelope:
    max_steps: int = 16
    max_model_calls: int = 8
    max_tool_calls: int = 16
    max_tokens: int = 32_000
    max_wall_seconds: float = 120.0
    max_cost: float = 0.0

    def __post_init__(self) -> None:
        for name in ("max_steps", "max_model_calls", "max_tool_calls", "max_tokens"):
            object.__setattr__(self, name, positive_int(name, getattr(self, name), maximum=100_000_000))
        wall = finite_number("max_wall_seconds", self.max_wall_seconds)
        cost = finite_number("max_cost", self.max_cost)
        if wall <= 0 or cost < 0:
            raise AgentContractError("invalid resource envelope")
        object.__setattr__(self, "max_wall_seconds", wall)
        object.__setattr__(self, "max_cost", cost)

    def scaled(self, fraction: float) -> "ResourceEnvelope":
        fraction = probability("fraction", fraction)
        factor = max(0.05, fraction)
        return ResourceEnvelope(
            max_steps=max(1, round(self.max_steps * factor)),
            max_model_calls=max(1, round(self.max_model_calls * factor)),
            max_tool_calls=max(1, round(self.max_tool_calls * factor)),
            max_tokens=max(256, round(self.max_tokens * factor)),
            max_wall_seconds=max(1.0, self.max_wall_seconds * factor),
            max_cost=self.max_cost * factor,
        )


@dataclass(frozen=True, slots=True)
class PlanConstraint:
    constraint_id: str
    kind: ConstraintKind
    statement: str
    inherited: bool = True
    priority: int = 100
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "constraint_id", require_id("constraint_id", self.constraint_id))
        if not isinstance(self.kind, ConstraintKind):
            object.__setattr__(self, "kind", ConstraintKind(str(self.kind)))
        object.__setattr__(self, "statement", bounded_text("constraint", self.statement, maximum=4096))
        if isinstance(self.priority, bool) or not isinstance(self.priority, int) or not 0 <= self.priority <= 1000:
            raise AgentContractError("constraint priority must be integer in [0,1000]")
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class SuccessPredicate:
    predicate_id: str
    description: str
    verifier: str
    threshold: float = 1.0
    required: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "predicate_id", require_id("predicate_id", self.predicate_id))
        object.__setattr__(self, "description", bounded_text("predicate description", self.description, maximum=4096))
        object.__setattr__(self, "verifier", require_id("verifier", self.verifier))
        object.__setattr__(self, "threshold", probability("threshold", self.threshold))


@dataclass(frozen=True, slots=True)
class HierarchyNode:
    node_id: str
    kind: NodeKind
    title: str
    objective: str
    parent_id: str | None = None
    dependencies: tuple[str, ...] = ()
    constraints: tuple[PlanConstraint, ...] = ()
    success_predicates: tuple[SuccessPredicate, ...] = ()
    risk: RiskTier = RiskTier.READ_ONLY
    state: NodeState = NodeState.ABSTRACT
    depth: int = 0
    priority: float = 0.5
    utility: float = 0.5
    uncertainty: float = 0.5
    novelty: float = 0.5
    budget: ResourceEnvelope = field(default_factory=ResourceEnvelope)
    tool: str | None = None
    arguments: Mapping[str, Any] = field(default_factory=dict)
    expected_outcome: str = ""
    verification: str = ""
    protected: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "node_id", require_id("node_id", self.node_id))
        if not isinstance(self.kind, NodeKind):
            object.__setattr__(self, "kind", NodeKind(str(self.kind)))
        object.__setattr__(self, "title", bounded_text("title", self.title, maximum=1024))
        object.__setattr__(self, "objective", bounded_text("objective", self.objective, maximum=8192))
        if self.parent_id is not None:
            object.__setattr__(self, "parent_id", require_id("parent_id", self.parent_id))
        object.__setattr__(self, "dependencies", tuple(require_id("dependency", value) for value in self.dependencies))
        if self.node_id in self.dependencies:
            raise AgentContractError("node cannot depend on itself")
        constraints = tuple(self.constraints)
        predicates = tuple(self.success_predicates)
        if any(not isinstance(value, PlanConstraint) for value in constraints):
            raise AgentContractError("constraints must contain PlanConstraint")
        if any(not isinstance(value, SuccessPredicate) for value in predicates):
            raise AgentContractError("success_predicates must contain SuccessPredicate")
        object.__setattr__(self, "constraints", constraints)
        object.__setattr__(self, "success_predicates", predicates)
        if not isinstance(self.risk, RiskTier):
            object.__setattr__(self, "risk", RiskTier(str(self.risk)))
        if not isinstance(self.state, NodeState):
            object.__setattr__(self, "state", NodeState(str(self.state)))
        if isinstance(self.depth, bool) or not isinstance(self.depth, int) or self.depth < 0:
            raise AgentContractError("depth must be non-negative integer")
        for name in ("priority", "utility", "uncertainty", "novelty"):
            object.__setattr__(self, name, probability(name, getattr(self, name)))
        if not isinstance(self.budget, ResourceEnvelope):
            raise AgentContractError("budget must be ResourceEnvelope")
        if self.tool is not None:
            object.__setattr__(self, "tool", require_id("tool", self.tool))
        object.__setattr__(self, "arguments", json_safe(dict(self.arguments)))
        object.__setattr__(self, "expected_outcome", bounded_text("expected_outcome", self.expected_outcome, maximum=4096, allow_empty=True))
        object.__setattr__(self, "verification", bounded_text("verification", self.verification, maximum=4096, allow_empty=True))
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))

    @property
    def terminal(self) -> bool:
        return self.state in {NodeState.VERIFIED, NodeState.FAILED, NodeState.BLOCKED, NodeState.SKIPPED}

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "kind": self.kind.value,
                "title": self.title,
                "objective": self.objective,
                "parent": self.parent_id,
                "dependencies": self.dependencies,
                "constraints": [(value.constraint_id, value.kind.value, value.statement, value.priority) for value in self.constraints],
                "predicates": [(value.predicate_id, value.verifier, value.threshold, value.required) for value in self.success_predicates],
                "risk": self.risk.value,
                "state": self.state.value,
                "depth": self.depth,
                "tool": self.tool,
                "arguments": self.arguments,
                "outcome": self.expected_outcome,
                "verification": self.verification,
            }
        )


@dataclass(frozen=True, slots=True)
class RefinementProposal:
    parent_id: str
    children: tuple[HierarchyNode, ...]
    rationale: str
    confidence: float
    preserves_parent_objective: bool = True
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "parent_id", require_id("parent_id", self.parent_id))
        children = tuple(self.children)
        if not children or any(not isinstance(value, HierarchyNode) for value in children):
            raise AgentContractError("refinement requires HierarchyNode children")
        if any(value.parent_id != self.parent_id for value in children):
            raise AgentContractError("refinement child parent mismatch")
        object.__setattr__(self, "children", children)
        object.__setattr__(self, "rationale", bounded_text("rationale", self.rationale, maximum=8192))
        object.__setattr__(self, "confidence", probability("confidence", self.confidence))
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))


class RefinementGenerator:
    def __call__(self, node: HierarchyNode, inherited_constraints: Sequence[PlanConstraint], target_depth: int) -> RefinementProposal:  # pragma: no cover - interface
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class RefinementPolicy:
    maximum_depth: int = 6
    frontier_depth: int = 2
    high_uncertainty: float = 0.65
    high_novelty: float = 0.65
    high_risk: float = 0.60
    minimum_refinement_confidence: float = 0.55
    maximum_children: int = 12

    def __post_init__(self) -> None:
        object.__setattr__(self, "maximum_depth", positive_int("maximum_depth", self.maximum_depth, maximum=64))
        object.__setattr__(self, "frontier_depth", positive_int("frontier_depth", self.frontier_depth, maximum=64))
        if self.frontier_depth > self.maximum_depth:
            raise AgentContractError("frontier_depth cannot exceed maximum_depth")
        for name in ("high_uncertainty", "high_novelty", "high_risk", "minimum_refinement_confidence"):
            object.__setattr__(self, name, probability(name, getattr(self, name)))
        object.__setattr__(self, "maximum_children", positive_int("maximum_children", self.maximum_children, maximum=128))


@dataclass(frozen=True, slots=True)
class RefinementDecision:
    refine: bool
    target_depth: int
    urgency: float
    reasons: tuple[str, ...]


class RollingHorizonController:
    _RISK = {
        RiskTier.READ_ONLY: 0.05,
        RiskTier.REVERSIBLE: 0.20,
        RiskTier.MUTATING: 0.55,
        RiskTier.EXTERNAL: 0.75,
        RiskTier.HIGH_IMPACT: 1.0,
    }

    def __init__(self, policy: RefinementPolicy | None = None) -> None:
        self.policy = policy or RefinementPolicy()

    def decide(self, node: HierarchyNode, *, distance_from_frontier: int = 0, budget_fraction_remaining: float = 1.0) -> RefinementDecision:
        remaining = probability("budget_fraction_remaining", budget_fraction_remaining)
        if node.terminal or node.depth >= self.policy.maximum_depth:
            return RefinementDecision(False, node.depth, 0.0, ("terminal/max-depth",))
        risk = self._RISK[node.risk]
        horizon_pressure = max(0.0, 1.0 - distance_from_frontier / max(1, self.policy.frontier_depth + 1))
        urgency = (
            node.uncertainty * 0.28
            + node.novelty * 0.18
            + risk * 0.24
            + node.priority * 0.16
            + horizon_pressure * 0.14
        )
        urgency *= 0.55 + 0.45 * remaining
        reasons: list[str] = []
        if node.uncertainty >= self.policy.high_uncertainty:
            reasons.append("high uncertainty")
        if node.novelty >= self.policy.high_novelty:
            reasons.append("high novelty")
        if risk >= self.policy.high_risk:
            reasons.append("high risk")
        if distance_from_frontier <= self.policy.frontier_depth:
            reasons.append("near execution frontier")
        target_depth = min(self.policy.maximum_depth, node.depth + (2 if urgency >= 0.75 else 1))
        refine = node.state is NodeState.ABSTRACT and (urgency >= 0.40 or distance_from_frontier <= self.policy.frontier_depth)
        return RefinementDecision(refine, target_depth, min(1.0, urgency), tuple(reasons or ["low refinement pressure"]))


class HierarchicalPlan:
    """Mutable host-owned hierarchy with immutable verified-node semantics."""

    def __init__(self, goal: Goal, *, root_budget: ResourceEnvelope | None = None, clock: Callable[[], float] = time.time) -> None:
        if not isinstance(goal, Goal):
            raise TypeError("goal must be Goal")
        self.goal = goal
        self._clock = clock
        root_id = stable_id("hnode", {"goal": goal.goal_id, "objective": goal.objective})
        constraints = tuple(
            PlanConstraint(stable_id("constraint", {"goal": goal.goal_id, "index": index, "text": text}), ConstraintKind.HARD, text)
            for index, text in enumerate(goal.constraints)
        )
        predicates = tuple(
            SuccessPredicate(stable_id("predicate", {"goal": goal.goal_id, "index": index, "text": text}), text, "goal_criterion", 1.0, True)
            for index, text in enumerate(goal.success_criteria)
        )
        root = HierarchyNode(
            node_id=root_id,
            kind=NodeKind.OBJECTIVE,
            title="Goal",
            objective=goal.objective,
            constraints=constraints,
            success_predicates=predicates,
            priority=1.0,
            utility=1.0,
            budget=root_budget or ResourceEnvelope(),
            protected=True,
        )
        self.root_id = root_id
        self._nodes: dict[str, HierarchyNode] = {root_id: root}
        self._children: dict[str, list[str]] = defaultdict(list)
        self._history: list[tuple[float, str, str]] = [(self._clock(), "create", root_id)]
        self._lock = threading.RLock()

    def node(self, node_id: str) -> HierarchyNode:
        with self._lock:
            value = self._nodes.get(require_id("node_id", node_id))
            if value is None:
                raise KeyError(node_id)
            return value

    def nodes(self) -> tuple[HierarchyNode, ...]:
        with self._lock:
            return tuple(sorted(self._nodes.values(), key=lambda value: (value.depth, value.node_id)))

    def children(self, node_id: str) -> tuple[HierarchyNode, ...]:
        node_id = require_id("node_id", node_id)
        with self._lock:
            return tuple(self._nodes[value] for value in self._children.get(node_id, ()))

    def inherited_constraints(self, node_id: str) -> tuple[PlanConstraint, ...]:
        node = self.node(node_id)
        chain: list[HierarchyNode] = []
        while node is not None:
            chain.append(node)
            node = self._nodes.get(node.parent_id) if node.parent_id else None
        constraints: dict[str, PlanConstraint] = {}
        for value in reversed(chain):
            for constraint in value.constraints:
                if value.node_id == node_id or constraint.inherited:
                    prior = constraints.get(constraint.constraint_id)
                    if prior is None or constraint.priority >= prior.priority:
                        constraints[constraint.constraint_id] = constraint
        return tuple(sorted(constraints.values(), key=lambda value: (-value.priority, value.constraint_id)))

    def apply_refinement(self, proposal: RefinementProposal, *, minimum_confidence: float = 0.55, maximum_children: int = 12) -> tuple[HierarchyNode, ...]:
        if not isinstance(proposal, RefinementProposal):
            raise TypeError("proposal must be RefinementProposal")
        minimum_confidence = probability("minimum_confidence", minimum_confidence)
        if proposal.confidence < minimum_confidence:
            raise HierarchicalPlanningError("refinement confidence below policy")
        if len(proposal.children) > maximum_children:
            raise HierarchicalPlanningError("refinement exceeds child limit")
        with self._lock:
            parent = self.node(proposal.parent_id)
            if parent.state in {NodeState.VERIFIED, NodeState.RUNNING}:
                raise HierarchicalPlanningError("cannot structurally refine verified/running node")
            if self._children.get(parent.node_id):
                existing = tuple(self._nodes[value] for value in self._children[parent.node_id])
                if stable_fingerprint([value.fingerprint for value in existing]) == stable_fingerprint([value.fingerprint for value in proposal.children]):
                    return existing
                raise HierarchicalPlanningError("node already has a different refinement")
            child_ids = {value.node_id for value in proposal.children}
            if len(child_ids) != len(proposal.children):
                raise HierarchicalPlanningError("duplicate child ids")
            for child in proposal.children:
                if child.node_id in self._nodes:
                    raise HierarchicalPlanningError("child id already exists")
                if child.depth != parent.depth + 1:
                    raise HierarchicalPlanningError("child depth mismatch")
                unknown = set(child.dependencies) - child_ids - set(self._nodes)
                if unknown:
                    raise HierarchicalPlanningError(f"child has unknown dependencies: {sorted(unknown)}")
                inherited_budget = parent.budget.scaled(1.0 / max(1, len(proposal.children)))
                budget = self._intersect_budget(child.budget, inherited_budget)
                self._nodes[child.node_id] = replace(child, budget=budget)
                self._children[parent.node_id].append(child.node_id)
            self._reject_cycles()
            self._nodes[parent.node_id] = replace(parent, state=NodeState.REFINED)
            self._history.append((self._clock(), "refine", parent.node_id))
            return tuple(self._nodes[value] for value in self._children[parent.node_id])

    def transition(self, node_id: str, state: NodeState) -> HierarchyNode:
        if not isinstance(state, NodeState):
            state = NodeState(str(state))
        with self._lock:
            node = self.node(node_id)
            allowed = {
                NodeState.ABSTRACT: {NodeState.REFINED, NodeState.READY, NodeState.SKIPPED},
                NodeState.REFINED: {NodeState.READY, NodeState.BLOCKED, NodeState.SKIPPED},
                NodeState.READY: {NodeState.RUNNING, NodeState.BLOCKED, NodeState.SKIPPED},
                NodeState.RUNNING: {NodeState.VERIFIED, NodeState.FAILED},
                NodeState.FAILED: {NodeState.READY, NodeState.BLOCKED},
                NodeState.BLOCKED: {NodeState.READY, NodeState.SKIPPED},
                NodeState.VERIFIED: set(),
                NodeState.SKIPPED: set(),
            }
            if state == node.state:
                return node
            if state not in allowed[node.state]:
                raise HierarchicalPlanningError(f"invalid node transition {node.state.value}->{state.value}")
            if state is NodeState.READY and not self._dependencies_satisfied(node):
                raise HierarchicalPlanningError("cannot ready node before dependencies are verified/skipped")
            updated = replace(node, state=state)
            self._nodes[node.node_id] = updated
            self._history.append((self._clock(), f"state:{state.value}", node.node_id))
            if state in {NodeState.VERIFIED, NodeState.SKIPPED}:
                self._propagate_parent_completion(node.parent_id)
            if state in {NodeState.FAILED, NodeState.BLOCKED}:
                self._propagate_blocking(node.node_id)
            return updated

    def executable_frontier(self) -> tuple[HierarchyNode, ...]:
        with self._lock:
            values: list[HierarchyNode] = []
            for node in self._nodes.values():
                if node.state not in {NodeState.ABSTRACT, NodeState.REFINED, NodeState.READY}:
                    continue
                if self._children.get(node.node_id):
                    continue
                if self._dependencies_satisfied(node):
                    values.append(node if node.state is NodeState.READY else replace(node, state=NodeState.READY))
            values.sort(key=lambda value: (value.priority, value.utility, -value.uncertainty, -value.depth, value.node_id), reverse=True)
            return tuple(values)

    def compile(self, *, plan_version: int = 1) -> Plan:
        """Compile leaf execution nodes into the stable flat Plan contract."""
        leaves = [node for node in self.nodes() if not self.children(node.node_id) and node.node_id != self.root_id and node.state not in {NodeState.VERIFIED, NodeState.SKIPPED}]
        if not leaves:
            raise HierarchicalPlanningError("hierarchy has no uncompleted executable leaves")
        leaf_ids = {node.node_id for node in leaves}
        steps: list[PlanStep] = []
        for node in leaves:
            dependencies = tuple(dep for dep in node.dependencies if dep in leaf_ids)
            if node.kind is NodeKind.VERIFICATION and not node.verification:
                verification = node.objective
            else:
                verification = node.verification
            status = StepStatus.READY if node in self.executable_frontier() else StepStatus.PENDING
            steps.append(
                PlanStep(
                    step_id=node.node_id,
                    title=node.title,
                    description=node.objective,
                    dependencies=dependencies,
                    tool=node.tool,
                    arguments=node.arguments,
                    expected_outcome=node.expected_outcome,
                    verification=verification,
                    risk=node.risk,
                    status=status,
                    max_attempts=max(1, min(8, node.budget.max_steps)),
                )
            )
        return Plan(
            plan_id=stable_id("plan", {"goal": self.goal.goal_id, "hierarchy": self.fingerprint, "version": plan_version}),
            goal_id=self.goal.goal_id,
            steps=tuple(steps),
            version=plan_version,
            rationale="Compiled from rolling-horizon hierarchical plan.",
            created_at=self._clock(),
        )

    def distance_to_frontier(self, node_id: str) -> int:
        node_id = require_id("node_id", node_id)
        frontier_ids = {node.node_id for node in self.executable_frontier()}
        if node_id in frontier_ids:
            return 0
        queue = deque([(node_id, 0)])
        visited: set[str] = set()
        while queue:
            current, distance = queue.popleft()
            if current in visited:
                continue
            visited.add(current)
            for child in self._children.get(current, ()):
                if child in frontier_ids:
                    return distance + 1
                queue.append((child, distance + 1))
        return 1_000_000

    def protected_fingerprints(self) -> Mapping[str, str]:
        with self._lock:
            return {node.node_id: node.fingerprint for node in self._nodes.values() if node.protected or node.state is NodeState.VERIFIED}

    def verify_replan_preserves(self, proposed: "HierarchicalPlan") -> tuple[str, ...]:
        if not isinstance(proposed, HierarchicalPlan):
            raise TypeError("proposed must be HierarchicalPlan")
        failures: list[str] = []
        for node_id, fingerprint in self.protected_fingerprints().items():
            try:
                other = proposed.node(node_id)
            except KeyError:
                failures.append(f"protected node removed: {node_id}")
                continue
            if other.fingerprint != fingerprint:
                failures.append(f"protected node changed: {node_id}")
        return tuple(failures)

    def progress(self) -> Mapping[str, Any]:
        values = self.nodes()
        counts = Counter(value.state.value for value in values)
        terminal = sum(counts[state.value] for state in (NodeState.VERIFIED, NodeState.SKIPPED, NodeState.FAILED, NodeState.BLOCKED))
        return {
            "nodes": len(values),
            "states": dict(sorted(counts.items())),
            "terminal_fraction": terminal / len(values) if values else 0.0,
            "verified_fraction": counts[NodeState.VERIFIED.value] / len(values) if values else 0.0,
            "frontier": [value.node_id for value in self.executable_frontier()],
            "fingerprint": self.fingerprint,
        }

    @property
    def fingerprint(self) -> str:
        with self._lock:
            return stable_fingerprint(
                {
                    "goal": self.goal.goal_id,
                    "root": self.root_id,
                    "nodes": sorted((node.node_id, node.fingerprint) for node in self._nodes.values()),
                    "children": {key: tuple(values) for key, values in sorted(self._children.items())},
                }
            )

    @staticmethod
    def _intersect_budget(left: ResourceEnvelope, right: ResourceEnvelope) -> ResourceEnvelope:
        costs = [value for value in (left.max_cost, right.max_cost) if value > 0]
        return ResourceEnvelope(
            max_steps=min(left.max_steps, right.max_steps),
            max_model_calls=min(left.max_model_calls, right.max_model_calls),
            max_tool_calls=min(left.max_tool_calls, right.max_tool_calls),
            max_tokens=min(left.max_tokens, right.max_tokens),
            max_wall_seconds=min(left.max_wall_seconds, right.max_wall_seconds),
            max_cost=min(costs) if costs else 0.0,
        )

    def _dependencies_satisfied(self, node: HierarchyNode) -> bool:
        return all(self._nodes[dependency].state in {NodeState.VERIFIED, NodeState.SKIPPED} for dependency in node.dependencies if dependency in self._nodes)

    def _propagate_parent_completion(self, parent_id: str | None) -> None:
        while parent_id is not None:
            parent = self._nodes[parent_id]
            children = [self._nodes[value] for value in self._children.get(parent_id, ())]
            if children and all(value.state in {NodeState.VERIFIED, NodeState.SKIPPED} for value in children):
                self._nodes[parent_id] = replace(parent, state=NodeState.VERIFIED)
                self._history.append((self._clock(), "auto-verified", parent_id))
                parent_id = parent.parent_id
            else:
                break

    def _propagate_blocking(self, node_id: str) -> None:
        queue = deque([node_id])
        while queue:
            failed_id = queue.popleft()
            for candidate in list(self._nodes.values()):
                if failed_id in candidate.dependencies and candidate.state not in {NodeState.VERIFIED, NodeState.SKIPPED, NodeState.FAILED, NodeState.BLOCKED}:
                    self._nodes[candidate.node_id] = replace(candidate, state=NodeState.BLOCKED)
                    self._history.append((self._clock(), "auto-blocked", candidate.node_id))
                    queue.append(candidate.node_id)

    def _reject_cycles(self) -> None:
        graph: dict[str, set[str]] = {}
        for node in self._nodes.values():
            deps = set(node.dependencies)
            if node.parent_id is not None:
                # parent-child is hierarchy, not execution dependency; include
                # only as a one-way structural edge for cycle detection.
                deps.add(node.parent_id)
            graph[node.node_id] = deps
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node_id: str) -> None:
            if node_id in visiting:
                raise HierarchicalPlanningError("hierarchical plan contains a cycle")
            if node_id in visited:
                return
            visiting.add(node_id)
            for dependency in graph.get(node_id, ()):
                if dependency in graph:
                    visit(dependency)
            visiting.remove(node_id)
            visited.add(node_id)

        for node_id in graph:
            visit(node_id)


@dataclass(frozen=True, slots=True)
class PortfolioCandidate:
    candidate_id: str
    plan: HierarchicalPlan
    expected_success: float
    expected_cost: float
    expected_latency: float
    novelty: float
    risk: float
    score: float
    rationale: str


class PlanPortfolio:
    """Keep diverse strategic alternatives without executing them all."""

    def __init__(self, *, maximum_candidates: int = 8) -> None:
        self.maximum_candidates = positive_int("maximum_candidates", maximum_candidates, maximum=64)
        self._candidates: dict[str, PortfolioCandidate] = {}
        self._lock = threading.RLock()

    def add(
        self,
        plan: HierarchicalPlan,
        *,
        expected_success: float,
        expected_cost: float = 0.0,
        expected_latency: float = 0.0,
        novelty: float = 0.5,
        risk: float = 0.0,
        rationale: str = "",
    ) -> PortfolioCandidate:
        success = probability("expected_success", expected_success)
        novelty = probability("novelty", novelty)
        risk = probability("risk", risk)
        cost = max(0.0, finite_number("expected_cost", expected_cost))
        latency = max(0.0, finite_number("expected_latency", expected_latency))
        score = success * 0.55 + novelty * 0.15 - risk * 0.20 - min(1.0, cost / (1.0 + cost)) * 0.05 - min(1.0, latency / (1000.0 + latency)) * 0.05
        payload = {"plan": plan.fingerprint, "success": success, "cost": cost, "latency": latency, "novelty": novelty, "risk": risk}
        candidate = PortfolioCandidate(stable_id("portfolio", payload), plan, success, cost, latency, novelty, risk, score, bounded_text("rationale", rationale, maximum=4096, allow_empty=True))
        with self._lock:
            self._candidates[candidate.candidate_id] = candidate
            if len(self._candidates) > self.maximum_candidates:
                keep = self.ranked()[: self.maximum_candidates]
                self._candidates = {value.candidate_id: value for value in keep}
        return candidate

    def ranked(self) -> tuple[PortfolioCandidate, ...]:
        with self._lock:
            values = list(self._candidates.values())
        values.sort(key=lambda value: (value.score, value.expected_success, value.novelty, -value.risk, value.candidate_id), reverse=True)
        return tuple(values)

    def diverse(self, *, limit: int = 4, minimum_distance: float = 0.20) -> tuple[PortfolioCandidate, ...]:
        limit = positive_int("limit", limit, maximum=64)
        minimum_distance = probability("minimum_distance", minimum_distance)
        selected: list[PortfolioCandidate] = []
        for candidate in self.ranked():
            if all(self._distance(candidate, existing) >= minimum_distance for existing in selected):
                selected.append(candidate)
            if len(selected) >= limit:
                break
        return tuple(selected)

    @staticmethod
    def _distance(left: PortfolioCandidate, right: PortfolioCandidate) -> float:
        left_tools = {node.tool for node in left.plan.nodes() if node.tool}
        right_tools = {node.tool for node in right.plan.nodes() if node.tool}
        union = left_tools | right_tools
        tool_distance = 1.0 - (len(left_tools & right_tools) / len(union) if union else 1.0)
        structure_distance = 1.0 if left.plan.fingerprint != right.plan.fingerprint else 0.0
        return tool_distance * 0.55 + structure_distance * 0.45


class HierarchicalPlanner:
    def __init__(
        self,
        generator: RefinementGenerator,
        *,
        controller: RollingHorizonController | None = None,
        policy: RefinementPolicy | None = None,
    ) -> None:
        if not callable(generator):
            raise TypeError("generator must be callable")
        self.generator = generator
        self.policy = policy or RefinementPolicy()
        self.controller = controller or RollingHorizonController(self.policy)

    def refine_frontier(self, plan: HierarchicalPlan, *, budget_fraction_remaining: float = 1.0, max_refinements: int = 8) -> tuple[str, ...]:
        if not isinstance(plan, HierarchicalPlan):
            raise TypeError("plan must be HierarchicalPlan")
        max_refinements = positive_int("max_refinements", max_refinements, maximum=1000)
        refined: list[str] = []
        candidates = sorted(plan.nodes(), key=lambda node: (plan.distance_to_frontier(node.node_id), -node.priority, -node.utility, node.node_id))
        for node in candidates:
            if len(refined) >= max_refinements:
                break
            decision = self.controller.decide(node, distance_from_frontier=plan.distance_to_frontier(node.node_id), budget_fraction_remaining=budget_fraction_remaining)
            if not decision.refine:
                continue
            proposal = self.generator(node, plan.inherited_constraints(node.node_id), decision.target_depth)
            if proposal.confidence < self.policy.minimum_refinement_confidence:
                continue
            plan.apply_refinement(proposal, minimum_confidence=self.policy.minimum_refinement_confidence, maximum_children=self.policy.maximum_children)
            refined.append(node.node_id)
        return tuple(refined)


def make_node(
    *,
    parent: HierarchyNode,
    kind: NodeKind,
    title: str,
    objective: str,
    index: int,
    dependencies: Sequence[str] = (),
    risk: RiskTier = RiskTier.READ_ONLY,
    priority: float = 0.5,
    utility: float = 0.5,
    uncertainty: float = 0.5,
    novelty: float = 0.5,
    tool: str | None = None,
    arguments: Mapping[str, Any] | None = None,
    expected_outcome: str = "",
    verification: str = "",
    constraints: Sequence[PlanConstraint] = (),
    success_predicates: Sequence[SuccessPredicate] = (),
    metadata: Mapping[str, Any] | None = None,
) -> HierarchyNode:
    payload = {"parent": parent.node_id, "index": index, "kind": kind.value, "title": title, "objective": objective}
    return HierarchyNode(
        node_id=stable_id("hnode", payload),
        kind=kind,
        title=title,
        objective=objective,
        parent_id=parent.node_id,
        dependencies=tuple(dependencies),
        constraints=tuple(constraints),
        success_predicates=tuple(success_predicates),
        risk=risk,
        depth=parent.depth + 1,
        priority=priority,
        utility=utility,
        uncertainty=uncertainty,
        novelty=novelty,
        budget=parent.budget.scaled(0.5),
        tool=tool,
        arguments=arguments or {},
        expected_outcome=expected_outcome,
        verification=verification,
        metadata=metadata or {},
    )
