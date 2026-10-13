"""Deterministic variation manifest for era, theology, comfort and fidelity.

Presentation options are NOT new authorship claims, executable ROMs or
verified performance profiles. This projection keeps the core mechanic
identity stable while giving each stylistic request a separate digest.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json

from .original_world_compiler import (
    OriginalWorldBlueprint, blueprint_at, blueprint_from_seed,
)
from .world_styling import WorldStyling

_RESTRICTED_RETRO_TARGETS = frozenset({
    "atari-vcs", "zx-spectrum", "commodore-64", "nes",
    "master-system", "game-boy", "sega-genesis", "snes",
    "game-gear", "neo-geo", "playstation-1", "sega-saturn",
    "nintendo-64", "game-boy-color", "game-boy-advance",
    "pc-dos",
})
_HIGH_FIDELITY_VISUALS = frozenset({
    "cinematic-pbr", "photogrammetric-inspired",
    "high-fidelity-realism", "photorealistic-target",
})
_INTENSITY_TONES = frozenset({
    "nightmarish", "harrowing", "dread-filled", "grim",
    "tragic", "terror", "nihilistic-fiction",
})
_CONTINUITY = {
    "closed": "finite campaign; postcampaign simulation is optional",
    "open": "optional objectives; no globally required ending",
    "postgame": "major ending unlocks ongoing world simulation",
    "persistent": "durable open-ended world, no forced completion",
    "unwinnable": "no promised winning state; local goals must remain meaningful",
    "branched": "mutually exclusive outcomes with durable consequence history",
    "looping": "world cycles while specified state and history may persist",
}


def _digest(value: dict) -> str:
    return sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"),
                   ensure_ascii=False, allow_nan=False).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class WorldExperienceManifest:
    blueprint: OriginalWorldBlueprint
    styling: WorldStyling
    experience_id: str
    compatibility_findings: tuple[str, ...]
    continuity_contract: str
    platform_readiness: str = "adapter-not-verified"
    realization_status: str = "design-only"

    def as_dict(self) -> dict:
        return {
            "blueprint": self.blueprint.as_dict(),
            "styling": self.styling.as_dict(),
            "experience_id": self.experience_id,
            "compatibility_findings": list(self.compatibility_findings),
            "continuity_contract": self.continuity_contract,
            "platform_readiness": self.platform_readiness,
            "realization_status": self.realization_status,
        }


def project_experience(
    blueprint: OriginalWorldBlueprint,
    styling: WorldStyling | None = None,
) -> WorldExperienceManifest:
    if not isinstance(blueprint, OriginalWorldBlueprint):
        raise ValueError("blueprint must be an OriginalWorldBlueprint")
    if not isinstance(styling, (WorldStyling, type(None))):
        raise ValueError("styling must be WorldStyling")
    selected = styling or WorldStyling()
    issues: list[str] = []

    if (selected.hardware_target in _RESTRICTED_RETRO_TARGETS
            and selected.visual_style in _HIGH_FIDELITY_VISUALS):
        issues.append("requested visual fidelity requires a target-specific "
                      "adaptation rather than native retro rendering")
    if (selected.hardware_target in _RESTRICTED_RETRO_TARGETS
            and selected.simulation_realism in {
                "high-fidelity-sim", "hyperrealism-target",
            }):
        issues.append("high-fidelity simulation exceeds an unverified retro "
                      "hardware budget; use bounded approximations")
    if selected.comfort >= 85 and selected.tone in _INTENSITY_TONES:
        issues.append("comfort and emotional intensity conflict; seek "
                      "explicit player settings and accessible alternatives")
    if selected.theology == "atheist-world" and "divinity" in selected.themes:
        issues.append("divine theme requires fictional, historical or "
                      "metaphorical interpretation in a no-deity setting")
    if blueprint.unresolved_lever_count:
        issues.append(
            f"{blueprint.unresolved_lever_count} selected world-derived levers "
            "need explicit cost models before mechanic execution"
        )
    if any(bridge.origin == "inferred" for bridge in blueprint.bridges):
        issues.append("cross-domain inferred interaction hypotheses require "
                      "causal review before executable composition")

    # A request for hyper-real rendering is not evidence of scientific
    # accuracy; a renderer or physics engine must independently validate it.
    experience_id = _digest({
        "recipe_id": blueprint.recipe_id,
        "styling": selected.as_dict(),
        "projection_schema": "world-experience.v1",
    })
    return WorldExperienceManifest(
        blueprint, selected, experience_id, tuple(issues),
        _CONTINUITY[blueprint.ending_policy],
    )


def experience_at(index: int, styling: WorldStyling | None = None) -> WorldExperienceManifest:
    return project_experience(blueprint_at(index), styling)


def experience_from_seed(seed: str, styling: WorldStyling | None = None) -> WorldExperienceManifest:
    return project_experience(blueprint_from_seed(seed), styling)
