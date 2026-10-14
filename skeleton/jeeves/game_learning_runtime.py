"""Bounded policy-learning adapters over the real coded Jeeves era engines.

Rewards below are declared task utilities computed from actual machine state.
They are not claims of hardware compatibility, game quality or model mastery.
Restoration re-executes the recorded actions instead of importing arbitrary
caller-provided native state. Uploaded Python is never executed here.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
import random
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from enum import Enum
from itertools import pairwise
from pathlib import Path
from types import MappingProxyType

from .game_console_catalog import ConsoleTarget, resolve_console
from .game_engine_lab import EngineEra, GameEngineLabError, VirtualFileTree
from .game_engine_legacy import InputButton, InputFrame
from .game_engine_runtime import ExecutableGameEngineLab, RoutedEngineSandbox

RUNTIME_SCHEMA = "skeleton.game_learning_runtime.v1"
SNAPSHOT_SCHEMA = "skeleton.game_learning_environment_snapshot.v1"
MAX_EPISODE_STEPS = 4096
MAX_SNAPSHOT_BYTES = 2_000_000
MAX_REPORT_BYTES = 4_000_000
MAX_FRAME_BYTES = 262_144
MAX_RENDER_ROWS = 128
_FEATURES = ("x", "z", "vx", "vz", "goal_dx", "goal_dz", "heading", "grounded", "progress", "score", "alive")
_REWARDS = ("progress", "score", "alignment", "goal", "time")
_BUTTONS = {
    "noop": InputButton.NONE,
    "up": InputButton.UP,
    "down": InputButton.DOWN,
    "left": InputButton.LEFT,
    "right": InputButton.RIGHT,
    "fire": InputButton.FIRE,
    "jump": InputButton.A,
    "right_jump": InputButton.RIGHT | InputButton.A,
    "left_jump": InputButton.LEFT | InputButton.A,
    "up_left": InputButton.UP | InputButton.LEFT,
    "up_right": InputButton.UP | InputButton.RIGHT,
    "up_fire": InputButton.UP | InputButton.FIRE,
}


def _int(value: object, name: str, lower: int, upper: int) -> int:
    if type(value) is not int or not lower <= value <= upper:
        raise GameEngineLabError(f"{name} must be an integer in [{lower}, {upper}]")
    return value


def _finite(value: object, name: str) -> float:
    if type(value) not in (int, float) or abs(value) > 1e12 or not math.isfinite(value):
        raise GameEngineLabError(f"{name} must be a bounded finite number")
    return float(value)


def _utf8_size(value: str) -> int:
    try:
        return len(value.encode("utf-8"))
    except UnicodeEncodeError as exc:
        raise GameEngineLabError("runtime text must be valid UTF-8") from exc


def _json_value(
    value: object,
    *,
    depth: int = 0,
    nodes: list[int] | None = None,
    budget: list[int] | None = None,
) -> object:
    if nodes is None:
        nodes = [0]
    if budget is None:
        budget = [MAX_REPORT_BYTES]
    nodes[0] += 1
    budget[0] -= 2
    if depth > 20 or nodes[0] > 500_000:
        raise GameEngineLabError("runtime JSON exceeds structural bounds")
    if budget[0] < 0:
        raise GameEngineLabError("runtime JSON exceeds byte capacity")
    if value is None or type(value) is bool:
        budget[0] -= 5
        return value
    if isinstance(value, Enum):
        return _json_value(value.value, depth=depth + 1, nodes=nodes, budget=budget)
    if isinstance(value, str):
        if _utf8_size(value) > 128_000:
            raise GameEngineLabError("runtime text exceeds bounded capacity")
        budget[0] -= len(json.dumps(value, ensure_ascii=True))
        if budget[0] < 0:
            raise GameEngineLabError("runtime JSON exceeds byte capacity")
        return value
    if type(value) is int:
        if abs(value) > 2**63 - 1:
            raise GameEngineLabError("runtime JSON integer exceeds 64-bit capacity")
        budget[0] -= len(str(value))
        return value
    if type(value) is float:
        _finite(value, "runtime JSON number")
        budget[0] -= 25
        return value
    if isinstance(value, Mapping):
        if len(value) > 4096 or any(not isinstance(key, str) for key in value):
            raise GameEngineLabError("runtime JSON object is invalid")
        result = {}
        for key, item in value.items():
            if _utf8_size(key) > 128_000:
                raise GameEngineLabError("runtime JSON key exceeds byte capacity")
            budget[0] -= len(json.dumps(key, ensure_ascii=True)) + 1
            result[key] = _json_value(item, depth=depth + 1, nodes=nodes, budget=budget)
        return result
    if isinstance(value, (list, tuple)):
        if len(value) > MAX_EPISODE_STEPS:
            raise GameEngineLabError("runtime JSON sequence exceeds capacity")
        return [_json_value(item, depth=depth + 1, nodes=nodes, budget=budget) for item in value]
    raise GameEngineLabError("runtime values must be deterministic JSON data")


def _encoded(value: object, maximum: int = MAX_REPORT_BYTES) -> bytes:
    raw = json.dumps(
        _json_value(value, budget=[maximum]),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    if len(raw) > maximum:
        raise GameEngineLabError("runtime evidence exceeds byte capacity")
    return raw


def _digest(value: object) -> str:
    return hashlib.sha256(_encoded(value)).hexdigest()


def _project_json(content: str) -> object:
    def pairs(values: list[tuple[str, object]]) -> dict[str, object]:
        result = {}
        for key, value in values:
            if key in result:
                raise GameEngineLabError("project JSON contains duplicate object keys")
            result[key] = value
        return result

    def constant(value: str) -> object:
        raise GameEngineLabError(f"project JSON contains nonfinite constant {value}")

    try:
        value = json.loads(content, object_pairs_hook=pairs, parse_constant=constant)
    except (json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise GameEngineLabError("project JSON is invalid or exceeds nesting bounds") from exc
    return _json_value(value)


def _project_tree(
    tree: VirtualFileTree | Mapping[str, str],
    target: ConsoleTarget,
    gameplay_dialect: str | None,
) -> VirtualFileTree:
    if not isinstance(tree, (VirtualFileTree, Mapping)):
        raise GameEngineLabError("project must be a bounded virtual file tree")
    files = tree.files if isinstance(tree, VirtualFileTree) else tree
    if len(files) > 96:
        raise GameEngineLabError("project exceeds file-count capacity")
    supplied = VirtualFileTree(files)
    for path, content in supplied.files.items():
        if path.endswith(".json"):
            _project_json(content)
    manifest = _project_json(supplied.read("engine/manifest.json"))
    if not isinstance(manifest, dict) or manifest.get("engine_era") != target.era.value:
        raise GameEngineLabError("project engine identity differs from selected target")
    if manifest.get("gameplay_dialect") != gameplay_dialect:
        raise GameEngineLabError("project gameplay dialect differs from request")
    return supplied


def _freeze(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (tuple, list)):
        return tuple(_freeze(item) for item in value)
    return value


def _numeric_mapping(value: Mapping[str, float], name: str) -> Mapping[str, float]:
    if not isinstance(value, Mapping) or not 1 <= len(value) <= 64:
        raise GameEngineLabError(f"{name} must be a bounded numeric mapping")
    clean = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key or len(key) > 128:
            raise GameEngineLabError(f"{name} has invalid feature identity")
        clean[key] = _finite(item, f"{name}.{key}")
    return MappingProxyType(clean)


@dataclass(frozen=True, slots=True)
class GameEnvironmentSpec:
    environment_id: str
    environment_digest: str
    actions: tuple[str, ...]
    observation_bins: Mapping[str, tuple[float, ...]]
    reward_components: tuple[str, ...]
    max_episode_steps: int

    def __post_init__(self) -> None:
        if not isinstance(self.environment_id, str) or not 1 <= len(self.environment_id) <= 256:
            raise GameEngineLabError("environment identity is invalid")
        if (
            not isinstance(self.environment_digest, str)
            or len(self.environment_digest) != 64
            or any(c not in "0123456789abcdef" for c in self.environment_digest)
        ):
            raise GameEngineLabError("environment digest is invalid")
        if (
            not isinstance(self.actions, (tuple, list))
            or not 1 <= len(self.actions) <= 32
            or len(set(self.actions)) != len(self.actions)
        ):
            raise GameEngineLabError("environment actions must be bounded and unique")
        if any(not isinstance(action, str) or not action or len(action) > 64 for action in self.actions):
            raise GameEngineLabError("environment action identity is invalid")
        if not isinstance(self.observation_bins, Mapping) or not 1 <= len(self.observation_bins) <= 32:
            raise GameEngineLabError("environment observation bins are invalid")
        bins = {}
        for key, values in self.observation_bins.items():
            if (
                not isinstance(key, str)
                or not key
                or len(key) > 64
                or not isinstance(values, (tuple, list))
                or not 1 <= len(values) <= 64
            ):
                raise GameEngineLabError("environment bin identity or capacity is invalid")
            clean = tuple(_finite(value, "observation bin") for value in values)
            if any(left >= right for left, right in pairwise(clean)):
                raise GameEngineLabError("observation bins must increase strictly")
            bins[key] = clean
        if (
            not isinstance(self.reward_components, (tuple, list))
            or not 1 <= len(self.reward_components) <= 32
            or len(set(self.reward_components)) != len(self.reward_components)
            or any(not isinstance(key, str) or not key or len(key) > 64 for key in self.reward_components)
        ):
            raise GameEngineLabError("environment reward components are invalid")
        _int(self.max_episode_steps, "max episode steps", 1, MAX_EPISODE_STEPS)
        object.__setattr__(self, "actions", tuple(self.actions))
        object.__setattr__(self, "reward_components", tuple(self.reward_components))
        object.__setattr__(self, "observation_bins", MappingProxyType(bins))

    def as_dict(self) -> dict[str, object]:
        return {
            "environment_id": self.environment_id,
            "environment_digest": self.environment_digest,
            "actions": list(self.actions),
            "observation_bins": {key: list(value) for key, value in self.observation_bins.items()},
            "reward_components": list(self.reward_components),
            "max_episode_steps": self.max_episode_steps,
        }


@dataclass(frozen=True, slots=True)
class EpisodeStep:
    observation: Mapping[str, float]
    reward_components: Mapping[str, float]
    terminated: bool
    truncated: bool = False
    info: Mapping[str, object] = field(default_factory=dict)
    transition_digest: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "observation", _numeric_mapping(self.observation, "observation"))
        object.__setattr__(self, "reward_components", _numeric_mapping(self.reward_components, "reward"))
        if (
            type(self.terminated) is not bool
            or type(self.truncated) is not bool
            or self.terminated
            and self.truncated
        ):
            raise GameEngineLabError("episode termination flags are invalid")
        if not isinstance(self.info, Mapping):
            raise GameEngineLabError("episode info must be bounded JSON")
        _encoded(self.info, MAX_FRAME_BYTES)
        object.__setattr__(self, "info", _freeze(self.info))
        if (
            not isinstance(self.transition_digest, str)
            or self.transition_digest
            and (
                len(self.transition_digest) != 64
                or any(c not in "0123456789abcdef" for c in self.transition_digest)
            )
        ):
            raise GameEngineLabError("transition digest is invalid")

    @property
    def reward(self) -> float:
        return math.fsum(self.reward_components.values())

    def as_dict(self) -> dict[str, object]:
        return {
            "observation": dict(self.observation),
            "reward_components": dict(self.reward_components),
            "reward": self.reward,
            "terminated": self.terminated,
            "truncated": self.truncated,
            "info": _json_value(self.info),
            "transition_digest": self.transition_digest,
        }


def _actions(era: EngineEra) -> tuple[str, ...]:
    if era is EngineEra.PONG:
        return ("noop", "up", "down")
    if era is EngineEra.ARCADE:
        return ("noop", "left", "right", "up", "fire", "up_left", "up_right", "up_fire")
    if era in (EngineEra.EIGHT_BIT, EngineEra.SIXTEEN_BIT):
        return ("noop", "left", "right", "jump", "left_jump", "right_jump")
    return ("noop", "up", "down", "left", "right", "up_left", "up_right")


def _source_digest() -> str:
    """Fence replay against changed local adapter or existing engine sources."""
    root = Path(__file__).parent
    paths = sorted(root.glob("game_engine_*.py")) + [root / "game_console_catalog.py", Path(__file__)]
    if len(paths) > 64:
        raise GameEngineLabError("engine source inventory exceeds capacity")
    rows = []
    total = 0
    for path in paths:
        size = path.stat().st_size
        total += size
        if size > 512_000 or total > 8_000_000:
            raise GameEngineLabError("engine source exceeds fingerprint capacity")
        rows.append((path.name, hashlib.sha256(path.read_bytes()).hexdigest()))
    return _digest(rows)


def _frame_projection(frame: object) -> dict[str, object]:
    raw = _json_value(asdict(frame))
    _encoded(raw, MAX_FRAME_BYTES)
    result = dict(raw)
    counts = {}
    for key in ("draw_commands", "audio_events", "commands", "instances", "loaded_cells"):
        values = result.get(key)
        if isinstance(values, list):
            counts[key] = len(values)
            result[key] = values[:MAX_RENDER_ROWS]
    result["complete_frame_digest"] = _digest(raw)
    result["row_counts"] = counts
    result["projection_truncated"] = any(count > MAX_RENDER_ROWS for count in counts.values())
    result["render_kind"] = "reference_commands"
    return result


class GameLearningEnvironment:
    """Single bounded episode over one existing reference-machine family."""

    def __init__(
        self,
        target_id: str | EngineEra,
        *,
        max_steps: int = 512,
        gameplay_dialect: str | None = None,
        tree: VirtualFileTree | Mapping[str, str] | None = None,
    ) -> None:
        self.target: ConsoleTarget = resolve_console(target_id)
        if self.target.native_target_id is not None:
            raise GameEngineLabError(
                "native source target requires an actual generated-map config or independent compiled execution bridge; choose its explicit reference_target_id for reference simulation"
            )
        if self.target.requires_rom:
            raise GameEngineLabError(
                "ROM target requires the explicit compatible ROM adapter; reference simulation cannot execute cartridges"
            )
        self.max_steps = _int(max_steps, "max episode steps", 1, MAX_EPISODE_STEPS)
        if gameplay_dialect is not None and (
            not isinstance(gameplay_dialect, str) or not 1 <= len(gameplay_dialect) <= 64
        ):
            raise GameEngineLabError("gameplay dialect must be a bounded identifier")
        self.gameplay_dialect = gameplay_dialect
        sandbox = ExecutableGameEngineLab().create(self.target.era, gameplay_dialect)
        if tree is not None:
            supplied = _project_tree(tree, self.target, gameplay_dialect)
            sandbox = sandbox.with_tree(supplied)
        self.sandbox: RoutedEngineSandbox = sandbox
        self.tree = sandbox.tree
        self.actions = _actions(self.target.era)
        self._source = _source_digest()
        self._descriptor = {
            "schema_version": RUNTIME_SCHEMA,
            "target_id": self.target.target_id,
            "engine_era": self.target.era.value,
            "family": self.target.family.value,
            "runtime_kind": "reference_game_simulation",
            "tree_digest": self.tree.digest,
            "source_digest": self._source,
            "gameplay_dialect": gameplay_dialect,
            "max_episode_steps": self.max_steps,
            "actions": list(self.actions),
            "observation_schema": "normalized_actual_state_goal_v1",
            "reward_schema": "state_potential_score_alignment_goal_time_v1",
            "reset_schema": "seeded_real_input_warmup_and_goal_v1",
            "reward_definitions": {
                "progress": "normalized previous distance minus next distance",
                "score": "actual Pong left score minus right score delta; otherwise zero",
                "alignment": "Pong paddle-to-ball alignment improvement scaled by 0.1; otherwise zero",
                "goal": "one on first observed goal/point; otherwise zero",
                "time": "declared step cost -0.001",
            },
            "observation_limitations": {
                "alive": "episode remains active; reference machines have no universal character-health model",
                "score": "actual Pong score difference; zero for reference machines without scoring",
                "vx_vz": "native velocity when available, otherwise measured per-step position displacement",
            },
            "rom_execution": False,
            "full_hardware_emulation": False,
            "project_execution_scope": "Existing bounded native tuning and adaptive-policy files are compiled; uploaded Python and arbitrary scenes are not executed",
        }
        bins = {key: (-0.75, -0.5, -0.25, -0.1, 0.0, 0.1, 0.25, 0.5, 0.75) for key in _FEATURES}
        self.spec = GameEnvironmentSpec(
            self.target.target_id, _digest(self._descriptor), self.actions, bins, _REWARDS, self.max_steps
        )
        self._machine = None
        self._seed = None
        self._actions_taken: list[str] = []
        self._last_frame: dict[str, object] | None = None
        self._observation: Mapping[str, float] | None = None
        self._goal = (0.0, 0.0)
        self._initial_distance = 1.0
        self._terminated = False
        self._truncated = False
        self._chain = ""

    @property
    def descriptor(self) -> dict[str, object]:
        return {
            **_json_value(self._descriptor),
            "environment_digest": self.spec.environment_digest,
            "spec": self.spec.as_dict(),
        }

    @property
    def done(self) -> bool:
        return self._terminated or self._truncated

    def preview(self) -> dict[str, object] | None:
        """Last actual commands, with measured RGB pixels for the 3D family."""
        if self._last_frame is None:
            return None
        result = _json_value(self._last_frame)
        spec = self._machine.spec
        if hasattr(spec, "width") and hasattr(spec, "height"):
            result["source_viewport"] = {"width": spec.width, "height": spec.height}
            result["width"], result["height"] = spec.width, spec.height
        if hasattr(self._machine, "reference_image"):
            image = self._machine.reference_image(width=96)
            result.update(
                {
                    "render_kind": "reference_raster",
                    "width": image.frame.width,
                    "height": image.frame.height,
                    "format": "rgb24",
                    "pixels_base64": base64.b64encode(image.pixels).decode("ascii"),
                    "pixel_digest": image.frame.color_digest,
                    "raster_digest": image.frame.digest,
                    "raster_stats": _json_value(asdict(image.frame.stats)),
                    "raster_native_state_digest": self._machine.fingerprint(),
                    "hardware_emulation": False,
                }
            )
        return result

    def observe(self) -> dict[str, object]:
        """Read the current native state and its exact learning projection."""
        state = self._state()
        return {
            "environment_digest": self.spec.environment_digest,
            "episode_step": len(self._actions_taken),
            "native_tick": self._machine.tick,
            "native_state": _json_value(state),
            "native_state_digest": self._machine.fingerprint(),
            "observation": dict(self._observation),
            "transition_digest": self._chain,
            "terminated": self._terminated,
            "truncated": self._truncated,
        }

    def _state(self) -> dict[str, object]:
        if self._machine is None:
            raise GameEngineLabError("reset the environment before observing or stepping")
        return dict(self._machine.snapshot().state)

    def _position(self, state: Mapping[str, object]) -> tuple[float, float, float, float, float, float]:
        era = self.target.era
        if era is EngineEra.PONG:
            return (
                float(state["ball_x"]),
                float(state["left_y"]),
                float(state["ball_vx"]),
                float(state["ball_vy"]),
                256.0,
                224.0,
            )
        if era is EngineEra.ARCADE:
            return (
                float(state["ship_x"]),
                float(state["ship_y"]),
                float(state["vx"]),
                float(state["vy"]),
                320.0,
                240.0,
            )
        if era is EngineEra.EIGHT_BIT:
            return float(state["x"]), float(state["y"]), float(state["vx"]), float(state["vy"]), 512.0, 240.0
        if era is EngineEra.SIXTEEN_BIT:
            return (
                float(state["player_x"]),
                float(state["player_y"]),
                float(state["vx"]),
                float(state["vy"]),
                1024.0,
                224.0,
            )
        if "camera" in state:
            camera = state["camera"]
            return float(camera[0]), float(camera[2]), 0.0, 0.0, 64.0, 64.0
        player = state["player"]
        return float(player[0]), float(player[1]), float(player[2]), float(player[3]), 64.0, 64.0

    def _delta(self, state: Mapping[str, object]) -> tuple[float, float, float]:
        x, z, _, _, sx, sz = self._position(state)
        if self.target.era is EngineEra.PONG:
            dx, dz = 0.0, float(state["ball_y"]) - z
        else:
            dx, dz = self._goal[0] - x, self._goal[1] - z
            if self.target.era is EngineEra.ARCADE:
                dx = (dx + sx / 2) % sx - sx / 2
                dz = (dz + sz / 2) % sz - sz / 2
        return dx, dz, math.hypot(dx / sx, dz / sz)

    def _observe(
        self, state: Mapping[str, object], previous: Mapping[str, object] | None = None
    ) -> Mapping[str, float]:
        x, z, vx, vz, sx, sz = self._position(state)
        if "camera" in state and previous is not None:
            px, pz, *_ = self._position(previous)
            vx, vz = x - px, z - pz
        dx, dz, distance = self._delta(state)
        score = float(state.get("left_score", 0)) - float(state.get("right_score", 0))
        clip = lambda number: max(-1.0, min(1.0, _finite(number, "machine observation")))
        heading = float(state.get("angle", state.get("yaw", 180.0))) / 180.0 - 1.0
        grounded = float(state.get("on_ground", self.target.era is EngineEra.SIXTEEN_BIT and z >= 176.0))
        values = {
            "x": clip(x / sx),
            "z": clip(z / sz),
            "vx": clip(vx / 8),
            "vz": clip(vz / 8),
            "goal_dx": clip(dx / sx),
            "goal_dz": clip(dz / sz),
            "heading": clip(heading),
            "grounded": grounded,
            "progress": clip(1.0 - distance / self._initial_distance),
            "score": clip(score / 10),
            "alive": 0.0 if self.done else 1.0,
        }
        return _numeric_mapping(values, "observation")

    def reset(self, seed: int) -> Mapping[str, float]:
        seed = _int(seed, "episode seed", 0, 2**63 - 1)
        self._machine = self.sandbox.machine()
        self._seed = seed
        self._actions_taken = []
        self._terminated = False
        self._truncated = False
        self._last_frame = None
        rng = random.Random(seed)
        warmup = rng.randrange(1, 13)
        for _ in range(warmup):
            action = rng.choice(self.actions)
            frame = self._machine.step(InputFrame(self._machine.tick, _BUTTONS[action]))
            self._last_frame = _frame_projection(frame)
        state = self._state()
        x, z, _, _, sx, sz = self._position(state)
        if self.target.era is EngineEra.ARCADE:
            self._goal = (rng.uniform(0, sx), rng.uniform(0, sz))
        elif self.target.era is EngineEra.EIGHT_BIT:
            # The real tile map is 16*16 wide; its bottom floor begins at y=224.
            self._goal = (rng.uniform(176, 232), 216.0)
        elif self.target.era is EngineEra.SIXTEEN_BIT:
            self._goal = (x + rng.uniform(64, 192), 176.0)
        elif self.target.era is EngineEra.PONG:
            self._goal = (x, float(state["ball_y"]))
        else:
            angle = rng.uniform(-math.pi, math.pi)
            distance = rng.uniform(4, 12)
            self._goal = (x + math.sin(angle) * distance, z + math.cos(angle) * distance)
        self._initial_distance = max(self._delta(state)[2], 1e-6)
        self._observation = self._observe(state)
        self._chain = _digest(
            {
                "environment_digest": self.spec.environment_digest,
                "seed": seed,
                "warmup_steps": warmup,
                "goal": self._goal,
                "machine_digest": self._machine.fingerprint(),
                "observation": dict(self._observation),
            }
        )
        return self._observation

    def step(self, action: str) -> EpisodeStep:
        if self._seed is None or self._machine is None:
            raise GameEngineLabError("reset the environment before stepping")
        if self.done:
            raise GameEngineLabError("episode already terminated or exhausted its step budget")
        if not isinstance(action, str) or action not in self.actions:
            raise GameEngineLabError("action is not registered for this environment")
        before = self._state()
        before_digest = self._machine.fingerprint()
        before_distance = self._delta(before)[2]
        packet = self._machine.step(InputFrame(self._machine.tick, _BUTTONS[action]))
        after = self._state()
        after_distance = self._delta(after)[2]
        self._actions_taken.append(action)
        score = (float(after.get("left_score", 0)) - float(before.get("left_score", 0))) - (
            float(after.get("right_score", 0)) - float(before.get("right_score", 0))
        )
        if self.target.era is EngineEra.PONG:
            self._terminated = score != 0.0
            progress, alignment = 0.0, (before_distance - after_distance) * 0.1
        else:
            self._terminated = after_distance < (
                0.035
                if self.target.era in (EngineEra.EIGHT_BIT, EngineEra.SIXTEEN_BIT, EngineEra.ARCADE)
                else 0.015
            )
            progress, alignment = before_distance - after_distance, 0.0
        self._truncated = len(self._actions_taken) >= self.max_steps and not self._terminated
        self._observation = self._observe(after, before)
        self._last_frame = _frame_projection(packet)
        rewards = {
            "progress": progress,
            "score": score,
            "alignment": alignment,
            "goal": 1.0 if self._terminated and (self.target.era is not EngineEra.PONG or score > 0) else 0.0,
            "time": -0.001,
        }
        evidence = {
            "environment_digest": self.spec.environment_digest,
            "seed": self._seed,
            "episode_step": len(self._actions_taken),
            "action": action,
            "machine_before_digest": before_digest,
            "machine_after_digest": self._machine.fingerprint(),
            "native_frame_tick": packet.tick,
            "native_frame_state_digest": packet.state_digest,
            "native_frame_digest": self._last_frame["complete_frame_digest"],
            "observation": dict(self._observation),
            "reward_components": rewards,
            "terminated": self._terminated,
            "truncated": self._truncated,
            "previous_transition_digest": self._chain,
        }
        self._chain = _digest(evidence)
        info = {
            "evidence": evidence,
            "runtime_kind": "reference_game_simulation",
            "rom_execution": False,
        }
        return EpisodeStep(self._observation, rewards, self._terminated, self._truncated, info, self._chain)

    def snapshot(self) -> dict[str, object]:
        if self._seed is None or self._machine is None:
            raise GameEngineLabError("reset the environment before snapshotting")
        native = self._machine.snapshot()
        payload = {
            "schema_version": SNAPSHOT_SCHEMA,
            "environment_digest": self.spec.environment_digest,
            "target_id": self.target.target_id,
            "tree_digest": self.tree.digest,
            "seed": self._seed,
            "actions": list(self._actions_taken),
            "goal": list(self._goal),
            "terminated": self._terminated,
            "truncated": self._truncated,
            "observation": dict(self._observation),
            "transition_digest": self._chain,
            "native": {
                "era": native.era.value,
                "tick": native.tick,
                "state": _json_value(native.state),
                "digest": native.digest,
            },
            "last_frame_digest": (
                None if self._last_frame is None else self._last_frame["complete_frame_digest"]
            ),
        }
        _encoded(payload, MAX_SNAPSHOT_BYTES)
        return {**payload, "digest": _digest(payload)}

    def restore(self, snapshot: Mapping[str, object]) -> Mapping[str, float]:
        if not isinstance(snapshot, Mapping):
            raise GameEngineLabError("environment snapshot must be an object")
        _encoded(snapshot, MAX_SNAPSHOT_BYTES)
        required = {
            "schema_version",
            "environment_digest",
            "target_id",
            "tree_digest",
            "seed",
            "actions",
            "goal",
            "terminated",
            "truncated",
            "observation",
            "transition_digest",
            "native",
            "last_frame_digest",
            "digest",
        }
        if set(snapshot) != required or snapshot.get("schema_version") != SNAPSHOT_SCHEMA:
            raise GameEngineLabError("environment snapshot schema differs")
        payload = {key: value for key, value in snapshot.items() if key != "digest"}
        if (
            _digest(payload) != snapshot["digest"]
            or snapshot["environment_digest"] != self.spec.environment_digest
            or snapshot["target_id"] != self.target.target_id
            or snapshot["tree_digest"] != self.tree.digest
        ):
            raise GameEngineLabError("environment snapshot identity or integrity differs")
        actions = snapshot["actions"]
        if (
            not isinstance(actions, (list, tuple))
            or len(actions) > self.max_steps
            or any(not isinstance(action, str) or action not in self.actions for action in actions)
        ):
            raise GameEngineLabError("environment replay action sequence is invalid")
        # Construct separately so a malformed replay never mutates the receiver.
        candidate = GameLearningEnvironment(
            self.target.target_id,
            max_steps=self.max_steps,
            gameplay_dialect=self.gameplay_dialect,
            tree=self.tree,
        )
        candidate.reset(snapshot["seed"])
        for action in actions:
            candidate.step(action)
        if candidate.snapshot() != _json_value(snapshot):
            raise GameEngineLabError("snapshot does not match executed replay")
        self.__dict__.update(candidate.__dict__)
        return self._observation


def create_game_environment(
    target_id: str | EngineEra,
    *,
    max_steps: int = 512,
    gameplay_dialect: str | None = None,
    tree: VirtualFileTree | Mapping[str, str] | None = None,
    rom_source: bytes | None = None,
    cycles_per_step: int = 1824,
) -> object:
    """Select the exact declared runtime; ROM bytes never enter a fallback."""
    target = resolve_console(target_id)
    if tree is not None:
        supplied = _project_tree(tree, target, gameplay_dialect)
        if "game/generated/game.json" in supplied.files:
            if rom_source is not None:
                raise GameEngineLabError("generated-map and raw-ROM execution inputs are ambiguous")
            from .game_learning_generation import GeneratedGameEnvironment

            config = _project_json(supplied.read("game/generated/game.json"))
            if not isinstance(config, Mapping):
                raise GameEngineLabError("generated game config must be an object")
            return GeneratedGameEnvironment(
                target.target_id, config, max_steps=max_steps, tree_digest=supplied.digest
            )
        tree = supplied
    if target.requires_rom:
        if tree is not None or gameplay_dialect is not None:
            raise GameEngineLabError("ROM execution does not compile a reference project or gameplay dialect")
        if not isinstance(rom_source, bytes):
            raise GameEngineLabError("experimental DMG execution requires explicit immutable ROM bytes")
        from .game_rom_runtime import GameBoyROMEnvironment

        return GameBoyROMEnvironment(rom_source, max_steps=max_steps, cycles_per_step=cycles_per_step)
    if rom_source is not None:
        raise GameEngineLabError("selected reference engine cannot execute a ROM source")
    if target.native_target_id == "thumby" and tree is None:
        if gameplay_dialect is not None:
            raise GameEngineLabError(
                "native Thumby gameplay uses its exact coded mechanics, not a reference dialect"
            )
        from .game_dragon_runtime import DragonThumbyEnvironment

        return DragonThumbyEnvironment(max_steps=max_steps)
    if target.native_target_id is not None:
        raise GameEngineLabError(
            "native source is not a compiled executable; generate a discrete-grid project or use an independently admitted native toolchain"
        )
    return GameLearningEnvironment(
        target.target_id, max_steps=max_steps, gameplay_dialect=gameplay_dialect, tree=tree
    )


def _simulate_adapter(
    environment: object,
    descriptor: Mapping[str, object],
    *,
    actions: Sequence[str],
    seed: int,
    cancelled: Callable[[], bool] | None,
) -> dict[str, object]:
    if any(not isinstance(action, str) or action not in environment.spec.actions for action in actions):
        raise GameEngineLabError("simulation contains an unavailable adapter action")
    initial = dict(environment.reset(seed))
    observation = initial
    initial_snapshot = environment.snapshot()
    total = {key: 0.0 for key in environment.spec.reward_components}
    traces = []
    was_cancelled = False
    terminated = truncated = False
    chain = _digest(
        {"environment_digest": environment.spec.environment_digest, "seed": seed, "observation": initial}
    )
    for sequence, action in enumerate(actions, 1):
        if cancelled is not None and cancelled():
            was_cancelled = True
            break
        if terminated or truncated:
            break
        step = environment.step(action)
        frame_digest = _digest(environment.preview())
        evidence = {
            "environment_digest": environment.spec.environment_digest,
            "sequence": sequence,
            "action": action,
            "observation": observation,
            "next_observation": dict(step.observation),
            "reward_components": dict(step.reward_components),
            "terminated": step.terminated,
            "truncated": step.truncated,
            "info": _json_value(step.info),
            "native_frame_digest": frame_digest,
            "previous_transition_digest": chain,
        }
        chain = _digest(evidence)
        traces.append({**evidence, "transition_digest": chain})
        for key, value in step.reward_components.items():
            total[key] += value
        observation = dict(step.observation)
        terminated, truncated = step.terminated, step.truncated
    snapshot = environment.snapshot()
    result = {
        "schema_version": RUNTIME_SCHEMA,
        "descriptor": {**descriptor, "spec": environment.spec.as_dict()},
        "initial_observation": initial,
        "initial_state_digest": _digest(initial_snapshot),
        "final_observation": observation,
        "transitions": traces,
        "executed_steps": len(traces),
        "requested_steps": len(actions),
        "reward_components": total,
        "reward": math.fsum(total.values()),
        "terminated": terminated,
        "truncated": truncated,
        "cancelled": was_cancelled,
        "last_frame": environment.preview(),
        "snapshot": snapshot,
        "transition_digest": chain,
        "execution_verified": True,
        "hardware_compatibility_verified": False,
    }
    _encoded(result, MAX_REPORT_BYTES)
    return {**result, "digest": _digest(result)}


def _simulate_rom(
    target_id: str | EngineEra,
    *,
    actions: Sequence[str],
    seed: int,
    max_steps: int,
    rom_source: bytes,
    cycles_per_step: int,
    cancelled: Callable[[], bool] | None,
) -> dict[str, object]:
    environment = create_game_environment(
        target_id, max_steps=max_steps, rom_source=rom_source, cycles_per_step=cycles_per_step
    )
    descriptor = {
        "target_id": resolve_console(target_id).target_id,
        "runtime_kind": "experimental_dmg_rom",
        "rom_metadata": environment.metadata,
        "cycles_per_step": cycles_per_step,
        "reward_semantics": "Measured visual exploration; game success and mastery are unavailable",
        "full_hardware_emulation": False,
    }
    return _simulate_adapter(environment, descriptor, actions=actions, seed=seed, cancelled=cancelled)


def simulate_game(
    target_id: str | EngineEra,
    *,
    actions: Sequence[str],
    seed: int = 0,
    max_steps: int = 512,
    gameplay_dialect: str | None = None,
    tree: VirtualFileTree | Mapping[str, str] | None = None,
    cancelled: Callable[[], bool] | None = None,
    rom_source: bytes | None = None,
    cycles_per_step: int = 1824,
) -> dict[str, object]:
    """Execute caller actions and return bounded measured state/render receipts."""
    if (
        not isinstance(actions, Sequence)
        or isinstance(actions, (str, bytes, bytearray))
        or len(actions) > MAX_EPISODE_STEPS
    ):
        raise GameEngineLabError("simulation actions must be a bounded sequence")
    max_steps = _int(max_steps, "simulation max steps", 1, MAX_EPISODE_STEPS)
    if len(actions) > max_steps:
        raise GameEngineLabError("simulation action count exceeds declared budget")
    if cancelled is not None and not callable(cancelled):
        raise GameEngineLabError("simulation cancellation probe must be callable")
    environment = create_game_environment(
        target_id,
        max_steps=max_steps,
        gameplay_dialect=gameplay_dialect,
        tree=tree,
        rom_source=rom_source,
        cycles_per_step=cycles_per_step,
    )
    if not isinstance(environment, GameLearningEnvironment):
        descriptor = getattr(environment, "descriptor", None)
        if descriptor is None:
            descriptor = {
                "target_id": resolve_console(target_id).target_id,
                "runtime_kind": "experimental_dmg_rom",
                "rom_metadata": environment.metadata,
                "cycles_per_step": cycles_per_step,
                "reward_semantics": "Measured visual exploration; game success and mastery are unavailable",
                "full_hardware_emulation": False,
            }
        return _simulate_adapter(environment, descriptor, actions=actions, seed=seed, cancelled=cancelled)
    if any(not isinstance(action, str) or action not in environment.actions for action in actions):
        raise GameEngineLabError("simulation contains an unavailable action")
    initial = dict(environment.reset(seed))
    initial_state_digest = environment.observe()["native_state_digest"]
    traces = []
    total = {key: 0.0 for key in _REWARDS}
    was_cancelled = False
    for action in actions:
        if cancelled is not None and cancelled():
            was_cancelled = True
            break
        if environment.done:
            break
        step = environment.step(action)
        for key, value in step.reward_components.items():
            total[key] += value
        # Retain every transition identity; project only the last native frame.
        traces.append(
            {
                "action": action,
                "observation": dict(step.observation),
                "reward_components": dict(step.reward_components),
                "terminated": step.terminated,
                "truncated": step.truncated,
                "transition_digest": step.transition_digest,
                "machine_before_digest": step.info["evidence"]["machine_before_digest"],
                "machine_after_digest": step.info["evidence"]["machine_after_digest"],
                "native_frame_digest": step.info["evidence"]["native_frame_digest"],
                "native_frame_tick": step.info["evidence"]["native_frame_tick"],
            }
        )
    snapshot = environment.snapshot()
    result = {
        "schema_version": RUNTIME_SCHEMA,
        "descriptor": environment.descriptor,
        "initial_observation": initial,
        "initial_state_digest": initial_state_digest,
        "final_observation": snapshot["observation"],
        "transitions": traces,
        "executed_steps": len(traces),
        "requested_steps": len(actions),
        "reward_components": total,
        "reward": math.fsum(total.values()),
        "terminated": environment._terminated,
        "truncated": environment._truncated,
        "cancelled": was_cancelled,
        "last_frame": environment.preview(),
        "snapshot": snapshot,
        "execution_verified": True,
        "hardware_compatibility_verified": False,
    }
    _encoded(result, MAX_REPORT_BYTES)
    return {**result, "digest": _digest(result)}
