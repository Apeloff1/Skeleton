"""Provider-neutral game mechanics generation contracts.

Promoted from the historical Tutolage/Prood Text-to-Game-Logic pipeline into a
pure Skeleton domain layer.  HTTP, Pydantic, database, and LLM dependencies are
intentionally excluded so forge/API/UI surfaces can share one deterministic
mechanics core.
"""

from __future__ import annotations

import copy
import math
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Iterable, Optional, Tuple

from skeleton.kernel.errors import KernelError

MAX_DESCRIPTION_CHARS = 8_000
MAX_LEVEL = 1_000
MAX_SKILL_BRANCHES = 5
MAX_CURRENCIES = 16
MAX_CUSTOM_BEHAVIORS = 64
MAX_TOKEN_CHARS = 64


class GameMechanicsError(KernelError):
    code = "GAME.MECHANICS"


class MechanicType(str, Enum):
    COMBAT = "combat"
    MOVEMENT = "movement"
    INVENTORY = "inventory"
    CRAFTING = "crafting"
    DIALOGUE = "dialogue"
    ECONOMY = "economy"
    PROGRESSION = "progression"
    PHYSICS = "physics"
    AI_BEHAVIOR = "ai_behavior"
    PUZZLE = "puzzle"
    STEALTH = "stealth"
    SURVIVAL = "survival"


class CombatStyle(str, Enum):
    TURN_BASED = "turn_based"
    REAL_TIME = "real_time"
    HYBRID = "hybrid"
    TACTICAL = "tactical"
    ACTION = "action"
    CARD_BASED = "card_based"


class ProgressionStyle(str, Enum):
    LINEAR = "linear"
    EXPONENTIAL = "exponential"
    LOGARITHMIC = "logarithmic"
    MILESTONE = "milestone"
    SKILL_TREE = "skill_tree"
    PRESTIGE = "prestige"


def _bounded_token(name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GameMechanicsError(f"{name} must be a non-empty string")
    normalized = value.strip()
    if len(normalized) > MAX_TOKEN_CHARS:
        raise GameMechanicsError(
            f"{name} is too long", context={"max_chars": MAX_TOKEN_CHARS}
        )
    return normalized


def _unit_interval(name: str, value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise GameMechanicsError(f"{name} must be numeric")
    number = float(value)
    if not math.isfinite(number) or not 0.0 <= number <= 1.0:
        raise GameMechanicsError(f"{name} must be between 0 and 1")
    return number


def _bounded_int(name: str, value: int, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise GameMechanicsError(f"{name} must be an integer")
    if not minimum <= value <= maximum:
        raise GameMechanicsError(
            f"{name} is outside the accepted range",
            context={"minimum": minimum, "maximum": maximum},
        )
    return value


def _stable_unique(values: Iterable[str]) -> Tuple[str, ...]:
    seen: set[str] = set()
    ordered = []
    for value in values:
        if value not in seen:
            seen.add(value)
            ordered.append(value)
    return tuple(ordered)


@dataclass(frozen=True)
class CombatSystemSpec:
    style: CombatStyle
    include_magic: bool = True
    include_status_effects: bool = True
    party_based: bool = False
    enemy_ai_complexity: str = "moderate"

    def __post_init__(self) -> None:
        if not isinstance(self.style, CombatStyle):
            try:
                object.__setattr__(self, "style", CombatStyle(self.style))
            except (TypeError, ValueError) as exc:
                raise GameMechanicsError("unknown combat style") from exc
        complexity = _bounded_token("enemy_ai_complexity", self.enemy_ai_complexity).lower()
        if complexity not in {"simple", "moderate", "complex"}:
            raise GameMechanicsError("unknown enemy AI complexity")
        object.__setattr__(self, "enemy_ai_complexity", complexity)
        for name in ("include_magic", "include_status_effects", "party_based"):
            if not isinstance(getattr(self, name), bool):
                raise GameMechanicsError(f"{name} must be boolean")


@dataclass(frozen=True)
class ProgressionSystemSpec:
    style: ProgressionStyle
    max_level: int = 100
    include_prestige: bool = False
    skill_tree_branches: int = 3

    def __post_init__(self) -> None:
        if not isinstance(self.style, ProgressionStyle):
            try:
                object.__setattr__(self, "style", ProgressionStyle(self.style))
            except (TypeError, ValueError) as exc:
                raise GameMechanicsError("unknown progression style") from exc
        _bounded_int("max_level", self.max_level, minimum=1, maximum=MAX_LEVEL)
        _bounded_int(
            "skill_tree_branches",
            self.skill_tree_branches,
            minimum=0,
            maximum=MAX_SKILL_BRANCHES,
        )
        if not isinstance(self.include_prestige, bool):
            raise GameMechanicsError("include_prestige must be boolean")


@dataclass(frozen=True)
class EconomySystemSpec:
    currencies: Tuple[str, ...] = ("gold",)
    include_trading: bool = True
    include_crafting: bool = False
    inflation_model: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.currencies, tuple):
            object.__setattr__(self, "currencies", tuple(self.currencies))
        if not 1 <= len(self.currencies) <= MAX_CURRENCIES:
            raise GameMechanicsError(
                "currency count is outside the accepted range",
                context={"maximum": MAX_CURRENCIES},
            )
        normalized = tuple(_bounded_token("currency", c) for c in self.currencies)
        if len(set(normalized)) != len(normalized):
            raise GameMechanicsError("currencies must be unique")
        object.__setattr__(self, "currencies", normalized)
        for name in ("include_trading", "include_crafting", "inflation_model"):
            if not isinstance(getattr(self, name), bool):
                raise GameMechanicsError(f"{name} must be boolean")


@dataclass(frozen=True)
class AIBehaviorSpec:
    entity_type: str
    behaviors: Tuple[str, ...] = ()
    aggression_level: float = 0.5
    intelligence_level: float = 0.5

    def __post_init__(self) -> None:
        object.__setattr__(self, "entity_type", _bounded_token("entity_type", self.entity_type))
        if not isinstance(self.behaviors, tuple):
            object.__setattr__(self, "behaviors", tuple(self.behaviors))
        if len(self.behaviors) > MAX_CUSTOM_BEHAVIORS:
            raise GameMechanicsError(
                "too many custom behaviors",
                context={"maximum": MAX_CUSTOM_BEHAVIORS},
            )
        object.__setattr__(
            self,
            "behaviors",
            tuple(_bounded_token("behavior", behavior) for behavior in self.behaviors),
        )
        object.__setattr__(
            self, "aggression_level", _unit_interval("aggression_level", self.aggression_level)
        )
        object.__setattr__(
            self,
            "intelligence_level",
            _unit_interval("intelligence_level", self.intelligence_level),
        )


_COMBAT_TEMPLATES: Dict[CombatStyle, Dict[str, Any]] = {
    CombatStyle.TURN_BASED: {
        "structure": "initiative_order",
        "actions_per_turn": 1,
        "time_limit": None,
        "components": ["attack", "defend", "skill", "item", "flee"],
        "damage_formula": "base_damage * (1 + strength/10) * random(0.9, 1.1)",
        "defense_formula": "incoming_damage * (1 - armor/100)",
        "critical_chance": 0.1,
        "critical_multiplier": 2.0,
    },
    CombatStyle.REAL_TIME: {
        "structure": "continuous",
        "cooldown_based": True,
        "hitbox_detection": "AABB",
        "components": ["light_attack", "heavy_attack", "block", "dodge", "special"],
        "damage_formula": "base_damage * attack_speed * multiplier",
        "stagger_system": True,
        "combo_system": True,
    },
    CombatStyle.TACTICAL: {
        "structure": "grid_based",
        "movement_points": 6,
        "action_points": 2,
        "components": ["move", "attack", "overwatch", "ability", "wait"],
        "cover_system": True,
        "flanking_bonus": 1.25,
        "height_advantage": 1.15,
    },
}

_RULE_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "rpg": {
        "dice_system": "d20",
        "attribute_system": [
            "strength",
            "dexterity",
            "constitution",
            "intelligence",
            "wisdom",
            "charisma",
        ],
        "skill_checks": "attribute_modifier + skill_bonus + d20 >= difficulty",
        "saving_throws": True,
        "advantage_disadvantage": True,
    },
    "arcade": {
        "score_based": True,
        "lives_system": True,
        "power_ups": True,
        "difficulty_scaling": "continuous",
    },
    "simulation": {
        "resource_management": True,
        "time_progression": "real_time_with_pause",
        "random_events": True,
        "feedback_loops": True,
    },
    "puzzle": {
        "state_machine": True,
        "valid_moves_check": True,
        "win_condition": "goal_state_reached",
        "hint_system": True,
    },
}


class GameMechanicsGenerator:
    """Pure generation engine for reusable game-system specifications."""

    @staticmethod
    def parse_mechanic_description(description: str) -> Dict[str, Any]:
        if not isinstance(description, str) or not description.strip():
            raise GameMechanicsError("description must be a non-empty string")
        if len(description) > MAX_DESCRIPTION_CHARS:
            raise GameMechanicsError(
                "description is too long", context={"max_chars": MAX_DESCRIPTION_CHARS}
            )
        desc = description.lower()
        mechanic_keywords = {
            MechanicType.COMBAT: ("combat", "fight", "battle", "attack", "damage"),
            MechanicType.MOVEMENT: ("movement", "walk", "run", "jump", "climb"),
            MechanicType.INVENTORY: ("inventory", "items", "equipment", "bag"),
            MechanicType.CRAFTING: ("craft", "forge", "create", "build", "recipe"),
            MechanicType.ECONOMY: ("economy", "money", "gold", "trade", "shop"),
            MechanicType.PROGRESSION: ("level", "xp", "experience", "skill", "upgrade"),
            MechanicType.AI_BEHAVIOR: ("ai", "enemy", "behavior", "patrol", "chase"),
            MechanicType.PUZZLE: ("puzzle", "riddle", "logic", "solve"),
            MechanicType.STEALTH: ("stealth", "sneak", "hide", "detection"),
            MechanicType.SURVIVAL: ("survival", "hunger", "thirst", "stamina"),
        }
        detected_types = tuple(
            mechanic_type
            for mechanic_type, keywords in mechanic_keywords.items()
            if any(keyword in desc for keyword in keywords)
        )

        combat_style: Optional[CombatStyle] = None
        if "turn-based" in desc or "turn based" in desc:
            combat_style = CombatStyle.TURN_BASED
        elif "real-time" in desc or "real time" in desc:
            combat_style = CombatStyle.REAL_TIME
        elif "tactical" in desc or "grid" in desc:
            combat_style = CombatStyle.TACTICAL
        elif "card" in desc:
            combat_style = CombatStyle.CARD_BASED
        elif "action" in desc:
            combat_style = CombatStyle.ACTION

        genre_keywords = {
            "rpg": ("rpg", "role-playing", "character", "stats"),
            "platformer": ("platformer", "jump", "platform"),
            "shooter": ("shooter", "fps", "gun", "shoot"),
            "strategy": ("strategy", "rts", "manage"),
            "puzzle": ("puzzle", "logic", "brain"),
            "survival": ("survival", "hunger"),
        }
        genres = tuple(
            genre
            for genre, keywords in genre_keywords.items()
            if any(keyword in desc for keyword in keywords)
        )
        return {
            "mechanic_types": detected_types,
            "combat_style": combat_style,
            "genre_hints": genres,
        }

    @staticmethod
    def generate_combat_system(spec: CombatSystemSpec) -> Dict[str, Any]:
        if not isinstance(spec, CombatSystemSpec):
            raise GameMechanicsError("spec must be CombatSystemSpec")
        # Hybrid/action/card systems currently derive from the turn-based base,
        # but named source templates must map exactly; notably REAL_TIME must
        # never silently fall back to TURN_BASED.
        base = _COMBAT_TEMPLATES.get(spec.style, _COMBAT_TEMPLATES[CombatStyle.TURN_BASED])
        system: Dict[str, Any] = {
            "id": str(uuid.uuid4()),
            "style": spec.style.value,
            "core_mechanics": copy.deepcopy(base),
            "damage_types": ["physical", "magical", "true"] if spec.include_magic else ["physical"],
            "status_effects": [],
            "enemy_ai": {},
            "balance_parameters": {
                "base_hp_formula": "10 + (constitution * 5) + (level * 10)",
                "base_damage_formula": "weapon_damage + (strength * 0.5)",
                "accuracy_formula": "base_accuracy + (dexterity * 2)",
                "crit_rate_base": 0.05,
                "crit_damage_multiplier": 1.5,
                "level_scaling": 1.1,
            },
        }
        if spec.include_status_effects:
            system["status_effects"] = [
                {"name": "poison", "type": "dot", "duration": 3, "damage_per_tick": 5},
                {"name": "burn", "type": "dot", "duration": 2, "damage_per_tick": 8},
                {"name": "freeze", "type": "cc", "duration": 1, "effect": "skip_turn"},
                {"name": "stun", "type": "cc", "duration": 1, "effect": "cannot_act"},
            ]
        if spec.include_magic:
            system["magic_system"] = {
                "resource": "mana",
                "regeneration": "per_turn",
                "schools": ["fire", "ice", "lightning", "earth", "light", "dark"],
                "spell_types": ["damage", "heal", "buff", "debuff", "summon"],
                "casting_time": spec.style != CombatStyle.REAL_TIME,
            }
        if spec.party_based:
            system["party_mechanics"] = {
                "max_party_size": 4,
                "formation_system": True,
                "combo_attacks": True,
                "switch_cost": 0 if spec.style == CombatStyle.TURN_BASED else 0.5,
                "shared_resources": ["items"],
                "individual_resources": ["hp", "mana"],
            }
        ai_profiles = {
            "simple": {
                "decision_tree_depth": 2,
                "behavior_patterns": ["attack_lowest_hp", "random_target"],
                "adapts_to_player": False,
            },
            "moderate": {
                "decision_tree_depth": 4,
                "behavior_patterns": ["focus_healer", "use_abilities", "retreat_low_hp"],
                "adapts_to_player": True,
                "threat_system": True,
            },
            "complex": {
                "decision_tree_depth": 8,
                "behavior_patterns": ["analyze_party", "counter_strategy", "coordinate_attacks"],
                "adapts_to_player": True,
                "learning_enabled": True,
                "personality_variance": True,
            },
        }
        system["enemy_ai"] = copy.deepcopy(ai_profiles[spec.enemy_ai_complexity])
        return system

    @staticmethod
    def generate_progression_system(spec: ProgressionSystemSpec) -> Dict[str, Any]:
        if not isinstance(spec, ProgressionSystemSpec):
            raise GameMechanicsError("spec must be ProgressionSystemSpec")
        progression: Dict[str, Any] = {
            "id": str(uuid.uuid4()),
            "style": spec.style.value,
            "level_cap": spec.max_level,
            "xp_table": [],
            "stat_growth": {
                "hp_per_level": 10,
                "mana_per_level": 5,
                "stat_points_per_level": 3,
                "skill_points_per_level": 1,
            },
            "unlocks": [],
            "skill_tree": None,
            "prestige": None,
        }
        base_xp = 100
        running_total = 0
        for level in range(1, spec.max_level + 1):
            if spec.style == ProgressionStyle.EXPONENTIAL:
                required = int(base_xp * (1.5**level))
            elif spec.style == ProgressionStyle.LOGARITHMIC:
                required = int(base_xp * (level + math.log(level + 1) * 10))
            else:
                required = base_xp * level
            running_total += required
            progression["xp_table"].append(
                {"level": level, "xp_required": required, "total_xp": running_total}
            )

        if spec.style == ProgressionStyle.SKILL_TREE or spec.skill_tree_branches > 0:
            names = ("Combat", "Magic", "Utility", "Defense", "Support")
            branches = []
            for branch_index, name in enumerate(names[: spec.skill_tree_branches]):
                nodes = []
                for node_index in range(10):
                    nodes.append(
                        {
                            "id": f"skill_{branch_index}_{node_index}",
                            "name": f"{name} Skill {node_index + 1}",
                            "tier": node_index // 3 + 1,
                            "cost": node_index + 1,
                            "prerequisites": (
                                [f"skill_{branch_index}_{node_index - 1}"]
                                if node_index > 0
                                else []
                            ),
                            "effect": f"Enhances {name.lower()} capabilities",
                        }
                    )
                branches.append(
                    {"id": f"branch_{branch_index}", "name": name, "nodes": nodes}
                )
            progression["skill_tree"] = {
                "branches": branches,
                "points_per_level": 1,
                "respec_cost": 100,
                "max_points": spec.max_level,
            }

        if spec.include_prestige:
            progression["prestige"] = {
                "unlock_level": spec.max_level,
                "prestige_levels": 10,
                "bonuses_per_prestige": {
                    "xp_multiplier": 0.1,
                    "stat_bonus": 0.05,
                    "unique_unlocks": True,
                },
                "reset_on_prestige": ["level", "skills"],
                "keep_on_prestige": ["achievements", "cosmetics"],
            }
        return progression

    @staticmethod
    def generate_economy_system(spec: EconomySystemSpec) -> Dict[str, Any]:
        if not isinstance(spec, EconomySystemSpec):
            raise GameMechanicsError("spec must be EconomySystemSpec")
        currencies = {
            currency: {
                "name": currency,
                "symbol": currency[0].upper(),
                "decimal_places": 0,
                "cap": 999_999_999,
                "sources": ["enemies", "quests", "trading"],
                "sinks": ["shops", "upgrades", "services"],
            }
            for currency in spec.currencies
        }
        economy: Dict[str, Any] = {
            "id": str(uuid.uuid4()),
            "currencies": currencies,
            "trading": None,
            "crafting": None,
            "shops": [
                {
                    "id": "general_store",
                    "name": "General Store",
                    "type": "general",
                    "inventory_refresh": "daily",
                    "price_modifier": 1.0,
                    "buys_from_player": True,
                    "buy_rate": 0.5,
                }
            ],
            "inflation": None,
        }
        if spec.include_trading:
            economy["trading"] = {
                "player_to_npc": True,
                "player_to_player": False,
                "auction_house": False,
                "price_variance": 0.1,
                "reputation_discount": True,
                "max_discount": 0.25,
            }
        if spec.include_crafting:
            economy["crafting"] = {
                "stations": ["forge", "alchemy_table", "enchanting_table", "workbench"],
                "skill_based": True,
                "quality_tiers": ["common", "uncommon", "rare", "epic", "legendary"],
                "failure_chance": True,
            }
        if spec.inflation_model:
            economy["inflation"] = {
                "enabled": True,
                "rate": 0.001,
                "calculation": "per_transaction",
                "price_floor": 0.5,
                "price_ceiling": 2.0,
            }
        return economy

    @staticmethod
    def generate_ai_behavior(spec: AIBehaviorSpec) -> Dict[str, Any]:
        if not isinstance(spec, AIBehaviorSpec):
            raise GameMechanicsError("spec must be AIBehaviorSpec")
        if spec.aggression_level > 0.7:
            base = ("attack_on_sight", "pursue_aggressively", "call_reinforcements")
        elif spec.aggression_level > 0.3:
            base = ("patrol", "investigate_noise", "attack_if_threatened")
        else:
            base = ("wander", "flee_if_threatened", "hide")
        if spec.intelligence_level > 0.7:
            base += ("use_cover", "flank_target", "coordinate_with_allies", "set_traps")
        elif spec.intelligence_level > 0.3:
            base += ("seek_advantage", "retreat_when_hurt")
        behaviors = _stable_unique((*base, *spec.behaviors))
        return {
            "id": str(uuid.uuid4()),
            "entity_type": spec.entity_type,
            "root": {
                "type": "selector",
                "children": [
                    {
                        "type": "sequence",
                        "name": behavior,
                        "children": [
                            {"type": "condition", "check": f"can_{behavior}"},
                            {"type": "action", "execute": behavior},
                        ],
                    }
                    for behavior in behaviors
                ],
            },
            "states": {
                "idle": {"transitions": ["alert", "patrol"]},
                "patrol": {"transitions": ["idle", "alert", "chase"]},
                "alert": {"transitions": ["patrol", "chase", "attack"]},
                "chase": {"transitions": ["attack", "search", "return"]},
                "attack": {"transitions": ["chase", "flee", "idle"]},
                "flee": {"transitions": ["hide", "idle"]},
                "search": {"transitions": ["patrol", "chase", "idle"]},
            },
            "parameters": {
                "sight_range": 10 + spec.intelligence_level * 10,
                "hearing_range": 5 + spec.intelligence_level * 5,
                "reaction_time": 0.5 - spec.intelligence_level * 0.3,
                "memory_duration": 10 + spec.intelligence_level * 20,
                "aggression": spec.aggression_level,
                "courage": 0.5 + spec.aggression_level * 0.3,
                "flee_threshold": 0.3 - spec.aggression_level * 0.2,
            },
        }

    @staticmethod
    def generate_game_rules(genre: str) -> Dict[str, Any]:
        genre = _bounded_token("genre", genre).lower()
        template = copy.deepcopy(_RULE_TEMPLATES.get(genre, _RULE_TEMPLATES["rpg"]))
        conditions = {
            "rpg": (["defeat_final_boss", "complete_main_quest"], ["party_wipe"]),
            "arcade": (["reach_target_score", "complete_all_levels"], ["lives_depleted"]),
            "puzzle": (["goal_state_reached"], ["moves_exhausted"]),
            "simulation": (["scenario_objectives_met"], ["critical_resource_failure"]),
        }
        wins, losses = conditions.get(genre, conditions["rpg"])
        return {
            "id": str(uuid.uuid4()),
            "genre": genre,
            "core_rules": template,
            "win_conditions": list(wins),
            "lose_conditions": list(losses),
            "game_loop": {
                "phases": ["input", "simulation", "resolution", "feedback"],
                "repeat_until": "win_or_lose_condition",
            },
        }
