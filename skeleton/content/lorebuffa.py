"""Lorebuffa-derived AI domain knowledge for Skeleton.

This module deliberately contains domain knowledge rather than the original
Lorebuffa web/game transport layer.  It gives Skeleton's NPC/dialogue
pipelines a reusable world model: roles, factions, personality signals,
voice styles, schedules, quests, and branching-dialogue conventions.

Source lineage: Apeloff1/Lorebuffa, main, January 2026.
Relevant source assets include backend/expanded_npcs.py,
backend/npc_dialogue_extended.py, backend/npc_dialogue_routes.py,
backend/quest_system.py, backend/reputation_system.py and
backend/captains_log.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class NpcKnowledge:
    id: str
    name: str
    title: str
    role: str
    personality: str
    faction: str
    disposition: int
    voice_style: str
    skills_taught: tuple[str, ...] = ()
    quests_offered: tuple[str, ...] = ()
    schedule: tuple[tuple[str, str], ...] = ()
    backstory: str = ""

    def to_context(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "title": self.title,
            "role": self.role,
            "personality": self.personality,
            "faction": self.faction,
            "initial_disposition": self.disposition,
            "voice_style": self.voice_style,
            "skills_taught": list(self.skills_taught),
            "quests_offered": list(self.quests_offered),
            "schedule": dict(self.schedule),
            "backstory": self.backstory,
        }


NPCS: tuple[NpcKnowledge, ...] = (
    NpcKnowledge(
        "barnacle_bill", "Barnacle Bill", "Legendary Fisherman", "mentor",
        "wise_gruff", "fishermen_guild", 50, "gruff_but_kind",
        ("basic_fishing", "fish_identification", "weather_reading"),
        ("first_catch", "golden_mackerel_hunt", "leviathan_tale"),
        (("morning", "docks"), ("afternoon", "tavern"), ("evening", "docks"), ("night", "home")),
        "Sailed for 70 years. Lost his ship in the Storm of '82 but gained wisdom.",
    ),
    NpcKnowledge(
        "harbor_master_jenkins", "Harbor Master Jenkins", "Port Authority", "official",
        "bureaucratic_fair", "port_authority", 40, "formal_clipped",
        ("navigation_permits", "trade_licenses"),
        ("smuggler_investigation", "dock_repairs", "missing_shipment"),
        (("morning", "office"), ("afternoon", "docks"), ("evening", "office"), ("night", "home")),
        "Former naval officer who values order above all else.",
    ),
    NpcKnowledge(
        "salty_pete", "Salty Pete", "Retired Pirate", "informant",
        "shifty_helpful", "neutral", 45, "conspiratorial_raspy",
        ("lockpicking", "smuggling_routes", "pirate_contacts"),
        ("hidden_treasure", "old_debts", "pirate_reunion"),
        (("morning", "sleeping"), ("afternoon", "tavern"), ("evening", "docks"), ("night", "tavern")),
        "Served under Captain Redbeard before losing his eye and his nerve.",
    ),
    NpcKnowledge(
        "fishwife_martha", "Fishwife Martha", "Fish Vendor", "merchant",
        "loud_motherly", "merchants", 60, "booming_warm",
        ("fish_prices", "bargaining", "gossip_network"),
        ("delivery_run", "competitor_sabotage", "lost_son"),
        (("morning", "market"), ("afternoon", "market"), ("evening", "home"), ("night", "home")),
        "Widowed young, raised six children selling fish. Knows everything.",
    ),
    NpcKnowledge(
        "young_tommy", "Tommy Waves", "Aspiring Fisher", "apprentice",
        "eager_innocent", "none", 80, "enthusiastic_squeaky",
        (), ("tommys_first_catch", "find_fathers_boat", "fishing_competition"),
        (("morning", "docks"), ("afternoon", "school"), ("evening", "docks"), ("night", "home")),
        "Lost his father to the Golden Depths. Refuses to give up hope.",
    ),
    NpcKnowledge(
        "dock_worker_bruno", "Bruno Strongarm", "Dock Worker", "laborer",
        "simple_loyal", "workers_union", 55, "slow_deep",
        ("heavy_lifting", "cargo_handling"),
        ("loading_competition", "strike_breaker", "missing_crate"),
        (("morning", "docks"), ("afternoon", "docks"), ("evening", "tavern"), ("night", "home")),
        "Born on the docks, will die on the docks. Simple life, simple man.",
    ),
    NpcKnowledge(
        "net_mender_agatha", "Agatha Threadfinger", "Net Mender", "craftsman",
        "patient_precise", "craftsmen", 65, "soft_precise",
        ("net_repair", "rope_work", "sail_mending"),
        ("rare_thread", "net_competition", "apprentice_needed"),
        (("morning", "workshop"), ("afternoon", "docks"), ("evening", "workshop"), ("night", "home")),
        "Mended nets for 50 years. Can fix anything with string.",
    ),
    NpcKnowledge(
        "tavern_keeper_rosie", "Rosie McTavern", "Innkeeper", "innkeeper",
        "warm_protective", "innkeepers", 70, "warm_motherly",
        ("cooking_basics", "local_gossip", "room_negotiation"),
        ("rowdy_customers", "missing_ring", "ghost_room"),
        (("morning", "inn"), ("afternoon", "inn"), ("evening", "inn"), ("night", "inn")),
        "Former fisher who lost her son Tommy. The inn is her new family.",
    ),
    NpcKnowledge(
        "customs_officer_chen", "Officer Chen", "Customs Inspector", "official",
        "suspicious_thorough", "port_authority", 35, "clipped_suspicious",
        ("contraband_detection", "legal_loopholes"),
        ("smuggler_ring", "false_manifest", "bribery_sting"),
        (("morning", "customs"), ("afternoon", "docks"), ("evening", "customs"), ("night", "patrol")),
        "Lost family to pirates. Now hunts criminals with cold precision.",
    ),
    NpcKnowledge(
        "shipwright_igor", "Igor Hammerbolt", "Master Shipwright", "craftsman",
        "gruff_perfectionist", "craftsmen", 45, "gruff_technical",
        ("ship_repair", "upgrade_installation", "hull_assessment"),
        ("rare_wood", "stolen_tools", "legendary_blueprint"),
        (("morning", "shipyard"), ("afternoon", "shipyard"), ("evening", "tavern"), ("night", "home")),
        "Third generation shipwright. Built the Crimson Terror herself.",
    ),
    NpcKnowledge(
        "fortune_teller_coral", "Madame Coral", "Seer of Depths", "mystic",
        "mysterious_dramatic", "mystics", 55, "ethereal_dramatic",
        ("fortune_reading", "curse_removal", "spirit_contact"),
        ("lost_artifact", "haunted_ship", "prophecy_quest"),
        (("morning", "tent"), ("afternoon", "tent"), ("evening", "tent"), ("night", "spirit_walks")),
        "May have mermaid blood. Her predictions are eerily accurate.",
    ),
)

# Dialogue design patterns extracted from the extended dialogue system.
DIALOGUE_PATTERNS: dict[str, Any] = {
    "choice_tags": ["Friendly", "Curious", "Business", "Casual", "Leave", "Lie", "Barter", "Dark"],
    "choice_effects": ["rep_change", "requires_item", "quest_unlock", "knowledge", "faction_discover", "trust_level"],
    "branch_shape": "node -> choices -> next node, with stateful reputation/trust side effects",
    "quality_rules": [
        "choices should expose materially different social strategies",
        "reputation changes should be explicit and deterministic",
        "important revelations should unlock knowledge, factions, or quests",
        "quests should be expressible as typed objectives with rewards",
    ],
}

FACTIONS: tuple[str, ...] = (
    "fishermen_guild", "port_authority", "merchants", "workers_union",
    "craftsmen", "innkeepers", "mystics", "neutral",
)

QUEST_PATTERNS: tuple[dict[str, Any], ...] = (
    {"id": "rescue_james_goldscale", "objectives": ["collect current_breaker", "collect spirit_compass", "reach forgotten_atoll"], "reward_types": ["gold", "item", "reputation"]},
    {"id": "smuggler_investigation", "objective_types": ["investigate", "collect_evidence", "confront"]},
    {"id": "prophecy_quest", "objective_types": ["discover", "retrieve", "return"]},
)

LOREBUFFA_AI_PACK: dict[str, Any] = {
    "world": "pirate-fishing fantasy with factional ports, dangerous waters, guilds, mystics and underwater civilizations",
    "npcs": [npc.to_context() for npc in NPCS],
    "factions": list(FACTIONS),
    "dialogue": DIALOGUE_PATTERNS,
    "quest_patterns": list(QUEST_PATTERNS),
    "source_lineage": "Apeloff1/Lorebuffa@279539fc299f5fe67a139b335ddc74fec0eccbdc",
}


def get_npc_context(name_or_id: str) -> dict[str, Any] | None:
    """Return the deterministic domain context for an NPC."""
    needle = name_or_id.strip().lower()
    for npc in NPCS:
        if needle in {npc.id.lower(), npc.name.lower()}:
            return npc.to_context()
    return None
