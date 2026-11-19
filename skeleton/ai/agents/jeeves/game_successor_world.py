"""Actual original topdown adventure, fishing and farming world simulation."""

from __future__ import annotations

import base64
import copy
import hashlib
import json
import math
import struct
import zlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .game_learning_runtime import EpisodeStep, GameEnvironmentSpec
from .game_successor_runtime import (
    SPEC_SCHEMA,
    SuccessorRuntimeError,
    _canonical,
    _clamp,
    _digest,
    _integer,
    _number,
    _overlap,
    resolved_fidelity,
)

DT = 1 / 60
VIEW_W, VIEW_H = 640, 360
BODY_W, BODY_H = 18, 20
SCHEMA = "skeleton.game.successor_world_save.v1"
ACTIONS = (
    "noop",
    "up",
    "down",
    "left",
    "right",
    "up_left",
    "up_right",
    "down_left",
    "down_right",
    "attack",
    "fire",
    "interact",
    "fish",
    "hoe",
    "water",
    "plant",
    "harvest",
    "tool_next",
    "rest",
)
REWARDS = ("exploration", "fish", "harvest", "combat", "quest", "goal", "death", "time")
SEASONS = ("spring", "summer", "autumn", "winter")
_MASKS = {
    "noop": 0,
    "left": 1,
    "right": 2,
    "up": 4,
    "down": 8,
    "up_left": 5,
    "up_right": 6,
    "down_left": 9,
    "down_right": 10,
    "attack": 16,
    "fire": 32,
    "interact": 64,
    "fish": 128,
    "hoe": 256,
    "water": 512,
    "plant": 1024,
    "harvest": 2048,
    "tool_next": 4096,
    "rest": 8192,
}


def validate_world_spec(spec: Mapping[str, Any]) -> dict[str, Any]:
    clean = json.loads(_canonical(spec))
    resolved_fidelity(clean)
    if clean.get("schema_version") != SPEC_SCHEMA or clean.get("gameplay_mode") != "top_down":
        raise SuccessorRuntimeError("an exact topdown successor spec is required")
    for field in ("project_id", "title"):
        value = clean.get(field)
        if not isinstance(value, str) or not 1 <= len(value) <= 120 or any(ord(char) < 32 for char in value):
            raise SuccessorRuntimeError("invalid original world " + field)
    _integer(clean.get("seed"), 0, 2**63 - 1, "world seed")
    if not isinstance(clean.get("origins"), list) or len(clean["origins"]) not in (1, 3):
        raise SuccessorRuntimeError("world requires exactly one or three original origin descriptors")
    palette = clean.get("palette")
    if not isinstance(palette, dict) or set(palette) != {
        "background",
        "terrain",
        "player",
        "enemy",
        "accent",
        "collectible",
    }:
        raise SuccessorRuntimeError("six original palette colours are required")
    for value in palette.values():
        if (
            not isinstance(value, str)
            or len(value) != 7
            or value[0] != "#"
            or any(char not in "0123456789abcdefABCDEF" for char in value[1:])
        ):
            raise SuccessorRuntimeError("invalid original palette colour")
    world = clean.get("world", {})
    width = _number(world.get("width"), VIEW_W, 8192, "world width")
    height = _number(world.get("height"), VIEW_H, 8192, "world height")
    tile = _integer(world.get("tile_size"), 16, 64, "world tile size")
    if math.ceil(width / tile) * math.ceil(height / tile) > 32768:
        raise SuccessorRuntimeError("large world tile capacity is exhausted")
    for name in ("spawn", "goal"):
        point = world.get(name)
        if not isinstance(point, list) or len(point) != 2:
            raise SuccessorRuntimeError("world " + name + " coordinate pair is required")
        _number(point[0], 0, width - BODY_W, name + " x")
        _number(point[1], 0, height - BODY_H, name + " y")
    terrain = world.get("terrain")
    if terrain is not None and (
        not isinstance(terrain, list)
        or len(terrain) != math.ceil(height / tile)
        or any(
            not isinstance(row, str)
            or len(row) != math.ceil(width / tile)
            or any(char not in "01234567" for char in row)
            for row in terrain
        )
    ):
        raise SuccessorRuntimeError("world terrain must be exact bounded tile rows")
    identities = set()
    capacities = {
        "obstacles_rects": 128,
        "platforms": 128,
        "ponds": 32,
        "farm_plots": 64,
        "villagers": 32,
        "dungeons": 8,
        "shops": 16,
        "collectibles": 64,
        "enemies": 32,
        "doors": 16,
        "checkpoints": 16,
        "landmarks": 64,
    }
    for section, maximum in capacities.items():
        rows = world.get(section, [])
        if not isinstance(rows, list) or len(rows) > maximum:
            raise SuccessorRuntimeError(section + " exceeds world entity capacity")
        for row in rows:
            if (
                not isinstance(row, dict)
                or not isinstance(row.get("id"), str)
                or not 1 <= len(row["id"]) <= 128
                or row["id"] in identities
            ):
                raise SuccessorRuntimeError("world entity requires a distinct bounded identity")
            identities.add(row["id"])
            _number(row.get("x"), 0, width - 1, section + " x")
            _number(row.get("y"), 0, height - 1, section + " y")
            if section in (
                "obstacles_rects",
                "platforms",
                "ponds",
                "farm_plots",
                "dungeons",
                "doors",
                "landmarks",
            ):
                _number(row.get("w"), 4, width, section + " width")
                _number(row.get("h"), 4, height, section + " height")
                if row["x"] + row["w"] > width or row["y"] + row["h"] > height:
                    raise SuccessorRuntimeError("world entity extends outside authored bounds")
            if section == "landmarks":
                if (
                    row.get("kind") not in ("house", "stall", "pier", "tree", "well", "sign", "camp")
                    or not isinstance(row.get("name", ""), str)
                    or len(row.get("name", "")) > 64
                ):
                    raise SuccessorRuntimeError("original landmark description is invalid")
                _integer(row.get("sprite_index"), 0, 63, "landmark sprite")
            if section == "villagers" and (
                row.get("role", "quest") not in ("shop", "quest", "crafter")
                or not isinstance(row.get("dialogue", ""), str)
                or len(row.get("dialogue", "")) > 256
            ):
                raise SuccessorRuntimeError("original villager dialogue or role is invalid")
            if section == "enemies":
                _integer(row.get("hp", 3), 1, 64, "enemy health")
                _number(row.get("speed", 40), 0, 200, "enemy speed")
                _number(row.get("attack_interval", 1.5), 0.25, 10, "enemy attack interval")
            if section == "doors":
                _number(row.get("target_x"), 0, width - BODY_W, "door target x")
                _number(row.get("target_y"), 0, height - BODY_H, "door target y")
    boss = world.get("boss")
    if boss is not None:
        if not isinstance(boss, dict) or boss.get("id") in identities or not isinstance(boss.get("id"), str):
            raise SuccessorRuntimeError("boss must have a distinct original identity")
        _number(boss.get("x"), 0, width - 36, "boss x")
        _number(boss.get("y"), 0, height - 36, "boss y")
        _integer(boss.get("hp", 16), 1, 64, "boss health")
        _number(boss.get("speed", 32), 0, 160, "boss speed")
        _number(boss.get("attack_interval", 1.2), 0.25, 10, "boss attack interval")
    mechanics = clean.get("mechanics", {})
    bounds = {
        "movement": {"acceleration": (60, 5000), "max_speed": (30, 600), "friction": (60, 5000)},
        "combat": {
            "projectile_speed": (100, 1000),
            "cooldown": (0.08, 3),
            "invulnerability_seconds": (0.1, 3),
        },
        "adventure": {"interact_radius": (24, 160), "melee_damage": (1, 16), "melee_cooldown": (0.08, 3)},
        "fishing": {
            "cast_range": (24, 320),
            "bite_min_seconds": (0.2, 30),
            "bite_max_seconds": (0.2, 60),
            "reel_speed": (0.05, 2),
            "tension_gain": (0.05, 2),
            "tension_release": (0.05, 2),
            "catch_window_seconds": (2, 30),
            "rod_strength": (0.1, 5),
        },
        "farming": {
            "growth_days": (0.1, 30),
            "water_decay": (0, 2),
            "soil_quality": (0.1, 2),
            "season_days": (1, 64),
            "day_seconds": (10, 600),
            "harvest_value": (1, 100),
            "seed_cost": (1, 100),
            "weather_wet_probability": (0, 1),
        },
    }
    for section, fields in bounds.items():
        if not isinstance(mechanics.get(section), dict):
            raise SuccessorRuntimeError("missing actual " + section + " mechanics")
        for key, (low, high) in fields.items():
            _number(mechanics[section].get(key), low, high, section + "." + key)
    if mechanics["fishing"]["bite_max_seconds"] < mechanics["fishing"]["bite_min_seconds"]:
        raise SuccessorRuntimeError("fish bite interval is reversed")
    _integer(mechanics.get("resources", {}).get("max_health"), 1, 32, "maximum health")
    _integer(mechanics.get("resources", {}).get("max_energy"), 1, 100, "maximum energy")
    for name in ("damage", "enemy_damage"):
        _integer(mechanics["combat"].get(name), 1, 16, name)
    for section, name in (("fishing", "fish_variants"), ("farming", "crop_variants")):
        variants = world.get(name, mechanics[section].get(name))
        if not isinstance(variants, list) or not 1 <= len(variants) <= 8:
            raise SuccessorRuntimeError("actual original " + name + " are required")
        seen = set()
        for variant in variants:
            if (
                not isinstance(variant, dict)
                or not isinstance(variant.get("id"), str)
                or variant["id"] in seen
                or not isinstance(variant.get("name"), str)
                or not 1 <= len(variant["name"]) <= 64
            ):
                raise SuccessorRuntimeError("species/crop identity is invalid")
            seen.add(variant["id"])
            _integer(variant.get("value"), 1, 100, "species/crop value")
            if section == "fishing":
                _number(variant.get("difficulty"), 0.1, 2, "fish difficulty")
            else:
                _number(variant.get("growth_days"), 0.1, 30, "crop growth days")
                _integer(variant.get("seed_cost"), 1, 100, "crop seed cost")
                if variant.get("season") not in (*SEASONS, "any"):
                    raise SuccessorRuntimeError("crop season is invalid")
    progression = mechanics.get("progression", {})
    rules = progression.get("unlock_rules", {})
    if not isinstance(rules, dict) or set(rules) - {
        "tackle_requires_sold_harvest",
        "key_requires_rod_level",
        "key_requires_rare_fish",
        "rare_fish_difficulty",
    }:
        raise SuccessorRuntimeError("original progression unlock rules are invalid")
    for name, maximum in (
        ("tackle_requires_sold_harvest", 64),
        ("key_requires_rod_level", 3),
        ("key_requires_rare_fish", 64),
    ):
        if name in rules:
            _integer(rules[name], 0, maximum, "unlock " + name)
    if "rare_fish_difficulty" in rules:
        _number(rules["rare_fish_difficulty"], 0.1, 2, "rare fish threshold")
    if not isinstance(progression.get("quest_text"), str) or not 1 <= len(progression["quest_text"]) <= 256:
        raise SuccessorRuntimeError("an original quest description is required")
    quests = progression.get("quests", [])
    if not isinstance(quests, list) or len(quests) > 16:
        raise SuccessorRuntimeError("quest capacity is exhausted")
    for quest in quests:
        if (
            not isinstance(quest, dict)
            or quest.get("kind") not in ("fish", "harvest", "defeat", "relic")
            or not isinstance(quest.get("id"), str)
            or not isinstance(quest.get("text"), str)
            or len(quest["text"]) > 256
        ):
            raise SuccessorRuntimeError("quest must declare an actual measured objective")
        _integer(quest.get("count"), 1, 64, "quest count")
        _integer(quest.get("reward"), 1, 100, "quest reward")
    if len({quest["id"] for quest in quests}) != len(quests):
        raise SuccessorRuntimeError("quest identifiers must be distinct")
    camera = clean.get("camera", {})
    if camera.get("mode", "top_down") != "top_down":
        raise SuccessorRuntimeError("topdown world camera mode differs")
    _number(camera.get("smoothing", 0.15), 0.01, 1, "camera smoothing")
    _number(camera.get("lookahead", 40), 0, 400, "camera lookahead")
    return clean


def _noise(seed: int, number: int) -> float:
    return ((seed % 2147483647 + number * 48271 + 12345) * 16807 % 2147483647) / 2147483647


class WorldSuccessorEnvironment:
    def __init__(self, spec: Mapping[str, Any], *, max_steps=4096):
        self.authored = validate_world_spec(spec)
        self.spec_digest = _digest(self.authored)
        self.max_steps = _integer(max_steps, 1, 4096, "episode steps")
        self.world, self.mechanics = self.authored["world"], copy.deepcopy(self.authored["mechanics"])
        self.fidelity = resolved_fidelity(self.authored)
        self.mechanics["fishing"]["fish_variants"] = self.world.get(
            "fish_variants", self.mechanics["fishing"].get("fish_variants")
        )
        self.mechanics["farming"]["crop_variants"] = self.world.get(
            "crop_variants", self.mechanics["farming"].get("crop_variants")
        )
        self._closed, self._seed, self._history = False, None, []
        identity = _digest(
            {
                "spec": self.spec_digest,
                "runtime": {
                    name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                    for name in (
                        "game_successor_world.py",
                        "game_successor_runtime.py",
                        "game_successor_assets.py",
                    )
                },
                "max_steps": max_steps,
                "step_hz": 60,
            }
        )
        bins = {
            "x": (0.1, 0.25, 0.5, 0.75, 0.9),
            "y": (0.1, 0.25, 0.5, 0.75, 0.9),
            "vx": (-0.7, -0.2, 0.2, 0.7),
            "vy": (-0.7, -0.2, 0.2, 0.7),
            "health": (0.25, 0.5, 0.75),
            "energy": (0.25, 0.5, 0.75),
            "goal_dx": (-0.5, -0.1, 0.1, 0.5),
            "goal_dy": (-0.5, -0.1, 0.1, 0.5),
            "pond_distance": (0.1, 0.3, 0.6),
            "fish_phase": (0.2, 0.6),
            "fish_progress": (0.25, 0.5, 0.75),
            "fish_tension": (0.25, 0.5, 0.75),
            "farm_distance": (0.1, 0.3, 0.6),
            "crop_ready": (0.5,),
            "time_fraction": (0.25, 0.5, 0.75),
            "enemy_distance": (0.1, 0.3, 0.6),
        }
        self.spec = GameEnvironmentSpec(
            "successor_world:" + self.authored["project_id"], identity, ACTIONS, bins, REWARDS, max_steps
        )

    @property
    def descriptor(self):
        return {
            "runtime_kind": "original_successor_game",
            "gameplay_mode": "top_down",
            "environment_digest": self.spec.environment_digest,
            "spec_digest": self.spec_digest,
            "spec": self.spec.as_dict(),
            "step_hz": 60,
            "fidelity": dict(self.fidelity),
            "hardware_compatibility_verified": False,
        }

    @property
    def done(self):
        return (
            self._closed
            or self._seed is not None
            and (self.state["mode"] != "playing" or self.state["steps"] >= self.max_steps)
        )

    def reset(self, seed=0):
        if self._closed:
            raise SuccessorRuntimeError("original world environment is closed")
        self._seed = _integer(seed, 0, 2**63 - 1, "episode seed")
        self._history = []
        crops = self.mechanics["farming"]["crop_variants"]
        enemies = []
        for row in [
            *self.world.get("enemies", []),
            *([self.world["boss"]] if self.world.get("boss") else []),
        ]:
            enemy = copy.deepcopy(row)
            boss = row is self.world.get("boss")
            enemy.update(
                {
                    "hp": row.get("hp", 16 if boss else 3),
                    "max_hp": row.get("hp", 16 if boss else 3),
                    "w": 36 if boss else 22,
                    "h": 36 if boss else 22,
                    "boss": boss,
                    "home_x": row["x"],
                    "home_y": row["y"],
                    "cooldown": row.get("attack_interval", 1.5),
                    "speed": row.get("speed", 32 if boss else 40),
                    "attack_interval": row.get("attack_interval", 1.5),
                }
            )
            enemies.append(enemy)
        self.state = {
            "x": float(self.world["spawn"][0]),
            "y": float(self.world["spawn"][1]),
            "vx": 0.0,
            "vy": 0.0,
            "facing_x": 0,
            "facing_y": 1,
            "steps": 0,
            "mode": "playing",
            "health": self.mechanics["resources"]["max_health"],
            "energy": float(self.mechanics["resources"]["max_energy"]),
            "coins": 20,
            "xp": 0,
            "kills": 0,
            "fish_caught": 0,
            "harvested": 0,
            "sold_harvest": 0,
            "rare_fish": 0,
            "granted_key": False,
            "relics": 0,
            "keys": 0,
            "day": 1,
            "season": "spring",
            "weather": "clear",
            "clock": 0.0,
            "attack_cooldown": 0.0,
            "shot_cooldown": 0.0,
            "invulnerable": 0.0,
            "action_cooldown": 0.0,
            "previous_input": 0,
            "tool": 0,
            "crop": 0,
            "seeds": [5 for _ in crops],
            "fish_inventory": [0 for _ in self.mechanics["fishing"]["fish_variants"]],
            "crop_inventory": [0 for _ in crops],
            "rod_level": 1,
            "watering_level": 1,
            "fish": {
                "phase": "idle",
                "timer": 0.0,
                "bite_at": 0.0,
                "progress": 0.0,
                "tension": 0.0,
                "species": 0,
                "casts": 0,
                "pond": None,
            },
            "plots": [],
            "enemies": enemies,
            "projectiles": [],
            "collected": [],
            "completed_quests": [],
            "visited": [],
            "checkpoint": list(self.world["spawn"]),
            "checkpoint_id": None,
            "camera_x": _clamp(self.world["spawn"][0] - VIEW_W / 2, 0, self.world["width"] - VIEW_W),
            "camera_y": _clamp(self.world["spawn"][1] - VIEW_H / 2, 0, self.world["height"] - VIEW_H),
            "events": [],
            "dialogue": "Welcome. Fish the ponds, grow your garden, and find the lost beacons.",
            "dialogue_time": 5.0,
            "scene": "overworld",
        }
        self._chain = _digest(
            {"environment": self.spec.environment_digest, "seed": seed, "initial": self.state}
        )
        self._last_camera = [self.state["camera_x"], self.state["camera_y"]]
        return self._observe()

    def _near(self, rows):
        x, y = self.state["x"] + BODY_W / 2, self.state["y"] + BODY_H / 2
        nearest, distance = None, float("inf")
        for row in rows:
            px = _clamp(x, row["x"], row["x"] + row.get("w", 0))
            py = _clamp(y, row["y"], row["y"] + row.get("h", 0))
            current = math.hypot(x - px, y - py)
            if current < distance:
                nearest, distance = row, current
        return nearest, distance

    def _observe(self):
        s, world, m = self.state, self.world, self.mechanics
        _, pond = self._near(world.get("ponds", []))
        _, farm = self._near(world.get("farm_plots", []))
        _, enemy = self._near([row for row in s["enemies"] if row["hp"] > 0])
        return {
            "x": s["x"] / world["width"],
            "y": s["y"] / world["height"],
            "vx": s["vx"] / m["movement"]["max_speed"],
            "vy": s["vy"] / m["movement"]["max_speed"],
            "health": s["health"] / m["resources"]["max_health"],
            "energy": s["energy"] / m["resources"]["max_energy"],
            "goal_dx": _clamp((world["goal"][0] - s["x"]) / VIEW_W, -1, 1),
            "goal_dy": _clamp((world["goal"][1] - s["y"]) / VIEW_H, -1, 1),
            "pond_distance": min(1, pond / VIEW_W),
            "farm_distance": min(1, farm / VIEW_W),
            "enemy_distance": min(1, enemy / VIEW_W),
            "fish_phase": {"idle": 0.0, "waiting": 0.4, "bite": 1.0}[s["fish"]["phase"]],
            "fish_progress": s["fish"]["progress"],
            "fish_tension": s["fish"]["tension"],
            "crop_ready": float(any(p["crop"] >= 0 and p["growth"] >= 1 for p in s["plots"])),
            "time_fraction": s["clock"] / m["farming"]["day_seconds"],
        }

    def current_observation(self):
        if self._seed is None:
            raise SuccessorRuntimeError("reset original world before observing")
        return self._observe()

    def _blocked(self, x, y):
        if x < 0 or y < 0 or x + BODY_W > self.world["width"] or y + BODY_H > self.world["height"]:
            return True
        if any(
            _overlap(x, y, BODY_W, BODY_H, row)
            for row in [
                *self.world.get("obstacles_rects", []),
                *self.world.get("platforms", []),
                *self.world.get("ponds", []),
            ]
        ):
            return True
        if self.state["keys"] == 0 and any(
            row.get("requires") == "key" and _overlap(x, y, BODY_W, BODY_H, row)
            for row in self.world.get("dungeons", [])
        ):
            return True
        terrain = self.world.get("terrain")
        if terrain:
            tile = self.world["tile_size"]
            for px, py in (
                (x, y),
                (x + BODY_W - 0.01, y),
                (x, y + BODY_H - 0.01),
                (x + BODY_W - 0.01, y + BODY_H - 0.01),
            ):
                if terrain[int(py // tile)][int(px // tile)] in "12":
                    return True
        return False

    def step(self, action):
        if action not in _MASKS:
            raise SuccessorRuntimeError("original world action is unavailable")
        return self._advance(_MASKS[action], action)

    def input_step(self, controls):
        if (
            not isinstance(controls, (list, tuple))
            or len(controls) != 1
            or not isinstance(controls[0], Mapping)
        ):
            raise SuccessorRuntimeError("original world requires one controller port")
        buttons = _integer(controls[0].get("buttons", 0), 0, 65535, "controller buttons")
        mask = (
            (1 if buttons & 64 else 0)
            | (2 if buttons & 128 else 0)
            | (4 if buttons & 16 else 0)
            | (8 if buttons & 32 else 0)
            | (16 if buttons & 1 else 0)
            | (64 if buttons & 256 else 0)
            | (4096 if buttons & 512 else 0)
        )
        if buttons & 1024:
            mask |= (128, 256, 512, 1024, 2048)[self.state["tool"]]
        return self._advance(mask, None)

    def _advance(self, mask, action):
        if self._seed is None or self.done:
            raise SuccessorRuntimeError("reset an active original world before stepping")
        s, m = self.state, self.mechanics
        rewards = {key: 0.0 for key in REWARDS}
        rewards["time"] = -0.001
        s["steps"] += 1
        s["events"] = []
        for key in ("attack_cooldown", "shot_cooldown", "invulnerable", "action_cooldown", "dialogue_time"):
            s[key] = max(0.0, s[key] - DT)
        s["energy"] = min(m["resources"]["max_energy"], s["energy"] + DT * 2)
        dx, dy = int(bool(mask & 2)) - int(bool(mask & 1)), int(bool(mask & 8)) - int(bool(mask & 4))
        if dx or dy:
            length = math.hypot(dx, dy)
            dx, dy = dx / length, dy / length
            s["facing_x"], s["facing_y"] = dx, dy
        for key, direction in (("vx", dx), ("vy", dy)):
            if direction:
                s[key] = _clamp(
                    s[key] + direction * m["movement"]["acceleration"] * DT,
                    -m["movement"]["max_speed"],
                    m["movement"]["max_speed"],
                )
            else:
                s[key] = math.copysign(max(0.0, abs(s[key]) - m["movement"]["friction"] * DT), s[key])
        speed = math.hypot(s["vx"], s["vy"])
        if speed > m["movement"]["max_speed"]:
            s["vx"], s["vy"] = (
                s["vx"] / speed * m["movement"]["max_speed"],
                s["vy"] / speed * m["movement"]["max_speed"],
            )
        if s["fish"]["phase"] == "idle":
            if not self._blocked(s["x"] + s["vx"] * DT, s["y"]):
                s["x"] += s["vx"] * DT
            else:
                s["vx"] = 0.0
            if not self._blocked(s["x"], s["y"] + s["vy"] * DT):
                s["y"] += s["vy"] * DT
            else:
                s["vy"] = 0.0
        pressed = mask & ~s["previous_input"]
        if pressed & 4096:
            s["tool"] = (s["tool"] + 1) % 5
            s["events"].append("tool")
        if mask & 16 and s["attack_cooldown"] <= 0:
            self._attack(rewards)
        if mask & 32 and s["shot_cooldown"] <= 0 and s["energy"] >= 1:
            self._shot(
                s["x"] + 9,
                s["y"] + 10,
                s["facing_x"] * m["combat"]["projectile_speed"],
                s["facing_y"] * m["combat"]["projectile_speed"],
                True,
            )
            s["energy"] -= 1
            s["shot_cooldown"] = m["combat"]["cooldown"]
            s["events"].append("fire")
        self._fish(mask, pressed, rewards)
        if pressed & 256:
            self._farm("hoe", rewards)
        if pressed & 512:
            self._farm("water", rewards)
        if pressed & 1024:
            self._farm("plant", rewards)
        if pressed & 2048:
            self._farm("harvest", rewards)
        if pressed & 64:
            self._interact(rewards)
        if pressed & 8192:
            _, distance = self._near(self.world.get("checkpoints", []))
            if distance <= 96:
                self._time(self.mechanics["farming"]["day_seconds"] - s["clock"] + 1e-8)
                s["energy"] = self.mechanics["resources"]["max_energy"]
                s["health"] = self.mechanics["resources"]["max_health"]
                self._say("Rested at a waystone. A new day begins in the valley.")
                s["events"].append("rest")
            else:
                self._say("Rest beside a village or a discovered waystone.")
        self._time()
        self._enemy_step(rewards)
        self._bullets(rewards)
        self._collect(rewards)
        for checkpoint in self.world.get("checkpoints", []):
            if (
                math.hypot(s["x"] - checkpoint["x"], s["y"] - checkpoint["y"]) < 40
                and s["checkpoint_id"] != checkpoint["id"]
            ):
                s["checkpoint"], s["checkpoint_id"] = [checkpoint["x"], checkpoint["y"]], checkpoint["id"]
                s["health"] = m["resources"]["max_health"]
                s["events"].append("checkpoint")
        for quest in m["progression"].get("quests", []):
            field = {"fish": "fish_caught", "harvest": "harvested", "defeat": "kills", "relic": "relics"}[
                quest["kind"]
            ]
            if quest["id"] not in s["completed_quests"] and s[field] >= quest["count"]:
                s["completed_quests"].append(quest["id"])
                s["coins"] += quest["reward"]
                s["xp"] += quest["reward"]
                rewards["quest"] += 2
                s["events"].append("quest")
                self._say("Quest complete: " + quest["text"])
        zone = (int(s["x"] // 128), int(s["y"] // 128))
        zone_id = str(zone[0]) + ":" + str(zone[1])
        if zone_id not in s["visited"] and len(s["visited"]) < 4096:
            s["visited"].append(zone_id)
            rewards["exploration"] = 0.05
        scene, _ = self._near(self.world.get("dungeons", []))
        s["scene"] = scene["id"] if scene and _overlap(s["x"], s["y"], BODY_W, BODY_H, scene) else "overworld"
        if s["health"] <= 0:
            s["mode"] = "dead"
            rewards["death"] = -5.0
            s["events"].append("death")
        goal = self.world["goal"]
        all_quests = len(s["completed_quests"]) == len(m["progression"].get("quests", []))
        boss_dead = all(e["hp"] <= 0 for e in s["enemies"] if e["boss"])
        if (
            s["mode"] == "playing"
            and math.hypot(s["x"] - goal[0], s["y"] - goal[1]) < 48
            and all_quests
            and boss_dead
            and (not m["progression"].get("unlock_rules") or s["keys"] > 0)
        ):
            s["mode"] = "won"
            rewards["goal"] = 10.0
            s["events"].append("victory")
        smoothing = self.authored.get("camera", {}).get("smoothing", 0.15)
        self._last_camera = [s["camera_x"], s["camera_y"]]
        lookahead = self.authored.get("camera", {}).get("lookahead", 40)
        s["camera_x"] += (
            _clamp(s["x"] + 9 - VIEW_W / 2 + s["facing_x"] * lookahead, 0, self.world["width"] - VIEW_W)
            - s["camera_x"]
        ) * smoothing
        s["camera_y"] += (
            _clamp(s["y"] + 10 - VIEW_H / 2 + s["facing_y"] * lookahead, 0, self.world["height"] - VIEW_H)
            - s["camera_y"]
        ) * smoothing
        s["previous_input"] = mask
        self._history.append(mask)
        self._chain = _digest(
            {
                "previous": self._chain,
                "input": mask,
                "steps": s["steps"],
                "state": self.state_digest,
                "reward": rewards,
            }
        )
        return EpisodeStep(
            self._observe(),
            rewards,
            s["mode"] != "playing",
            s["mode"] == "playing" and s["steps"] >= self.max_steps,
            {
                "runtime_kind": "original_successor_game",
                "gameplay_mode": "top_down",
                "events": s["events"],
                "state_digest": self.state_digest,
                "goal_reached": s["mode"] == "won",
                "fish_caught": s["fish_caught"],
                "harvested": s["harvested"],
                "completed_quests": list(s["completed_quests"]),
                "controller_only": action is None,
                "player_x": s["x"],
                "player_y": s["y"],
                "vx": s["vx"],
                "vy": s["vy"],
                "won": s["mode"] == "won",
                "dead": s["mode"] == "dead",
            },
            self._chain,
        )

    def _say(self, text):
        self.state["dialogue"], self.state["dialogue_time"] = text[:256], 5.0

    def _attack(self, rewards):
        s, m = self.state, self.mechanics
        s["attack_cooldown"] = m["adventure"]["melee_cooldown"]
        target_x, target_y = s["x"] + 9 + s["facing_x"] * 28, s["y"] + 10 + s["facing_y"] * 28
        for enemy in s["enemies"]:
            if (
                enemy["hp"] > 0
                and math.hypot(enemy["x"] + enemy["w"] / 2 - target_x, enemy["y"] + enemy["h"] / 2 - target_y)
                < 36
            ):
                self._hit_enemy(enemy, m["adventure"]["melee_damage"], rewards)
        s["events"].append("attack")

    def _hit_enemy(self, enemy, damage, rewards):
        enemy["hp"] = max(0, enemy["hp"] - damage)
        rewards["combat"] += 0.1
        self.state["events"].append("hit")
        if enemy["hp"] == 0:
            self.state["kills"] += 1
            self.state["xp"] += 3
            self.state["coins"] += 5 if not enemy["boss"] else 25
            rewards["combat"] += 1
            self.state["events"].append("defeat")

    def _fish(self, mask, pressed, rewards):
        s, cfg = self.state, self.mechanics["fishing"]
        fish = s["fish"]
        if fish["phase"] == "idle" and pressed & 128:
            pond, distance = self._near(self.world.get("ponds", []))
            if pond and distance <= cfg["cast_range"]:
                fish.update(
                    phase="waiting",
                    timer=0.0,
                    progress=0.0,
                    tension=0.0,
                    pond=pond["id"],
                    casts=fish["casts"] + 1,
                )
                fish["bite_at"] = cfg["bite_min_seconds"] + _noise(self._seed, fish["casts"]) * (
                    cfg["bite_max_seconds"] - cfg["bite_min_seconds"]
                )
                fish["species"] = min(
                    len(cfg["fish_variants"]) - 1,
                    int(_noise(self._seed, fish["casts"] + 97) * len(cfg["fish_variants"])),
                )
                rules = self.mechanics["progression"].get("unlock_rules", {})
                if s["rod_level"] < rules.get("key_requires_rod_level", 1):
                    available = [
                        index
                        for index, variant in enumerate(cfg["fish_variants"])
                        if variant["difficulty"] < rules.get("rare_fish_difficulty", 2)
                    ]
                    if available:
                        fish["species"] = available[fish["species"] % len(available)]
                self._say("Cast. Wait for a bite, then hold reel while the tension is low.")
                s["events"].append("cast")
            else:
                self._say("Move closer to a pond to cast your line.")
        if fish["phase"] == "idle":
            return
        fish["timer"] += DT
        if fish["phase"] == "waiting" and fish["timer"] >= fish["bite_at"]:
            fish["phase"], fish["timer"] = "bite", 0.0
            self._say("A bite! Hold fish to reel; release when tension rises.")
            s["events"].append("bite")
        if fish["phase"] == "bite":
            difficulty = cfg["fish_variants"][fish["species"]]["difficulty"]
            safe = 0.45 + 0.2 * math.sin(fish["timer"] * 4)
            if mask & 128:
                fish["progress"] = min(
                    1.0, fish["progress"] + cfg["reel_speed"] * DT * cfg["rod_strength"] * s["rod_level"]
                )
                fish["tension"] = _clamp(
                    fish["tension"] + cfg["tension_gain"] * difficulty * DT * (1.4 if safe < 0.4 else 0.65),
                    0,
                    1,
                )
            else:
                fish["tension"] = max(0.0, fish["tension"] - cfg["tension_release"] * DT)
                fish["progress"] = max(0.0, fish["progress"] - DT * 0.03)
            if fish["progress"] >= 1 and fish["tension"] < 1:
                species = cfg["fish_variants"][fish["species"]]
                s["fish_inventory"][fish["species"]] += 1
                s["fish_caught"] += 1
                if species["difficulty"] >= self.mechanics["progression"].get("unlock_rules", {}).get(
                    "rare_fish_difficulty", 2
                ):
                    s["rare_fish"] += 1
                s["xp"] += 2
                rewards["fish"] += 1.0
                fish["phase"] = "idle"
                self._say("Caught " + species["name"] + "! Sell fish in town or keep them.")
                s["events"].append("catch")
            elif fish["tension"] >= 1 or fish["timer"] >= cfg["catch_window_seconds"]:
                fish["phase"] = "idle"
                self._say("The fish escaped. Relax the line and try again.")
                s["events"].append("escape")

    def _farm(self, action, rewards):
        s, cfg, tile = self.state, self.mechanics["farming"], self.world["tile_size"]
        x = math.floor((s["x"] + 9 + s["facing_x"] * 28) / tile) * tile
        y = math.floor((s["y"] + 10 + s["facing_y"] * 28) / tile) * tile
        zone = next(
            (
                row
                for row in self.world.get("farm_plots", [])
                if row["x"] <= x < row["x"] + row["w"] and row["y"] <= y < row["y"] + row["h"]
            ),
            None,
        )
        if not zone:
            self._say("Use farming tools in a marked garden plot.")
            return
        plot = next((row for row in s["plots"] if row["x"] == x and row["y"] == y), None)
        if action == "hoe":
            if plot is None and len(s["plots"]) < 64:
                plot = {"x": x, "y": y, "soil": cfg["soil_quality"], "water": 0.0, "crop": -1, "growth": 0.0}
                s["plots"].append(plot)
                s["events"].append("hoe")
            self._say("Soil prepared. Plant a seed, then water it.")
        elif plot is None:
            self._say("Prepare this soil with the hoe first.")
        elif action == "water":
            plot["water"] = min(1.0, plot["water"] + 0.6 * s["watering_level"])
            s["events"].append("water")
        elif action == "plant" and plot["crop"] < 0:
            if s["seeds"][s["crop"]] > 0:
                s["seeds"][s["crop"]] -= 1
                plot["crop"], plot["growth"] = s["crop"], 0.0
                s["events"].append("plant")
                self._say("Seed planted. Water helps it grow through the seasons.")
            else:
                self._say("You need more seeds. Visit the town shop.")
        elif action == "harvest" and plot["crop"] >= 0:
            if plot["growth"] >= 1:
                crop = plot["crop"]
                s["crop_inventory"][crop] += 1
                s["harvested"] += 1
                s["xp"] += 2
                rewards["harvest"] += 1
                plot["crop"], plot["growth"] = -1, 0.0
                s["events"].append("harvest")
                self._say(
                    "Harvested " + cfg["crop_variants"][crop]["name"] + ". Visit town to sell your crops."
                )
            else:
                self._say("This crop is still growing. Keep the soil watered.")

    def _time(self, delta=DT):
        s, cfg = self.state, self.mechanics["farming"]
        s["clock"] += delta
        if s["clock"] >= cfg["day_seconds"]:
            s["clock"] -= cfg["day_seconds"]
            s["day"] += 1
            s["season"] = SEASONS[int((s["day"] - 1) // cfg["season_days"]) % 4]
            s["weather"] = (
                "rain"
                if _noise(self.authored["seed"], s["day"]) < cfg["weather_wet_probability"]
                else "clear"
            )
            s["events"].append("day")
        for plot in s["plots"]:
            plot["water"] = _clamp(
                plot["water"]
                + (
                    delta * 0.2
                    if s["weather"] == "rain"
                    else -cfg["water_decay"] * delta / cfg["day_seconds"]
                ),
                0,
                1,
            )
            if plot["crop"] >= 0:
                variant = cfg["crop_variants"][plot["crop"]]
                if plot["water"] > 0.1 and variant["season"] in ("any", s["season"]):
                    plot["growth"] = min(
                        1.0,
                        plot["growth"]
                        + delta / (cfg["day_seconds"] * variant["growth_days"]) * (0.5 + plot["soil"] * 0.5),
                    )

    def _interact(self, rewards):
        s = self.state
        npc, distance = self._near(self.world.get("villagers", []))
        if npc and distance <= self.mechanics["adventure"]["interact_radius"]:
            role = npc.get("role", "quest")
            if role == "shop":
                s["sold_harvest"] += sum(s["crop_inventory"])
                proceeds = sum(
                    count * row["value"]
                    for count, row in zip(
                        s["fish_inventory"], self.mechanics["fishing"]["fish_variants"], strict=True
                    )
                ) + sum(
                    count * row["value"]
                    for count, row in zip(
                        s["crop_inventory"], self.mechanics["farming"]["crop_variants"], strict=True
                    )
                )
                s["coins"] += proceeds
                s["fish_inventory"] = [0 for _ in s["fish_inventory"]]
                s["crop_inventory"] = [0 for _ in s["crop_inventory"]]
                crop = self.mechanics["farming"]["crop_variants"][s["crop"]]
                if s["coins"] >= crop["seed_cost"]:
                    s["coins"] -= crop["seed_cost"]
                    s["seeds"][s["crop"]] += 1
                self._say(
                    "Sold goods for " + str(proceeds) + " coins. A fresh seed is ready for your garden."
                )
                s["events"].append("shop")
            elif role == "crafter":
                required = (
                    self.mechanics["progression"]
                    .get("unlock_rules", {})
                    .get("tackle_requires_sold_harvest", 0)
                )
                if s["sold_harvest"] < required:
                    self._say("Trade a homegrown crop in town before crafting improved tackle.")
                elif s["coins"] >= 15 and s["rod_level"] < 3:
                    s["coins"] -= 15
                    s["rod_level"] += 1
                    s["watering_level"] = min(3, s["watering_level"] + 1)
                    self._say("Crafted stronger tackle and an improved watering can.")
                    s["events"].append("craft")
                else:
                    self._say("Bring 15 coins to improve your rod and watering can.")
            else:
                rules = self.mechanics["progression"].get("unlock_rules", {})
                if (
                    rules
                    and not s["granted_key"]
                    and s["rod_level"] >= rules.get("key_requires_rod_level", 1)
                    and s["rare_fish"] >= rules.get("key_requires_rare_fish", 0)
                ):
                    s["keys"] += 1
                    s["granted_key"] = True
                    s["events"].append("key")
                    self._say("Your rare catch earned a shrine key. The adventure trail is open.")
                elif rules and not s["granted_key"]:
                    self._say(
                        "Improve your tackle with crop trade, then land a rare fish to earn a shrine key."
                    )
                else:
                    self._say(npc.get("dialogue", self.mechanics["progression"]["quest_text"]))
            return
        for door in self.world.get("doors", []):
            if _overlap(s["x"], s["y"], BODY_W, BODY_H, door) and (not door.get("requires") or s["keys"] > 0):
                s["x"], s["y"], s["vx"], s["vy"] = door["target_x"], door["target_y"], 0.0, 0.0
                s["events"].append("door")
                return
        self._say(self.mechanics["progression"]["quest_text"])

    def _shot(self, x, y, vx, vy, friendly):
        if len(self.state["projectiles"]) < 128:
            self.state["projectiles"].append(
                {"x": x, "y": y, "vx": vx, "vy": vy, "life": 2.0, "friendly": friendly}
            )

    def _enemy_step(self, rewards):
        s = self.state
        for enemy in s["enemies"]:
            if enemy["hp"] <= 0:
                continue
            dx, dy = s["x"] - enemy["x"], s["y"] - enemy["y"]
            distance = math.hypot(dx, dy)
            phase = 1.5 if enemy["boss"] and enemy["hp"] <= enemy["max_hp"] / 2 else 1.0
            if distance < (380 if enemy["boss"] else 240) and distance > 20:
                mx, my = dx / distance, dy / distance
            else:
                mx, my = math.sin((s["steps"] % 360) / 60), math.cos((s["steps"] % 360) / 60)
                if math.hypot(enemy["x"] - enemy["home_x"], enemy["y"] - enemy["home_y"]) > 80:
                    home = max(1, math.hypot(enemy["home_x"] - enemy["x"], enemy["home_y"] - enemy["y"]))
                    mx, my = (enemy["home_x"] - enemy["x"]) / home, (enemy["home_y"] - enemy["y"]) / home
            x, y = (
                enemy["x"] + mx * enemy["speed"] * phase * DT,
                enemy["y"] + my * enemy["speed"] * phase * DT,
            )
            if not self._blocked(x, enemy["y"]):
                enemy["x"] = x
            if not self._blocked(enemy["x"], y):
                enemy["y"] = y
            enemy["cooldown"] -= DT
            if (
                (enemy.get("kind") in ("shooter", "boss") or enemy["boss"])
                and distance < 420
                and enemy["cooldown"] <= 0
            ):
                speed = self.mechanics["combat"]["projectile_speed"] * 0.6
                self._shot(
                    enemy["x"] + enemy["w"] / 2,
                    enemy["y"] + enemy["h"] / 2,
                    dx / max(1, distance) * speed,
                    dy / max(1, distance) * speed,
                    False,
                )
                enemy["cooldown"] = enemy["attack_interval"] / phase
            if _overlap(s["x"], s["y"], BODY_W, BODY_H, enemy):
                self._damage(rewards)

    def _damage(self, rewards):
        if self.state["invulnerable"] <= 0:
            self.state["health"] = max(0, self.state["health"] - self.mechanics["combat"]["enemy_damage"])
            self.state["invulnerable"] = self.mechanics["combat"]["invulnerability_seconds"]
            self.state["events"].append("hurt")
            rewards["combat"] -= 0.5

    def _bullets(self, rewards):
        retained = []
        for bullet in self.state["projectiles"]:
            bullet["x"] += bullet["vx"] * DT
            bullet["y"] += bullet["vy"] * DT
            bullet["life"] -= DT
            hit = bullet["life"] <= 0 or self._blocked(bullet["x"], bullet["y"])
            if not hit and bullet["friendly"]:
                for enemy in self.state["enemies"]:
                    if enemy["hp"] > 0 and _overlap(bullet["x"] - 3, bullet["y"] - 3, 6, 6, enemy):
                        self._hit_enemy(enemy, self.mechanics["combat"]["damage"], rewards)
                        hit = True
                        break
            elif not hit and _overlap(
                bullet["x"] - 3,
                bullet["y"] - 3,
                6,
                6,
                {"x": self.state["x"], "y": self.state["y"], "w": BODY_W, "h": BODY_H},
            ):
                self._damage(rewards)
                hit = True
            if not hit:
                retained.append(bullet)
        self.state["projectiles"] = retained

    def _collect(self, rewards):
        s = self.state
        for item in self.world.get("collectibles", []):
            if item["id"] not in s["collected"] and math.hypot(s["x"] - item["x"], s["y"] - item["y"]) < 28:
                s["collected"].append(item["id"])
                kind, value = item.get("kind", "relic"), item.get("value", 1)
                if kind in ("key", "relic", "shard"):
                    s["keys"] += int(kind == "key") * value
                    s["relics"] += int(kind in ("relic", "shard")) * value
                    rewards["quest"] += 0.5
                elif kind == "health":
                    s["health"] = min(self.mechanics["resources"]["max_health"], s["health"] + value)
                elif kind == "energy":
                    s["energy"] = min(self.mechanics["resources"]["max_energy"], s["energy"] + value)
                else:
                    s["coins"] += value
                s["events"].append("collect")

    @property
    def state_digest(self):
        return _digest(self.state)

    def snapshot(self):
        if self._seed is None:
            raise SuccessorRuntimeError("reset original world before saving")
        payload = {
            "schema_version": SCHEMA,
            "environment_digest": self.spec.environment_digest,
            "spec_digest": self.spec_digest,
            "seed": self._seed,
            "inputs": list(self._history),
            "state_digest": self.state_digest,
            "transition_digest": self._chain,
        }
        return {**payload, "snapshot_digest": _digest(payload)}

    def restore(self, snapshot):
        clean = json.loads(_canonical(snapshot, 262144))
        fields = {
            "schema_version",
            "environment_digest",
            "spec_digest",
            "seed",
            "inputs",
            "state_digest",
            "transition_digest",
            "snapshot_digest",
        }
        if (
            not isinstance(clean, dict)
            or set(clean) != fields
            or clean["schema_version"] != SCHEMA
            or clean["environment_digest"] != self.spec.environment_digest
            or clean["spec_digest"] != self.spec_digest
        ):
            raise SuccessorRuntimeError("world save belongs to another exact recipe/runtime")
        payload = {key: value for key, value in clean.items() if key != "snapshot_digest"}
        if (
            _digest(payload) != clean["snapshot_digest"]
            or not isinstance(clean["inputs"], list)
            or len(clean["inputs"]) > self.max_steps
        ):
            raise SuccessorRuntimeError("world save identity or cursor differs")
        replacement = WorldSuccessorEnvironment(self.authored, max_steps=self.max_steps)
        replacement.reset(clean["seed"])
        for mask in clean["inputs"]:
            replacement._advance(_integer(mask, 0, 16383, "saved world input"), None)
        if (
            replacement.state_digest != clean["state_digest"]
            or replacement._chain != clean["transition_digest"]
        ):
            raise SuccessorRuntimeError("world save does not reproduce its measured state")
        self.state, self._history, self._seed, self._chain = (
            replacement.state,
            replacement._history,
            replacement._seed,
            replacement._chain,
        )
        self._last_camera = replacement._last_camera
        return self._observe()

    def preview(self):
        if self._seed is None:
            return None
        width, height = 320, 180
        s, world = dict(self.state), self.world
        if self.fidelity["render_camera_interpolation"]:
            s["camera_x"] = (s["camera_x"] + self._last_camera[0]) / 2
            s["camera_y"] = (s["camera_y"] + self._last_camera[1]) / 2
        palette = {key: bytes.fromhex(value[1:]) for key, value in self.authored["palette"].items()}
        from .game_successor_assets import successor_art

        art = successor_art(self.authored)
        rgba = art["rgba"]
        pixels = bytearray(palette["background"] * width * height)
        colours = [
            bytes.fromhex(value)
            for value in ("34694c", "3274a3", "647078", "c9ae6e", "ac9570", "244933", "745236", "41424f")
        ]

        def rect(x, y, w, h, colour, camera=True):
            if camera:
                x, y, w, h = (x - s["camera_x"]) / 2, (y - s["camera_y"]) / 2, w / 2, h / 2
            left, top, right, bottom = (
                max(0, int(x)),
                max(0, int(y)),
                min(width, math.ceil(x + w)),
                min(height, math.ceil(y + h)),
            )
            if right <= left or bottom <= top:
                return
            for row in range(top, bottom):
                pixels[(row * width + left) * 3 : (row * width + right) * 3] = colour * (right - left)

        def sprite(index, x, y, w, h):
            x, y, w, h = (x - s["camera_x"]) / 2, (y - s["camera_y"]) / 2, w / 2, h / 2
            left, top, right, bottom = (
                max(0, math.floor(x)),
                max(0, math.floor(y)),
                min(width, math.ceil(x + w)),
                min(height, math.ceil(y + h)),
            )
            if right <= left or bottom <= top:
                return
            sx, sy = index % 8 * 16, index // 8 * 16
            for row in range(top, bottom):
                source_y = min(15, max(0, int((row - y) / h * 16))) + sy
                for column in range(left, right):
                    if self.fidelity["filter"] == "linear":
                        u = _clamp((column + 0.5 - x) / w * 16 - 0.5, 0, 15)
                        v = _clamp((row + 0.5 - y) / h * 16 - 0.5, 0, 15)
                        ax, ay = math.floor(u), math.floor(v)
                        fx, fy = u - ax, v - ay
                        samples = [
                            (ax, ay, (1 - fx) * (1 - fy)),
                            (min(15, ax + 1), ay, fx * (1 - fy)),
                            (ax, min(15, ay + 1), (1 - fx) * fy),
                            (min(15, ax + 1), min(15, ay + 1), fx * fy),
                        ]
                        alpha, rgb = 0.0, [0.0, 0.0, 0.0]
                        for px, py, weight in samples:
                            source = ((py + sy) * 128 + px + sx) * 4
                            amount = rgba[source + 3] / 255 * weight
                            alpha += amount
                            for channel in range(3):
                                rgb[channel] += rgba[source + channel] * amount
                        destination = (row * width + column) * 3
                        for channel in range(3):
                            pixels[destination + channel] = int(
                                rgb[channel] + pixels[destination + channel] * (1 - alpha)
                            )
                        continue
                    source_x = min(15, max(0, int((column - x) / w * 16))) + sx
                    offset = (source_y * 128 + source_x) * 4
                    if rgba[offset + 3]:
                        pixels[(row * width + column) * 3 : (row * width + column) * 3 + 3] = rgba[
                            offset : offset + 3
                        ]

        tile = world["tile_size"]
        terrain = world.get("terrain")
        left, top = int(s["camera_x"] // tile), int(s["camera_y"] // tile)
        for ty in range(top, min(math.ceil(world["height"] / tile), top + math.ceil(VIEW_H / tile) + 1)):
            for tx in range(left, min(math.ceil(world["width"] / tile), left + math.ceil(VIEW_W / tile) + 1)):
                kind = int(terrain[ty][tx]) if terrain else 0
                variation = (tx * 17 + ty * 31 + self.authored["seed"] % 97) % 4
                slot = (
                    4 + s["steps"] // 20 % 4
                    if kind == 1
                    else {2: 10, 3: 8, 4: 9, 5: 13, 6: 11, 7: 14}.get(kind, variation)
                )
                sprite(slot, tx * tile, ty * tile, tile, tile)
                if kind in (0, 3, 5):
                    rect(tx * tile + (tx * 7 + ty * 3) % 24, ty * tile + 7, 2, 4, palette["terrain"])
                if kind == 1:
                    rect(tx * tile + 3, ty * tile + 5 + s["steps"] // 20 % 7, 16, 2, palette["accent"])
        for pond in world.get("ponds", []):
            rect(pond["x"], pond["y"], pond["w"], pond["h"], colours[1])
            for index in range(4):
                rect(
                    pond["x"] + 8 + index * 22,
                    pond["y"] + 8 + (s["steps"] // 20 + index * 7) % max(1, int(pond["h"] - 12)),
                    15,
                    2,
                    palette["accent"],
                )
        for farm in world.get("farm_plots", []):
            rect(farm["x"], farm["y"], farm["w"], farm["h"], colours[6])
        for landmark in world.get("landmarks", []):
            sprite(landmark["sprite_index"], landmark["x"], landmark["y"], landmark["w"], landmark["h"])
        for obstacle in [*world.get("obstacles_rects", []), *world.get("platforms", [])]:
            rect(obstacle["x"], obstacle["y"], obstacle["w"], obstacle["h"], palette["terrain"])
            rect(obstacle["x"] + 3, obstacle["y"] + 3, max(1, obstacle["w"] - 6), 4, palette["accent"])
        for plot in s["plots"]:
            rect(
                plot["x"] + 2,
                plot["y"] + 2,
                tile - 4,
                tile - 4,
                colours[1] if plot["water"] > 0.5 else colours[6],
            )
            if plot["crop"] >= 0:
                growth = 5 + plot["growth"] * 18
                rect(
                    plot["x"] + tile / 2 - 2,
                    plot["y"] + tile - growth - 3,
                    4,
                    growth,
                    palette["collectible"] if plot["growth"] >= 1 else palette["player"],
                )
                rect(plot["x"] + tile / 2 - 7, plot["y"] + tile - growth, 14, 4, palette["accent"])
        for npc in world.get("villagers", []):
            rect(npc["x"] + 3, npc["y"] - 9, 12, 10, palette["collectible"])
            rect(npc["x"], npc["y"], 18, 20, palette["accent"])
            sprite(20 + world.get("villagers", []).index(npc) % 4, npc["x"] - 7, npc["y"] - 12, 32, 36)
        for item in world.get("collectibles", []):
            if item["id"] not in s["collected"]:
                rect(item["x"], item["y"], 10, 14, palette["collectible"])
        for enemy in s["enemies"]:
            if enemy["hp"] > 0:
                rect(enemy["x"], enemy["y"], enemy["w"], enemy["h"], palette["enemy"])
                rect(enemy["x"] + 4, enemy["y"] + 4, enemy["w"] - 8, 3, palette["background"])
                rect(
                    enemy["x"],
                    enemy["y"] - 6,
                    enemy["w"] * enemy["hp"] / enemy["max_hp"],
                    3,
                    palette["collectible"],
                )
        for bullet in s["projectiles"]:
            rect(
                bullet["x"] - 3,
                bullet["y"] - 3,
                6,
                6,
                palette["accent"] if bullet["friendly"] else palette["enemy"],
            )
        for enemy in s["enemies"]:
            if enemy["hp"] > 0:
                sprite(
                    27 if enemy["boss"] else 24 + s["enemies"].index(enemy) % 3,
                    enemy["x"] - 5,
                    enemy["y"] - 10,
                    enemy["w"] + 10,
                    enemy["h"] + 12,
                )
        if s["invulnerable"] <= 0 or s["steps"] % 8 < 4:
            rect(s["x"] + 3, s["y"] - 8, 12, 10, palette["collectible"])
            rect(s["x"], s["y"], BODY_W, BODY_H, palette["player"])
            rect(s["x"] + 3, s["y"] + 16, 4, 4, palette["accent"])
            rect(s["x"] + 11, s["y"] + 16, 4, 4, palette["accent"])
            facing = (
                (18 if s["facing_x"] < 0 else 19)
                if abs(s["facing_x"]) > abs(s["facing_y"])
                else (17 if s["facing_y"] < 0 else 16)
            )
            sprite(facing, s["x"] - 7, s["y"] - 12, 32, 36)
        if s["fish"]["phase"] != "idle":
            rect(85, 145, 150, 20, palette["background"], False)
            rect(88, 148, 144 * s["fish"]["progress"], 5, palette["collectible"], False)
            rect(88, 156, 144 * s["fish"]["tension"], 5, palette["enemy"], False)
        rect(5, 5, 75, 5, palette["enemy"], False)
        rect(5, 5, 75 * s["health"] / self.mechanics["resources"]["max_health"], 5, palette["player"], False)
        rect(5, 13, 75 * s["energy"] / self.mechanics["resources"]["max_energy"], 3, palette["accent"], False)
        if s["weather"] == "rain":
            for index in range(40):
                rect(
                    (index * 73 + s["steps"] * 2) % width,
                    (index * 29 + s["steps"] * 3) % height,
                    1,
                    5,
                    palette["accent"],
                    False,
                )
        tint = self.fidelity["tint"]
        night = (
            self.fidelity["lighting"]
            * (1 - math.cos(s["clock"] / self.mechanics["farming"]["day_seconds"] * math.pi * 2))
            / 2
        )
        for offset in range(0, len(pixels), 3):
            for channel in range(3):
                pixels[offset + channel] = int(
                    pixels[offset + channel] * tint[channel] / 255 * (1 - night * (1 - channel * 0.12))
                )
        for layer in range(1, self.fidelity["layers"]):
            for index in range(self.fidelity["particles"] // self.fidelity["layers"]):
                x = (
                    index * 73 + layer * 41 + s["steps"] // (3 + layer) - int(s["camera_x"] * 0.1 * layer)
                ) % width
                y = (index * 29 + layer * 37 - s["steps"] // (7 + layer)) % height
                rect(x, y, 1 + int(layer == 2), 1, palette["collectible"], False)
        raw = b"".join(b"\0" + pixels[row * width * 3 : (row + 1) * width * 3] for row in range(height))

        def chunk(kind, data):
            return (
                struct.pack(">I", len(data))
                + kind
                + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
            )

        png = (
            b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 6))
            + chunk(b"IEND", b"")
        )
        pixel_hash, png_hash = hashlib.sha256(pixels).hexdigest(), hashlib.sha256(png).hexdigest()
        return {
            "runtime_kind": "original_successor_game",
            "gameplay_mode": "top_down",
            "render_kind": "actual_successor_frame",
            "width": width,
            "height": height,
            "data_uri": "data:image/png;base64," + base64.b64encode(png).decode(),
            "pixel_digest": pixel_hash,
            "art_digest": art["digest"],
            "fidelity": dict(self.fidelity),
            "png_digest": png_hash,
            "raster": {"width": width, "height": height, "pixel_digest": pixel_hash, "png_digest": png_hash},
            "state_digest": self.state_digest,
            "hud": {
                key: s[key]
                for key in (
                    "health",
                    "energy",
                    "coins",
                    "xp",
                    "fish_caught",
                    "harvested",
                    "relics",
                    "day",
                    "season",
                    "weather",
                    "clock",
                    "tool",
                    "crop",
                    "mode",
                    "scene",
                )
            },
            "fishing": dict(s["fish"]),
            "quest": self.mechanics["progression"]["quest_text"],
            "completed_quests": list(s["completed_quests"]),
            "dialogue": s["dialogue"] if s["dialogue_time"] > 0 else None,
            "camera": [s["camera_x"], s["camera_y"]],
            "hardware_compatibility_verified": False,
        }

    def close(self):
        self._closed = True
