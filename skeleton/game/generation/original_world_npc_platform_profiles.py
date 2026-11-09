"""Conservative console, PC-generation and gameplay-form NPC fidelity policy.

Design budgets, NOT measured industry averages or certified frame-rate targets.
Every advertised target maps explicitly. Maxima mean actual locally embodied
persistent NPC slots; only a smaller rotating subset executes full cognition
each turn. Remote populations have real but simplified finite cohort books.
Visual proxy caps are separate and cannot be treated as AI entities.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from .original_foundation_compiler import FoundationError
from .original_world_era_runtime import ERA_LEVELS
from .original_world_play_forms import FORM_BY_ID
from .world_styling import HARDWARE_TARGETS

PROFILE_SCHEMA = "original-era-hardware-genre-npc-profile.v1"
PC_GENERATIONS = (
    "1980s-8bit", "1990s-dos", "1990s-windows",
    "2000s-mainstream", "2010s-integrated", "2010s-gaming",
    "2020s-integrated", "2020s-mainstream", "2020s-highend",
)
DEFAULT_PC_GENERATION = "2020s-integrated"
# Each tuple: detailed local cap, abstract historical group census max,
# district cap, per-turn full brain cap, visible decorative crowd budget.
TIERS = {
    "tiny-8bit": (3, 2, 1, 2, 0),
    "retro-16bit": (5, 6, 2, 3, 1),
    "early-3d": (7, 12, 2, 4, 2),
    "sixth-generation": (10, 24, 3, 5, 2),
    "seventh-generation": (13, 40, 4, 6, 3),
    "eighth-generation": (18, 72, 5, 8, 5),
    "ninth-generation": (24, 120, 7, 12, 8),
    "portable-modern": (15, 54, 4, 7, 4),
    "browser-safe": (10, 24, 3, 5, 2),
    "pc-enthusiast": (24, 144, 8, 14, 10),
}
PLATFORM_TIER = {
    "atari-vcs": "tiny-8bit",
    "zx-spectrum": "tiny-8bit",
    "commodore-64": "tiny-8bit",
    "nes": "tiny-8bit",
    "master-system": "tiny-8bit",
    "game-boy": "tiny-8bit",
    "sega-genesis": "retro-16bit",
    "snes": "retro-16bit",
    "game-gear": "tiny-8bit",
    "neo-geo": "retro-16bit",
    "playstation-1": "early-3d",
    "sega-saturn": "early-3d",
    "nintendo-64": "early-3d",
    "game-boy-color": "retro-16bit",
    "dreamcast": "sixth-generation",
    "playstation-2": "sixth-generation",
    "gamecube": "sixth-generation",
    "original-xbox": "sixth-generation",
    "game-boy-advance": "retro-16bit",
    "nintendo-ds": "retro-16bit",
    "psp": "early-3d",
    "wii": "sixth-generation",
    "xbox-360": "seventh-generation",
    "playstation-3": "seventh-generation",
    "nintendo-3ds": "early-3d",
    "ps-vita": "sixth-generation",
    "wii-u": "seventh-generation",
    "nintendo-switch": "portable-modern",
    "playstation-4": "eighth-generation",
    "xbox-one": "eighth-generation",
    "playstation-5": "ninth-generation",
    "xbox-series": "ninth-generation",
    "pc-dos": "tiny-8bit",
    "pc-windows": "portable-modern",
    "pc-linux": "portable-modern",
    "pc-macos": "portable-modern",
    "steam-deck": "portable-modern",
    "browser": "browser-safe",
    "mobile-android": "browser-safe",
    "mobile-ios": "browser-safe",
    "custom-homebrew": "retro-16bit",
}
PC_TIERS = {
    "1980s-8bit": "tiny-8bit",
    "1990s-dos": "tiny-8bit",
    "1990s-windows": "early-3d",
    "2000s-mainstream": "sixth-generation",
    "2010s-integrated": "seventh-generation",
    "2010s-gaming": "eighth-generation",
    "2020s-integrated": "portable-modern",
    "2020s-mainstream": "eighth-generation",
    "2020s-highend": "pc-enthusiast",
}
# Gameplay modifiers: one primary named individual is better than a crowd
# of decorative puppets. Fractions apply to actual bodies *and* remote census.
# Numerators / 100 used for exact cross-platform deterministic calculation.
GENRE_BUDGETS = {
    "platform": (55, 30),
    "puzzle": (50, 20),
    "tactics": (75, 65),
    "survival": (80, 75),
    "colony": (100, 100),
    "racing": (35, 12),
    "stealth": (65, 42),
    "commerce": (75, 80),
    "exploration": (85, 65),
    "rhythm": (35, 10),
}
# Fictional historical context reduces settlement size as appropriate.
# This is a GAME design schedule, not a claim about actual human demography.
ERA_BODY_LIMITS = (6, 8, 10, 12, 14, 17, 19, 22, 24)
ERA_CENSUS_PERCENT = (20, 30, 42, 55, 67, 78, 88, 95, 100)


@dataclass(frozen=True)
class PopulationProfile:
    schema: str
    era: str
    platform: str
    pc_generation: str
    genre: str
    hardware_tier: str
    local_limit: int
    starting_locals: int
    regional_limit: int
    district_limit: int
    brain_limit: int
    visual_proxy_limit: int
    district_update_limit: int

    def as_dict(self) -> dict:
        return asdict(self)


def _ceil_div(value: int, divisor: int) -> int:
    return (value + divisor - 1) // divisor


def plan_population(
    era: str, platform: str, genre: str, *,
    pc_generation: str | None = None,
) -> PopulationProfile:
    if era not in ERA_LEVELS:
        raise FoundationError("unknown authored world era for NPC population")
    if platform not in PLATFORM_TIER or platform not in HARDWARE_TARGETS:
        raise FoundationError("unknown console, PC or legal homebrew target")
    if genre not in FORM_BY_ID or genre not in GENRE_BUDGETS:
        raise FoundationError("unknown original playable genre")
    pc = platform.startswith("pc-")
    if pc:
        generation = pc_generation or ("1990s-dos" if platform == "pc-dos"
                                       else DEFAULT_PC_GENERATION)
        if generation not in PC_GENERATIONS:
            raise FoundationError("unknown PC hardware generation")
        # A DOS target never silently upgrades into a modern PC.
        if platform == "pc-dos" and generation not in (
                "1980s-8bit", "1990s-dos"):
            raise FoundationError("DOS native target cannot claim modern CPU")
        hardware = PC_TIERS[generation]
    else:
        if pc_generation is not None:
            raise FoundationError("PC generations do not apply to console targets")
        generation = ""
        hardware = PLATFORM_TIER[platform]
    detailed, background, regions, brains, visual = TIERS[hardware]
    tier = ERA_LEVELS[era]
    interactive_weight, world_weight = GENRE_BUDGETS[genre]
    if era in ("primordial-earth", "early-life"):
        detailed, background, regions, visual = 1, 0, 0, 0
    else:
        detailed = min(
            detailed, ERA_BODY_LIMITS[tier],
            max(2, _ceil_div(detailed * interactive_weight, 100)),
        )
        background = min(
            144,
            background * world_weight * ERA_CENSUS_PERCENT[tier] // 10000,
        )
        # No fake local town in racing, rhythm or self-contained puzzles.
        if genre in ("racing", "rhythm") and background < 4:
            background = 0
        regions = min(regions, _ceil_div(background, 12)) if background else 0
        visual = min(visual, _ceil_div(detailed, 3),
                     _ceil_div(background, 6)) if background else 0
    reserve = 2 if detailed >= 4 else 1 if detailed >= 2 else 0
    initial = detailed - reserve
    decisions = min(detailed, brains)
    if detailed == 1:
        decisions = 1
    return PopulationProfile(
        PROFILE_SCHEMA, era, platform, generation, genre, hardware,
        detailed, initial, background, regions, decisions, visual,
        min(3, regions),
    )


def platform_inventory() -> dict:
    return {
        platform: {
            "hardware_tier": PLATFORM_TIER[platform],
            "pc_generations": list(PC_GENERATIONS) if platform.startswith("pc-")
                else [],
        }
        for platform in HARDWARE_TARGETS
    }


if set(PLATFORM_TIER) != set(HARDWARE_TARGETS):
    raise RuntimeError("every advertised console/PC/homebrew target needs an NPC budget")
if set(GENRE_BUDGETS) != set(FORM_BY_ID):
    raise RuntimeError("every game genre must have an explicit independent NPC budget")
