"""Consequence-driven dialogue graph for generated NPC interactions.

Turns relationship-aware dialogue ideas into deterministic domain rules. Choices
can require relationship/stat/unlock conditions and apply relationship, currency,
item, quest and unlock effects without depending on UI or persistence.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping


class DialogueError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class DialogueEffect:
    relationship_delta: int = 0
    currency_delta: int = 0
    grant_items: tuple[str, ...] = ()
    grant_unlocks: tuple[str, ...] = ()
    start_quests: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DialogueChoice:
    id: str
    text: str
    next_node: str | None
    min_relationship: int = -100
    required_stats: tuple[tuple[str, int], ...] = ()
    required_unlocks: tuple[str, ...] = ()
    effect: DialogueEffect = DialogueEffect()


@dataclass(frozen=True, slots=True)
class DialogueNode:
    id: str
    text: str
    choices: tuple[DialogueChoice, ...]


@dataclass(slots=True)
class DialogueContext:
    relationship: int = 0
    currency: int = 0
    stats: dict[str, int] | None = None
    inventory: dict[str, int] | None = None
    unlocks: set[str] | None = None
    quests: set[str] | None = None

    def __post_init__(self) -> None:
        self.stats = dict(self.stats or {})
        self.inventory = dict(self.inventory or {})
        self.unlocks = set(self.unlocks or ())
        self.quests = set(self.quests or ())


@dataclass(frozen=True, slots=True)
class DialogueOutcome:
    node_id: str | None
    relationship: int
    currency: int
    granted_items: tuple[str, ...]
    granted_unlocks: tuple[str, ...]
    started_quests: tuple[str, ...]


class DialogueRuntime:
    def __init__(self, nodes: Iterable[DialogueNode], *, start_node: str) -> None:
        materialized = tuple(nodes)
        self.nodes = {node.id: node for node in materialized}
        if not self.nodes or len(self.nodes) != len(materialized):
            raise DialogueError("dialogue requires unique nodes")
        if start_node not in self.nodes:
            raise DialogueError("unknown start node")
        self.start_node = start_node
        for node in self.nodes.values():
            ids = [choice.id for choice in node.choices]
            if len(ids) != len(set(ids)):
                raise DialogueError(f"duplicate choice id in {node.id}")
            for choice in node.choices:
                if choice.next_node is not None and choice.next_node not in self.nodes:
                    raise DialogueError(f"choice references unknown node: {choice.next_node}")

    @staticmethod
    def _available(choice: DialogueChoice, context: DialogueContext) -> bool:
        if context.relationship < choice.min_relationship:
            return False
        if any((context.stats or {}).get(stat, 0) < minimum for stat, minimum in choice.required_stats):
            return False
        return set(choice.required_unlocks).issubset(context.unlocks or set())

    def choices(self, node_id: str, context: DialogueContext) -> tuple[DialogueChoice, ...]:
        try:
            node = self.nodes[node_id]
        except KeyError as exc:
            raise DialogueError(f"unknown node: {node_id}") from exc
        return tuple(choice for choice in node.choices if self._available(choice, context))

    def choose(self, node_id: str, choice_id: str, context: DialogueContext) -> DialogueOutcome:
        available = {choice.id: choice for choice in self.choices(node_id, context)}
        if choice_id not in available:
            raise DialogueError("choice unavailable")
        choice = available[choice_id]
        effect = choice.effect
        next_relationship = max(-100, min(100, context.relationship + effect.relationship_delta))
        next_currency = context.currency + effect.currency_delta
        if next_currency < 0:
            raise DialogueError("dialogue consequence would overdraw currency")

        # Mutate only after all fail-closed checks pass.
        context.relationship = next_relationship
        context.currency = next_currency
        for item in effect.grant_items:
            context.inventory[item] = context.inventory.get(item, 0) + 1
        context.unlocks.update(effect.grant_unlocks)
        context.quests.update(effect.start_quests)
        return DialogueOutcome(
            choice.next_node,
            context.relationship,
            context.currency,
            effect.grant_items,
            effect.grant_unlocks,
            effect.start_quests,
        )
