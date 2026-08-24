"""Dialogue-tree engine — branching NPC conversation structures.

Text-to-NPC generates the persona; this module generates what the persona
*says*: a validated, traversable dialogue tree with conditions, effects,
and fallback edges. Trees are data (JSON-serialisable), so the pipeline can
store them, the runtime can walk them, and the validator can prove them
safe before either happens.

Invariants
----------
1. Every node is reachable from the entry node (no orphan dialogue).
2. Every node has at least one outgoing edge (no dead air) — explicit
   ``terminal=True`` opts out.
3. Condition expressions are pure functions over a fact bag; they never
   touch I/O or the outside world.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from skeleton.kernel.errors import PipelineError
from skeleton.kernel.events import DomainEvent, EventBus


class DialogueError(PipelineError):
    code = "PPL.DIALOGUE"
    http_status = 422


FactBag = Dict[str, Any]
Condition = Callable[[FactBag], bool]


@dataclass
class DialogueEdge:
    """One player-facing option leading to the next node."""
    text: str
    target: str
    condition: Optional[Condition] = None     # gate: shown only if true
    effects: Dict[str, Any] = field(default_factory=dict)  # applied on choice

    def available(self, facts: FactBag) -> bool:
        return self.condition is None or self.condition(facts)


@dataclass
class DialogueNode:
    node_id: str
    speaker: str
    line: str
    edges: List[DialogueEdge] = field(default_factory=list)
    terminal: bool = False
    on_enter: Dict[str, Any] = field(default_factory=dict)  # effects on entry


@dataclass
class DialogueTree:
    """A complete, validated conversation."""
    tree_id: str
    entry: str
    nodes: Dict[str, DialogueNode]

    def validate(self) -> List[str]:
        """Return a list of structural problems; empty means valid."""
        problems: List[str] = []
        if self.entry not in self.nodes:
            problems.append(f"entry node {self.entry!r} missing")
        for nid, node in self.nodes.items():
            if not node.terminal and not node.edges:
                problems.append(f"node {nid!r} has no edges and is not terminal")
            for edge in node.edges:
                if edge.target not in self.nodes:
                    problems.append(f"node {nid!r} edge targets missing node {edge.target!r}")
        # reachability
        seen, stack = set(), [self.entry]
        while stack:
            current = stack.pop()
            if current in seen or current not in self.nodes:
                continue
            seen.add(current)
            stack.extend(e.target for e in self.nodes[current].edges)
        for nid in self.nodes:
            if nid not in seen:
                problems.append(f"node {nid!r} is unreachable from entry")
        return problems

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tree_id": self.tree_id,
            "entry": self.entry,
            "nodes": {
                nid: {
                    "speaker": n.speaker,
                    "line": n.line,
                    "terminal": n.terminal,
                    "on_enter": n.on_enter,
                    "edges": [
                        {"text": e.text, "target": e.target, "effects": e.effects}
                        for e in n.edges
                    ],
                }
                for nid, n in self.nodes.items()
            },
        }


class DialogueWalker:
    """Runtime traversal: tracks position + fact bag, applies effects."""

    def __init__(self, tree: DialogueTree, *, bus: Optional[EventBus] = None) -> None:
        problems = tree.validate()
        if problems:
            raise DialogueError(
                "dialogue tree failed validation",
                context={"tree_id": tree.tree_id, "problems": problems},
            )
        self.tree = tree
        self.node = tree.nodes[tree.entry]
        self.facts: FactBag = {}
        self._bus = bus
        self._apply(self.node.on_enter)

    def _apply(self, effects: Dict[str, Any]) -> None:
        self.facts.update(effects)

    def options(self) -> List[DialogueEdge]:
        """Currently visible choices, in authored order."""
        return [e for e in self.node.edges if e.available(self.facts)]

    def choose(self, index: int) -> DialogueNode:
        """Take the index-th visible option; returns the new node."""
        visible = self.options()
        if not 0 <= index < len(visible):
            raise DialogueError(
                "choice index out of range",
                context={"index": index, "visible": len(visible), "node": self.node.node_id},
            )
        edge = visible[index]
        self._apply(edge.effects)
        self.node = self.tree.nodes[edge.target]
        self._apply(self.node.on_enter)
        if self._bus:
            self._bus.publish(
                DomainEvent(
                    topic="pipeline.dialogue.advanced",
                    payload={
                        "tree_id": self.tree.tree_id,
                        "node": self.node.node_id,
                        "terminal": self.node.terminal,
                    },
                    correlation_id=f"dlg_{self.tree.tree_id}",
                )
            )
        return self.node

    @property
    def finished(self) -> bool:
        return self.node.terminal
