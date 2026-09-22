"""Reusable interactive narrative primitives distilled from Newmove.

The source game contains large branching NPC dialogue trees with persistent
reputation changes, trust, item/quest requirements, rewards and world-state
consequences. This module keeps those AI-facing semantics without importing
FastAPI, MongoDB, or game-specific content.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class DialogueChoice:
    id: str
    text: str
    next_node: str | None = None
    effects: Mapping[str, Any] = field(default_factory=dict)
    requirements: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DialogueNode:
    id: str
    text: str
    choices: tuple[DialogueChoice, ...] = ()
    rewards: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DialogueState:
    node_id: str
    facts: Mapping[str, Any] = field(default_factory=dict)
    inventory: frozenset[str] = frozenset()
    reputation: Mapping[str, int] = field(default_factory=dict)
    trust: Mapping[str, int] = field(default_factory=dict)

    def can_choose(self, choice: DialogueChoice) -> bool:
        for key, expected in choice.requirements.items():
            if key == "item" and expected not in self.inventory:
                return False
            if key.startswith("fact:") and self.facts.get(key[5:]) != expected:
                return False
            if key.startswith("rep:") and self.reputation.get(key[4:], 0) < expected:
                return False
            if key.startswith("trust:") and self.trust.get(key[6:], 0) < expected:
                return False
        return True


class DialogueGraph:
    """Validate and traverse a deterministic branching dialogue graph."""
    def __init__(self, nodes: Mapping[str, DialogueNode]):
        self.nodes = dict(nodes)
        self.validate()

    def validate(self) -> None:
        for node in self.nodes.values():
            for choice in node.choices:
                if choice.next_node is not None and choice.next_node not in self.nodes:
                    raise ValueError(f"choice {choice.id!r} points to missing node {choice.next_node!r}")

    def available_choices(self, state: DialogueState) -> tuple[DialogueChoice, ...]:
        node = self.nodes[state.node_id]
        return tuple(c for c in node.choices if state.can_choose(c))

    def advance(self, state: DialogueState, choice_id: str) -> DialogueState:
        choice = next((c for c in self.available_choices(state) if c.id == choice_id), None)
        if choice is None:
            raise ValueError(f"choice {choice_id!r} is unavailable")
        reputation = dict(state.reputation)
        trust = dict(state.trust)
        facts = dict(state.facts)
        for key, value in choice.effects.items():
            if key.startswith("rep:"):
                faction = key[4:]
                reputation[faction] = reputation.get(faction, 0) + int(value)
            elif key.startswith("trust:"):
                npc = key[6:]
                trust[npc] = max(0, min(100, trust.get(npc, 0) + int(value)))
            elif key.startswith("fact:"):
                facts[key[5:]] = value
        return DialogueState(choice.next_node or state.node_id, facts, state.inventory, reputation, trust)


@dataclass(frozen=True)
class NpcRelationship:
    npc_id: str
    disposition: int = 0
    trust: int = 0
    memory_tags: frozenset[str] = frozenset()

    def adjust(self, *, disposition: int = 0, trust: int = 0, memory: str | None = None) -> "NpcRelationship":
        tags = set(self.memory_tags)
        if memory:
            tags.add(memory)
        return NpcRelationship(
            self.npc_id,
            max(-100, min(100, self.disposition + disposition)),
            max(0, min(100, self.trust + trust)),
            frozenset(tags),
        )

    def social_signal(self) -> str:
        if self.trust >= 80 and self.disposition >= 50:
            return "bonded"
        if self.trust >= 50:
            return "trusted"
        if self.disposition <= -50:
            return "hostile"
        if self.disposition < 0:
            return "wary"
        return "friendly"
