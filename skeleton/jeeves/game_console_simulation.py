"""Actual fixed-step simulation of an authored console-editor design scene.

This runs typed original scene rules, never console instructions or uploaded
source. Pixels, PCM and reward components are measured from those rules. The
canonical installed emulator remains a separate execution mode.
"""

from __future__ import annotations

import base64
import hashlib
import math
import random
import struct
import sys
from collections.abc import Mapping
from pathlib import Path

from .game_console_assets import decode_pcm_wav, decode_png, decode_tim, png_rgba
from .game_console_editor import (
    ConsoleEditorError,
    ConsoleProject,
    _digest,
    _int,
    _json,
)
from .game_learning_runtime import EpisodeStep, GameEnvironmentSpec

SIMULATION_SCHEMA = "skeleton.console_editor_simulation.v1"
_SNAPSHOT_SCHEMA = "skeleton.console_editor_simulation_snapshot.v1"
_ACTIONS = ("idle", "left", "right", "up", "down", "jump", "attack", "interact", "water", "plant", "fish")
_REWARDS = ("progress", "goal", "pickup", "farming", "fishing", "quest", "combat", "damage", "time")


def _overlap(a, b):
    return a[0] < b[0] + b[2] and a[0] + a[2] > b[0] and a[1] < b[1] + b[3] and a[1] + a[3] > b[1]


def _rgba(value):
    return bytes.fromhex(value[1:])


class EditorSimulationEnvironment:
    """Shared human/AI action adapter over exactly one committed project."""

    def __init__(self, project: ConsoleProject, max_steps: int = 512):
        if not isinstance(project, ConsoleProject):
            raise ConsoleEditorError(
                "editor_simulation_project", "A validated authored ConsoleProject is required"
            )
        self.project = ConsoleProject(project.as_dict(), project.export_files())
        self.document = self.project.as_dict()
        self.max_steps = _int(max_steps, 1, 4096, "design simulation steps")
        self._config = self.document["config"]
        self._layers = self.document["layers"]
        self._entities = self.document["entities"]
        self._entity_by = {row["id"]: row for row in self._entities}
        self._player_source = next(row for row in self._entities if row["kind"] == "player")
        self._world_width = max(row["offset"][0] + row["width"] * 8 for row in self._layers)
        self._world_height = max(row["offset"][1] + row["height"] * 8 for row in self._layers)
        if (
            self._world_width <= self._player_source["width"]
            or self._world_height <= self._player_source["height"]
        ):
            raise ConsoleEditorError("editor_simulation_world", "Authored world cannot contain its player")
        if (
            self._player_source["x"] + self._player_source["width"] > self._world_width
            or self._player_source["y"] + self._player_source["height"] > self._world_height
        ):
            raise ConsoleEditorError(
                "editor_simulation_spawn", "Player spawn lies outside the authored world"
            )
        self._palettes = {
            row["id"]: tuple(_rgba(color) for color in row["colors"]) for row in self.document["palettes"]
        }
        self._tiles = {row["id"]: row["tiles"] for row in self.document["tilesets"]}
        self._images = {}
        self._audio_assets = {}
        self._unrendered_assets = []
        for row in self.document["assets"]:
            data = base64.b64decode(row["data_base64"], validate=True)
            if row["kind"] == "audio" and row["codec"] == "pcm_wav":
                self._audio_assets[row["id"]] = decode_pcm_wav(data)
            if row["kind"] != "image":
                continue
            if row["codec"] == "rgba8888":
                self._images[row["id"]] = (row["metadata"]["width"], row["metadata"]["height"], data)
            elif row["codec"] == "png":
                self._images[row["id"]] = decode_png(data)
            elif row["codec"] == "ps1_tim":
                image = decode_tim(data)
                self._images[row["id"]] = (image.width, image.height, image.rgba_bytes())
            else:
                self._unrendered_assets.append(row["id"])
        code = {
            name: hashlib.sha256((Path(__file__).parent / name).read_bytes()).hexdigest()
            for name in ("game_console_simulation.py", "game_console_editor.py", "game_console_assets.py")
        }
        self._descriptor = {
            "schema_version": SIMULATION_SCHEMA,
            "runtime_kind": "design_scene_simulation",
            "execution_mode": "typed_original_2d_scene",
            "target_id": self.project.target_id,
            "project_digest": self.project.digest,
            "manifest_digest": self.project.manifest_digest,
            "source_manifest_digest": self.project.source_manifest_digest,
            "controller_bindings": dict(self.document["controls"]["bindings"]),
            "python": list(sys.version_info[:3]),
            "source_code_digest": _digest(code),
            "tick_hz": 60,
            "max_episode_steps": self.max_steps,
            "hardware_emulation": False,
            "commercial_compatibility_verified": False,
            "reward_scope": "Declared authored task utility, not game quality or hardware compatibility",
            "audio_scope": "Actual bounded synthesized original cues; no hardware APU emulation",
            "unrendered_assets": list(self._unrendered_assets),
        }
        bins = (-1.0, -0.5, -0.1, 0.0, 0.1, 0.25, 0.5, 0.75, 1.0)
        self.spec = GameEnvironmentSpec(
            "console-editor:" + self.project.target_id + ":" + self.project.digest[:24],
            _digest(self._descriptor),
            _ACTIONS,
            {
                key: bins
                for key in (
                    "x",
                    "y",
                    "vx",
                    "vy",
                    "goal_dx",
                    "goal_dy",
                    "health",
                    "grounded",
                    "day_phase",
                    "season",
                    "crop_maturity",
                    "crops",
                    "fish",
                    "quest_progress",
                )
            },
            _REWARDS,
            self.max_steps,
        )
        self._closed = False
        self._seed = None
        self._tick = 0
        self._actions = []
        self._audio = b""
        self._audio_total = 0
        self._last_events = []

    @property
    def descriptor(self):
        return {
            **self._descriptor,
            "environment_digest": self.spec.environment_digest,
            "spec": self.spec.as_dict(),
        }

    @property
    def done(self):
        return (
            self._closed
            or self._seed is not None
            and (
                self._health <= 0
                or self._tick >= self.max_steps
                or self._won
                and self._config.get("end_on_goal", False)
            )
        )

    def reset(self, seed: int = 0):
        self._seed = _int(seed, 0, 2**63 - 1, "design episode seed")
        self._rng = random.Random(seed)
        self._closed = False
        self._tick, self._actions, self._audio_total, self._audio, self._last_events = 0, [], 0, b"", []
        self._x, self._y = self._player_source["x"], self._player_source["y"]
        self._vx = self._vy = 0.0
        self._health = self._player_source["properties"]["health"]
        self._grounded, self._won = False, False
        self._score = 0
        self._money, self._crops, self._fish, self._seeds = 0, 0, 0, 3
        self._collected, self._completed = set(), set()
        self._enemy_health = {
            row["id"]: row["properties"]["health"] for row in self._entities if row["kind"] == "enemy"
        }
        self._crops_state = {
            row["id"]: {"planted": row["properties"]["planted"], "age_days": 0, "watered_day": -1}
            for row in self._entities
            if row["kind"] == "crop"
        }
        self._last_damage, self._last_fish, self._last_attack, self._last_interact = -60, -60, -30, -30
        self._dialogue = None
        self._chain = _digest(
            {"environment_digest": self.spec.environment_digest, "seed": seed, "state": self._state()}
        )
        return self._observation()

    def _player_rect(self):
        return (self._x, self._y, self._player_source["width"], self._player_source["height"])

    def _rect(self, row):
        x, y = row["x"], row["y"]
        if row["kind"] == "enemy":
            properties = row["properties"]
            radius = properties["patrol_range"]
            if radius and properties["speed"]:
                period = radius * 4 / properties["speed"]
                phase = (self._tick / 60) % period / period
                x += radius * (1 - 4 * abs(phase - 0.5))
                x = max(0, min(x, self._world_width - row["width"]))
        return x, y, row["width"], row["height"]

    def _near(self, row, distance=20):
        px, py, pw, ph = self._player_rect()
        x, y, width, height = self._rect(row)
        return (
            math.hypot(px + pw / 2 - x - width / 2, py + ph / 2 - y - height / 2)
            <= distance + max(width, height) / 2
        )

    def _collision(self, x, y, *, downward=False, previous_bottom=None):
        width, height = self._player_source["width"], self._player_source["height"]
        rect = (x, y, width, height)
        if x < 0 or y < 0 or x + width > self._world_width or y + height > self._world_height:
            return True
        for layer in self._layers:
            ox, oy = layer["offset"]
            left, right = math.floor((x - ox) / 8), math.floor((x + width - 1e-8 - ox) / 8)
            top, bottom = math.floor((y - oy) / 8), math.floor((y + height - 1e-8 - oy) / 8)
            for ty in range(max(0, top), min(layer["height"] - 1, bottom) + 1):
                for tx in range(max(0, left), min(layer["width"] - 1, right) + 1):
                    collision = layer["cells"][ty * layer["width"] + tx]["collision"]
                    if (
                        collision == "solid"
                        or collision == "one_way"
                        and downward
                        and previous_bottom is not None
                        and previous_bottom <= ty * 8 + oy + 0.01
                    ):
                        return True
        for row in self._entities:
            if (
                row["kind"] == "platform"
                and _overlap(rect, self._rect(row))
                and (
                    not row["properties"]["one_way"]
                    or downward
                    and previous_bottom is not None
                    and previous_bottom <= row["y"] + 0.01
                )
            ):
                return True
        return False

    def _move(self, dx, dy):
        pieces = max(1, math.ceil(max(abs(dx), abs(dy)) / 2))
        self._grounded = False
        for _ in range(pieces):
            if not self._collision(self._x + dx / pieces, self._y):
                self._x += dx / pieces
            else:
                self._vx = 0.0
            old_bottom = self._y + self._player_source["height"]
            if not self._collision(
                self._x, self._y + dy / pieces, downward=dy > 0, previous_bottom=old_bottom
            ):
                self._y += dy / pieces
            else:
                self._grounded = dy > 0
                self._vy = 0.0

    def _growth_days(self, row):
        return row["properties"]["growth_days"] or self._config["crop_growth_days"]

    def _fishing_probability(self, row):
        value = row["properties"]["fishing_probability"]
        return self._config["fishing_probability"] if value is None else value

    def _touched_cells(self):
        x, y, width, height = self._player_rect()
        result = set()
        for layer in self._layers:
            ox, oy = layer["offset"]
            for ty in range(
                max(0, math.floor((y - oy) / 8)),
                min(layer["height"] - 1, math.floor((y + height - 1e-8 - oy) / 8)) + 1,
            ):
                for tx in range(
                    max(0, math.floor((x - ox) / 8)),
                    min(layer["width"] - 1, math.floor((x + width - 1e-8 - ox) / 8)) + 1,
                ):
                    result.add(layer["cells"][ty * layer["width"] + tx]["collision"])
        return result

    def _goal_distance(self):
        goals = [row for row in self._entities if row["kind"] == "goal"]
        if not goals:
            return 0.0
        return min(math.hypot(row["x"] - self._x, row["y"] - self._y) for row in goals)

    def _day(self):
        return int(self._tick / (self._config["day_length_seconds"] * 60))

    def _state(self):
        return {
            "tick": self._tick,
            "position": [self._x, self._y],
            "velocity": [self._vx, self._vy],
            "health": self._health,
            "grounded": self._grounded,
            "won": self._won,
            "score": self._score,
            "inventory": {
                "money": self._money,
                "crops": self._crops,
                "fish": self._fish,
                "seeds": self._seeds,
            },
            "collected": sorted(self._collected),
            "completed_quests": sorted(self._completed),
            "enemy_health": dict(self._enemy_health),
            "crops": self._crops_state,
            "dialogue": self._dialogue,
            "day": self._day(),
            "season": self._day() // self._config["season_days"] % 4,
        }

    def _observation(self):
        goals = [row for row in self._entities if row["kind"] == "goal"]
        goal = (
            min(goals, key=lambda row: math.hypot(row["x"] - self._x, row["y"] - self._y))
            if goals
            else {"x": self._x, "y": self._y}
        )
        maturity = [
            min(1.0, state["age_days"] / self._growth_days(self._entity_by[key]))
            for key, state in self._crops_state.items()
            if state["planted"]
        ]
        quests = sum(
            row["kind"] == "npc" and row["properties"]["quest_type"] != "none" for row in self._entities
        )
        speed = max(1, self._config["speed"])
        return {
            "x": self._x / self._world_width,
            "y": self._y / self._world_height,
            "vx": max(-1.0, min(1.0, self._vx / speed)),
            "vy": max(-1.0, min(1.0, self._vy / max(speed, self._config["jump_speed"]))),
            "goal_dx": (goal["x"] - self._x) / self._world_width,
            "goal_dy": (goal["y"] - self._y) / self._world_height,
            "health": self._health / self._player_source["properties"]["health"],
            "grounded": float(self._grounded),
            "day_phase": self._tick
            % (self._config["day_length_seconds"] * 60)
            / (self._config["day_length_seconds"] * 60),
            "season": self._day() // self._config["season_days"] % 4 / 3,
            "crop_maturity": max(maturity, default=0.0),
            "crops": min(1.0, self._crops / 100),
            "fish": min(1.0, self._fish / 100),
            "quest_progress": len(self._completed) / max(1, quests),
        }

    def step(self, action: str):
        if self._seed is None or self.done:
            raise ConsoleEditorError(
                "editor_simulation_inactive", "Reset an active design scene before stepping"
            )
        if not isinstance(action, str) or action not in _ACTIONS:
            raise ConsoleEditorError(
                "editor_simulation_action", "Action is outside the exact declared action set"
            )
        previous_distance, previous_day, previous = self._goal_distance(), self._day(), self._chain
        config, speed = self._config, self._config["speed"]
        self._vx = -speed if action == "left" else speed if action == "right" else 0.0
        if config["movement_mode"] == "top_down":
            self._vy = -speed if action == "up" else speed if action == "down" else 0.0
        else:
            if action == "jump" and self._grounded:
                self._vy = -config["jump_speed"]
            self._vy = min(2000.0, self._vy + config["gravity"] / 60)
        self._move(self._vx / 60, self._vy / 60)
        self._tick += 1
        rewards = {key: 0.0 for key in _REWARDS}
        rewards["time"] = -0.001
        rewards["progress"] = (previous_distance - self._goal_distance()) / max(
            self._world_width, self._world_height
        )
        events = []
        if self._day() > previous_day:
            for identity, state in self._crops_state.items():
                row = self._entity_by[identity]
                if state["planted"] and (
                    not row["properties"]["requires_water"] or state["watered_day"] == previous_day
                ):
                    state["age_days"] += 1
        for row in self._entities:
            kind, properties, identity = row["kind"], row["properties"], row["id"]
            overlapping = _overlap(self._player_rect(), self._rect(row))
            if kind == "goal" and overlapping and not self._won:
                self._won = True
                self._score += properties["points"]
                rewards["goal"] += 1.0
                events.append("goal")
            elif kind == "pickup" and overlapping and identity not in self._collected:
                self._collected.add(identity)
                value = properties["value"]
                if properties["item"] == "health":
                    self._health = min(self._player_source["properties"]["health"], self._health + value)
                elif properties["item"] == "seed":
                    self._seeds += value
                else:
                    self._money += value
                self._score += value
                rewards["pickup"] += value * 0.02
                events.append("pickup")
            elif kind in {"hazard", "enemy"} and overlapping and self._tick - self._last_damage >= 30:
                if kind == "enemy" and self._enemy_health[identity] <= 0:
                    continue
                lost = min(self._health, properties["damage"])
                self._health -= lost
                self._last_damage = self._tick
                rewards["damage"] -= lost * 0.1
                events.append("damage")
            if (
                kind == "enemy"
                and action == "attack"
                and self._tick - self._last_attack >= 15
                and self._near(row, config["attack_range"])
                and self._enemy_health[identity] > 0
            ):
                self._enemy_health[identity] = max(0, self._enemy_health[identity] - config["attack_damage"])
                self._last_attack = self._tick
                events.append("attack")
                if self._enemy_health[identity] == 0:
                    self._score += 1
                    rewards["combat"] += 0.1
            if kind == "crop" and self._near(row):
                state = self._crops_state[identity]
                if action == "water" and state["planted"] and state["watered_day"] != self._day():
                    state["watered_day"] = self._day()
                    events.append("water")
                elif action == "plant" and not state["planted"] and self._seeds > 0:
                    self._seeds -= 1
                    state.update(planted=True, age_days=0, watered_day=-1)
                    events.append("plant")
                elif (
                    action == "interact" and state["planted"] and state["age_days"] >= self._growth_days(row)
                ):
                    state.update(planted=False, age_days=0, watered_day=-1)
                    self._crops += properties["yield"]
                    self._score += properties["yield"]
                    rewards["farming"] += properties["yield"] * 0.1
                    events.append("harvest")
            if (
                kind == "water"
                and action == "fish"
                and self._near(row)
                and self._tick - self._last_fish >= 30
            ):
                self._last_fish = self._tick
                if self._rng.random() < self._fishing_probability(row):
                    self._fish += properties["fish_value"]
                    self._score += properties["fish_value"]
                    rewards["fishing"] += properties["fish_value"] * 0.1
                    events.append("fish")
            if (
                kind == "npc"
                and action == "interact"
                and self._near(row)
                and self._tick - self._last_interact >= 15
            ):
                self._last_interact = self._tick
                self._dialogue = {
                    "npc_id": identity,
                    "text": properties["dialogue"],
                    "quest_type": properties["quest_type"],
                    "required_count": properties["required_count"],
                    "completed": identity in self._completed,
                }
                quest, count = properties["quest_type"], properties["required_count"]
                complete = (
                    quest == "deliver_crop"
                    and self._crops >= count
                    or quest == "catch_fish"
                    and self._fish >= count
                    or quest == "visit_goal"
                    and self._won
                )
                if complete and identity not in self._completed:
                    if quest == "deliver_crop":
                        self._crops -= count
                    if quest == "catch_fish":
                        self._fish -= count
                    self._completed.add(identity)
                    self._money += properties["reward"]
                    self._score += properties["reward"]
                    rewards["quest"] += properties["reward"] * 0.02
                    events.append("quest")
            if kind == "portal" and action == "interact" and overlapping:
                x, y = properties["destination_x"], properties["destination_y"]
                if not self._collision(x, y):
                    self._x, self._y = x, y
        cells = self._touched_cells()
        if "hazard" in cells and self._tick - self._last_damage >= 30:
            lost = min(1, self._health)
            self._health -= lost
            self._last_damage = self._tick
            rewards["damage"] -= lost * 0.1
            events.append("damage")
        if "goal" in cells and not self._won:
            self._won = True
            self._score += 10
            rewards["goal"] += 1.0
            events.append("goal")
        if "water" in cells and action == "fish" and self._tick - self._last_fish >= 30:
            self._last_fish = self._tick
            if self._rng.random() < config["fishing_probability"]:
                self._fish += 1
                self._score += 1
                rewards["fishing"] += 0.1
                events.append("fish")
        self._last_events = events[:64]
        self._audio = self._synthesize(events)
        self._audio_total += len(self._audio) // 2
        self._actions.append(action)
        observation = self._observation()
        state = self._state()
        evidence = {
            "environment_digest": self.spec.environment_digest,
            "tick": self._tick,
            "action": action,
            "observation": observation,
            "reward_components": rewards,
            "state_digest": _digest(state),
            "events": self._last_events,
            "previous_transition_digest": previous,
        }
        self._chain = _digest(evidence)
        return EpisodeStep(
            observation,
            rewards,
            self._health <= 0 or self._won and config.get("end_on_goal", False),
            self._tick >= self.max_steps,
            {
                "runtime_kind": "design_scene_simulation",
                "won": self._won,
                "state_digest": evidence["state_digest"],
                "events": self._last_events,
                "day": state["day"],
                "season": state["season"],
                "inventory": state["inventory"],
                "hardware_emulation": False,
            },
            self._chain,
        )

    def _synthesize(self, events):
        cues = [cue for cue in self.document["audio"]["cues"] if cue["event"] in events][:8]
        if not cues:
            return b""
        rate, maximum = 22050, 16384
        count = min(maximum, max(round(cue["duration"] * rate) for cue in cues))
        samples = [0.0] * count
        for cue in cues:
            noise = random.Random(_digest([self._seed, self._tick, cue["id"]]))
            length = min(count, round(cue["duration"] * rate))
            for index in range(length):
                time = index / rate
                phase = time * cue["frequency"] % 1
                source = self._audio_assets.get(cue.get("asset_id"))
                if source:
                    position = int(index * source["sample_rate"] / rate)
                    if position >= source["sample_frames"]:
                        continue
                    values = []
                    for channel in range(source["channels"]):
                        at = (position * source["channels"] + channel) * source["sample_width"]
                        values.append(
                            (source["pcm"][at] - 128) / 128
                            if source["sample_width"] == 1
                            else struct.unpack_from("<h", source["pcm"], at)[0] / 32768
                        )
                    wave = sum(values) / len(values)
                else:
                    wave = (
                        math.sin(2 * math.pi * phase)
                        if cue["waveform"] == "sine"
                        else (
                            (1 if phase < 0.5 else -1)
                            if cue["waveform"] == "square"
                            else (
                                1 - 4 * abs(phase - 0.5)
                                if cue["waveform"] == "triangle"
                                else noise.uniform(-1, 1)
                            )
                        )
                    )
                envelope = min(1.0, time / cue["attack"]) if cue["attack"] else 1.0
                if cue["release"]:
                    envelope *= min(1.0, max(0.0, (cue["duration"] - time) / cue["release"]))
                samples[index] += wave * envelope * cue["gain"]
        return b"".join(struct.pack("<h", round(max(-1.0, min(1.0, value)) * 32767)) for value in samples)

    def preview(self):
        if self._seed is None or self._closed:
            return None
        viewport = self.document["viewport"]
        ratio = min(1.0, 320 / viewport["width"], 320 / viewport["height"])
        width, height = max(1, int(viewport["width"] * ratio)), max(1, int(viewport["height"] * ratio))
        camera_x = (
            max(0.0, min(self._x - viewport["width"] / 2, self._world_width - viewport["width"]))
            if self._config["camera_follow"]
            else 0.0
        )
        camera_y = (
            max(0.0, min(self._y - viewport["height"] / 2, self._world_height - viewport["height"]))
            if self._config["camera_follow"]
            else 0.0
        )
        background = _rgba(self._config["background_color"])
        pixels = bytearray(background * (width * height))
        layers = sorted(
            (row for row in self._layers if row["visible"]), key=lambda row: (row["z"], row["id"])
        )

        def blend(offset, color):
            alpha = color[3]
            if alpha == 255:
                pixels[offset : offset + 4] = color
            elif alpha:
                for channel in range(3):
                    pixels[offset + channel] = (
                        color[channel] * alpha + pixels[offset + channel] * (255 - alpha)
                    ) // 255
                pixels[offset + 3] = 255

        def paint_layer(layer):
            for py in range(height):
                world_y = camera_y + py / ratio
                for px in range(width):
                    world_x = camera_x + px / ratio
                    offset = (py * width + px) * 4
                    local_x, local_y = world_x - layer["offset"][0], world_y - layer["offset"][1]
                    tx, ty = math.floor(local_x / 8), math.floor(local_y / 8)
                    if not 0 <= tx < layer["width"] or not 0 <= ty < layer["height"]:
                        continue
                    cell = layer["cells"][ty * layer["width"] + tx]
                    ix, iy = int(local_x % 8), int(local_y % 8)
                    if cell["flip_x"]:
                        ix = 7 - ix
                    if cell["flip_y"]:
                        iy = 7 - iy
                    value = self._tiles[cell["tileset_id"]][cell["tile"]][iy * 8 + ix]
                    blend(offset, self._palettes[cell["palette_id"]][value])

        painted = 0
        for row in sorted(
            self._entities,
            key=lambda row: (
                next(layer["z"] for layer in self._layers if layer["id"] == row["layer_id"]),
                row["id"],
            ),
        ):
            depth = next(layer["z"] for layer in self._layers if layer["id"] == row["layer_id"])
            while painted < len(layers) and layers[painted]["z"] <= depth:
                paint_layer(layers[painted])
                painted += 1
            if row["id"] in self._collected or row["kind"] == "enemy" and self._enemy_health[row["id"]] <= 0:
                continue
            rect = self._player_rect() if row["kind"] == "player" else self._rect(row)
            x, y, rw, rh = rect
            color = _rgba(row["properties"]["color"])
            if row["kind"] == "crop":
                crop = self._crops_state[row["id"]]
                if not crop["planted"]:
                    color = bytes((100, 64, 32, 255))
                elif crop["age_days"] >= self._growth_days(row):
                    color = bytes((240, 210, 70, 255))
            texture = self._images.get(row["asset_id"])
            for py in range(
                max(0, int((y - camera_y) * ratio)), min(height, math.ceil((y + rh - camera_y) * ratio))
            ):
                for px in range(
                    max(0, int((x - camera_x) * ratio)), min(width, math.ceil((x + rw - camera_x) * ratio))
                ):
                    actual = color
                    if texture:
                        tw, th, raw = texture
                        sx = min(tw - 1, max(0, int((camera_x + px / ratio - x) / rw * tw)))
                        sy = min(th - 1, max(0, int((camera_y + py / ratio - y) / rh * th)))
                        source = (sy * tw + sx) * 4
                        actual = raw[source : source + 4]
                    blend((py * width + px) * 4, actual)
        while painted < len(layers):
            paint_layer(layers[painted])
            painted += 1
        image = png_rgba(bytes(pixels), width, height)
        return {
            "runtime_kind": "design_scene_simulation",
            "render_kind": "actual_authored_scene_raster",
            "width": width,
            "height": height,
            "data_uri": "data:image/png;base64," + base64.b64encode(image).decode(),
            "pixel_digest": hashlib.sha256(pixels).hexdigest(),
            "raster": {
                "format": "rgba32",
                "width": width,
                "height": height,
                "source_viewport_width": viewport["width"],
                "source_viewport_height": viewport["height"],
                "scaling_method": "nearest_neighbor" if ratio < 1 else "identity",
                "png_digest": hashlib.sha256(image).hexdigest(),
            },
            "tick": self._tick,
            "camera": [camera_x, camera_y],
            "state_digest": _digest(self._state()),
            "day": self._day(),
            "season": self._day() // self._config["season_days"] % 4,
            "inventory": self._state()["inventory"],
            "events": self._last_events,
            "dialogue": self._dialogue,
            "controller_bindings": dict(self.document["controls"]["bindings"]),
            "audio": {
                "format": "s16le",
                "channels": 1,
                "sample_rate": 22050,
                "scope": "actual_original_synthesized_or_imported_PCM_cues",
                "voice_limit": 8,
                "sample_capacity": 16384,
                "samples_base64": base64.b64encode(self._audio).decode(),
                "sample_frames": len(self._audio) // 2,
                "total_sample_frames": self._audio_total,
                "sample_start_frame": self._audio_total - len(self._audio) // 2,
                "sample_digest": hashlib.sha256(self._audio).hexdigest(),
                "stream_id": _digest([self.spec.environment_digest, self._seed]),
            },
            "hardware_emulation": False,
        }

    def current_observation(self):
        if self._seed is None:
            raise ConsoleEditorError(
                "editor_simulation_inactive", "Reset before reading actual scene observation"
            )
        return self._observation()

    def snapshot(self):
        if self._seed is None:
            raise ConsoleEditorError("editor_simulation_inactive", "Reset before snapshotting a scene")
        payload = {
            "schema_version": _SNAPSHOT_SCHEMA,
            "environment_digest": self.spec.environment_digest,
            "seed": self._seed,
            "actions": list(self._actions),
            "state_digest": _digest(self._state()),
            "transition_digest": self._chain,
            "audio_total": self._audio_total,
        }
        return {**payload, "snapshot_digest": _digest(payload)}

    def restore(self, snapshot: Mapping):
        if (
            not isinstance(snapshot, Mapping)
            or set(snapshot)
            != {
                "schema_version",
                "environment_digest",
                "seed",
                "actions",
                "state_digest",
                "transition_digest",
                "audio_total",
                "snapshot_digest",
            }
            or snapshot["schema_version"] != _SNAPSHOT_SCHEMA
            or snapshot["environment_digest"] != self.spec.environment_digest
        ):
            raise ConsoleEditorError(
                "editor_snapshot_foreign", "Snapshot belongs to another exact authored scene"
            )
        _json(snapshot, 1024 * 1024)
        actions = snapshot["actions"]
        if (
            not isinstance(actions, list)
            or len(actions) > self.max_steps
            or any(not isinstance(action, str) or action not in _ACTIONS for action in actions)
        ):
            raise ConsoleEditorError(
                "editor_snapshot_actions", "Snapshot action history exceeds declared bounds"
            )
        payload = {key: value for key, value in snapshot.items() if key != "snapshot_digest"}
        if _digest(payload) != snapshot["snapshot_digest"]:
            raise ConsoleEditorError("editor_snapshot_corrupt", "Snapshot canonical checksum differs")
        replay = EditorSimulationEnvironment(self.project, max_steps=self.max_steps)
        replay.reset(snapshot["seed"])
        for action in actions:
            replay.step(action)
        if (
            _digest(replay._state()) != snapshot["state_digest"]
            or replay._chain != snapshot["transition_digest"]
            or replay._audio_total != snapshot["audio_total"]
        ):
            raise ConsoleEditorError(
                "editor_snapshot_corrupt", "Replay does not reproduce the measured scene state"
            )
        self.__dict__.update(replay.__dict__)
        return self._observation()

    def close(self):
        self._closed = True
