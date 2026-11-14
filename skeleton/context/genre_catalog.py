"""GameForge genre taxonomy: discoverability labels mapped to existing canonical eras.

A selectable genre is not a claim of a complete dedicated gameplay engine.
Keep historical tokens and era votes stable; new labels reuse compiled eras.
The frontend mirror is enforced by tests to prevent silent catalog drift.
"""
from __future__ import annotations

from typing import Any

CATALOG_VERSION = 1
GENRE_GROUPS: tuple[dict[str, Any], ...] = (
    {
        "id": "action-shooting", "label": "Action & shooting",
        "genres": (
            ("action-adventure", "modern_aaa"),
            ("action", "modern_aaa"),
            ("shooter", "boomer_shooter"),
            ("fps", "boomer_shooter"),
            ("third-person-shooter", "modern_aaa"),
            ("twin-stick-shooter", "boomer_shooter"),
            ("arena-shooter", "boomer_shooter"),
            ("boomer-shooter", "boomer_shooter"),
            ("hero-shooter", "modern_aaa"),
            ("tactical-shooter", "extraction_now"),
            ("looter-shooter", "extraction_now"),
            ("rail-shooter", "boomer_shooter"),
            ("run-and-gun", "boomer_shooter"),
            ("hack-and-slash", "soulslike"),
            ("beat-em-up", "fighting_game"),
            ("fighting", "fighting_game"),
            ("brawler", "fighting_game"),
            ("bullet-heaven", "bullet_heaven"),
            ("bullet-hell", "bullet_heaven"),
            ("battle-royale", "battle_royale"),
            ("extraction-shooter", "extraction_now"),
        ),
    },
    {
        "id": "role-playing", "label": "Role-playing & progression",
        "genres": (
            ("rpg", "crpg"),
            ("crpg", "crpg"),
            ("jrpg", "jrpg"),
            ("arpg", "soulslike"),
            ("soulslike", "soulslike"),
            ("mmo", "mmorpg"),
            ("mmorpg", "mmorpg"),
            ("roguelike", "roguelike"),
            ("roguelite", "roguelike"),
            ("dungeon-crawler", "crpg"),
            ("tactical-rpg", "tactics_grid"),
            ("monster-tamer", "jrpg"),
            ("creature-collector", "jrpg"),
            ("looter-rpg", "extraction_now"),
            ("open-world-rpg", "modern_aaa"),
            ("idle-rpg", "indie_experimental"),
        ),
    },
    {
        "id": "strategy-tactics", "label": "Strategy & tactics",
        "genres": (
            ("strategy", "grand_strategy"),
            ("rts", "grand_strategy"),
            ("tactics", "tactics_grid"),
            ("turn-based-strategy", "tactics_grid"),
            ("4x", "grand_strategy"),
            ("grand-strategy", "grand_strategy"),
            ("war-game", "grand_strategy"),
            ("tower-defense", "tactics_grid"),
            ("auto-battler", "tactics_grid"),
            ("real-time-tactics", "tactics_grid"),
            ("base-building", "city_builder"),
            ("city-defense", "tactics_grid"),
        ),
    },
    {
        "id": "simulation-management", "label": "Simulation & management",
        "genres": (
            ("simulation", "city_builder"),
            ("city-builder", "city_builder"),
            ("life-sim", "city_builder"),
            ("farming-sim", "city_builder"),
            ("colony-sim", "city_builder"),
            ("factory-sim", "city_builder"),
            ("automation", "city_builder"),
            ("management", "city_builder"),
            ("business-sim", "city_builder"),
            ("tycoon", "city_builder"),
            ("transport-sim", "city_builder"),
            ("construction-sim", "city_builder"),
            ("god-game", "city_builder"),
            ("economy-sim", "city_builder"),
            ("medical-sim", "city_builder"),
            ("job-sim", "city_builder"),
        ),
    },
    {
        "id": "adventure-narrative", "label": "Adventure & narrative",
        "genres": (
            ("adventure", "modern_aaa"),
            ("narrative", "walking_sim"),
            ("visual-novel", "visual_novel"),
            ("walking-sim", "walking_sim"),
            ("point-and-click", "walking_sim"),
            ("interactive-fiction", "walking_sim"),
            ("detective", "stealth"),
            ("mystery", "visual_novel"),
            ("narrative-adventure", "visual_novel"),
            ("choice-driven", "visual_novel"),
            ("cinematic-adventure", "modern_aaa"),
            ("dating-sim", "visual_novel"),
            ("otome", "visual_novel"),
            ("fmv", "visual_novel"),
        ),
    },
    {
        "id": "platform-exploration", "label": "Platform & exploration",
        "genres": (
            ("platformer", "metroidvania"),
            ("metroidvania", "metroidvania"),
            ("precision-platformer", "metroidvania"),
            ("3d-platformer", "modern_aaa"),
            ("collectathon", "modern_aaa"),
            ("parkour", "modern_aaa"),
            ("open-world", "modern_aaa"),
            ("exploration", "walking_sim"),
            ("sandbox", "immersive_sim"),
            ("survival", "extraction_now"),
            ("extraction", "extraction_now"),
            ("stealth", "stealth"),
            ("immersive-sim", "immersive_sim"),
            ("cozy", "cozy_wholesome"),
            ("survival-crafting", "extraction_now"),
        ),
    },
    {
        "id": "puzzle-tabletop", "label": "Puzzle & tabletop",
        "genres": (
            ("puzzle", "indie_experimental"),
            ("deckbuilder", "deckbuilder"),
            ("card", "deckbuilder"),
            ("card-battler", "deckbuilder"),
            ("board-game", "deckbuilder"),
            ("logic-puzzle", "indie_experimental"),
            ("physics-puzzle", "indie_experimental"),
            ("escape-room", "indie_experimental"),
            ("hidden-object", "indie_experimental"),
            ("match-3", "indie_experimental"),
            ("word-game", "indie_experimental"),
            ("trivia", "indie_experimental"),
            ("mahjong", "indie_experimental"),
            ("incremental", "indie_experimental"),
        ),
    },
    {
        "id": "horror-suspense", "label": "Horror & suspense",
        "genres": (
            ("horror", "horror_survival"),
            ("survival-horror", "horror_survival"),
            ("psychological-horror", "horror_survival"),
            ("cosmic-horror", "horror_survival"),
            ("stealth-horror", "stealth"),
            ("asymmetric-horror", "horror_survival"),
            ("zombie-survival", "extraction_now"),
        ),
    },
    {
        "id": "racing-sports", "label": "Racing, sports & vehicles",
        "genres": (
            ("racing", "modern_aaa"),
            ("arcade-racing", "arcade_golden_age"),
            ("sim-racing", "modern_aaa"),
            ("kart-racing", "arcade_golden_age"),
            ("rally", "modern_aaa"),
            ("vehicle-combat", "boomer_shooter"),
            ("sports", "modern_aaa"),
            ("football", "modern_aaa"),
            ("basketball", "modern_aaa"),
            ("golf", "modern_aaa"),
            ("tennis", "modern_aaa"),
            ("skateboarding", "modern_aaa"),
            ("snowboarding", "modern_aaa"),
            ("flight-sim", "modern_aaa"),
            ("space-sim", "modern_aaa"),
            ("sailing", "cozy_wholesome"),
            ("fishing", "cozy_wholesome"),
            ("combat-flight", "modern_aaa"),
        ),
    },
    {
        "id": "creative-social", "label": "Creative, social & rhythm",
        "genres": (
            ("rhythm", "arcade_golden_age"),
            ("music", "indie_experimental"),
            ("dance", "arcade_golden_age"),
            ("party", "cozy_wholesome"),
            ("minigame-collection", "arcade_golden_age"),
            ("social-deduction", "indie_experimental"),
            ("co-op", "modern_aaa"),
            ("party-game", "arcade_golden_age"),
            ("sandbox-creator", "indie_experimental"),
            ("creative-building", "indie_experimental"),
            ("user-generated-content", "indie_experimental"),
            ("educational", "indie_experimental"),
            ("serious-game", "indie_experimental"),
            ("virtual-pet", "cozy_wholesome"),
        ),
    },
    {
        "id": "arcade-casual", "label": "Arcade & casual",
        "genres": (
            ("arcade", "arcade_golden_age"),
            ("endless-runner", "arcade_golden_age"),
            ("shoot-em-up", "arcade_golden_age"),
            ("side-scrolling-shooter", "arcade_golden_age"),
            ("pinball", "arcade_golden_age"),
            ("brick-breaker", "arcade_golden_age"),
            ("maze", "arcade_golden_age"),
            ("score-attack", "arcade_golden_age"),
            ("retro-arcade", "arcade_golden_age"),
            ("hypercasual", "arcade_golden_age"),
            ("clicker", "indie_experimental"),
        ),
    },
)

GENRE_ERA_VOTES: dict[str, str] = {
    token: era for group in GENRE_GROUPS for token, era in group["genres"]
}
GENRE_COUNT = sum(len(group["genres"]) for group in GENRE_GROUPS)
if len(GENRE_ERA_VOTES) != GENRE_COUNT:
    raise RuntimeError("duplicate GameForge genre id")


def genre_catalog_payload() -> dict[str, Any]:
    """Bounded, public catalog; era is a design-intake vote, not genre proof."""
    return {
        "version": CATALOG_VERSION,
        "count": GENRE_COUNT,
        "groups": [
            {
                "id": group["id"],
                "label": group["label"],
                "genres": [{"id": token, "era": era} for token, era in group["genres"]],
            }
            for group in GENRE_GROUPS
        ],
    }
