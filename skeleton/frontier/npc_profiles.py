"""Structured NPC profiles promoted from the Prood/Tutolage NPC pipeline.

Lineage: Apeloff1/Prood backend/routes/npc_pipeline.py. Only the reusable
semantic layer is promoted; FastAPI, vendor LLM calls, and transport models
remain outside the frontier kernel.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True, slots=True)
class ArchetypeProfile:
    archetype: str
    stats: Mapping[str, int]
    skills: tuple[str, ...]
    behavior_patterns: tuple[str, ...]
    dialogue_topics: tuple[str, ...]


PROFILES: dict[str, ArchetypeProfile] = {
    "merchant": ArchetypeProfile("merchant", {"charisma": 14, "intelligence": 12, "wisdom": 10}, ("persuasion", "appraisal", "negotiation"), ("haggle", "showcase_goods", "gossip"), ("prices", "goods", "rumors", "trade_routes")),
    "warrior": ArchetypeProfile("warrior", {"strength": 16, "constitution": 14, "dexterity": 12}, ("combat", "tactics", "weapon_mastery"), ("patrol", "challenge", "protect"), ("battles", "honor", "training", "enemies")),
    "mage": ArchetypeProfile("mage", {"intelligence": 18, "wisdom": 14, "charisma": 10}, ("arcana", "spellcasting", "alchemy"), ("study", "experiment", "lecture"), ("magic", "research", "mysteries", "artifacts")),
    "mentor": ArchetypeProfile("mentor", {"wisdom": 18, "intelligence": 16, "charisma": 14}, ("teaching", "guidance", "insight"), ("observe", "advise", "test", "encourage"), ("lessons", "growth", "challenges", "wisdom")),
    "villain": ArchetypeProfile("villain", {"intelligence": 16, "charisma": 14, "wisdom": 12}, ("manipulation", "intimidation", "deception"), ("scheme", "threaten", "manipulate"), ("power", "revenge", "control", "superiority")),
}


def get_profile(archetype: str) -> ArchetypeProfile:
    key = archetype.strip().lower()
    try:
        return PROFILES[key]
    except KeyError as exc:
        raise ValueError(f"unknown NPC archetype: {archetype!r}") from exc


def infer_archetype(description: str) -> str | None:
    text = description.lower()
    aliases = {
        "merchant": ("merchant", "trader", "shopkeeper", "vendor"),
        "warrior": ("warrior", "soldier", "fighter", "knight", "guard"),
        "mage": ("mage", "wizard", "sorcerer", "witch"),
        "mentor": ("mentor", "teacher", "master", "guide", "elder"),
        "villain": ("villain", "antagonist", "corrupt", "enemy"),
    }
    for archetype, words in aliases.items():
        if any(word in text for word in words):
            return archetype
    return None
