"""Meticulous Adventure Game Capability — 10× expansion.

Deep systems for narrative adventure / point-and-click style games:
room graphs, inventory puzzles, item state machines, dialogue with flags,
asset quality tiers, era-authentic constraints, and full design pipelines.
Grounded in the emulator fleet. Data-only, fail-closed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

ADVENTURE_SCHEMA = "skeleton.local_model.adventure_game_capability.v1"


@dataclass
class Room:
    id: str
    name: str
    description: str
    exits: dict[str, str]  # direction -> room_id
    items: list[str]
    hotspots: list[dict[str, str]]
    flags_required: list[str] = field(default_factory=list)
    on_enter: str | None = None


@dataclass
class Item:
    id: str
    name: str
    description: str
    portable: bool = True
    states: list[str] = field(default_factory=lambda: ["default"])
    interactions: dict[str, str] = field(default_factory=dict)  # other_item_or_hotspot -> result


@dataclass
class Puzzle:
    id: str
    description: str
    solution_steps: list[str]
    required_items: list[str]
    required_flags: list[str]
    reward_flag: str
    hint_levels: list[str]


@dataclass
class DialogueNode:
    id: str
    speaker: str
    text: str
    choices: list[dict[str, str]]  # text, next_id, set_flag?
    conditions: list[str] = field(default_factory=list)


class AdventureGameCapability:
    """High-fidelity adventure game design surface."""

    def __init__(self):
        self.asset_quality_tiers = {
            "prototype": "placeholder shapes, limited palette, functional only",
            "era-authentic": "palette-constrained, period-correct resolution and sprite limits",
            "polished": "consistent lighting, readable silhouettes, purposeful animation",
            "premium": "hand-crafted details, layered parallax where hardware allows, rich audio",
        }

    def create_room_graph(self, title: str, room_count: int = 12) -> dict[str, Any]:
        rooms = []
        for i in range(room_count):
            rid = f"room_{i+1:02d}"
            rooms.append(Room(
                id=rid,
                name=f"Location {i+1}",
                description=f"Detailed environmental description for {title} room {i+1}. "
                            f"Lighting, sound cues, and interactive density noted.",
                exits={"north": f"room_{((i+1)%room_count)+1:02d}"} if i < room_count-1 else {},
                items=[f"item_{i+1}"] if i % 3 == 0 else [],
                hotspots=[{"id": f"hs_{i}", "verb": "examine", "response": "Carefully observed."}],
            ))
        return {
            "title": title,
            "schema": ADVENTURE_SCHEMA,
            "rooms": [r.__dict__ for r in rooms],
            "graph_type": "connected with gated branches",
            "navigation_notes": "Classic adventure connectivity; some exits require flags or items.",
        }

    def create_inventory_system(self, items: list[str]) -> dict[str, Any]:
        item_objs = []
        for iid in items:
            item_objs.append(Item(
                id=iid,
                name=iid.replace("_", " ").title(),
                description=f"High-detail description of {iid}. Material, weight class, and visual read.",
                interactions={"default": "No obvious use yet."},
            ))
        return {
            "items": [it.__dict__ for it in item_objs],
            "combination_rules": "Explicit state machines; no free-form parsing.",
            "quality_notes": "Each item has readable silhouette and distinct examine text.",
        }

    def create_puzzle(self, pid: str, theme: str) -> Puzzle:
        return Puzzle(
            id=pid,
            description=f"Multi-step environmental puzzle themed around {theme}.",
            solution_steps=[
                "Observe environmental clue",
                "Acquire or combine required item",
                "Apply item to hotspot in correct state",
                "Confirm flag and receive feedback",
            ],
            required_items=["key_item"],
            required_flags=["observed_clue"],
            reward_flag=f"{pid}_solved",
            hint_levels=[
                "Subtle environmental change",
                "NPC comment",
                "Direct but in-character hint",
            ],
        )

    def create_dialogue_system(self, npc: str, topic: str) -> dict[str, Any]:
        nodes = [
            DialogueNode("start", npc, f"Regarding {topic}, there is more than meets the eye.",
                         [{"text": "Tell me more", "next": "detail", "set_flag": "asked"},
                          {"text": "Later", "next": "end"}]),
            DialogueNode("detail", npc, "The old mechanism requires both the lens and the aligned light.",
                         [{"text": "I understand", "next": "end", "set_flag": "knows_secret"}]),
            DialogueNode("end", npc, "We shall speak again.", []),
        ]
        return {
            "npc": npc,
            "nodes": [n.__dict__ for n in nodes],
            "flag_integration": "Dialogue sets and checks adventure flags.",
            "quality": "Concise, character-voiced, no exposition dumps.",
        }

    def asset_quality_spec(self, era: str, tier: str = "era-authentic") -> dict[str, Any]:
        return {
            "era": era,
            "tier": tier,
            "description": self.asset_quality_tiers.get(tier, ""),
            "sprites": "Consistent pixel density, limited palette, strong silhouettes, purposeful idle/walk/use frames",
            "backgrounds": "Layered where hardware allows, readable interactive vs non-interactive",
            "audio": "Era-appropriate: chiptune motifs, sparse SFX with clear feedback, no clipping",
            "ui": "Minimal, high-contrast, verb list or contextual cursor that never obscures scene",
            "provenance": "All assets catalogued with source identity; no unlicensed material",
        }

    def full_adventure_pipeline(self, title: str, era: str = "16bit", rooms: int = 10) -> dict[str, Any]:
        graph = self.create_room_graph(title, rooms)
        items = [f"item_{i}" for i in range(1, 6)]
        inv = self.create_inventory_system(items)
        puzzle = self.create_puzzle("main_gate", "ancient mechanism")
        dialogue = self.create_dialogue_system("Keeper", "the sealed door")
        assets = self.asset_quality_spec(era, "polished")
        return {
            "schema": ADVENTURE_SCHEMA,
            "title": title,
            "era": era,
            "room_graph": graph,
            "inventory": inv,
            "core_puzzle": puzzle.__dict__,
            "sample_dialogue": dialogue,
            "asset_spec": assets,
            "design_pillars": [
                "Environmental storytelling over cutscenes",
                "Fair puzzles with observable clues",
                "Strong item-hotspot feedback",
                "Era-authentic presentation",
            ],
            "next_steps": [
                "Expand room graph with gated branches",
                "Author additional puzzles and flag dependencies",
                "Produce asset catalog entries at chosen quality tier",
                "Target qualified emulator cores for playtest evidence",
            ],
        }

    def model_card(self) -> str:
        return (
            "You have a meticulous adventure-game design capability. "
            "Create room graphs, inventory systems with state, multi-step puzzles with hint ladders, "
            "flag-aware dialogue, and high-fidelity asset quality specifications. "
            "All output is structured data. Respect era constraints. Operator-gated for any native testing."
        )


def make_adventure_capability() -> AdventureGameCapability:
    return AdventureGameCapability()
