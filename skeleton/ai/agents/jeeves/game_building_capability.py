"""Game Building, Design, and Story Capability v1 — integrated with 169+ emulator fleet.

Enables the local model to orchestrate full game creation pipelines:
world/level design, narrative/story/quests/dialogue, asset planning,
hardware-era targeting (via emulator cores), and export of design docs.
Read-only on emulator fleet; never executes native code or downloads assets.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    from .local_model_console_capability_v2 import make_capability_v2
except ImportError:
    make_capability_v2 = None  # type: ignore


GAME_SCHEMA = "skeleton.local_model.game_building_capability.v1"
MAX_PROMPT = 32768


@dataclass
class DesignBrief:
    title: str
    genre: str
    era: str
    target_cores: list[str]
    pillars: list[str]
    constraints: list[str]


class GameBuildingCapability:
    """Full capability surface for game building, design, and story, grounded in the emulator fleet."""

    def __init__(self, fleet_db: str | Path | None = None):
        self.fleet = None
        if make_capability_v2 and fleet_db:
            self.fleet = make_capability_v2(fleet_db)
        elif make_capability_v2:
            self.fleet = make_capability_v2(Path(__file__).parent / "fleet_database_v3.json")
        self._genres = [
            "platformer", "rpg", "adventure", "shooter", "puzzle", "racing",
            "fighting", "strategy", "simulation", "horror", "metroidvania",
            "roguelike", "visual-novel", "rhythm", "sports", "educational"
        ]
        self._eras = ["8bit", "16bit", "32bit", "64bit", "handheld", "arcade", "pc", "modern", "fantasy"]

    def available_genres(self) -> list[str]:
        return self._genres

    def available_eras(self) -> list[str]:
        return self._eras

    def recommend_cores_for_era(self, era: str, limit: int = 8) -> list[str]:
        if not self.fleet:
            return []
        recs = self.fleet.filter(era=era)
        return [r.name for r in recs[:limit]]

    def design_brief(
        self,
        title: str,
        genre: str,
        era: str = "16bit",
        pillars: list[str] | None = None,
    ) -> DesignBrief:
        cores = self.recommend_cores_for_era(era, 5)
        return DesignBrief(
            title=title,
            genre=genre,
            era=era,
            target_cores=cores,
            pillars=pillars or ["tight controls", "readable feedback", "satisfying progression"],
            constraints=[
                "operator-approved content only",
                "no native execution in this layer",
                "hardware limits of target era must be respected in design",
                "story and levels must be expressible in data catalogs",
            ],
        )

    def generate_level_outline(self, brief: DesignBrief, rooms: int = 8) -> dict[str, Any]:
        return {
            "title": brief.title,
            "genre": brief.genre,
            "era": brief.era,
            "target_cores": brief.target_cores,
            "structure": "hub-and-spoke" if brief.genre in ("metroidvania", "rpg") else "linear-with-secrets",
            "rooms": rooms,
            "key_beats": [
                "tutorial introduction of core verb",
                "first major obstacle",
                "mid-point twist or new mechanic",
                "climax confrontation",
                "resolution and reward",
            ],
            "pacing_notes": "Respect era hardware: limited sprites, palette, and resolution.",
        }

    def generate_story_arc(self, brief: DesignBrief, acts: int = 3) -> dict[str, Any]:
        return {
            "title": brief.title,
            "genre": brief.genre,
            "acts": acts,
            "themes": brief.pillars,
            "protagonist": "player avatar with clear goal",
            "antagonist": "opposing force tied to world rules",
            "arc": [
                {"act": 1, "focus": "setup and call to adventure"},
                {"act": 2, "focus": "rising complications and midpoint reversal"},
                {"act": 3, "focus": "climax and resolution"},
            ][:acts],
            "dialogue_style": "era-appropriate (sparse text for 8/16-bit, richer for later)",
            "quest_hooks": [
                "retrieve lost artifact",
                "rescue companion",
                "uncover hidden truth",
                "defeat recurring boss",
            ],
        }

    def generate_dialogue_tree(self, npc: str, topic: str) -> dict[str, Any]:
        return {
            "npc": npc,
            "topic": topic,
            "nodes": [
                {"id": "greeting", "text": f"Hello, traveler. What do you seek regarding {topic}?", "choices": ["ask_more", "leave"]},
                {"id": "ask_more", "text": "There is an old tale... but it will cost you.", "choices": ["accept", "decline"]},
                {"id": "accept", "text": "Very well. Listen closely.", "choices": ["end"]},
                {"id": "decline", "text": "Perhaps another time.", "choices": ["end"]},
                {"id": "leave", "text": "Safe travels.", "choices": ["end"]},
                {"id": "end", "text": "", "choices": []},
            ],
        }

    def asset_plan(self, brief: DesignBrief) -> dict[str, Any]:
        return {
            "title": brief.title,
            "era": brief.era,
            "sprites": "character, enemies, tiles, UI — palette-limited for early eras",
            "audio": "chiptune or limited samples matching hardware",
            "levels": "tilemaps or room graphs exportable to data catalogs",
            "story_data": "dialogue trees, quest flags, cutscene scripts as JSON/YAML",
            "provenance": "all assets must carry source identity; no unlicensed fetches",
        }

    def full_pipeline(self, title: str, genre: str, era: str = "16bit") -> dict[str, Any]:
        brief = self.design_brief(title, genre, era)
        return {
            "schema": GAME_SCHEMA,
            "brief": brief.__dict__,
            "level_outline": self.generate_level_outline(brief),
            "story_arc": self.generate_story_arc(brief),
            "asset_plan": self.asset_plan(brief),
            "sample_dialogue": self.generate_dialogue_tree("Elder", "the ancient prophecy"),
            "next_steps": [
                "operator reviews brief and constraints",
                "export data catalogs for GameForge / world.tscn style packs",
                "target specific cores from the 169+ fleet for testing",
                "iterate via local model tool calls",
            ],
        }

    def curriculum_game_design(self, stages: int = 5) -> list[dict[str, Any]]:
        stages_data = [
            {"stage": 1, "focus": "single-screen puzzle or platformer", "era": "8bit", "cores": ["fceumm", "gambatte"]},
            {"stage": 2, "focus": "multi-room adventure with simple story", "era": "16bit", "cores": ["snes9x", "genesis_plus_gx"]},
            {"stage": 3, "focus": "hub world + quests", "era": "16bit", "cores": ["bsnes", "mgba"]},
            {"stage": 4, "focus": "narrative-heavy with dialogue trees", "era": "32bit", "cores": ["pcsx_rearmed", "ppsspp"]},
            {"stage": 5, "focus": "full pipeline export to data catalogs", "era": "any", "cores": ["any qualified"]},
        ]
        return stages_data[:stages]

    def model_card(self) -> str:
        fleet_note = ""
        if self.fleet:
            s = self.fleet.fleet_summary()
            fleet_note = f" Grounded in {s['total_declared_cores']} declared emulator cores."
        return (
            f"You have a full game-building, design, and story capability.{fleet_note} "
            f"Use game_building_capability to create design briefs, level outlines, story arcs, "
            f"dialogue trees, asset plans, and complete pipelines targeted at specific hardware eras. "
            f"All output is data-only; native testing stays in the isolated emulator host."
        )

    def inject_into_prompt(self, prompt: str) -> str:
        card = f"[GAME_BUILDING_CAPABILITY schema={GAME_SCHEMA}]\n{self.model_card()}\n"
        combined = card + "\n" + prompt
        return combined[:MAX_PROMPT]

    def build_tool_schema(self) -> dict[str, Any]:
        return {
            "name": "game_building_capability",
            "description": "Design games, levels, stories, dialogue, and asset plans targeted at the 169+ emulator fleet.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": [
                            "design_brief", "generate_level_outline", "generate_story_arc",
                            "generate_dialogue_tree", "asset_plan", "full_pipeline",
                            "curriculum_game_design", "recommend_cores_for_era", "model_card",
                        ],
                    },
                    "title": {"type": "string"},
                    "genre": {"type": "string"},
                    "era": {"type": "string"},
                    "npc": {"type": "string"},
                    "topic": {"type": "string"},
                    "rooms": {"type": "integer"},
                    "acts": {"type": "integer"},
                },
                "required": ["action"],
            },
        }

    def dispatch(self, action: str, **kwargs: Any) -> Any:
        if action == "design_brief":
            b = self.design_brief(kwargs.get("title", "Untitled"), kwargs.get("genre", "platformer"), kwargs.get("era", "16bit"))
            return b.__dict__
        if action == "full_pipeline":
            return self.full_pipeline(kwargs.get("title", "Untitled"), kwargs.get("genre", "platformer"), kwargs.get("era", "16bit"))
        if action == "generate_story_arc":
            b = self.design_brief(kwargs.get("title", "Untitled"), kwargs.get("genre", "rpg"), kwargs.get("era", "16bit"))
            return self.generate_story_arc(b, kwargs.get("acts", 3))
        if action == "generate_dialogue_tree":
            return self.generate_dialogue_tree(kwargs.get("npc", "NPC"), kwargs.get("topic", "quest"))
        if action == "curriculum_game_design":
            return self.curriculum_game_design()
        if action == "recommend_cores_for_era":
            return self.recommend_cores_for_era(kwargs.get("era", "16bit"))
        if action == "model_card":
            return self.model_card()
        return {"error": "unknown_action"}


def make_game_capability(fleet_db: str | Path | None = None) -> GameBuildingCapability:
    return GameBuildingCapability(fleet_db)
