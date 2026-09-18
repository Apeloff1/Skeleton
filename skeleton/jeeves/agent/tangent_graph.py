"""Durable tangent and perpendicular-exploration graph for Jeeves.

Deep reasoning loses value when every replan/restart collapses onto the current
main line.  This module preserves side directions as explicit hypotheses with
parents, triggers, expected value, novelty, evidence gaps, and lifecycle state.

A tangent is never truth.  It is a *deferred research direction*.  The graph is
therefore safe to serialize into checkpoints and rehydrate after replanning,
provider failover, or context compaction without promoting speculative content
into durable semantic memory.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Iterable, Mapping, Sequence

from .semantic_lenses import LensFamily, TangentSeed
from .types import AgentContractError, bounded_text, json_safe, positive_int, probability, stable_fingerprint, stable_id


class TangentState(str, Enum):
    OPEN = "open"
    ACTIVE = "active"
    PARKED = "parked"
    SUPPORTED = "supported"
    FALSIFIED = "falsified"
    PROMOTED = "promoted"


class ExplorationAxis(str, Enum):
    CAUSAL = "causal"
    PROBABILISTIC = "probabilistic"
    TEMPORAL = "temporal"
    SEMANTIC = "semantic"
    CINEMATIC = "cinematic"
    LITERARY = "literary"
    LUDIC = "ludic"
    SOCIAL = "social"
    ADVERSARIAL = "adversarial"
    SYSTEM = "system"
    MEMORY = "memory"
    COMPILER = "compiler"


@dataclass(frozen=True, slots=True)
class TangentNode:
    tangent_id: str
    parent_id: str | None
    root_fingerprint: str
    axis: ExplorationAxis
    family: LensFamily | None
    lens_key: str
    direction: str
    rationale: str
    state: TangentState = TangentState.OPEN
    novelty: float = 0.5
    expected_value: float = 0.5
    evidence_gap: float = 0.5
    risk: float = 0.0
    depth: int = 0
    created_sequence: int = 0
    last_touched_sequence: int = 0
    activation_count: int = 0
    evidence_ids: tuple[str, ...] = ()
    trigger_terms: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not str(self.tangent_id).strip() or not str(self.root_fingerprint).strip():
            raise AgentContractError("tangent node requires tangent_id and root_fingerprint")
        if self.parent_id is not None and not str(self.parent_id).strip():
            raise AgentContractError("parent_id cannot be blank")
        if not isinstance(self.axis, ExplorationAxis):
            object.__setattr__(self, "axis", ExplorationAxis(str(self.axis)))
        if self.family is not None and not isinstance(self.family, LensFamily):
            object.__setattr__(self, "family", LensFamily(str(self.family)))
        if not isinstance(self.state, TangentState):
            object.__setattr__(self, "state", TangentState(str(self.state)))
        object.__setattr__(self, "lens_key", str(self.lens_key).strip().casefold())
        object.__setattr__(self, "direction", bounded_text("tangent direction", self.direction, maximum=8192))
        object.__setattr__(self, "rationale", bounded_text("tangent rationale", self.rationale, maximum=8192))
        for name in ("novelty", "expected_value", "evidence_gap", "risk"):
            object.__setattr__(self, name, probability(name, getattr(self, name)))
        for name in ("depth", "created_sequence", "last_touched_sequence", "activation_count"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise AgentContractError(f"{name} must be non-negative integer")
        object.__setattr__(self, "evidence_ids", tuple(sorted({str(x) for x in self.evidence_ids if str(x)})))
        object.__setattr__(self, "trigger_terms", tuple(sorted({str(x).casefold() for x in self.trigger_terms if str(x).strip()})))
        object.__setattr__(self, "tags", tuple(sorted({str(x).casefold() for x in self.tags if str(x).strip()})))
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "parent": self.parent_id,
                "root": self.root_fingerprint,
                "axis": self.axis.value,
                "family": self.family.value if self.family else None,
                "lens": self.lens_key,
                "direction": self.direction,
                "rationale": self.rationale,
                "state": self.state.value,
                "evidence": self.evidence_ids,
            }
        )

    @property
    def priority(self) -> float:
        state_multiplier = {
            TangentState.OPEN: 1.0,
            TangentState.ACTIVE: 1.15,
            TangentState.PARKED: 0.65,
            TangentState.SUPPORTED: 0.8,
            TangentState.FALSIFIED: 0.0,
            TangentState.PROMOTED: 0.15,
        }[self.state]
        return max(
            0.0,
            min(
                1.0,
                state_multiplier
                * (
                    0.30 * self.expected_value
                    + 0.25 * self.novelty
                    + 0.25 * self.evidence_gap
                    + 0.15 * (1.0 - self.risk)
                    + 0.05 * min(1.0, self.activation_count / 4.0)
                ),
            ),
        )


@dataclass(frozen=True, slots=True)
class FrontierSelection:
    tangent_ids: tuple[str, ...]
    axes: tuple[ExplorationAxis, ...]
    families: tuple[LensFamily, ...]
    omitted_due_to_budget: tuple[str, ...]
    fingerprint: str


@dataclass(frozen=True, slots=True)
class RestartContinuityBundle:
    root_fingerprint: str
    sequence: int
    active_ids: tuple[str, ...]
    open_ids: tuple[str, ...]
    parked_ids: tuple[str, ...]
    promoted_ids: tuple[str, ...]
    graph_fingerprint: str
    notes: str = ""


class TangentGraph:
    """In-memory reference graph with deterministic serialization semantics."""

    def __init__(self, nodes: Iterable[TangentNode] = ()) -> None:
        self._nodes: dict[str, TangentNode] = {}
        self._children: defaultdict[str, set[str]] = defaultdict(set)
        for node in nodes:
            self.add(node)

    def add(self, node: TangentNode) -> TangentNode:
        if not isinstance(node, TangentNode):
            raise TypeError("node must be TangentNode")
        existing = self._nodes.get(node.tangent_id)
        if existing is not None:
            if existing.fingerprint != node.fingerprint:
                raise AgentContractError(f"tangent id collision: {node.tangent_id}")
            return existing
        if node.parent_id is not None:
            parent = self._nodes.get(node.parent_id)
            if parent is None:
                raise AgentContractError("parent tangent must exist before child")
            if node.depth != parent.depth + 1:
                raise AgentContractError("child tangent depth mismatch")
            if node.root_fingerprint != parent.root_fingerprint:
                raise AgentContractError("child tangent root mismatch")
            self._children[parent.tangent_id].add(node.tangent_id)
        self._nodes[node.tangent_id] = node
        return node

    def add_seed(
        self,
        seed: TangentSeed,
        *,
        axis: ExplorationAxis,
        family: LensFamily | None,
        parent_id: str | None = None,
        sequence: int = 0,
        trigger_terms: Sequence[str] = (),
        risk: float = 0.0,
        evidence_gap: float = 0.7,
    ) -> TangentNode:
        if not isinstance(seed, TangentSeed):
            raise TypeError("seed must be TangentSeed")
        depth = 0
        if parent_id is not None:
            parent = self._nodes.get(parent_id)
            if parent is None:
                raise AgentContractError("unknown parent tangent")
            depth = parent.depth + 1
        tangent_id = stable_id(
            "tangent",
            {
                "seed": seed.seed_id,
                "parent": parent_id,
                "root": seed.parent_fingerprint,
                "axis": axis.value,
                "direction": seed.direction,
            },
            length=32,
        )
        return self.add(
            TangentNode(
                tangent_id=tangent_id,
                parent_id=parent_id,
                root_fingerprint=seed.parent_fingerprint,
                axis=axis,
                family=family,
                lens_key=seed.lens_key,
                direction=seed.direction,
                rationale=seed.rationale,
                novelty=seed.novelty,
                expected_value=seed.expected_value,
                evidence_gap=evidence_gap,
                risk=risk,
                depth=depth,
                created_sequence=sequence,
                last_touched_sequence=sequence,
                evidence_ids=seed.evidence_ids,
                trigger_terms=tuple(trigger_terms),
                tags=seed.tags,
            )
        )

    def get(self, tangent_id: str) -> TangentNode | None:
        return self._nodes.get(str(tangent_id))

    def update_state(
        self,
        tangent_id: str,
        state: TangentState,
        *,
        sequence: int,
        evidence_ids: Sequence[str] = (),
        expected_value: float | None = None,
        evidence_gap: float | None = None,
        risk: float | None = None,
    ) -> TangentNode:
        node = self._nodes[str(tangent_id)]
        if not isinstance(state, TangentState):
            state = TangentState(str(state))
        updates: dict[str, Any] = {
            "state": state,
            "last_touched_sequence": sequence,
            "activation_count": node.activation_count + (1 if state is TangentState.ACTIVE else 0),
            "evidence_ids": tuple(sorted(set(node.evidence_ids) | {str(x) for x in evidence_ids if str(x)})),
        }
        if expected_value is not None:
            updates["expected_value"] = probability("expected_value", expected_value)
        if evidence_gap is not None:
            updates["evidence_gap"] = probability("evidence_gap", evidence_gap)
        if risk is not None:
            updates["risk"] = probability("risk", risk)
        updated = replace(node, **updates)
        self._nodes[node.tangent_id] = updated
        return updated

    def reactivate_by_terms(self, terms: Sequence[str], *, sequence: int) -> tuple[TangentNode, ...]:
        cues = {str(term).casefold() for term in terms if str(term).strip()}
        activated: list[TangentNode] = []
        for node in sorted(self._nodes.values(), key=lambda item: item.tangent_id):
            if node.state not in {TangentState.OPEN, TangentState.PARKED}:
                continue
            if not cues.intersection(node.trigger_terms):
                continue
            updated = replace(
                node,
                state=TangentState.ACTIVE,
                last_touched_sequence=sequence,
                activation_count=node.activation_count + 1,
            )
            self._nodes[node.tangent_id] = updated
            activated.append(updated)
        return tuple(activated)

    def frontier(
        self,
        *,
        limit: int = 8,
        max_per_axis: int = 2,
        max_per_family: int = 2,
        include_parked: bool = False,
    ) -> FrontierSelection:
        limit = positive_int("limit", limit, maximum=1000)
        max_per_axis = positive_int("max_per_axis", max_per_axis, maximum=100)
        max_per_family = positive_int("max_per_family", max_per_family, maximum=100)
        allowed = {TangentState.OPEN, TangentState.ACTIVE}
        if include_parked:
            allowed.add(TangentState.PARKED)
        candidates = [node for node in self._nodes.values() if node.state in allowed]
        candidates.sort(key=lambda node: (-node.priority, node.depth, node.created_sequence, node.tangent_id))
        selected: list[TangentNode] = []
        omitted: list[str] = []
        axis_count: defaultdict[ExplorationAxis, int] = defaultdict(int)
        family_count: defaultdict[LensFamily, int] = defaultdict(int)

        # Perpendicular first pass: maximize axis diversity before taking siblings.
        used_axes: set[ExplorationAxis] = set()
        for node in candidates:
            if len(selected) >= limit:
                break
            if node.axis in used_axes:
                continue
            if node.family is not None and family_count[node.family] >= max_per_family:
                continue
            selected.append(node)
            used_axes.add(node.axis)
            axis_count[node.axis] += 1
            if node.family is not None:
                family_count[node.family] += 1

        selected_ids = {node.tangent_id for node in selected}
        for node in candidates:
            if node.tangent_id in selected_ids:
                continue
            if len(selected) >= limit:
                omitted.append(node.tangent_id)
                continue
            if axis_count[node.axis] >= max_per_axis:
                omitted.append(node.tangent_id)
                continue
            if node.family is not None and family_count[node.family] >= max_per_family:
                omitted.append(node.tangent_id)
                continue
            selected.append(node)
            selected_ids.add(node.tangent_id)
            axis_count[node.axis] += 1
            if node.family is not None:
                family_count[node.family] += 1

        fingerprint = stable_fingerprint(
            {
                "selected": [(node.tangent_id, round(node.priority, 12), node.fingerprint) for node in selected],
                "omitted": sorted(omitted),
            }
        )
        return FrontierSelection(
            tangent_ids=tuple(node.tangent_id for node in selected),
            axes=tuple(sorted({node.axis for node in selected}, key=lambda item: item.value)),
            families=tuple(sorted({node.family for node in selected if node.family is not None}, key=lambda item: item.value)),
            omitted_due_to_budget=tuple(sorted(omitted)),
            fingerprint=fingerprint,
        )

    def checkpoint(self, *, root_fingerprint: str, sequence: int, notes: str = "") -> RestartContinuityBundle:
        matching = [node for node in self._nodes.values() if node.root_fingerprint == root_fingerprint]
        by_state: defaultdict[TangentState, list[str]] = defaultdict(list)
        for node in matching:
            by_state[node.state].append(node.tangent_id)
        return RestartContinuityBundle(
            root_fingerprint=root_fingerprint,
            sequence=sequence,
            active_ids=tuple(sorted(by_state[TangentState.ACTIVE])),
            open_ids=tuple(sorted(by_state[TangentState.OPEN])),
            parked_ids=tuple(sorted(by_state[TangentState.PARKED])),
            promoted_ids=tuple(sorted(by_state[TangentState.PROMOTED])),
            graph_fingerprint=self.fingerprint,
            notes=bounded_text("continuity notes", notes, maximum=8192, allow_empty=True),
        )

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            [(node.tangent_id, node.fingerprint, round(node.priority, 12)) for node in sorted(self._nodes.values(), key=lambda x: x.tangent_id)]
        )

    def snapshot(self) -> tuple[TangentNode, ...]:
        return tuple(sorted(self._nodes.values(), key=lambda node: (node.depth, node.created_sequence, node.tangent_id)))
