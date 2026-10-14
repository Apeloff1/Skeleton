"""Original fixed-step successor gameplay and portable project generation.

The authored recipe is data. Physics, combat and progression execute here;
source lineage never imports a source game's code, assets or privileges.
Application owners retain rights, tenant and durable publication authority.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import json
import math
import re
import struct
import zlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .game_learning_runtime import EpisodeStep, GameEnvironmentSpec

SPEC_SCHEMA = "skeleton.game.successor_spec.v1"
STATE_SCHEMA = "skeleton.game.successor_state.v1"
DT = 1.0 / 60.0
PLAYER_W, PLAYER_H = 18.0, 26.0
VIEW_W, VIEW_H = 512, 288
MAX_PROJECTILES = 128
ACTIONS = (
    "noop",
    "left",
    "right",
    "jump",
    "left_jump",
    "right_jump",
    "fire",
    "left_fire",
    "right_fire",
    "left_jump_fire",
    "right_jump_fire",
    "interact",
)
REWARDS = ("progress", "collectibles", "damage", "kills", "goal", "death", "time")
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


class SuccessorRuntimeError(ValueError):
    pass


def resolved_fidelity(spec: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(spec, Mapping):
        raise SuccessorRuntimeError("fidelity requires an authored spec object")
    value = spec.get("fidelity", {"profile": "pixel"})
    if (
        not isinstance(value, Mapping)
        or set(value) != {"profile"}
        or value.get("profile") not in ("pixel", "enhanced", "cinematic")
    ):
        raise SuccessorRuntimeError("fidelity requires an exact declared 2D renderer profile")
    level = ("pixel", "enhanced", "cinematic").index(value["profile"])
    return {
        "profile": value["profile"],
        "level": level,
        "particles": (0, 24, 64)[level],
        "layers": (1, 2, 3)[level],
        "lighting": (0.2, 0.32, 0.42)[level],
        "filter": "linear" if level == 2 else "nearest",
        "tint": ((255, 255, 255), (255, 247, 235), (246, 235, 255))[level],
        "render_camera_interpolation": level == 2,
        "render_limit": "bounded original 2D pixel art",
    }


def _canonical(value: Any, limit: int = 131072) -> bytes:
    stack, count = [(value, 0)], 0
    while stack:
        item, depth = stack.pop()
        count += 1
        if count > 16384 or depth > 16:
            raise SuccessorRuntimeError("successor data exceeds structural capacity")
        if isinstance(item, Mapping):
            if len(item) > 256 or any(not isinstance(key, str) or len(key) > 256 for key in item):
                raise SuccessorRuntimeError("successor object shape exceeds capacity")
            stack.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, (list, tuple)):
            if len(item) > 4096:
                raise SuccessorRuntimeError("successor sequence exceeds capacity")
            stack.extend((child, depth + 1) for child in item)
        elif isinstance(item, str):
            if len(item) > 16384:
                raise SuccessorRuntimeError("successor string exceeds capacity")
        elif item is not None and type(item) not in (int, float, bool):
            raise SuccessorRuntimeError("successor data must contain only JSON values")
    try:
        raw = json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
        ).encode()
    except (ValueError, TypeError, OverflowError) as exc:
        raise SuccessorRuntimeError("successor data is not finite JSON") from exc
    if len(raw) > limit:
        raise SuccessorRuntimeError("successor data exceeds byte capacity")
    return raw


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value, 262144)).hexdigest()


def _number(value: Any, low: float, high: float, name: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise SuccessorRuntimeError(name + " is outside its finite bounds")
    return float(value)


def _integer(value: Any, low: int, high: int, name: str) -> int:
    if type(value) is not int or not low <= value <= high:
        raise SuccessorRuntimeError(name + " is outside its integer bounds")
    return value


def _point(value: Any, width: float, height: float, name: str) -> list[float]:
    if not isinstance(value, list) or len(value) != 2:
        raise SuccessorRuntimeError(name + " requires an exact coordinate pair")
    return [
        _number(value[0], 0, width - PLAYER_W, name + ".x"),
        _number(value[1], 0, height - PLAYER_H, name + ".y"),
    ]


def validate_successor_spec(spec: Mapping[str, Any]) -> dict[str, Any]:
    """Preserve the exact authored spec after bounded semantic validation."""
    clean = json.loads(_canonical(spec))
    resolved_fidelity(clean)
    if isinstance(clean, dict) and clean.get("gameplay_mode") == "top_down":
        from .game_successor_world import validate_world_spec

        return validate_world_spec(clean)
    if not isinstance(clean, dict) or clean.get("schema_version") != SPEC_SCHEMA:
        raise SuccessorRuntimeError("an authored successor spec is required")
    for name in ("project_id", "title"):
        value = clean.get(name)
        if not isinstance(value, str) or not 1 <= len(value) <= 120 or any(ord(char) < 32 for char in value):
            raise SuccessorRuntimeError("invalid successor " + name)
    _integer(clean.get("seed"), 0, 2**63 - 1, "seed")
    origins = clean.get("origins")
    if not isinstance(origins, list) or len(origins) not in (1, 3):
        raise SuccessorRuntimeError("a successor requires exactly one or three origin profiles")
    for origin in origins:
        if (
            not isinstance(origin, dict)
            or not isinstance(origin.get("profile_id"), str)
            or not _ID.fullmatch(origin["profile_id"])
        ):
            raise SuccessorRuntimeError("origin profile identity is invalid")
    palette = clean.get("palette")
    if not isinstance(palette, dict) or set(palette) != {
        "background",
        "terrain",
        "player",
        "enemy",
        "accent",
        "collectible",
    }:
        raise SuccessorRuntimeError("successor palette requires its six original colours")
    if any(not isinstance(value, str) or not _COLOR.fullmatch(value) for value in palette.values()):
        raise SuccessorRuntimeError("successor palette is invalid")
    world = clean.get("world")
    if not isinstance(world, dict):
        raise SuccessorRuntimeError("successor world is required")
    width = _number(world.get("width"), 512, 8192, "world width")
    height = _number(world.get("height"), 288, 4096, "world height")
    _integer(world.get("tile_size"), 8, 64, "tile size")
    spawn = _point(world.get("spawn"), width, height, "spawn")
    _point(world.get("goal"), width, height, "goal")
    names = set()
    for key, maximum in (
        ("platforms", 128),
        ("collectibles", 64),
        ("enemies", 32),
        ("doors", 16),
        ("checkpoints", 16),
    ):
        rows = world.get(key, [])
        if not isinstance(rows, list) or len(rows) > maximum:
            raise SuccessorRuntimeError(key + " exceeds entity capacity")
        for row in rows:
            if (
                not isinstance(row, dict)
                or not isinstance(row.get("id"), str)
                or not _ID.fullmatch(row["id"])
                or row["id"] in names
            ):
                raise SuccessorRuntimeError("world entity identity is invalid or duplicated")
            names.add(row["id"])
            _number(row.get("x"), 0, width, key + ".x")
            _number(row.get("y"), 0, height, key + ".y")
            if key in ("platforms", "doors"):
                _number(row.get("w"), 4, width, key + ".w")
                _number(row.get("h"), 4, height, key + ".h")
                if row["x"] + row["w"] > width or row["y"] + row["h"] > height:
                    raise SuccessorRuntimeError("world rectangle extends outside its bounds")
            if key == "platforms":
                if row.get("kind", "solid") not in ("solid", "one_way"):
                    raise SuccessorRuntimeError("unsupported platform kind")
                if row.get("kind", "solid") == "solid" and _overlap(
                    spawn[0], spawn[1], PLAYER_W, PLAYER_H, row
                ):
                    raise SuccessorRuntimeError("spawn is embedded in solid terrain")
            if key == "collectibles":
                if row.get("kind") not in ("shard", "key", "energy", "health"):
                    raise SuccessorRuntimeError("unsupported original collectible kind")
                _integer(row.get("value", 1), 1, 100, "collectible value")
            if key == "doors":
                _point([row.get("target_x"), row.get("target_y")], width, height, "door destination")
                if row.get("requires") not in (None, "key", "shard", "boss"):
                    raise SuccessorRuntimeError("unsupported door requirement")
            if key == "enemies":
                _validate_enemy(row, width)
    if not world.get("platforms"):
        raise SuccessorRuntimeError("a platformer world requires actual terrain")
    boss = world.get("boss")
    if boss is not None:
        if (
            not isinstance(boss, dict)
            or not isinstance(boss.get("id"), str)
            or not _ID.fullmatch(boss["id"])
            or boss["id"] in names
        ):
            raise SuccessorRuntimeError("boss identity is invalid")
        _number(boss.get("x"), 0, width - 36, "boss x")
        _number(boss.get("y"), 0, height - 44, "boss y")
        _validate_enemy(boss, width, boss=True)
    mechanics = clean.get("mechanics")
    if not isinstance(mechanics, dict):
        raise SuccessorRuntimeError("quantified mechanics are required")
    bounds = {
        "movement": {
            "acceleration": (60, 5000),
            "max_speed": (30, 600),
            "friction": (60, 5000),
            "gravity": (100, 3000),
            "max_fall_speed": (100, 1200),
        },
        "jump": {"velocity": (-900, -60), "coyote_seconds": (0, 0.3), "buffer_seconds": (0, 0.3)},
        "combat": {
            "projectile_speed": (100, 1000),
            "cooldown": (0.08, 2),
            "invulnerability_seconds": (0.1, 3),
        },
    }
    for section, values in bounds.items():
        if not isinstance(mechanics.get(section), dict):
            raise SuccessorRuntimeError("missing quantified " + section)
        for name, (low, high) in values.items():
            _number(mechanics[section].get(name), low, high, section + "." + name)
    _integer(mechanics["jump"].get("air_jumps"), 0, 2, "air jumps")
    for name in ("damage", "enemy_damage"):
        _integer(mechanics["combat"].get(name), 1, 16, name)
    resources = mechanics.get("resources", {})
    _integer(resources.get("max_health"), 1, 32, "maximum health")
    _integer(resources.get("max_energy"), 1, 100, "maximum energy")
    progression = mechanics.get("progression", {})
    _integer(progression.get("required_collectibles"), 0, 64, "required shards")
    if not isinstance(progression.get("quest_text"), str) or not 1 <= len(progression["quest_text"]) <= 256:
        raise SuccessorRuntimeError("original quest text is required")
    camera = clean.get("camera", {})
    if camera.get("mode", "side_scroll") != "side_scroll":
        raise SuccessorRuntimeError("unsupported successor camera")
    _number(camera.get("lookahead", 40), 0, 160, "camera lookahead")
    _number(camera.get("smoothing", 0.12), 0.02, 1, "camera smoothing")
    return clean


def _validate_enemy(row: dict[str, Any], width: float, boss: bool = False) -> None:
    if row.get("kind", "boss" if boss else "walker") not in ("walker", "shooter", "flyer", "boss"):
        raise SuccessorRuntimeError("unsupported enemy behaviour")
    _integer(row.get("hp", 12 if boss else 2), 1, 64, "enemy health")
    _number(row.get("speed", 45), 0, 240, "enemy speed")
    _number(row.get("attack_interval", 1.4), 0.25, 10, "enemy attack interval")
    patrol = row.get("patrol", [max(0, row["x"] - 80), min(width - 36, row["x"] + 80)])
    if not isinstance(patrol, list) or len(patrol) != 2 or not 0 <= patrol[0] <= patrol[1] <= width:
        raise SuccessorRuntimeError("enemy patrol bounds are invalid")


def _overlap(x: float, y: float, w: float, h: float, other: Mapping[str, float]) -> bool:
    return (
        x < other["x"] + other.get("w", 20)
        and x + w > other["x"]
        and y < other["y"] + other.get("h", 24)
        and y + h > other["y"]
    )


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


class PlatformSuccessorEnvironment:
    """Actual continuous platformer, combat and exploration simulation."""

    def __init__(self, spec: Mapping[str, Any], *, max_steps: int = 4096):
        self.authored = validate_successor_spec(spec)
        self.max_steps = _integer(max_steps, 1, 4096, "episode steps")
        self.spec_digest = _digest(self.authored)
        self._world = self.authored["world"]
        self._mechanics = self.authored["mechanics"]
        self._closed = False
        self._seed = None
        self._history: list[int] = []
        code = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        self.spec = GameEnvironmentSpec(
            "successor:" + self.authored["project_id"],
            _digest(
                {"authored_spec": self.spec_digest, "runtime": code, "step_hz": 60, "max_steps": max_steps}
            ),
            ACTIONS,
            {
                key: tuple(bins)
                for key, bins in {
                    "x": (0.1, 0.25, 0.5, 0.75, 0.9),
                    "y": (0.25, 0.5, 0.75),
                    "vx": (-0.7, -0.2, 0.2, 0.7),
                    "vy": (-0.7, -0.2, 0.2, 0.7),
                    "grounded": (0.5,),
                    "health": (0.25, 0.5, 0.75),
                    "energy": (0.25, 0.5, 0.75),
                    "goal_dx": (-0.5, -0.1, 0.1, 0.5),
                    "enemy_dx": (-0.5, -0.1, 0.1, 0.5),
                    "enemy_dy": (-0.5, -0.1, 0.1, 0.5),
                    "shards": (0.25, 0.5, 0.75),
                    "boss_health": (0.25, 0.5, 0.75),
                }.items()
            },
            REWARDS,
            max_steps,
        )

    @property
    def descriptor(self) -> dict[str, Any]:
        return {
            "runtime_kind": "original_successor_game",
            "spec_digest": self.spec_digest,
            "environment_digest": self.spec.environment_digest,
            "step_hz": 60,
            "spec": self.spec.as_dict(),
            "hardware_compatibility_verified": False,
        }

    @property
    def done(self) -> bool:
        return (
            self._closed
            or self._seed is not None
            and (self.state["mode"] != "playing" or self.state["steps"] >= self.max_steps)
        )

    def reset(self, seed: int = 0) -> dict[str, float]:
        if self._closed:
            raise SuccessorRuntimeError("successor environment is closed")
        self._seed = _integer(seed, 0, 2**63 - 1, "episode seed")
        self._history = []
        spawn = self._world["spawn"]
        resources = self._mechanics["resources"]
        enemies = []
        for source in [
            *self._world.get("enemies", []),
            *([self._world["boss"]] if self._world.get("boss") else []),
        ]:
            enemy = copy.deepcopy(source)
            boss = source is self._world.get("boss")
            enemy.update(
                {
                    "w": 36 if boss else 20,
                    "h": 44 if boss else 24,
                    "kind": "boss" if boss else source.get("kind", "walker"),
                    "hp": source.get("hp", 12 if boss else 2),
                    "max_hp": source.get("hp", 12 if boss else 2),
                    "direction": -1,
                    "cooldown": source.get("attack_interval", 1.4),
                    "vy": 0.0,
                }
            )
            enemy.setdefault("speed", 45)
            enemy.setdefault("attack_interval", 1.4)
            enemy.setdefault(
                "patrol", [max(0, enemy["x"] - 80), min(self._world["width"] - 36, enemy["x"] + 80)]
            )
            enemies.append(enemy)
        self.state = {
            "x": float(spawn[0]),
            "y": float(spawn[1]),
            "vx": 0.0,
            "vy": 0.0,
            "facing": 1,
            "grounded": False,
            "coyote": 0.0,
            "jump_buffer": 0.0,
            "air_jumps": 0,
            "previous_input": 0,
            "shot_cooldown": 0.0,
            "invulnerable": 0.0,
            "health": resources["max_health"],
            "energy": float(resources["max_energy"]),
            "shards": 0,
            "keys": 0,
            "xp": 0,
            "kills": 0,
            "steps": 0,
            "mode": "playing",
            "camera_x": 0.0,
            "camera_y": _clamp(spawn[1] - VIEW_H * 0.6, 0, self._world["height"] - VIEW_H),
            "checkpoint": list(spawn),
            "checkpoint_id": None,
            "collected": [],
            "enemies": enemies,
            "projectiles": [],
            "door_cooldown": 0.0,
            "scene": 0,
            "events": [],
            "max_x": float(spawn[0]),
        }
        self._chain = _digest(
            {"environment": self.spec.environment_digest, "seed": seed, "initial": self.state}
        )
        return self._observe()

    def _observe(self) -> dict[str, float]:
        state, world, mechanics = self.state, self._world, self._mechanics
        alive = [enemy for enemy in state["enemies"] if enemy["hp"] > 0]
        nearest = min(
            alive, key=lambda enemy: abs(enemy["x"] - state["x"]) + abs(enemy["y"] - state["y"]), default=None
        )
        boss = next((enemy for enemy in state["enemies"] if enemy["kind"] == "boss"), None)
        return {
            "x": state["x"] / world["width"],
            "y": state["y"] / world["height"],
            "vx": state["vx"] / mechanics["movement"]["max_speed"],
            "vy": _clamp(state["vy"] / mechanics["movement"]["max_fall_speed"], -1, 1),
            "grounded": float(state["grounded"]),
            "health": state["health"] / mechanics["resources"]["max_health"],
            "energy": state["energy"] / mechanics["resources"]["max_energy"],
            "goal_dx": _clamp((world["goal"][0] - state["x"]) / VIEW_W, -1, 1),
            "enemy_dx": 1.0 if nearest is None else _clamp((nearest["x"] - state["x"]) / VIEW_W, -1, 1),
            "enemy_dy": 0.0 if nearest is None else _clamp((nearest["y"] - state["y"]) / VIEW_H, -1, 1),
            "shards": _clamp(
                state["shards"] / max(1, mechanics["progression"]["required_collectibles"]), 0, 1
            ),
            "boss_health": 0.0 if boss is None else boss["hp"] / boss["max_hp"],
        }

    def current_observation(self) -> dict[str, float]:
        if self._seed is None:
            raise SuccessorRuntimeError("reset successor before observing it")
        return self._observe()

    @staticmethod
    def _mask(action: str) -> int:
        if action not in ACTIONS:
            raise SuccessorRuntimeError("successor action is unavailable")
        return (
            (1 if "left" in action else 0)
            | (2 if "right" in action else 0)
            | (4 if "jump" in action else 0)
            | (8 if "fire" in action else 0)
            | (16 if action == "interact" else 0)
        )

    def step(self, action: str) -> EpisodeStep:
        return self._advance(self._mask(action), action)

    def input_step(self, controls) -> EpisodeStep:
        if (
            not isinstance(controls, (list, tuple))
            or len(controls) != 1
            or not isinstance(controls[0], Mapping)
        ):
            raise SuccessorRuntimeError("successor has one bounded controller port")
        buttons = _integer(controls[0].get("buttons", 0), 0, 65535, "controller buttons")
        mask = (
            (1 if buttons & 64 else 0)
            | (2 if buttons & 128 else 0)
            | (4 if buttons & 256 else 0)
            | (8 if buttons & 1 else 0)
            | (16 if buttons & (16 | 8) else 0)
        )
        return self._advance(mask, None)

    def _advance(self, mask: int, action: str | None) -> EpisodeStep:
        if self._seed is None or self.done:
            raise SuccessorRuntimeError("reset an active successor episode before stepping")
        state, movement, jump, combat = (
            self.state,
            self._mechanics["movement"],
            self._mechanics["jump"],
            self._mechanics["combat"],
        )
        rewards = {key: 0.0 for key in REWARDS}
        rewards["time"] = -0.001
        state["events"] = []
        state["steps"] += 1
        state["invulnerable"] = max(0.0, state["invulnerable"] - DT)
        state["shot_cooldown"] = max(0.0, state["shot_cooldown"] - DT)
        state["door_cooldown"] = max(0.0, state["door_cooldown"] - DT)
        state["energy"] = min(self._mechanics["resources"]["max_energy"], state["energy"] + DT * 2)
        direction = int(bool(mask & 2)) - int(bool(mask & 1))
        if direction:
            state["vx"] = _clamp(
                state["vx"] + direction * movement["acceleration"] * DT,
                -movement["max_speed"],
                movement["max_speed"],
            )
            state["facing"] = direction
        else:
            state["vx"] = math.copysign(max(0.0, abs(state["vx"]) - movement["friction"] * DT), state["vx"])
        state["coyote"] = jump["coyote_seconds"] if state["grounded"] else max(0.0, state["coyote"] - DT)
        state["jump_buffer"] = (
            jump["buffer_seconds"]
            if mask & 4 and not state["previous_input"] & 4
            else max(0.0, state["jump_buffer"] - DT)
        )
        if state["jump_buffer"] > 0 and (state["coyote"] > 0 or state["air_jumps"] < jump["air_jumps"]):
            airborne = state["coyote"] <= 0
            state["vy"] = jump["velocity"]
            state["grounded"] = False
            state["coyote"] = state["jump_buffer"] = 0.0
            state["air_jumps"] += int(airborne)
            state["events"].append("jump")
        if not mask & 4 and state["vy"] < jump["velocity"] * 0.45:
            state["vy"] = jump["velocity"] * 0.45
        self._move_player()
        if mask & 8 and state["shot_cooldown"] <= 0 and state["energy"] >= 1:
            self._projectile(
                state["x"] + PLAYER_W * 0.5,
                state["y"] + PLAYER_H * 0.45,
                state["facing"] * combat["projectile_speed"],
                0.0,
                True,
            )
            state["energy"] -= 1
            state["shot_cooldown"] = combat["cooldown"]
            state["events"].append("shoot")
        self._enemies()
        self._projectiles(rewards)
        for enemy in state["enemies"]:
            if enemy["hp"] > 0 and _overlap(state["x"], state["y"], PLAYER_W, PLAYER_H, enemy):
                self._damage(rewards)
        for source in self._world.get("collectibles", []):
            if source["id"] not in state["collected"] and _overlap(
                state["x"], state["y"], PLAYER_W, PLAYER_H, {**source, "w": 14, "h": 14}
            ):
                state["collected"].append(source["id"])
                value, kind = source.get("value", 1), source["kind"]
                if kind == "shard":
                    state["shards"] += value
                elif kind == "key":
                    state["keys"] += value
                elif kind == "health":
                    state["health"] = min(self._mechanics["resources"]["max_health"], state["health"] + value)
                else:
                    state["energy"] = min(self._mechanics["resources"]["max_energy"], state["energy"] + value)
                state["xp"] += value
                state["events"].append("collect")
                rewards["collectibles"] += value
        for checkpoint in self._world.get("checkpoints", []):
            if (
                abs(state["x"] - checkpoint["x"]) < 32
                and abs(state["y"] - checkpoint["y"]) < 48
                and state["checkpoint_id"] != checkpoint["id"]
            ):
                state["checkpoint"] = [checkpoint["x"], checkpoint["y"]]
                state["checkpoint_id"] = checkpoint["id"]
                state["health"] = self._mechanics["resources"]["max_health"]
                state["events"].append("checkpoint")
        for door in self._world.get("doors", []):
            requirement = door.get("requires")
            permitted = (
                requirement is None
                or requirement == "key"
                and state["keys"] > 0
                or requirement == "shard"
                and state["shards"] >= self._mechanics["progression"]["required_collectibles"]
                or requirement == "boss"
                and self._boss_dead()
            )
            if (
                mask & 16
                and state["door_cooldown"] <= 0
                and permitted
                and _overlap(state["x"], state["y"], PLAYER_W, PLAYER_H, door)
            ):
                state["x"], state["y"] = door["target_x"], door["target_y"]
                state["vx"] = state["vy"] = 0.0
                state["scene"] += 1
                state["door_cooldown"] = 0.5
                state["events"].append("door")
        if state["y"] > self._world["height"] - PLAYER_H or state["health"] <= 0:
            state["health"] = 0
            state["mode"] = "dead"
            state["events"].append("death")
            rewards["death"] = -5.0
        goal = self._world["goal"]
        if (
            state["mode"] == "playing"
            and abs(state["x"] - goal[0]) < 40
            and abs(state["y"] - goal[1]) < 64
            and state["shards"] >= self._mechanics["progression"]["required_collectibles"]
            and self._boss_dead()
        ):
            state["mode"] = "won"
            state["events"].append("victory")
            rewards["goal"] = 10.0
        rewards["progress"] = max(0.0, state["x"] - state["max_x"]) / self._world["width"]
        state["max_x"] = max(state["max_x"], state["x"])
        target_x = _clamp(
            state["x"]
            + PLAYER_W / 2
            - VIEW_W / 2
            + state["facing"] * self.authored.get("camera", {}).get("lookahead", 40),
            0,
            self._world["width"] - VIEW_W,
        )
        target_y = _clamp(state["y"] - VIEW_H * 0.6, 0, self._world["height"] - VIEW_H)
        smooth = self.authored.get("camera", {}).get("smoothing", 0.12)
        state["camera_x"] += (target_x - state["camera_x"]) * smooth
        state["camera_y"] += (target_y - state["camera_y"]) * smooth
        state["previous_input"] = mask
        self._history.append(mask)
        observation = self._observe()
        self._chain = _digest(
            {
                "previous": self._chain,
                "mask": mask,
                "step": state["steps"],
                "state": self.state_digest,
                "reward": rewards,
            }
        )
        return EpisodeStep(
            observation,
            rewards,
            state["mode"] != "playing",
            state["mode"] == "playing" and state["steps"] >= self.max_steps,
            {
                "runtime_kind": "original_successor_game",
                "events": list(state["events"]),
                "goal_reached": state["mode"] == "won",
                "controller_only": action is None,
                "scene": state["scene"],
                "state_digest": self.state_digest,
            },
            self._chain,
        )

    def _move_player(self):
        s, movement = self.state, self._mechanics["movement"]
        old_x, old_y = s["x"], s["y"]
        s["x"] = _clamp(old_x + s["vx"] * DT, 0, self._world["width"] - PLAYER_W)
        for platform in self._world["platforms"]:
            if platform.get("kind", "solid") == "one_way" or not _overlap(
                s["x"], old_y, PLAYER_W, PLAYER_H, platform
            ):
                continue
            if s["vx"] > 0 and old_x + PLAYER_W <= platform["x"] + 1e-9:
                s["x"], s["vx"] = platform["x"] - PLAYER_W, 0.0
            elif s["vx"] < 0 and old_x >= platform["x"] + platform["w"] - 1e-9:
                s["x"], s["vx"] = platform["x"] + platform["w"], 0.0
        s["vy"] = min(movement["max_fall_speed"], s["vy"] + movement["gravity"] * DT)
        s["y"] += s["vy"] * DT
        s["grounded"] = False
        for platform in self._world["platforms"]:
            if not s["x"] < platform["x"] + platform["w"] or not s["x"] + PLAYER_W > platform["x"]:
                continue
            if (
                s["vy"] >= 0
                and old_y + PLAYER_H <= platform["y"] + 1e-9
                and s["y"] + PLAYER_H >= platform["y"]
            ):
                s["y"], s["vy"], s["grounded"], s["air_jumps"] = platform["y"] - PLAYER_H, 0.0, True, 0
            elif (
                platform.get("kind", "solid") != "one_way"
                and s["vy"] < 0
                and old_y >= platform["y"] + platform["h"] - 1e-9
                and s["y"] <= platform["y"] + platform["h"]
            ):
                s["y"], s["vy"] = platform["y"] + platform["h"], 0.0

    def _projectile(self, x, y, vx, vy, friendly):
        if len(self.state["projectiles"]) < MAX_PROJECTILES:
            self.state["projectiles"].append(
                {"x": x, "y": y, "vx": vx, "vy": vy, "friendly": friendly, "life": 2.0}
            )

    def _enemies(self):
        s = self.state
        for enemy in s["enemies"]:
            if enemy["hp"] <= 0:
                continue
            phase = 1.5 if enemy["kind"] == "boss" and enemy["hp"] <= enemy["max_hp"] * 0.5 else 1.0
            enemy["cooldown"] -= DT
            dx = s["x"] - enemy["x"]
            if abs(dx) < 260:
                enemy["direction"] = 1 if dx >= 0 else -1
            enemy["x"] += enemy["direction"] * enemy["speed"] * phase * DT
            lo, hi = enemy["patrol"]
            if enemy["x"] <= lo:
                enemy["x"], enemy["direction"] = lo, 1
            if enemy["x"] >= hi:
                enemy["x"], enemy["direction"] = hi, -1
            if enemy["kind"] == "flyer":
                enemy["y"] += _clamp(s["y"] - enemy["y"], -40, 40) * DT
            else:
                old_y = enemy["y"]
                enemy["vy"] = min(
                    self._mechanics["movement"]["max_fall_speed"],
                    enemy["vy"] + self._mechanics["movement"]["gravity"] * DT,
                )
                enemy["y"] += enemy["vy"] * DT
                for platform in self._world["platforms"]:
                    if (
                        enemy["x"] < platform["x"] + platform["w"]
                        and enemy["x"] + enemy["w"] > platform["x"]
                        and old_y + enemy["h"] <= platform["y"] + 1e-9
                        and enemy["y"] + enemy["h"] >= platform["y"]
                    ):
                        enemy["y"], enemy["vy"] = platform["y"] - enemy["h"], 0.0
            if enemy["kind"] in ("shooter", "boss", "flyer") and enemy["cooldown"] <= 0 and abs(dx) < 500:
                distance = max(1, math.hypot(dx, s["y"] - enemy["y"]))
                speed = self._mechanics["combat"]["projectile_speed"] * 0.55
                vx, vy = dx / distance * speed, (s["y"] - enemy["y"]) / distance * speed
                self._projectile(enemy["x"] + enemy["w"] / 2, enemy["y"] + enemy["h"] / 2, vx, vy, False)
                if phase > 1:
                    self._projectile(
                        enemy["x"] + enemy["w"] / 2, enemy["y"] + enemy["h"] / 2, vx, vy + 80, False
                    )
                    self._projectile(
                        enemy["x"] + enemy["w"] / 2, enemy["y"] + enemy["h"] / 2, vx, vy - 80, False
                    )
                enemy["cooldown"] = enemy["attack_interval"] / phase

    def _projectiles(self, rewards):
        retained = []
        for projectile in self.state["projectiles"]:
            projectile["x"] += projectile["vx"] * DT
            projectile["y"] += projectile["vy"] * DT
            projectile["life"] -= DT
            hit = (
                projectile["life"] <= 0
                or not 0 <= projectile["x"] <= self._world["width"]
                or not 0 <= projectile["y"] <= self._world["height"]
            )
            if any(
                _overlap(projectile["x"] - 3, projectile["y"] - 3, 6, 6, p) for p in self._world["platforms"]
            ):
                hit = True
            if not hit and projectile["friendly"]:
                for enemy in self.state["enemies"]:
                    if enemy["hp"] > 0 and _overlap(projectile["x"] - 3, projectile["y"] - 3, 6, 6, enemy):
                        enemy["hp"] = max(0, enemy["hp"] - self._mechanics["combat"]["damage"])
                        rewards["damage"] += 0.2
                        hit = True
                        self.state["events"].append("hit")
                        if enemy["hp"] == 0:
                            self.state["kills"] += 1
                            self.state["xp"] += 3
                            rewards["kills"] += 1
                            self.state["events"].append("defeat")
                        break
            elif not hit and _overlap(
                projectile["x"] - 3,
                projectile["y"] - 3,
                6,
                6,
                {"x": self.state["x"], "y": self.state["y"], "w": PLAYER_W, "h": PLAYER_H},
            ):
                self._damage(rewards)
                hit = True
            if not hit:
                retained.append(projectile)
        self.state["projectiles"] = retained

    def _damage(self, rewards):
        s = self.state
        if s["invulnerable"] <= 0:
            s["health"] = max(0, s["health"] - self._mechanics["combat"]["enemy_damage"])
            s["invulnerable"] = self._mechanics["combat"]["invulnerability_seconds"]
            s["vx"] = -s["facing"] * 90
            s["vy"] = -140
            s["events"].append("hurt")
            rewards["damage"] -= 0.5

    def _boss_dead(self):
        return all(enemy["hp"] <= 0 for enemy in self.state["enemies"] if enemy["kind"] == "boss")

    @property
    def state_digest(self) -> str:
        return _digest(self.state)

    def snapshot(self) -> dict[str, Any]:
        if self._seed is None:
            raise SuccessorRuntimeError("reset successor before saving")
        payload = {
            "schema_version": STATE_SCHEMA,
            "environment_digest": self.spec.environment_digest,
            "spec_digest": self.spec_digest,
            "seed": self._seed,
            "inputs": list(self._history),
            "state_digest": self.state_digest,
            "transition_digest": self._chain,
        }
        return {**payload, "snapshot_digest": _digest(payload)}

    def restore(self, snapshot: Mapping[str, Any]) -> dict[str, float]:
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
            or clean["schema_version"] != STATE_SCHEMA
            or clean["environment_digest"] != self.spec.environment_digest
            or clean["spec_digest"] != self.spec_digest
        ):
            raise SuccessorRuntimeError("successor save belongs to a different exact environment")
        payload = {key: value for key, value in clean.items() if key != "snapshot_digest"}
        if (
            _digest(payload) != clean["snapshot_digest"]
            or not isinstance(clean["inputs"], list)
            or len(clean["inputs"]) > self.max_steps
        ):
            raise SuccessorRuntimeError("successor save identity or cursor is invalid")
        temporary = PlatformSuccessorEnvironment(self.authored, max_steps=self.max_steps)
        temporary.reset(clean["seed"])
        for mask in clean["inputs"]:
            temporary._advance(_integer(mask, 0, 31, "saved input mask"), None)
        if temporary.state_digest != clean["state_digest"] or temporary._chain != clean["transition_digest"]:
            raise SuccessorRuntimeError("successor save cannot be reproduced from actual inputs")
        self.state, self._seed, self._history, self._chain = (
            temporary.state,
            temporary._seed,
            temporary._history,
            temporary._chain,
        )
        return self._observe()

    def preview(self) -> dict[str, Any] | None:
        if self._seed is None:
            return None
        width, height = 256, 144
        palette = {key: bytes.fromhex(value[1:]) for key, value in self.authored["palette"].items()}
        pixels = bytearray(palette["background"] * (width * height))
        s = self.state

        def rect(x, y, w, h, colour, camera=True):
            if camera:
                x, y = (x - s["camera_x"]) / 2, (y - s["camera_y"]) / 2
                w, h = w / 2, h / 2
            left, top, right, bottom = (
                max(0, int(x)),
                max(0, int(y)),
                min(width, math.ceil(x + w)),
                min(height, math.ceil(y + h)),
            )
            if right <= left or bottom <= top:
                return
            line = colour * (right - left)
            for row in range(top, bottom):
                pixels[(row * width + left) * 3 : (row * width + right) * 3] = line

        for index in range(24):
            x = (index * 137 + self.authored["seed"] % 37 - s["camera_x"] * 0.2) % VIEW_W
            y = 30 + index * 29 % 130
            rect(x / 2, y / 2, 1, 1, palette["accent"], False)
        for platform in self._world["platforms"]:
            rect(platform["x"], platform["y"], platform["w"], platform["h"], palette["terrain"])
            rect(platform["x"], platform["y"], platform["w"], 3, palette["accent"])
        for door in self._world.get("doors", []):
            rect(door["x"], door["y"], door["w"], door["h"], palette["accent"])
        for checkpoint in self._world.get("checkpoints", []):
            rect(checkpoint["x"], checkpoint["y"] - 22, 3, 48, palette["accent"])
            rect(checkpoint["x"] + 3, checkpoint["y"] - 22, 16, 9, palette["collectible"])
        for item in self._world.get("collectibles", []):
            if item["id"] not in s["collected"]:
                rect(item["x"] + 3, item["y"], 8, 14, palette["collectible"])
                rect(item["x"], item["y"] + 4, 14, 6, palette["collectible"])
        for enemy in s["enemies"]:
            if enemy["hp"] <= 0:
                continue
            rect(enemy["x"], enemy["y"], enemy["w"], enemy["h"], palette["enemy"])
            rect(enemy["x"] + 4, enemy["y"] + 4, enemy["w"] - 8, 4, palette["background"])
            rect(enemy["x"], enemy["y"] - 6, enemy["w"] * enemy["hp"] / enemy["max_hp"], 3, palette["accent"])
        for bullet in s["projectiles"]:
            rect(
                bullet["x"] - 3,
                bullet["y"] - 3,
                6,
                6,
                palette["collectible"] if bullet["friendly"] else palette["enemy"],
            )
        if s["invulnerable"] <= 0 or s["steps"] % 8 < 4:
            rect(s["x"] + 3, s["y"], 12, 9, palette["player"])
            rect(s["x"], s["y"] + 8, 18, 13, palette["player"])
            rect(s["x"] + 3, s["y"] + 21, 5, 5, palette["accent"])
            rect(s["x"] + 11, s["y"] + 21, 5, 5, palette["accent"])
            rect(s["x"] + (11 if s["facing"] > 0 else 4), s["y"] + 3, 3, 3, palette["background"])
        goal = self._world["goal"]
        rect(goal[0], goal[1] - 36, 4, 62, palette["collectible"])
        rect(5, 5, 70, 5, palette["enemy"], False)
        rect(5, 5, 70 * s["health"] / self._mechanics["resources"]["max_health"], 5, palette["player"], False)
        rect(
            5, 12, 70 * s["energy"] / self._mechanics["resources"]["max_energy"], 3, palette["accent"], False
        )
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
        pixel_digest, png_digest = hashlib.sha256(pixels).hexdigest(), hashlib.sha256(png).hexdigest()
        return {
            "runtime_kind": "original_successor_game",
            "render_kind": "actual_successor_frame",
            "width": width,
            "height": height,
            "data_uri": "data:image/png;base64," + base64.b64encode(png).decode(),
            "pixel_digest": pixel_digest,
            "png_digest": png_digest,
            "raster": {
                "width": width,
                "height": height,
                "pixel_digest": pixel_digest,
                "png_digest": png_digest,
            },
            "state_digest": self.state_digest,
            "camera": [s["camera_x"], s["camera_y"]],
            "hud": {
                key: s[key] for key in ("health", "energy", "shards", "keys", "xp", "kills", "mode", "scene")
            },
            "quest": self._mechanics["progression"]["quest_text"],
            "hardware_compatibility_verified": False,
        }

    def close(self):
        self._closed = True


def emit_successor_project(spec: Mapping[str, Any]) -> dict[str, str]:
    """Emit original full projects. Actual compilation remains the build owner."""
    from .game_successor_browser import emit_browser
    from .game_successor_native import emit_native

    authored = validate_successor_spec(spec)
    files = {"game/successor/spec.json": _canonical(authored).decode()}
    files.update(emit_browser(authored))
    files.update(emit_native(authored))
    return files


class SuccessorEnvironment:
    """Dispatch only an exact authored mode to its actual simulation."""

    def __new__(cls, spec: Mapping[str, Any], *, max_steps: int = 4096):
        if isinstance(spec, Mapping) and spec.get("gameplay_mode") == "top_down":
            from .game_successor_world import WorldSuccessorEnvironment

            return WorldSuccessorEnvironment(spec, max_steps=max_steps)
        return PlatformSuccessorEnvironment(spec, max_steps=max_steps)
