"""Original, lineage-bound one-source successors and exactly-three-source fusion.

Compilation is deterministic authored game design, not an unobserved claim of
having mastered an inspiration. Optional optimization executes real bounded
rollouts of the emitted game's runtime and reports separate held-out outcomes.
No original cartridge assets, source code, text or music enter emitted projects.
"""

from __future__ import annotations

import colorsys
import hashlib
import json
import math
import random
import sys
from collections import deque
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .game_style_analysis import (
    MECHANIC_CATALOG,
    GameStyleError,
    SourceGameProfile,
    analyze_play_traces,
    authored_game_profile,
    canonical,
    digest,
)

RECIPE_SCHEMA = "skeleton.game.successor_recipe.v1"
SPEC_SCHEMA = "skeleton.game.successor_spec.v1"
OPTIMIZATION_SCHEMA = "skeleton.game.successor_optimization.v1"
STYLE_PRIORITIES = ("speed", "jump_arc", "fire_cadence", "exploration", "palette", "fishing", "farming")
MECHANIC_GROUPS = tuple(dict.fromkeys(path.split(".")[0] for path in MECHANIC_CATALOG)) + ("progression",)
OPTIMIZATION_METRICS = {
    "speed_median": {"unit": "pixels/second", "minimum": 0.0, "maximum": 2000.0, "style_dimension": "speed"},
    "speed_p95": {"unit": "pixels/second", "minimum": 0.0, "maximum": 2000.0, "style_dimension": "speed"},
    "acceleration_p95": {
        "unit": "pixels/second^2",
        "minimum": 0.0,
        "maximum": 100000.0,
        "style_dimension": "speed",
    },
    "action_interval_median": {
        "unit": "seconds",
        "minimum": 0.0,
        "maximum": 600.0,
        "style_dimension": "fire_cadence",
    },
    "combat_cadence_median": {
        "unit": "seconds",
        "minimum": 0.0,
        "maximum": 600.0,
        "style_dimension": "fire_cadence",
    },
    "jump_airtime_median": {
        "unit": "seconds",
        "minimum": 0.0,
        "maximum": 600.0,
        "style_dimension": "jump_arc",
    },
    "bite_delay_median": {"unit": "seconds", "minimum": 0.0, "maximum": 60.0, "style_dimension": "fishing"},
    "catch_reel_seconds_median": {
        "unit": "seconds",
        "minimum": 0.0,
        "maximum": 60.0,
        "style_dimension": "fishing",
    },
    "distance_mean": {
        "unit": "pixels",
        "minimum": 0.0,
        "maximum": 200000.0,
        "style_dimension": "exploration",
    },
    "action_change_rate": {"unit": "ratio", "minimum": 0.0, "maximum": 1.0, "style_dimension": "exploration"},
    "idle_fraction": {"unit": "ratio", "minimum": 0.0, "maximum": 1.0, "style_dimension": "exploration"},
    "completion_fraction": {
        "unit": "ratio",
        "minimum": 0.0,
        "maximum": 1.0,
        "style_dimension": "exploration",
    },
    "death_fraction": {"unit": "ratio", "minimum": 0.0, "maximum": 1.0, "style_dimension": "exploration"},
    "fishing_attempts": {"unit": "events", "minimum": 0.0, "maximum": 32768.0, "style_dimension": "fishing"},
    "catches": {"unit": "events", "minimum": 0.0, "maximum": 32768.0, "style_dimension": "fishing"},
    "harvests": {"unit": "events", "minimum": 0.0, "maximum": 32768.0, "style_dimension": "farming"},
}


def optimization_metric_catalog() -> dict[str, dict[str, Any]]:
    """Detached authoritative target dimensions; missing exposure stays unavailable."""
    return json.loads(canonical(OPTIMIZATION_METRICS))


_FAMILY_ROLE = {
    "adventure": "adventure",
    "fishing": "fishing",
    "farming": "farming",
    "platformer": "traversal",
    "arena": "combat",
}
_AFFINITY = {
    "movement": ("adventure", "platformer"),
    "jump": ("platformer",),
    "combat": ("arena", "adventure"),
    "resources": ("farming", "adventure"),
    "adventure": ("adventure",),
    "fishing": ("fishing",),
    "farming": ("farming",),
    "camera": ("adventure", "platformer"),
    "pacing": ("arena", "farming"),
}

_STYLE_GROUP = {
    "movement": "speed",
    "jump": "jump_arc",
    "combat": "fire_cadence",
    "resources": "farming",
    "adventure": "exploration",
    "fishing": "fishing",
    "farming": "farming",
    "camera": "exploration",
    "pacing": "exploration",
}


class GameSuccessorError(GameStyleError):
    """An invalid, unauthorized, or unsupported original-game recipe."""


def _integer(value: Any, name: str, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise GameSuccessorError(f"{name} must be an integer within[{low},{high}]")
    return value


def _printable(value: Any, name: str, maximum: int = 120) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= maximum or any(ord(c) < 32 for c in value):
        raise GameSuccessorError(f"{name} must be bounded printable text")
    return value


def default_successor_profiles() -> tuple[SourceGameProfile, ...]:
    """The user's three inspirations, explicitly authored original analogs.

    Platform associations distinguish references; no actual ROM or measured
    original-game physics were supplied. Fishing is this requested design role,
    not a claim about the defining gameplay of all Pokemon games.
    """
    return (
        authored_game_profile(
            profile_id="zelda_nes_adventure_reference",
            title="Top-down adventure reference",
            family="adventure",
            reference_game="The Legend of Zelda",
            reference_platform="NES",
            mechanics={
                "movement.max_speed": 172.0,
                "movement.acceleration": 1450.0,
                "movement.friction": 1650.0,
                "adventure.melee_cooldown": 0.32,
                "adventure.interact_radius": 52.0,
                "adventure.dungeon_count": 3,
                "pacing.enemy_density": 0.3,
            },
            palette=("#223c37", "#719d60", "#dec99b", "#638899", "#c46b52"),
            loops=("explore", "solve", "fight", "discover", "unlock"),
        ),
        authored_game_profile(
            profile_id="pokemon_gb_fishing_reference",
            title="Creature fishing and collection reference",
            family="fishing",
            reference_game="Pokemon",
            reference_platform="Game Boy",
            mechanics={
                "fishing.cast_range": 112.0,
                "fishing.bite_min_seconds": 1.25,
                "fishing.bite_max_seconds": 3.75,
                "fishing.reel_speed": 0.48,
                "fishing.tension_gain": 0.95,
                "fishing.tension_release": 0.62,
                "fishing.catch_window_seconds": 8.0,
                "fishing.fish_variants": 8,
            },
            palette=("#263c58", "#72b4bf", "#cce6d2", "#e3ab64", "#9e7cad"),
            loops=("cast", "notice_bite", "manage_tension", "catch", "catalogue", "upgrade"),
        ),
        authored_game_profile(
            profile_id="harvest_moon_snes_farming_reference",
            title="Seasonal farming and village reference",
            family="farming",
            reference_game="Harvest Moon",
            reference_platform="SNES",
            mechanics={
                "farming.growth_days": 3,
                "farming.day_seconds": 75.0,
                "farming.season_days": 12,
                "farming.crop_variants": 8,
                "farming.harvest_value": 22,
                "farming.seed_cost": 4,
                "farming.weather_wet_probability": 0.3,
                "pacing.rest_frequency": 3,
            },
            palette=("#304837", "#7faa66", "#e0c680", "#b57b53", "#e3b8c3"),
            loops=("till", "plant", "water", "grow", "harvest", "sell", "improve"),
        ),
    )


@dataclass(frozen=True, slots=True)
class SuccessorRecipe:
    """Canonical immutable recipe and exact emitted project, if requested."""

    payload_json: str

    def __post_init__(self) -> None:
        try:
            raw = json.loads(self.payload_json)
        except (TypeError, ValueError, RecursionError) as exc:
            raise GameSuccessorError("successor recipe is not canonical JSON") from exc
        expected = {
            "schema_version",
            "spec",
            "profiles",
            "experience_graph",
            "decisions",
            "style_priorities",
            "lineage",
            "files",
            "implementation_digest",
            "recipe_digest",
        }
        if not isinstance(raw, dict) or set(raw) != expected or raw["schema_version"] != RECIPE_SCHEMA:
            raise GameSuccessorError("successor recipe schema/fields differ")
        profiles = [SourceGameProfile.from_dict(value) for value in raw["profiles"]]
        if len(profiles) not in (1, 3) or len({p.as_dict()["origin"]["source_id"] for p in profiles}) != len(
            profiles
        ):
            raise GameSuccessorError("successor requires one or exactly three distinct source origins")
        if not isinstance(raw["spec"], dict) or raw["spec"].get("schema_version") != SPEC_SCHEMA:
            raise GameSuccessorError("successor runtime spec differs")
        if len(canonical(raw["spec"])) > 131072:
            raise GameSuccessorError("successor runtime spec exceeds bounds")
        if raw["lineage"] != [
            p.as_dict()["origin"] | {"profile_id": p.profile_id, "profile_digest": p.digest} for p in profiles
        ]:
            raise GameSuccessorError("successor source lineage differs from exact profiles")
        origins = raw["spec"].get("origins")
        if not isinstance(origins, list) or len(origins) != len(profiles):
            raise GameSuccessorError("successor runtime origins differ from recipe lineage")
        weights = []
        for profile, origin in zip(profiles, origins, strict=True):
            source = profile.as_dict()
            expected_origin = {
                "profile_id": profile.profile_id,
                "source_id": source["origin"]["source_id"],
                "source_digest": source["origin"]["source_digest"],
                "bundle_digest": source["origin"]["bundle_digest"],
                "profile_digest": profile.digest,
                "role": _FAMILY_ROLE[source["family"]],
            }
            if (
                not isinstance(origin, dict)
                or set(origin) != set(expected_origin) | {"weight"}
                or any(origin[k] != v for k, v in expected_origin.items())
            ):
                raise GameSuccessorError("runtime source identity/profile/role differs")
            weight = origin["weight"]
            if type(weight) not in (int, float) or not 0 < weight <= 1 or not math.isfinite(weight):
                raise GameSuccessorError("runtime source influence weight differs")
            weights.append(weight)
        if not math.isclose(math.fsum(weights), 1.0, rel_tol=0, abs_tol=1e-12):
            raise GameSuccessorError("runtime source weights must normalize to one")
        if not isinstance(raw["files"], dict) or len(raw["files"]) > 128:
            raise GameSuccessorError("successor emitted project files exceed bounds")
        total = 0
        for path, content in raw["files"].items():
            if (
                not isinstance(path, str)
                or path.startswith(("/", "\\"))
                or "\\" in path
                or any(part in ("", ".", "..") for part in path.split("/"))
                or not isinstance(content, str)
            ):
                raise GameSuccessorError("successor project file path/content differs")
            total += len(content.encode("utf-8"))
        if total > 8 * 1024 * 1024:
            raise GameSuccessorError("successor project bytes exceed8MiB")
        unsigned = {k: v for k, v in raw.items() if k != "recipe_digest"}
        if raw["recipe_digest"] != digest(unsigned) or canonical(raw).decode() != self.payload_json:
            raise GameSuccessorError("successor recipe digest/encoding differs")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> SuccessorRecipe:
        return cls(canonical(dict(value)).decode())

    def as_dict(self) -> dict[str, Any]:
        return json.loads(self.payload_json)

    @property
    def spec(self) -> dict[str, Any]:
        return self.as_dict()["spec"]

    @property
    def files(self) -> dict[str, str]:
        return self.as_dict()["files"]

    @property
    def digest(self) -> str:
        return self.as_dict()["recipe_digest"]


def _authorize(
    profiles: Iterable[SourceGameProfile], authorize_source: Callable[[Mapping[str, Any]], None] | None
) -> None:
    for profile in profiles:
        origin = profile.as_dict()["origin"]
        if origin["source_kind"] != "authored_reference" and authorize_source is None:
            raise GameSuccessorError("current source authorization callback required for ingested influence")
        if authorize_source is not None:
            outcome = authorize_source(
                origin | {"profile_id": profile.profile_id, "profile_digest": profile.digest}
            )
            if outcome is False:
                raise GameSuccessorError("current source authorization denied")
            if outcome is not None and outcome is not True:
                raise GameSuccessorError("source authorization must finish synchronously")


def _influences(
    profiles: tuple[SourceGameProfile, ...],
    weights: Mapping[str, float] | None,
    priorities: Mapping[str, str] | None,
) -> tuple[dict[str, float], dict[str, str]]:
    ids = {p.profile_id for p in profiles}
    values = dict(weights or {p.profile_id: 1.0 for p in profiles})
    if set(values) != ids:
        raise GameSuccessorError("influence weights must bind every exact profile")
    if any(type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1 for v in values.values()):
        raise GameSuccessorError("influence weights must be finite within[0,1]")
    if any(v <= 0 for v in values.values()):
        raise GameSuccessorError("every identified origin must have positive influence")
    total = math.fsum(values.values())
    clean = {key: value / total for key, value in values.items()}
    groups = dict(priorities or {})
    if set(groups) - set(MECHANIC_GROUPS) or any(value not in ids for value in groups.values()):
        raise GameSuccessorError("mechanic priority must name a declared group and exact source profile")
    return clean, groups


def _fuse(
    profiles: tuple[SourceGameProfile, ...],
    weights: Mapping[str, float],
    priorities: Mapping[str, str],
    style_priorities: Mapping[str, float],
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    raw = [p.as_dict() for p in profiles]
    mechanics: dict[str, dict[str, Any]] = {}
    decisions = []
    for path, (low, high, default, unit, integer) in MECHANIC_CATALOG.items():
        group, field = path.split(".")
        candidates = [p for p in raw if path in p["mechanics"]]
        if group in priorities:
            candidates = [p for p in candidates if p["profile_id"] == priorities[group]]
            if not candidates:
                raise GameSuccessorError("selected source lacks its required mechanic evidence")
            policy = "explicit_source_priority"
        else:
            affinity = [p for p in candidates if p["family"] in _AFFINITY.get(group, ())]
            if affinity:
                candidates = affinity
            policy = "role_then_confidence_weighted_blend"
        contributors = []
        denominator = 0.0
        numerator = 0.0
        for p in candidates:
            evidence = p["mechanics"][path]
            factor = weights[p["profile_id"]] * max(0.05, evidence["confidence"])
            denominator += factor
            numerator += evidence["value"] * factor
            contributors.append(
                {
                    "profile_id": p["profile_id"],
                    "value": evidence["value"],
                    "classification": evidence["classification"],
                    "confidence": evidence["confidence"],
                    "weight": factor,
                    "evidence_refs": evidence["evidence_refs"],
                }
            )
        chosen = default if not denominator else numerator / denominator
        retention = style_priorities.get(_STYLE_GROUP[group], 1.0)
        chosen = default + (chosen - default) * retention
        chosen = min(high, max(low, chosen))
        if integer:
            chosen = math.floor(chosen + 0.5)
        mechanics.setdefault(group, {})[field] = chosen
        decisions.append(
            {
                "mechanic": path,
                "value": chosen,
                "unit": unit,
                "policy": policy,
                "contributors": contributors,
                "retention": retention,
                "evidence_status": (
                    "authored_fallback"
                    if not contributors
                    else (
                        "measured"
                        if all(x["classification"] == "measured" for x in contributors)
                        else "authored_or_declared"
                    )
                ),
            }
        )
    fish = mechanics["fishing"]
    if fish["bite_max_seconds"] < fish["bite_min_seconds"]:
        fish["bite_max_seconds"] = fish["bite_min_seconds"]
        decisions.append(
            {
                "mechanic": "fishing.bite_max_seconds",
                "policy": "coherence_floor",
                "value": fish["bite_max_seconds"],
                "reason": "maximum bite delay cannot precede minimum",
            }
        )
    farm = mechanics["farming"]
    if farm["harvest_value"] <= farm["seed_cost"]:
        previous_cost = farm["seed_cost"]
        farm["seed_cost"] = min(98, farm["seed_cost"])
        farm["harvest_value"] = farm["seed_cost"] + 2
        decisions.append(
            {
                "mechanic": "farming.harvest_value",
                "policy": "positive_authored_economy",
                "value": farm["harvest_value"],
                "seed_cost_before": previous_cost,
                "seed_cost_after": farm["seed_cost"],
                "reason": "harvest value exceeds consumed seed cost",
            }
        )
    return mechanics, decisions


def _palette(
    profiles: tuple[SourceGameProfile, ...], weights: Mapping[str, float], retention: float
) -> dict[str, str]:
    # New swatches derive from weighted color statistics with an authored hue
    # offset; no image, tile, sprite or palette file is copied from a source.
    keys = ("background", "terrain", "player", "enemy", "accent", "collectible")
    result = {}
    baseline = ("#203a38", "#7a9e69", "#e5c67b", "#ab6470", "#7ab4ba", "#e0ad64")
    for index, key in enumerate(keys):
        sums = [0.0, 0.0, 0.0]
        for profile in profiles:
            p = profile.as_dict()
            color = p["palette"][index % len(p["palette"])][1:]
            for axis in range(3):
                sums[axis] += int(color[axis * 2 : axis * 2 + 2], 16) / 255 * weights[profile.profile_id]
        for axis in range(3):
            original = int(baseline[index][1 + axis * 2 : 3 + axis * 2], 16) / 255
            sums[axis] = original + (sums[axis] - original) * retention
        hue, saturation, value = colorsys.rgb_to_hsv(*sums)
        color = colorsys.hsv_to_rgb(
            (hue + 0.021 * (index + 1)) % 1, min(0.85, max(0.2, saturation)), min(0.95, max(0.14, value))
        )
        result[key] = "#" + "".join(f"{round(c * 255):02x}" for c in color)
    return result


def _world(seed: int, mechanics: Mapping[str, Any], *, top_down: bool) -> dict[str, Any]:
    rng = random.Random(seed)
    if not top_down:
        width = 3072
        return {
            "width": width,
            "height": 720,
            "tile_size": 32,
            "spawn": [64, 574],
            "goal": [width - 64, 574],
            "platforms": [{"id": "floor", "x": 0, "y": 600, "w": width, "h": 120, "kind": "solid"}]
            + [
                {
                    "id": f"ledge-{i}",
                    "x": 384 + i * 448,
                    "y": 520 - (i % 2) * 40,
                    "w": 160,
                    "h": 16,
                    "kind": "solid",
                }
                for i in range(6)
            ],
            "doors": [],
            "checkpoints": [{"id": "start", "x": 64, "y": 574}],
            "collectibles": [
                {"id": f"shard-{i}", "x": 512 + i * 896, "y": 574, "kind": "shard", "value": 1}
                for i in range(3)
            ],
            "enemies": [
                {
                    "id": f"watcher-{i}",
                    "x": 704 + i * 704,
                    "y": 574,
                    "kind": "patrol",
                    "hp": 3,
                    "speed": 48,
                    "patrol": [624 + i * 704, 784 + i * 704],
                    "attack_interval": 1.5,
                }
                for i in range(3)
            ],
            "boss": {"id": "stone-warden", "x": 2816, "y": 574, "hp": 12, "attack_interval": 1.8},
        }
    width, height = 6144, 3072
    # Walkable original open-world districts with clear connecting corridors.
    ponds = [
        {"id": "reedwater", "x": 896, "y": 512, "w": 640, "h": 416},
        {"id": "glassmere", "x": 3264, "y": 1536, "w": 736, "h": 448},
        {"id": "moonwell", "x": 4864, "y": 448, "w": 544, "h": 352},
    ]
    plots = [
        {"id": f"homestead-{i}", "x": 384 + (i % 6) * 48, "y": 896 + (i // 6) * 48, "w": 40, "h": 40}
        for i in range(18)
    ]
    obstacles = []
    for i in range(24):
        x = rng.randrange(12, 178) * 32
        y = rng.randrange(6, 86) * 32
        # Preserve roads, village/farm, pond margins and completion approach.
        if x < 1024 or abs(y - 512) < 160 or abs(y - 1248) < 160 or abs(x - 2880) < 192 or x > 5376:
            continue
        if any(
            p["x"] - 96 <= x <= p["x"] + p["w"] + 96 and p["y"] - 96 <= y <= p["y"] + p["h"] + 96
            for p in ponds
        ):
            continue
        obstacles.append({"id": f"grove-rock-{i}", "x": x, "y": y, "w": 64, "h": 64, "kind": "solid"})
    enemies = []
    count = min(16, max(3, round(mechanics["pacing"]["enemy_density"] * 24)))
    for i in range(count):
        x = 2112 + (i % 4) * 704
        y = 832 + (i // 4) * 512
        if any(
            p["x"] - 32 <= x <= p["x"] + p["w"] + 32 and p["y"] - 32 <= y <= p["y"] + p["h"] + 32
            for p in ponds
        ):
            y = min(p["y"] for p in ponds if p["x"] - 32 <= x <= p["x"] + p["w"] + 32) - 64
        enemies.append(
            {
                "id": f"moss-guardian-{i}",
                "x": x,
                "y": y,
                "kind": "patrol" if i % 2 else "shooter",
                "hp": 3 + i % 3,
                "speed": 38 + i % 3 * 8,
                "patrol": [x - 96, x + 96],
                "attack_interval": 1.8 + i % 3 * 0.3,
            }
        )
    terrain = []
    for row in range(height // 32):
        tiles = []
        for col in range(width // 32):
            x, y = col * 32, row * 32
            code = "0" if col < 64 else "3" if col < 128 else "5"
            if abs(y - 512) < 48 or abs(y - 1248) < 48 or abs(x - 2880) < 48:
                code = "4"
            if any(p["x"] <= x < p["x"] + p["w"] and p["y"] <= y < p["y"] + p["h"] for p in ponds):
                code = "1"
            if any(p["x"] <= x < p["x"] + p["w"] and p["y"] <= y < p["y"] + p["h"] for p in plots):
                code = "6"
            tiles.append(code)
        terrain.append("".join(tiles))
    fish_names = (
        "Siltglider",
        "Prismperch",
        "Reedskipper",
        "Lanternfin",
        "Glassgill",
        "Dusktrout",
        "Mistwhisker",
        "Crowncarp",
    )
    crop_names = (
        "Amberroot",
        "Sunleaf",
        "Mistbean",
        "Moonmelon",
        "Cloudgrain",
        "Dawnpepper",
        "Riverberry",
        "Starbulb",
    )
    fish_variants = [
        {"id": f"fish-{i}", "name": name, "value": 8 + i * 4, "difficulty": 0.25 + i * 0.08}
        for i, name in enumerate(fish_names[: min(8, mechanics["fishing"]["fish_variants"])])
    ]
    crop_variants = [
        {
            "id": f"crop-{i}",
            "name": name,
            "growth_days": min(14, mechanics["farming"]["growth_days"] + i % 3),
            "value": min(100, mechanics["farming"]["harvest_value"] + i * 3),
            "seed_cost": min(
                min(100, mechanics["farming"]["harvest_value"] + i * 3) - 1,
                mechanics["farming"]["seed_cost"] + i,
            ),
            "season": ("spring", "summer", "autumn", "winter")[i % 4],
        }
        for i, name in enumerate(crop_names[: min(8, mechanics["farming"]["crop_variants"])])
    ]
    rest_count = min(
        16,
        max(
            1,
            math.ceil(
                math.ceil(width / mechanics["pacing"]["room_length"]) / mechanics["pacing"]["rest_frequency"]
            ),
        ),
    )
    checkpoints = [{"id": "village", "x": 768, "y": 800}] + [
        {"id": f"trail-rest-{i}", "x": round(1024 + i * (width - 1536) / max(1, rest_count - 1)), "y": 1248}
        for i in range(1, rest_count)
    ]
    dungeon_sites = (
        (2112, 832),
        (3520, 2336),
        (5376, 2240),
        (4160, 800),
        (1728, 2240),
        (2816, 832),
        (4480, 2336),
        (5184, 1120),
    )
    dungeons = [
        {"id": f"valley-sanctum-{i}", "x": x, "y": y, "w": 384, "h": 320, "requires": "key"}
        for i, (x, y) in enumerate(dungeon_sites[: mechanics["adventure"]["dungeon_count"]])
    ]
    obstacles = [
        rock
        for rock in obstacles
        if not any(
            room["x"] - 64 < rock["x"] < room["x"] + room["w"] + 64
            and room["y"] - 64 < rock["y"] < room["y"] + room["h"] + 64
            for room in dungeons
        )
    ]
    for room in dungeons:
        x, y, w, h = room["x"], room["y"], room["w"], room["h"]
        segments = (
            (x, y, w, 32),
            (x, y, 32, h),
            (x + w - 32, y, 32, h),
            (x, y + h - 32, 128, 32),
            (x + w - 128, y + h - 32, 128, 32),
            (x + 160, y + 160, 64, 64),
        )
        for index, (wx, wy, ww, wh) in enumerate(segments):
            obstacles.append(
                {"id": f'{room["id"]}-wall-{index}', "x": wx, "y": wy, "w": ww, "h": wh, "kind": "solid"}
            )
    for index, enemy in enumerate(enemies):
        if index < len(dungeons):
            room = dungeons[index]
            enemy["x"], enemy["y"] = room["x"] + 96, room["y"] + 112
            enemy["patrol"] = [room["x"] + 64, room["x"] + 128]
        elif any(
            r["x"] - 32 <= enemy["x"] <= r["x"] + r["w"] + 32
            and r["y"] - 32 <= enemy["y"] <= r["y"] + r["h"] + 32
            for r in obstacles
        ):
            enemy["y"] = 1376
    for row, tiles in enumerate(terrain):
        updated = list(tiles)
        for col in range(len(updated)):
            x, y = col * 32 + 16, row * 32 + 16
            if any(r["x"] <= x < r["x"] + r["w"] and r["y"] <= y < r["y"] + r["h"] for r in obstacles):
                updated[col] = "2"
        terrain[row] = "".join(updated)
    relics = []
    fallback = ((1920, 512), (2880, 1248), (4608, 2240))
    for index in range(3):
        x, y = (
            (dungeons[index]["x"] + 192, dungeons[index]["y"] + 80)
            if index < len(dungeons)
            else fallback[index]
        )
        relics.append({"id": f"waystone-{index}", "x": x, "y": y, "kind": "shard", "value": 1})
    last_room = dungeons[min(2, len(dungeons) - 1)]
    landmarks = [
        {
            "id": "home-cottage",
            "x": 544,
            "y": 672,
            "w": 96,
            "h": 64,
            "kind": "house",
            "name": "Riverlight Homestead",
            "sprite_index": 41,
        },
        {
            "id": "market-stall",
            "x": 656,
            "y": 672,
            "w": 96,
            "h": 48,
            "kind": "stall",
            "name": "Rillhaven Exchange",
            "sprite_index": 40,
        },
        {
            "id": "tackle-workshop",
            "x": 400,
            "y": 704,
            "w": 96,
            "h": 64,
            "kind": "house",
            "name": "Nia's Tackle and Tools",
            "sprite_index": 41,
        },
        {
            "id": "casting-pier",
            "x": 832,
            "y": 752,
            "w": 64,
            "h": 32,
            "kind": "pier",
            "name": "Reedwater Casting Dock",
            "sprite_index": 47,
        },
        {
            "id": "village-well",
            "x": 768,
            "y": 704,
            "w": 32,
            "h": 32,
            "kind": "well",
            "name": "Rillhaven Well",
            "sprite_index": 44,
        },
        {
            "id": "garden-sign",
            "x": 800,
            "y": 832,
            "w": 24,
            "h": 32,
            "kind": "sign",
            "name": "Garden west, lakes east, trails south",
            "sprite_index": 56,
        },
        {
            "id": "glassmere-camp",
            "x": 3040,
            "y": 1424,
            "w": 96,
            "h": 64,
            "kind": "camp",
            "name": "Glassmere Angler Camp",
            "sprite_index": 41,
        },
        {
            "id": "highland-inn",
            "x": 4384,
            "y": 1152,
            "w": 128,
            "h": 64,
            "kind": "house",
            "name": "The Lantern Rest",
            "sprite_index": 41,
        },
        {
            "id": "moonwell-pier",
            "x": 4800,
            "y": 608,
            "w": 64,
            "h": 32,
            "kind": "pier",
            "name": "Moonwell Tackle Point",
            "sprite_index": 47,
        },
    ]
    for prop in landmarks:
        if prop["kind"] in ("house", "stall", "camp"):
            obstacles.append(
                {
                    "id": prop["id"] + "-body",
                    "x": prop["x"],
                    "y": prop["y"],
                    "w": prop["w"],
                    "h": prop["h"],
                    "kind": "building",
                }
            )
    fences = (
        (352, 864, 16, 208),
        (704, 864, 16, 208),
        (352, 864, 128, 16),
        (608, 864, 112, 16),
        (352, 1072, 368, 16),
    )
    for index, (x, y, w, h) in enumerate(fences):
        obstacles.append({"id": f"homestead-fence-{index}", "x": x, "y": y, "w": w, "h": h, "kind": "fence"})
    for index, rock in enumerate(obstacles[:10]):
        if rock["id"].startswith("grove-rock"):
            rock["kind"] = "tree" if index % 2 else "rock"
            landmarks.append(
                {
                    "id": rock["id"] + "-art",
                    "x": rock["x"],
                    "y": rock["y"],
                    "w": rock["w"],
                    "h": rock["h"],
                    "kind": "tree",
                    "name": "Original valley grove",
                    "sprite_index": 28 if index % 2 else 30,
                }
            )
    for index, checkpoint in enumerate(checkpoints):
        landmarks.append(
            {
                "id": checkpoint["id"] + "-landmark",
                "x": checkpoint["x"] - 16,
                "y": checkpoint["y"] - 24,
                "w": 32,
                "h": 48,
                "kind": "well",
                "name": "Rest waystone " + str(index + 1),
                "sprite_index": 44,
            }
        )
    return {
        "width": width,
        "height": height,
        "tile_size": 32,
        "spawn": [768, 800],
        "goal": [5632, 2560],
        "platforms": obstacles,
        "doors": [
            {
                "id": "meadow-trail-gate",
                "x": 1792,
                "y": 1216,
                "w": 32,
                "h": 32,
                "target_x": 4160,
                "target_y": 1216,
                "requires": "key",
            },
            {
                "id": "highland-trail-gate",
                "x": 4160,
                "y": 1216,
                "w": 32,
                "h": 32,
                "target_x": 1760,
                "target_y": 1216,
                "requires": "key",
            },
        ],
        "checkpoints": checkpoints,
        "collectibles": relics
        + [
            {"id": "meadow-supply", "x": 1856, "y": 1248, "kind": "health", "value": 2},
            {"id": "highland-supply", "x": 4352, "y": 1248, "kind": "energy", "value": 8},
        ],
        "enemies": enemies,
        "boss": {
            "id": "orchard-warden",
            "x": last_room["x"] + 256,
            "y": last_room["y"] + 160,
            "hp": 18,
            "attack_interval": 2.1,
        },
        "ponds": ponds,
        "farm_plots": plots,
        "landmarks": landmarks,
        "terrain": terrain,
        "fish_variants": fish_variants,
        "crop_variants": crop_variants,
        "villagers": [
            {
                "id": "mara",
                "x": 704,
                "y": 720,
                "role": "shop",
                "dialogue": "Trade your harvest and catch for seeds, tackle and trail supplies.",
            },
            {
                "id": "orin",
                "x": 832,
                "y": 768,
                "role": "quest",
                "dialogue": "Watch the bite, then balance reel progress and line tension.",
            },
            {
                "id": "nia",
                "x": 448,
                "y": 768,
                "role": "crafter",
                "dialogue": "Water growing crops each day. Seasons change what thrives.",
            },
        ],
        "shops": [{"id": "village-exchange", "x": 704, "y": 720}],
        "dungeons": dungeons,
        "biomes": [
            {"id": "home-meadow", "x": 0, "y": 0, "w": 2048, "h": height, "kind": "meadow"},
            {"id": "lake-country", "x": 2048, "y": 0, "w": 2048, "h": height, "kind": "wetland"},
            {"id": "orchard-highlands", "x": 4096, "y": 0, "w": 2048, "h": height, "kind": "highland"},
        ],
    }


def validate_successor_routes(spec: Mapping[str, Any]) -> dict[str, Any]:
    """Analytic authored geometry validation, explicitly separate from play metrics.

    A body-sized flood checks the top-down spawn, goal, relics and interaction
    areas. It does not pretend to solve combat, fishing or farming tasks.
    """
    if spec.get("gameplay_mode") != "top_down":
        return {
            "classification": "analytic_geometry",
            "method": "sideview_continuous_floor",
            "measured_play": False,
            "goal_route": True,
        }
    world = spec["world"]
    tile = world["tile_size"]
    columns, rows = math.ceil(world["width"] / tile), math.ceil(world["height"] / tile)
    if columns * rows > 32768:
        raise GameSuccessorError("authored route grid exceeds bounded capacity")
    obstacles = world.get("platforms", []) + world.get("obstacles_rects", []) + world.get("ponds", [])
    terrain = world.get("terrain")
    open_cells = set()
    for row in range(rows):
        for col in range(columns):
            x, y = (col + 0.5) * tile - 9, (row + 0.5) * tile - 10
            if x < 0 or y < 0 or x + 18 > world["width"] or y + 20 > world["height"]:
                continue
            if terrain is not None and terrain[row][col] in "12":
                continue
            if any(
                x < r["x"] + r["w"] and x + 18 > r["x"] and y < r["y"] + r["h"] and y + 20 > r["y"]
                for r in obstacles
            ):
                continue
            open_cells.add((col, row))
    spawn = tuple(int(value // tile) for value in world["spawn"])
    if spawn not in open_cells:
        raise GameSuccessorError("original world spawn is obstructed")
    queue = deque([spawn])
    visited = {spawn}
    while queue:
        col, row = queue.popleft()
        for cell in ((col - 1, row), (col + 1, row), (col, row - 1), (col, row + 1)):
            if cell in open_cells and cell not in visited:
                visited.add(cell)
                queue.append(cell)
    targets = {"goal": world["goal"]} | {
        r["id"]: [r["x"], r["y"]]
        for r in world.get("collectibles", [])
        if r.get("kind") in ("shard", "relic", "key")
    }
    reachable = {
        name: tuple(int(value // tile) for value in point) in visited for name, point in targets.items()
    }
    if not all(reachable.values()):
        raise GameSuccessorError("authored world contains an unreachable goal, key or relic")
    return {
        "classification": "analytic_geometry",
        "method": "body-aware-four-neighbor-cell-flood-v1",
        "measured_play": False,
        "cell_size": tile,
        "visited_cells": len(visited),
        "open_cells": len(open_cells),
        "targets": reachable,
        "gate_assumption": "conditional key gates evaluated after their authored unlock",
        "goal_route": reachable["goal"],
    }


def compile_successor(
    profiles: Iterable[SourceGameProfile | Mapping[str, Any]],
    *,
    project_id: str,
    title: str,
    seed: int = 1,
    weights: Mapping[str, float] | None = None,
    mechanic_priorities: Mapping[str, str] | None = None,
    style_priorities: Mapping[str, float] | None = None,
    authorize_source: Callable[[Mapping[str, Any]], None] | None = None,
    emit_project: bool = True,
) -> SuccessorRecipe:
    values = []
    for index, value in enumerate(profiles):
        if index >= 3:
            raise GameSuccessorError("successor supports one or exactly three origins")
        values.append(value if isinstance(value, SourceGameProfile) else SourceGameProfile.from_dict(value))
    sources = tuple(values)
    if (
        len(sources) not in (1, 3)
        or len({p.profile_id for p in sources}) != len(sources)
        or len({p.as_dict()["origin"]["source_id"] for p in sources}) != len(sources)
    ):
        raise GameSuccessorError("successor requires one or exactly three distinct profiles and origins")
    _printable(project_id, "project id", 96)
    if not project_id[0].isalnum() or any(
        c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-" for c in project_id
    ):
        raise GameSuccessorError("project id must be path safe")
    _printable(title, "game title")
    _integer(seed, "game seed", 0, 2**32 - 1)
    if type(emit_project) is not bool:
        raise GameSuccessorError("emit_project must be boolean")
    _authorize(sources, authorize_source)
    influence, priorities = _influences(sources, weights, mechanic_priorities)
    styles = {name: 1.0 for name in STYLE_PRIORITIES}
    if style_priorities is not None:
        styles.update(style_priorities)
    if set(styles) - set(STYLE_PRIORITIES) or any(
        type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1 for v in styles.values()
    ):
        raise GameSuccessorError("style priorities must name declared dimensions within[0,1]")
    mechanics, decisions = _fuse(sources, influence, priorities, styles)
    top_down = not any(p.as_dict()["family"] == "platformer" for p in sources)
    mechanics["progression"] = {
        "required_collectibles": 3,
        "quest_text": "Restore the three waystones: explore the valleys, cultivate a home and catalogue the lakes.",
        "required_catches": 2 if top_down else 0,
        "required_harvests": 3 if top_down else 0,
        "requires_boss": True,
        "unlock_rules": {
            "tackle_requires_sold_harvest": 1,
            "key_requires_rod_level": 2,
            "key_requires_rare_fish": 1,
            "rare_fish_difficulty": 0.65,
        },
        "quests": [
            {"id": "lake-ledger", "text": "Land two valley fish.", "kind": "fish", "count": 2, "reward": 20},
            {
                "id": "first-harvest",
                "text": "Harvest three homegrown crops.",
                "kind": "harvest",
                "count": 3,
                "reward": 30,
            },
            {
                "id": "waystone-trail",
                "text": "Recover the three original waystones.",
                "kind": "relic",
                "count": 3,
                "reward": 40,
            },
            {
                "id": "warden",
                "text": "Defeat the orchard warden.",
                "kind": "defeat",
                "count": 1,
                "reward": 60,
            },
        ],
    }
    progression_source = next((p for p in sources if p.profile_id == priorities.get("progression")), None)
    if progression_source is not None and top_down:
        family = progression_source.as_dict()["family"]
        counts = (4, 1) if family == "fishing" else (1, 5) if family == "farming" else (2, 3)
        mechanics["progression"]["required_catches"], mechanics["progression"]["required_harvests"] = counts
        mechanics["progression"]["quests"][0]["count"] = counts[0]
        mechanics["progression"]["quests"][1]["count"] = counts[1]
        decisions.append(
            {
                "mechanic": "progression",
                "policy": "explicit_source_role_priority",
                "profile_id": progression_source.profile_id,
                "role": family,
                "required_catches": counts[0],
                "required_harvests": counts[1],
                "evidence_status": "authored_original_goal_composition",
            }
        )
    origins = []
    for p in sources:
        raw = p.as_dict()
        origins.append(
            {
                "profile_id": p.profile_id,
                "source_id": raw["origin"]["source_id"],
                "source_digest": raw["origin"]["source_digest"],
                "bundle_digest": raw["origin"]["bundle_digest"],
                "profile_digest": p.digest,
                "role": _FAMILY_ROLE[raw["family"]],
                "weight": influence[p.profile_id],
            }
        )
    camera = mechanics.pop("camera")
    spec = {
        "schema_version": SPEC_SCHEMA,
        "project_id": project_id,
        "title": title,
        "seed": seed,
        "gameplay_mode": "top_down" if top_down else "side_scroll",
        "origins": origins,
        "palette": _palette(sources, influence, styles["palette"]),
        "camera": {
            "mode": "top_down" if top_down else "side_scroll",
            "lookahead": camera["lookahead"],
            "smoothing": camera["smoothing"],
        },
        "mechanics": mechanics,
        "world": _world(seed, mechanics, top_down=top_down),
    }
    graph = {
        "nodes": [
            {"id": "home", "role": "safe_hub"},
            {"id": "fields", "role": "resource_cycle"},
            {"id": "lakes", "role": "timing_and_collection"},
            {"id": "exchange", "role": "economy"},
            {"id": "trails", "role": "exploration"},
            {"id": "sanctum", "role": "adventure_resolution"},
        ],
        "edges": [
            {"from": "fields", "to": "exchange", "resource": "harvest"},
            {"from": "lakes", "to": "exchange", "resource": "fish"},
            {"from": "exchange", "to": "fields", "resource": "seeds"},
            {"from": "exchange", "to": "lakes", "resource": "tackle"},
            {"from": "exchange", "to": "trails", "resource": "supplies"},
            {"from": "trails", "to": "sanctum", "resource": "waystones"},
            {"from": "sanctum", "to": "home", "resource": "world_restoration"},
        ],
        "design_status": "authored_original_mechanics_not_measured_player_satisfaction",
        "route_validation": validate_successor_routes(spec),
    }
    files: dict[str, str] = {}
    if emit_project:
        from .game_successor_runtime import emit_successor_project

        files = emit_successor_project(spec)
    _authorize(sources, authorize_source)
    raw = {
        "schema_version": RECIPE_SCHEMA,
        "spec": spec,
        "profiles": [p.as_dict() for p in sources],
        "experience_graph": graph,
        "decisions": decisions,
        "style_priorities": styles,
        "lineage": [
            p.as_dict()["origin"] | {"profile_id": p.profile_id, "profile_digest": p.digest} for p in sources
        ],
        "files": files,
        "implementation_digest": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    raw["recipe_digest"] = digest(raw)
    return SuccessorRecipe.from_dict(raw)


def _rollout(
    spec: Mapping[str, Any],
    *,
    seeds: tuple[int, ...],
    steps: int,
    policy: Callable[[Mapping[str, float], int, Mapping[str, Any]], str] | None,
    environment_factory: Callable[[Mapping[str, Any], int], Any],
    cancel: Callable[[], bool] | None,
    authorize: Callable[[], None] | None,
    on_trace: Callable[[Mapping[str, Any]], None] | None = None,
) -> dict[str, Any]:
    traces = []
    for seed in seeds:
        if cancel is not None and cancel():
            raise GameSuccessorError("successor optimization cancelled")
        if authorize is not None:
            authorize()
        env = environment_factory(spec, steps)
        try:
            observation = dict(env.reset(seed))
            descriptor = env.spec.as_dict()
            transitions = []
            for sequence in range(1, steps + 1):
                if cancel is not None and cancel():
                    raise GameSuccessorError("successor optimization cancelled")
                if authorize is not None:
                    authorize()
                if policy is None:
                    allowed = descriptor["actions"]
                    # Deterministic real input protocol probes exploration and
                    # each available interaction; it is not an expert player.
                    preferred = (
                        "right",
                        "down",
                        "interact",
                        "fish",
                        "hoe",
                        "plant",
                        "water",
                        "harvest",
                        "attack",
                        "rest",
                        "up",
                        "left",
                    )
                    candidates = [action for action in preferred if action in allowed]
                    action = (
                        candidates[((sequence - 1) // 30 + seed) % len(candidates)]
                        if candidates
                        else allowed[0]
                    )
                else:
                    action = policy(observation, sequence, descriptor)
                step = env.step(action)
                after = dict(step.observation)
                terminal, truncated = step.terminated, step.truncated
                if sequence == steps and not terminal:
                    truncated = True
                transition = {
                    "sequence": sequence,
                    "observation": observation,
                    "action": action,
                    "next_observation": after,
                    "reward": step.reward,
                    "reward_components": dict(step.reward_components),
                    "terminated": terminal,
                    "truncated": truncated,
                    "info": dict(step.info),
                }
                if step.transition_digest:
                    transition["transition_digest"] = step.transition_digest
                transitions.append(transition)
                observation = after
                if terminal or truncated:
                    break
            trace = {
                "schema_version": "skeleton.game.trace.v1",
                "environment": descriptor,
                "episode_id": f"successor-measure-{seed}",
                "seed": seed,
                "source_lineage": {
                    "recipe_spec_digest": digest(spec),
                    "rights_acknowledged": True,
                    "measurement": "actual_successor_runtime_rollout",
                },
                "transitions": transitions,
                "steps": len(transitions),
                "return": math.fsum(t["reward"] for t in transitions),
            }
            trace["trace_digest"] = digest(trace)
            traces.append(trace)
        finally:
            closer = getattr(env, "close", None)
            if callable(closer):
                closer()
    analysis = analyze_play_traces(
        traces,
        coordinate_units="pixels",
        coordinate_scale={"x": spec["world"]["width"], "y": spec["world"]["height"]},
        verified_trace_digests=[t["trace_digest"] for t in traces],
    )
    if on_trace is not None:
        for trace in traces:
            if authorize is not None:
                authorize()
            on_trace(json.loads(canonical(trace)))
    return {"analysis": analysis, "traces": traces}


def _metric_score(
    metrics: Mapping[str, Any], targets: Mapping[str, float], priorities: Mapping[str, float]
) -> float:
    dimensions = {key: value["style_dimension"] for key, value in OPTIMIZATION_METRICS.items()}
    denominator = math.fsum(priorities.get(dimensions[key], 1.0) for key in targets)
    if denominator <= 0:
        raise GameSuccessorError("selected target dimensions all have zero preservation priority")
    if any(metrics[key] is None and priorities.get(dimensions[key], 1.0) > 0 for key in targets):
        return math.inf
    return (
        math.fsum(
            abs(metrics[key] - target) / max(1.0, abs(target)) * priorities.get(dimensions[key], 1.0)
            for key, target in targets.items()
            if priorities.get(dimensions[key], 1.0) > 0
        )
        / denominator
    )


def _runtime_identity() -> dict[str, Any]:
    names = (
        "game_successor.py",
        "game_style_analysis.py",
        "game_successor_runtime.py",
        "game_successor_world.py",
    )
    return {
        "python": list(sys.version_info[:3]),
        "sources": {
            name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
            for name in names
            if Path(__file__).with_name(name).is_file()
        },
    }


def optimize_successor(
    recipe: SuccessorRecipe,
    *,
    target_metrics: Mapping[str, float],
    candidates: int = 8,
    episodes: int = 3,
    max_steps: int = 512,
    seed: int = 7,
    policy: Callable[[Mapping[str, float], int, Mapping[str, Any]], str] | None = None,
    environment_factory: Callable[[Mapping[str, Any], int], Any] | None = None,
    authorize_source: Callable[[Mapping[str, Any]], None] | None = None,
    cancel: Callable[[], bool] | None = None,
    on_progress: Callable[[Mapping[str, Any]], None] | None = None,
    on_trace: Callable[[Mapping[str, Any]], None] | None = None,
    emit_project: bool = True,
) -> dict[str, Any]:
    """Actual bounded seeded coordinate search with an untouched held-out ledger.

    Scores measure distance to explicit authored target statistics. The default
    controller is a documented input probe, not learned game mastery; callers
    can pass a genuinely trained policy bound to their admitted runtime.
    """
    if not isinstance(recipe, SuccessorRecipe):
        raise GameSuccessorError("typed successor recipe required")
    _integer(candidates, "optimization candidates", 1, 16)
    _integer(episodes, "optimization episodes", 1, 8)
    _integer(max_steps, "optimization steps", 1, 4096)
    _integer(seed, "optimization seed", 0, 2**32 - 1)
    planned_steps = (candidates + 2) * episodes * max_steps
    if planned_steps > 131072:
        raise GameSuccessorError("optimization cumulative simulation step budget exceeds131072")
    if type(emit_project) is not bool:
        raise GameSuccessorError("emit_project must be boolean")
    targets = dict(target_metrics)
    if not targets or set(targets) - set(OPTIMIZATION_METRICS):
        raise GameSuccessorError("optimization targets must name declared measured dimensions")
    for key, value in targets.items():
        bounds = OPTIMIZATION_METRICS[key]
        if (
            type(value) not in (int, float)
            or not bounds["minimum"] <= value <= bounds["maximum"]
            or not math.isfinite(value)
        ):
            raise GameSuccessorError(f"optimization target {key} exceeds its declared units/range")
    sources = tuple(SourceGameProfile.from_dict(p) for p in recipe.as_dict()["profiles"])

    def guard() -> None:
        if authorize_source is not None:
            _authorize(sources, authorize_source)

    _authorize(sources, authorize_source)
    guard()
    runtime_identity = _runtime_identity()

    def phase_guard() -> None:
        guard()
        if _runtime_identity() != runtime_identity:
            raise GameSuccessorError("successor measurement implementation changed during optimization")

    if environment_factory is None:
        from .game_successor_runtime import SuccessorEnvironment

        environment_factory = lambda spec, limit: SuccessorEnvironment(spec, max_steps=limit)
    selection_seeds = tuple((seed + i * 104729) % (2**32) for i in range(episodes))
    heldout_seeds = tuple((seed ^ 0x9E3779B9 ^ (i + 1) * 65537) % (2**32) for i in range(episodes))
    if set(selection_seeds) & set(heldout_seeds):
        raise GameSuccessorError("selection and held-out seed ledgers collide")
    original = recipe.spec
    trials = []
    rng = random.Random(seed)
    best_spec, best_score = original, math.inf
    actual_steps = 0
    preservation = recipe.as_dict()["style_priorities"]
    for index in range(candidates):
        phase_guard()
        spec = json.loads(canonical(original))
        if index:
            for group, field in (
                ("movement", "max_speed"),
                ("movement", "acceleration"),
                ("combat", "cooldown"),
                ("fishing", "reel_speed"),
                ("fishing", "tension_gain"),
                ("farming", "day_seconds"),
            ):
                low, high, _, _, _ = MECHANIC_CATALOG[f"{group}.{field}"]
                spec["mechanics"][group][field] = min(
                    high, max(low, original["mechanics"][group][field] * rng.uniform(0.8, 1.2))
                )
        result = _rollout(
            spec,
            seeds=selection_seeds,
            steps=max_steps,
            policy=policy,
            environment_factory=environment_factory,
            cancel=cancel,
            authorize=guard,
            on_trace=on_trace,
        )
        measured = result["analysis"]["metrics"]
        missing = [key for key in targets if measured[key] is None]
        score = _metric_score(measured, targets, preservation)
        actual_steps += result["analysis"]["transitions"]
        row = {
            "candidate": index,
            "spec_digest": digest(spec),
            "score": None if math.isinf(score) else score,
            "missing_dimensions": missing,
            "analysis": result["analysis"],
        }
        trials.append(row)
        if score < best_score:
            best_spec, best_score = spec, score
        if on_progress is not None:
            on_progress(row)
    if math.isinf(best_score):
        raise GameSuccessorError("requested feel targets lack measurable exposure in these actual rollouts")
    before = _rollout(
        original,
        seeds=heldout_seeds,
        steps=max_steps,
        policy=policy,
        environment_factory=environment_factory,
        cancel=cancel,
        authorize=guard,
        on_trace=on_trace,
    )
    after = _rollout(
        best_spec,
        seeds=heldout_seeds,
        steps=max_steps,
        policy=policy,
        environment_factory=environment_factory,
        cancel=cancel,
        authorize=guard,
        on_trace=on_trace,
    )
    actual_steps += before["analysis"]["transitions"] + after["analysis"]["transitions"]
    phase_guard()
    before_score = _metric_score(before["analysis"]["metrics"], targets, preservation)
    after_score = _metric_score(after["analysis"]["metrics"], targets, preservation)
    candidate_digest = digest(best_spec)
    accepted = math.isfinite(after_score) and after_score <= before_score
    parameter_changes = [
        {"mechanic": f"{group}.{field}", "before": value, "after": best_spec["mechanics"][group][field]}
        for group, fields in original["mechanics"].items()
        for field, value in fields.items()
        if best_spec["mechanics"][group][field] != value
    ]
    if not accepted:
        best_spec = original
    raw = recipe.as_dict()
    raw["spec"] = best_spec
    raw["files"] = {}
    if emit_project:
        from .game_successor_runtime import emit_successor_project

        raw["files"] = emit_successor_project(best_spec)
    raw["decisions"].append(
        {
            "policy": "actual_bounded_parameter_search",
            "parent_recipe_digest": recipe.digest,
            "selected_spec_digest": digest(best_spec),
            "selection_score": best_score,
            "heldout_accepted": accepted,
            "parameter_changes": parameter_changes if accepted else [],
        }
    )
    raw.pop("recipe_digest")
    raw["recipe_digest"] = digest(raw)
    optimized = SuccessorRecipe.from_dict(raw)
    phase_guard()
    report = {
        "schema_version": OPTIMIZATION_SCHEMA,
        "algorithm": "bounded-seeded-coordinate-search-v1",
        "parent_recipe_digest": recipe.digest,
        "optimized_recipe": optimized.as_dict(),
        "target_metrics": targets,
        "selection_seeds": list(selection_seeds),
        "heldout_seeds": list(heldout_seeds),
        "trials": trials,
        "before": before["analysis"],
        "after": after["analysis"],
        "runtime_identity": runtime_identity,
        "candidate_spec_digest": candidate_digest,
        "heldout_accepted": accepted,
        "heldout_before_score": None if math.isinf(before_score) else before_score,
        "heldout_after_score": None if math.isinf(after_score) else after_score,
        "parameter_changes": parameter_changes,
        "published_spec_digest": digest(best_spec),
        "selected_score": best_score,
        "planned_steps": planned_steps,
        "actual_steps": actual_steps,
        "controller": "caller_policy" if policy is not None else "deterministic_input_probe",
        "claim": "Actual rollout statistics; no commercial-original equivalence or player-satisfaction claim.",
    }
    report["optimization_digest"] = digest(report)
    return report
