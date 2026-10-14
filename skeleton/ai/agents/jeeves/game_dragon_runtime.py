"""Actual local gameplay reuse of the canonical Dragon Thumby program.

Only fixed, trusted numeric functions from the existing native source owner
are compiled. User projects and uploads never become Python instructions.
Device rendering, firmware and timings are outside this gameplay adapter.
"""

from __future__ import annotations

import ast
import base64
import hashlib
import importlib
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from types import CodeType, FunctionType

from .game_engine_lab import GameEngineLabError
from .game_learning_runtime import EpisodeStep, GameEnvironmentSpec

SCHEMA = "skeleton.dragon_thumby_gameplay.v1"
_FUNCTIONS = {"fresh", "_rand", "_bound", "step"}
_CALLS = _FUNCTIONS | {"int", "bool", "abs", "max", "range"}
_BUILTINS = {"int": int, "bool": bool, "abs": abs, "max": max, "range": range}
_PARAMETERS = {
    "fresh": ("seed",),
    "_rand": ("s", "limit"),
    "_bound": ("x", "a", "b"),
    "step": ("s", "held", "pressed"),
}
_ABI = {
    "WIDTH": 72,
    "HEIGHT": 40,
    "HX": 0,
    "HY": 1,
    "GX": 2,
    "GY": 3,
    "EX": 4,
    "EY": 5,
    "HP": 6,
    "SCORE": 7,
    "STAGE": 8,
    "TICK": 9,
    "RNG": 10,
    "GUARD": 11,
    "COOLDOWN": 12,
    "MODE": 13,
    "DIRX": 14,
    "DIRY": 15,
    "READY": 0,
    "PLAYING": 1,
    "DEFEAT": 2,
    "VICTORY": 3,
    "UP": 1,
    "DOWN": 2,
    "LEFT": 4,
    "RIGHT": 8,
    "ACTION_A": 16,
    "ACTION_B": 32,
    "MAX_CRYSTALS": 16,
}
_ACTIONS = {
    "noop": (0, 0),
    "left": (4, 0),
    "right": (8, 0),
    "up": (1, 0),
    "down": (2, 0),
    "shield": (0, 16),
    "dash_left": (4, 32),
    "dash_right": (8, 32),
    "dash_up": (1, 32),
    "dash_down": (2, 32),
}


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def _kernel() -> tuple[dict[str, object], dict[str, bytes], str]:
    module = importlib.import_module("skeleton.ai.webcrawler.dragon_native_thumby")
    source = module.GAME
    if not isinstance(source, str) or len(source.encode()) > 128_000:
        raise GameEngineLabError("canonical native gameplay source exceeds capacity")
    try:
        parsed = ast.parse(source.replace("__SEED__", "1"))
    except (SyntaxError, RecursionError) as exc:
        raise GameEngineLabError("canonical native gameplay syntax is unavailable") from exc
    nodes = []
    assets = {}
    found = set()
    for node in parsed.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name.isupper() and isinstance(node.value, ast.Constant) and type(node.value.value) is int:
                if not 0 <= node.value.value <= 2**32:
                    raise GameEngineLabError("native gameplay constant exceeds capacity")
                nodes.append(node)
            elif name in {"DRAGON", "CRYSTAL", "FOE"}:
                if (
                    not isinstance(node.value, ast.Call)
                    or not isinstance(node.value.func, ast.Name)
                    or node.value.func.id != "bytes"
                    or len(node.value.args) != 1
                    or node.value.keywords
                ):
                    raise GameEngineLabError("native bitmap source is not fixed bytes")
                raw = ast.literal_eval(node.value.args[0])
                if (
                    not isinstance(raw, tuple)
                    or len(raw) != 8
                    or any(type(value) is not int or not 0 <= value <= 255 for value in raw)
                ):
                    raise GameEngineLabError("native bitmap source exceeds capacity")
                assets[name] = bytes(raw)
        elif isinstance(node, ast.FunctionDef) and node.name in _FUNCTIONS:
            if node.name in found or node.decorator_list:
                raise GameEngineLabError("native gameplay function identity is invalid")
            if (
                tuple(argument.arg for argument in node.args.args) != _PARAMETERS[node.name]
                or node.args.posonlyargs
                or node.args.kwonlyargs
                or node.args.vararg is not None
                or node.args.kwarg is not None
            ):
                raise GameEngineLabError("native gameplay parameter schema differs")
            found.add(node.name)
            for inner in ast.walk(node):
                if isinstance(inner, ast.FunctionDef) and inner is not node:
                    raise GameEngineLabError("nested native gameplay functions are not admitted")
                if isinstance(inner, ast.Pow):
                    raise GameEngineLabError("native gameplay exponentiation is not admitted")
                if (
                    isinstance(inner, ast.Constant)
                    and type(inner.value) is int
                    and not -(2**32) <= inner.value <= 2**32
                ):
                    raise GameEngineLabError("native gameplay literal exceeds numeric capacity")
                if (
                    isinstance(inner, ast.BinOp)
                    and isinstance(inner.op, (ast.LShift, ast.RShift))
                    and (
                        not isinstance(inner.right, ast.Constant)
                        or type(inner.right.value) is not int
                        or not 0 <= inner.right.value <= 32
                    )
                ):
                    raise GameEngineLabError("native gameplay bit shift is not statically bounded")
                if isinstance(
                    inner,
                    (
                        ast.Import,
                        ast.ImportFrom,
                        ast.Attribute,
                        ast.While,
                        ast.With,
                        ast.Try,
                        ast.Lambda,
                        ast.ClassDef,
                        ast.Global,
                        ast.Nonlocal,
                        ast.AsyncFunctionDef,
                        ast.Await,
                        ast.Yield,
                        ast.YieldFrom,
                        ast.ListComp,
                        ast.SetComp,
                        ast.DictComp,
                        ast.GeneratorExp,
                    ),
                ):
                    raise GameEngineLabError("native gameplay exceeds the pure numeric AST boundary")
                if isinstance(inner, ast.Name) and inner.id.startswith("__"):
                    raise GameEngineLabError("native gameplay uses a forbidden dynamic name")
                if isinstance(inner, ast.Call) and (
                    not isinstance(inner.func, ast.Name) or inner.func.id not in _CALLS
                ):
                    raise GameEngineLabError("native gameplay uses an undeclared function call")
                if isinstance(inner, ast.For):
                    call = inner.iter
                    if (
                        not isinstance(call, ast.Call)
                        or not isinstance(call.func, ast.Name)
                        or call.func.id != "range"
                        or len(call.args) != 1
                        or call.keywords
                        or not isinstance(call.args[0], ast.Constant)
                        or type(call.args[0].value) is not int
                        or not 0 <= call.args[0].value <= 16
                    ):
                        raise GameEngineLabError("native gameplay loop is not statically bounded")
            nodes.append(node)
    if found != _FUNCTIONS or set(assets) != {"DRAGON", "CRYSTAL", "FOE"}:
        raise GameEngineLabError("canonical native gameplay functions or bitmaps are missing")
    dependencies = {
        node.name: {
            call.func.id
            for call in ast.walk(node)
            if isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id in _FUNCTIONS
        }
        for node in nodes
        if isinstance(node, ast.FunctionDef)
    }
    resolved = set()
    while len(resolved) < len(_FUNCTIONS):
        available = {
            name for name, calls in dependencies.items() if name not in resolved and calls <= resolved
        }
        if not available:
            raise GameEngineLabError("native gameplay recursion is not bounded")
        resolved.update(available)
    namespace = {"__builtins__": _BUILTINS}
    # Install literal constants directly and materialize only the audited
    # function code objects. No module statement, import or decorator runs.
    for node in nodes:
        if isinstance(node, ast.Assign):
            namespace[node.targets[0].id] = node.value.value
    if any(type(namespace.get(key)) is not int or namespace[key] != value for key, value in _ABI.items()):
        raise GameEngineLabError("canonical native gameplay state/input ABI changed")
    for node in nodes:
        if not isinstance(node, ast.FunctionDef):
            continue
        selected = ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[]))
        compiled = compile(selected, str(module.__file__), "exec")
        codes = [value for value in compiled.co_consts if isinstance(value, CodeType)]
        if len(codes) != 1 or codes[0].co_name != node.name:
            raise GameEngineLabError("native gameplay function code identity differs")
        defaults = []
        for default in node.args.defaults:
            if isinstance(default, ast.Name) and type(namespace.get(default.id)) is int:
                defaults.append(namespace[default.id])
            elif isinstance(default, ast.Constant) and type(default.value) is int:
                defaults.append(default.value)
            else:
                raise GameEngineLabError("native gameplay default is not an audited integer")
        namespace[node.name] = FunctionType(codes[0], namespace, node.name, tuple(defaults) or None)
    source_identity = _digest(
        {
            "template": hashlib.sha256(source.encode()).hexdigest(),
            "module": hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest(),
            "adapter": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "python": list(sys.version_info[:3]),
        }
    )
    return namespace, assets, source_identity


class DragonThumbyEnvironment:
    """Exact coded micro-game mechanics, independent of device IO."""

    def __init__(self, *, max_steps: int = 512) -> None:
        if type(max_steps) is not int or not 1 <= max_steps <= 4096:
            raise GameEngineLabError("native gameplay step budget is invalid")
        self.max_steps = max_steps
        self._kernel, self._assets, self._code_digest = _kernel()
        self._descriptor = {
            "schema_version": SCHEMA,
            "target_id": "dragon_native:thumby",
            "native_target_id": "thumby",
            "runtime_kind": "native_gameplay_python",
            "canonical_owner": "skeleton.ai.webcrawler.dragon_native_thumby",
            "source_code_digest": self._code_digest,
            "max_episode_steps": max_steps,
            "reset_seed_schema": "caller_uint63_to_native_uint32_v1",
            "execution_scope": "Exact original native numeric gameplay functions; no Thumby firmware or device IO",
            "device_graphics_verified": False,
            "rom_execution": False,
            "full_hardware_emulation": False,
            "reward_semantics": {
                "progress": "goal-distance reduction divided by screen width",
                "score": "actual crystal score increase",
                "damage": "actual health change",
                "goal": "one on native VICTORY",
                "time": "declared step cost -0.001",
            },
        }
        features = (
            "x",
            "z",
            "vx",
            "vz",
            "goal_dx",
            "goal_dz",
            "enemy_dx",
            "enemy_dz",
            "health",
            "guard",
            "cooldown",
            "stage",
            "score",
            "alive",
        )
        bins = (-0.75, -0.5, -0.25, -0.1, 0.0, 0.1, 0.25, 0.5, 0.75)
        self.spec = GameEnvironmentSpec(
            "dragon_native:thumby",
            _digest(self._descriptor),
            tuple(_ACTIONS),
            {key: bins for key in features},
            ("progress", "score", "damage", "goal", "time"),
            max_steps,
        )
        self._state = None
        self._seed = None
        self._actions: list[str] = []
        self._chain = ""
        self._motion = (0.0, 0.0)

    @property
    def descriptor(self) -> dict[str, object]:
        return {
            **self._descriptor,
            "environment_digest": self.spec.environment_digest,
            "spec": self.spec.as_dict(),
        }

    @property
    def done(self) -> bool:
        return self._state is not None and (self._state[13] in (2, 3) or len(self._actions) >= self.max_steps)

    def _validate_state(self) -> None:
        s = self._state
        if (
            not isinstance(s, list)
            or len(s) != 16
            or any(type(value) is not int or not -1 <= value <= 2**32 - 1 for value in s)
            or not 0 <= s[6] <= 3
            or not 0 <= s[7] <= 16
            or s[13] not in (0, 1, 2, 3)
            or not 1 <= s[0] <= 63
            or not 10 <= s[1] <= 31
        ):
            raise GameEngineLabError("native gameplay returned an invalid bounded state")

    def _observation(self) -> dict[str, float]:
        if self._state is None:
            raise GameEngineLabError("reset native gameplay before observing")
        s = self._state
        return {
            "x": s[0] / 72,
            "z": s[1] / 40,
            "vx": self._motion[0] / 2,
            "vz": self._motion[1] / 2,
            "goal_dx": (s[2] - s[0]) / 72,
            "goal_dz": (s[3] - s[1]) / 40,
            "enemy_dx": (s[4] - s[0]) / 72,
            "enemy_dz": (s[5] - s[1]) / 40,
            "health": s[6] / 3,
            "guard": s[11] / 32,
            "cooldown": s[12] / 38,
            "stage": s[8] / 5,
            "score": s[7] / 16,
            "alive": 1.0 if s[6] > 0 else 0.0,
        }

    def reset(self, seed: int) -> dict[str, float]:
        if type(seed) is not int or not 0 <= seed <= 2**63 - 1:
            raise GameEngineLabError("native gameplay seed must be uint63")
        self._seed = seed
        self._state = self._kernel["fresh"](seed & 0xFFFFFFFF)
        self._kernel["step"](self._state, 0, 16)
        self._validate_state()
        self._actions = []
        self._motion = (0.0, 0.0)
        self._chain = _digest(
            {
                "environment_digest": self.spec.environment_digest,
                "seed": seed,
                "native_seed": (seed & 0xFFFFFFFF) or 1,
                "state": self._state,
            }
        )
        return self._observation()

    def step(self, action: str) -> EpisodeStep:
        if self._state is None or self.done:
            raise GameEngineLabError("native gameplay is not in an active episode")
        if not isinstance(action, str) or action not in _ACTIONS:
            raise GameEngineLabError("native gameplay action is unavailable")
        before = list(self._state)
        old_distance = ((before[2] - before[0]) ** 2 + (before[3] - before[1]) ** 2) ** 0.5
        held, pressed = _ACTIONS[action]
        event = self._kernel["step"](self._state, held, pressed)
        self._validate_state()
        self._actions.append(action)
        self._motion = (float(self._state[0] - before[0]), float(self._state[1] - before[1]))
        distance = ((before[2] - self._state[0]) ** 2 + (before[3] - self._state[1]) ** 2) ** 0.5
        terminated = self._state[13] in (2, 3)
        truncated = len(self._actions) >= self.max_steps and not terminated
        rewards = {
            "progress": (old_distance - distance) / 72,
            "score": float(self._state[7] - before[7]),
            "damage": float(self._state[6] - before[6]),
            "goal": 1.0 if self._state[13] == 3 else 0.0,
            "time": -0.001,
        }
        evidence = {
            "environment_digest": self.spec.environment_digest,
            "episode_step": len(self._actions),
            "action": action,
            "held": held,
            "pressed": pressed,
            "state_before_digest": _digest(before),
            "state_after_digest": _digest(self._state),
            "native_event": event,
            "observation": self._observation(),
            "reward_components": rewards,
            "terminated": terminated,
            "truncated": truncated,
            "previous_transition_digest": self._chain,
        }
        self._chain = _digest(evidence)
        return EpisodeStep(
            evidence["observation"],
            rewards,
            terminated,
            truncated,
            {
                "evidence": evidence,
                "runtime_kind": "native_gameplay_python",
                "device_graphics_verified": False,
            },
            self._chain,
        )

    def preview(self) -> dict[str, object] | None:
        if self._state is None:
            return None
        s = self._state
        pixels = bytearray(72 * 40)
        for x in range(72):
            pixels[9 * 72 + x] = pixels[39 * 72 + x] = 255
        for y in range(9, 40):
            pixels[y * 72] = pixels[y * 72 + 71] = 255
        for name, x, y in (("CRYSTAL", s[2], s[3]), ("FOE", s[4], s[5]), ("DRAGON", s[0], s[1])):
            if name == "DRAGON" and s[11] and s[9] % 6 >= 3:
                continue
            for column, value in enumerate(self._assets[name]):
                for row in range(8):
                    px, py = x + column, y + row
                    if value & (1 << row) and 0 <= px < 72 and 0 <= py < 40:
                        pixels[py * 72 + px] = 255
        return {
            "runtime_kind": "native_gameplay_python",
            "render_kind": "native_bitmap_host_preview",
            "width": 72,
            "height": 40,
            "format": "gray8",
            "pixels_base64": base64.b64encode(pixels).decode("ascii"),
            "pixel_digest": hashlib.sha256(pixels).hexdigest(),
            "state_digest": _digest(s),
            "native_tick": s[9],
            "score": s[7],
            "health": s[6],
            "stage": s[8],
            "device_graphics_verified": False,
            "render_scope": "Original fixed native bitmaps at actual gameplay positions; host pixel layout, no device font or firmware certification",
        }

    def snapshot(self) -> dict[str, object]:
        if self._state is None:
            raise GameEngineLabError("reset native gameplay before snapshotting")
        payload = {
            "schema_version": SCHEMA,
            "environment_digest": self.spec.environment_digest,
            "seed": self._seed,
            "actions": list(self._actions),
            "state": list(self._state),
            "motion": list(self._motion),
            "transition_digest": self._chain,
        }
        return {**payload, "snapshot_digest": _digest(payload)}

    def restore(self, snapshot: Mapping[str, object]) -> dict[str, float]:
        if not isinstance(snapshot, Mapping) or set(snapshot) != {
            "schema_version",
            "environment_digest",
            "seed",
            "actions",
            "state",
            "motion",
            "transition_digest",
            "snapshot_digest",
        }:
            raise GameEngineLabError("native gameplay snapshot schema differs")
        actions = snapshot["actions"]
        state, motion, seed = snapshot["state"], snapshot["motion"], snapshot["seed"]
        if (
            not isinstance(state, list)
            or len(state) != 16
            or any(type(value) is not int or not -1 <= value <= 2**32 - 1 for value in state)
            or not isinstance(motion, list)
            or len(motion) != 2
            or any(type(value) not in (int, float) or not -2 <= value <= 2 for value in motion)
            or type(seed) is not int
            or not 0 <= seed <= 2**63 - 1
        ):
            raise GameEngineLabError("native gameplay snapshot state shape or numeric bounds differ")
        for key in ("transition_digest", "snapshot_digest"):
            value = snapshot[key]
            if (
                not isinstance(value, str)
                or len(value) != 64
                or any(character not in "0123456789abcdef" for character in value)
            ):
                raise GameEngineLabError("native gameplay snapshot digest identity is invalid")
        if (
            not isinstance(actions, list)
            or len(actions) > self.max_steps
            or any(not isinstance(action, str) or action not in _ACTIONS for action in actions)
            or snapshot["schema_version"] != SCHEMA
            or snapshot["environment_digest"] != self.spec.environment_digest
        ):
            raise GameEngineLabError("native gameplay snapshot identity or action capacity differs")
        payload = {key: value for key, value in snapshot.items() if key != "snapshot_digest"}
        if len(json.dumps(payload)) > 128_000 or _digest(payload) != snapshot["snapshot_digest"]:
            raise GameEngineLabError("native gameplay snapshot integrity differs")
        candidate = DragonThumbyEnvironment(max_steps=self.max_steps)
        candidate.reset(snapshot["seed"])
        for action in actions:
            candidate.step(action)
        if candidate.snapshot() != dict(snapshot):
            raise GameEngineLabError("native gameplay snapshot fails actual replay")
        self.__dict__.update(candidate.__dict__)
        return self._observation()
