"""Validate a provider-neutral mechanics pack. Fail closed."""

from __future__ import annotations

from typing import Any, Mapping

from skeleton.game.mechanics import (
    AIBehaviorSpec,
    CombatSystemSpec,
    EconomySystemSpec,
    GameMechanicsError,
    ProgressionSystemSpec,
)


class PackError(GameMechanicsError):
    code = "GAME.PACK"


REQUIRED = ("combat", "economy", "progression")


def validate_pack(raw: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise PackError("pack must be an object")
    missing = [key for key in REQUIRED if key not in raw]
    if missing:
        raise PackError(f"pack missing {missing[0]}")
    combat = raw["combat"]
    economy = raw["economy"]
    progression = raw["progression"]
    if not isinstance(combat, Mapping) or not isinstance(economy, Mapping):
        raise PackError("combat and economy must be objects")
    if not isinstance(progression, Mapping):
        raise PackError("progression must be an object")
    combat_spec = CombatSystemSpec(
        style=combat.get("style", "turn_based"),
        include_magic=bool(combat.get("include_magic", True)),
        include_status_effects=bool(combat.get("include_status_effects", True)),
        party_based=bool(combat.get("party_based", False)),
        enemy_ai_complexity=str(combat.get("enemy_ai_complexity", "moderate")),
    )
    economy_spec = EconomySystemSpec(
        currencies=tuple(economy.get("currencies") or ("gold",)),
        include_trading=bool(economy.get("include_trading", True)),
        include_crafting=bool(economy.get("include_crafting", False)),
        inflation_model=bool(economy.get("inflation_model", False)),
    )
    progression_spec = ProgressionSystemSpec(
        style=progression.get("style", "linear"),
        max_level=int(progression.get("max_level", 100)),
        include_prestige=bool(progression.get("include_prestige", False)),
        skill_tree_branches=int(progression.get("skill_tree_branches", 3)),
    )
    ai_spec = None
    if "ai" in raw:
        ai = raw["ai"]
        if not isinstance(ai, Mapping):
            raise PackError("ai must be an object")
        ai_spec = AIBehaviorSpec(
            entity_type=str(ai.get("entity_type", "enemy")),
            behaviors=tuple(ai.get("behaviors") or ()),
            aggression_level=float(ai.get("aggression_level", 0.5)),
            intelligence_level=float(ai.get("intelligence_level", 0.5)),
        )
    return {
        "ok": True,
        "combat_style": combat_spec.style.value,
        "currencies": list(economy_spec.currencies),
        "progression_style": progression_spec.style.value,
        "max_level": progression_spec.max_level,
        "ai_entity": None if ai_spec is None else ai_spec.entity_type,
        "stored_prose": 0,
    }
