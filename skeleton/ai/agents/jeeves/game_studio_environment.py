"""Emulator-compatible learning adapter for the canonical original-game studio.

Exactly the existing advanced-session engine runs every game transition; state
is always reconstructed from source, seed and accepted commands. Observation
and reward projections are declared local training utilities, never evidence
of native display output, emulator hardware compatibility or game mastery.

This is the canonical Jeeves game-learning environment owner, not a new
renderer/provider/service. Untrusted scene data are never executed as code.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from functools import lru_cache
from hashlib import sha256
from pathlib import Path

from skeleton.ai.game_builder import advanced_gameplay_runtime as gameplay
from skeleton.ai.game_builder import advanced_level_scenes as scenes
from skeleton.ai.game_builder import system_editors

from .game_learning_runtime import EpisodeStep, GameEnvironmentSpec
from .game_studio_frame import render_studio_scene, render_studio_state_telemetry

SOURCE_SCHEMA = "skeleton.game_builder.learning_source.v1"
SNAPSHOT_SCHEMA = "skeleton.game_builder.learning_snapshot.v1"
MAX_SOURCE_BYTES = 131072
MAX_PREVIEW_BYTES = 65536
MAX_ENGINE_STEPS = gameplay.MAX_TURNS
_FEATURES = ("progress", "score", "resources", "health", "time", "success", "failure")
_REWARDS = ("progress", "score", "health", "goal", "invalid", "time")
_THRESHOLDS = (-0.8, -0.4, -0.1, 0.0, 0.1, 0.4, 0.8)
_STATE_THRESHOLDS = (-0.5, 0.0, 0.1, 0.25, 0.5, 0.75, 1.0, 2.0, 4.0)
_METRICS = {
    "progress": (
        "trade_volume",
        "x",
        "distance",
        "distance_travelled",
        "tick",
        "turn",
        "round",
        "waves_cleared",
        "level",
        "collected",
        "defeated",
        "quests_completed",
        "score",
        "journeys",
        "regions_discovered",
        "craft_count",
        "mined",
        "played_shots",
        "shot_index",
    ),
    "score": ("net_worth", "score", "points", "home_score", "gold", "credits", "victory_points"),
    "resources": (
        "credits",
        "gold",
        "energy",
        "stamina",
        "mana",
        "food",
        "wood",
        "ore",
        "supplies",
        "resources",
        "cargo",
    ),
    "health": ("health", "hp", "player_health", "life", "stamina", "max_health", "energy"),
}


class StudioEnvironmentError(ValueError):
    """Invalid original-game source, action, replay or learning boundary."""


def _json(value: object, max_bytes: int = MAX_SOURCE_BYTES) -> bytes:
    try:
        raw = json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
        ).encode("utf-8")
    except (ValueError, TypeError, OverflowError, RecursionError) as exc:
        raise StudioEnvironmentError("studio learning source must be finite JSON") from exc
    if len(raw) > max_bytes:
        raise StudioEnvironmentError("studio learning data exceed byte admission")
    return raw


def _digest(value: object) -> str:
    return sha256(_json(value, 2_000_000)).hexdigest()


def _plain(value: object) -> object:
    # Also strips untrusted mapping/list subclasses before source custody.
    return json.loads(_json(value))


@lru_cache(maxsize=1)
def _implementation_digest() -> str:
    folder = Path(gameplay.__file__).parent
    paths = [
        Path(__file__),
        Path(gameplay.__file__),
        Path(scenes.__file__),
        Path(system_editors.__file__),
        Path(__file__).with_name("game_studio_frame.py"),
    ] + sorted(folder.glob("advanced_*_runtime.py"))
    return _digest({p.name: sha256(p.read_bytes()).hexdigest() for p in paths})


def _palette(editor: str) -> tuple[str, ...]:
    registered = gameplay.ACTION_HELP[editor]
    if len(registered) != len(set(registered)):
        raise StudioEnvironmentError("original gameplay action catalog contains duplicates")
    # The canonical policy learner permits 32 actions per training policy;
    # explicit overrides can instead choose other real registered actions.
    favored = (
        "inspect",
        "wait",
        "rest",
        "observe",
        "survey",
        "coast",
        "tick",
        "end_turn",
        "guard",
        "north",
        "south",
        "east",
        "west",
        "accelerate",
        "jump",
        "attack",
    )
    selected = [name for name in favored if name in registered]
    seen = set(selected)
    for name in registered:
        if name not in seen:
            seen.add(name)
            selected.append(name)
            if len(selected) >= 32:
                break
    return tuple(selected[:32])


def make_studio_source(
    editor: str,
    settings: Mapping[str, object] | None = None,
    *,
    scene: Mapping[str, object] | None = None,
    actions: Sequence[str] | None = None,
) -> dict[str, object]:
    if not isinstance(editor, str) or editor not in gameplay.ENGINES:
        raise StudioEnvironmentError("engine is not executable in the original-game studio")
    try:
        config = system_editors.make_editor_document(editor, settings)
        validated_scene = (
            None if scene is None else scenes.validate_advanced_scene(_plain(scene), config["settings"])
        )
    except (ValueError, TypeError, KeyError) as exc:
        raise StudioEnvironmentError("invalid source-bound studio settings or scene") from exc
    palette = _palette(editor) if actions is None else tuple(actions)
    if (
        not 1 <= len(palette) <= 32
        or len(set(palette)) != len(palette)
        or any(type(action) is not str or action not in gameplay.ACTION_HELP[editor] for action in palette)
    ):
        raise StudioEnvironmentError("learning palette must select 1..32 registered actions")
    source = {
        "schema_version": SOURCE_SCHEMA,
        "editor": editor,
        "settings": config["settings"],
        "scene": validated_scene,
        "actions": list(palette),
    }
    return _plain(source)


def parse_studio_source(value: object) -> dict[str, object]:
    if (
        type(value) is not dict
        or set(value) != {"schema_version", "editor", "settings", "scene", "actions"}
        or value["schema_version"] != SOURCE_SCHEMA
    ):
        raise StudioEnvironmentError("exact studio learning source envelope required")
    if type(value["actions"]) is not list:
        raise StudioEnvironmentError("learning actions must be a JSON array")
    canonical = make_studio_source(
        value["editor"],
        value["settings"],
        scene=value["scene"],
        actions=value["actions"],
    )
    if _plain(value) != canonical:
        raise StudioEnvironmentError("source normalization or registered actions mismatch")
    return canonical


def studio_request_tree(source: Mapping[str, object]) -> dict[str, str]:
    normalized = parse_studio_source(dict(source))
    return {"game/studio/session.json": _json(normalized).decode("utf-8")}


def _numeric(state: Mapping[str, object], names: Sequence[str]) -> float:
    for key in names:
        value = state.get(key)
        if type(value) in (int, float) and math.isfinite(value):
            return min(1_000_000.0, max(-1_000_000.0, float(value)))
    return 0.0


def _scale(value: float) -> float:
    # Controlled potential shaping: no arbitrary nested game state can mint
    # a reward. Values come only from the re-executed authoritative state.
    return max(-10.0, min(10.0, value / 100.0))


def _state_features(
    editor: str, state: Mapping[str, object], settings: Mapping[str, object]
) -> dict[str, float]:
    """Finite task prerequisites, projected only from the canonical replay."""
    if editor == "farming":
        result = {
            "coins": _numeric(state, ("coins",)) / 80.0,
            "seeds": _numeric(state, ("seeds",)) / 8.0,
            "stored_water": _numeric(state, ("water",)) / 12.0,
            "harvest_stock": _numeric(state, ("harvest_stock",)) / 8.0,
            "contracts": _numeric(state, ("contracts_completed",)) / 2.0,
            "farm_day": _numeric(state, ("day",)) / 40.0,
            "weather": {"sun": 0.0, "rain": 0.5, "drought": 1.0}.get(state.get("weather"), 0.0),
        }
        plots = state.get("plots", [])
        for index in range(4):
            row = plots[index] if index < len(plots) else None
            planted = row is not None and row.get("crop", -1) >= 0
            target = max(1, settings["growth_days"] // (row["crop"] + 2)) if planted else 1
            result.update(
                {
                    f"plot_{index}_growth": min(1.0, row["age"] / target) if planted else -1.0,
                    f"plot_{index}_moisture": row["moisture"] / 5.0 if row else -1.0,
                    f"plot_{index}_soil": row["soil"] / 5.0 if row else -1.0,
                    f"plot_{index}_pests": row["pests"] / 3.0 if row else -1.0,
                }
            )
        return result
    if editor == "maze":
        x, y = state.get("position", (0, 0))
        goal_x, goal_y = state.get("exit", (0, 0))
        key_x, key_y = state.get("key_position", (0, 0))
        width, height = max(1, settings["width"] - 1), max(1, settings["height"] - 1)
        return {
            "position_x": x / width,
            "position_y": y / height,
            "exit_dx": (goal_x - x) / width,
            "exit_dy": (goal_y - y) / height,
            "key_dx": (key_x - x) / width,
            "key_dy": (key_y - y) / height,
            "has_key": float(bool(state.get("has_key"))),
            "surveyed_fraction": len(state.get("surveyed", [])) / (settings["width"] * settings["height"]),
        }
    if editor == "rpg":
        return {
            "quest_stage": {"unknown": 0.0, "offered": 0.25, "active": 0.5, "completed": 1.0}.get(
                state.get("quest_state"), 0.0
            ),
            "quest_evidence": _numeric(state, ("quest_evidence",)) / 2.0,
            "enemy_health": _numeric(state, ("enemy_hp",)) / 10.0,
            "rations": _numeric(state, ("rations",)) / 6.0,
            "gold": _numeric(state, ("gold",)) / 20.0,
            "region": _numeric(state, ("region",)) / 3.0,
            "experience": _numeric(state, ("experience",)) / 20.0,
            "party_health": sum(row["hp"] for row in state.get("party", []))
            / max(1, 8 * settings["party_size"]),
        }
    return {}


def _feature_bins(editor: str, settings: Mapping[str, object]) -> dict[str, tuple[float, ...]]:
    result = {name: _THRESHOLDS for name in _FEATURES}
    # Empty canonical rows establish names without creating an episode or
    # running any game work during descriptor admission.
    result.update({name: _STATE_THRESHOLDS for name in _state_features(editor, {}, settings)})
    return result


class StudioGameEnvironment:
    """The same spec/reset/step/snapshot/restore/preview protocol as libretro."""

    def __init__(self, source: Mapping[str, object], *, max_steps: int = 64) -> None:
        if type(max_steps) is not int or not 1 <= max_steps <= MAX_ENGINE_STEPS:
            raise StudioEnvironmentError("studio policy episode length exceeds game replay budget")
        self.source = parse_studio_source(dict(source))
        self.editor = self.source["editor"]
        self.max_steps = max_steps
        self.settings = self.source["settings"]
        self.scene = self.source["scene"]
        self.actions = tuple(self.source["actions"])
        self.source_digest = _digest(self.source)
        self._descriptor = {
            "schema_version": SOURCE_SCHEMA,
            "target_id": "studio:" + self.editor,
            "runtime_kind": "original_game_reference_runtime",
            "source_digest": self.source_digest,
            "implementation_digest": _implementation_digest(),
            "max_steps": max_steps,
            "actions": list(self.actions),
            "observation_schema": "actual_state_task_prerequisites_v2",
            "reward_schema": "actual_state_delta_success_failure_attempt_time_v2",
            "rejection_semantics": "penalized_attempt_preserves_accepted_game_prefix",
            "preview_semantics": "original_replayed_scene_or_labelled_scalar_telemetry",
            "scene_seed_pinned": self.scene is not None,
            "training_weight_owner": "Jeeves local tabular game policy only",
            "native_hardware_verified": False,
            "production_neural_weights_modified": False,
        }
        self.spec = GameEnvironmentSpec(
            "studio:" + self.editor,
            _digest(self._descriptor),
            self.actions,
            _feature_bins(self.editor, self.settings),
            _REWARDS,
            max_steps,
        )
        self._seed: int | None = None
        self._engine_seed: int | None = None
        self._receipt: dict[str, object] | None = None
        self._actions_taken: list[str] = []
        self._observation: dict[str, float] | None = None
        self._invalid: str | None = None
        self._terminated = False
        self._truncated = False
        self._chain = ""

    @property
    def descriptor(self) -> dict[str, object]:
        return {
            **self._descriptor,
            "environment_digest": self.spec.environment_digest,
            "spec": self.spec.as_dict(),
        }

    @property
    def done(self) -> bool:
        return self._terminated or self._truncated

    def _observe(self) -> dict[str, float]:
        if self._receipt is None:
            raise StudioEnvironmentError("reset before observation")
        state = self._receipt["state"]
        result = {
            "progress": _scale(_numeric(state, _METRICS["progress"])),
            "score": _scale(_numeric(state, _METRICS["score"])),
            "resources": _scale(_numeric(state, _METRICS["resources"])),
            "health": _scale(_numeric(state, _METRICS["health"])),
            "time": len(self._actions_taken) / float(self.max_steps),
            "success": float(bool(state.get("finished")) and not state.get("failed")),
            "failure": float(bool(state.get("failed"))),
        }
        if self.editor == "farming":
            result.update(
                progress=state["harvested"] / 8.0,
                score=state["coins"] / 80.0,
                resources=(state["seeds"] + state["water"] + state["harvest_stock"]) / 32.0,
            )
        elif self.editor == "maze":
            result["progress"] = (state["completed_levels"] + 0.5 * bool(state["has_key"])) / self.settings[
                "levels"
            ]
            result["health"] = state["health"] / max(1, state["max_health"])
        elif self.editor == "rpg":
            result.update(
                progress=state["quests_completed"] / 10.0,
                score=state["gold"] / 20.0,
                resources=state["rations"] / 6.0,
                health=sum(row["hp"] for row in state["party"]) / max(1, 8 * self.settings["party_size"]),
            )
        result.update(_state_features(self.editor, state, self.settings))
        return {key: max(-10.0, min(10.0, float(value))) for key, value in result.items()}

    def current_observation(self) -> dict[str, float]:
        if self._observation is None:
            raise StudioEnvironmentError("reset before observation")
        return dict(self._observation)

    def reset(self, seed: int) -> Mapping[str, float]:
        if type(seed) is not int or not 0 <= seed <= 2**63 - 1:
            raise StudioEnvironmentError("bounded policy episode seed required")
        # Authored scenes are immutable and pin an exact engine-world seed.
        # Without scenes, derive a source-bound 31-bit engine seed from the
        # possibly 63-bit policy seed without truncation-by-platform.
        engine_seed = (
            self.scene["seed"]
            if self.scene is not None
            else int(_digest({"seed": seed, "source": self.source_digest})[:12], 16) % (2**31)
        )
        receipt = gameplay.run_advanced_session(
            self.editor,
            self.settings,
            [],
            seed=engine_seed,
            scene=self.scene,
        )
        if not gameplay.verify_advanced_session(receipt, self.settings):
            raise StudioEnvironmentError("initial studio replay did not verify")
        self._seed = seed
        self._engine_seed = engine_seed
        self._receipt = receipt
        self._actions_taken = []
        self._invalid = None
        self._terminated = bool(receipt["terminal"])
        self._truncated = False
        self._observation = self._observe()
        self._chain = _digest(
            {
                "environment": self.spec.environment_digest,
                "seed": seed,
                "engine_seed": engine_seed,
                "initial_session": receipt["digest"],
            }
        )
        return dict(self._observation)

    def step(self, action: str) -> EpisodeStep:
        if self._receipt is None or self._seed is None or self._observation is None:
            raise StudioEnvironmentError("reset before stepping")
        if self.done:
            raise StudioEnvironmentError("terminal learning environment cannot advance")
        if type(action) is not str or action not in self.actions:
            raise StudioEnvironmentError("learning action outside approved engine palette")
        previous = self._observation
        previous_receipt = self._receipt
        attempted = self._actions_taken + [action]
        accepted = previous_receipt["actions"] + [action]
        invalid = None
        try:
            current = gameplay.run_advanced_session(
                self.editor,
                self.settings,
                accepted,
                seed=self._engine_seed,
                scene=self.scene,
            )
        except gameplay.AdvancedRuntimeError as exc:
            # An action can be registered but unaffordable in this state.
            # Penalize it as an actual rejected command, never fabricate game
            # progress or silently legalize an impossible transition.
            invalid = type(exc).__name__
            current = previous_receipt
        self._actions_taken = attempted
        self._receipt = current
        self._invalid = invalid
        self._observation = self._observe()
        self._terminated = bool(current["terminal"])
        self._truncated = len(self._actions_taken) >= self.max_steps and not self._terminated
        rewards = {
            "progress": max(-1.0, min(1.0, (self._observation["progress"] - previous["progress"]) * 0.25)),
            "score": max(-1.0, min(1.0, (self._observation["score"] - previous["score"]) * 0.25)),
            "health": max(-1.0, min(1.0, (self._observation["health"] - previous["health"]) * 0.25)),
            "goal": (
                5.0
                if self._observation["success"] > previous["success"]
                else -5.0 if self._observation["failure"] > previous["failure"] else 0.0
            ),
            "invalid": -1.0 if invalid is not None else 0.0,
            "time": -0.01,
        }
        evidence = {
            "environment_digest": self.spec.environment_digest,
            "episode_seed": self._seed,
            "engine_seed": self._engine_seed,
            "index": len(self._actions_taken),
            "action": action,
            "accepted": invalid is None,
            "error_type": invalid,
            "accepted_game_actions": len(current["actions"]),
            "source_session_digest_before": previous_receipt["digest"],
            "source_session_digest_after": current["digest"],
            "observed": dict(self._observation),
            "reward_components": rewards,
            "terminated": self._terminated,
            "truncated": self._truncated,
            "previous_transition_digest": self._chain,
        }
        self._chain = _digest(evidence)
        return EpisodeStep(
            dict(self._observation),
            rewards,
            self._terminated,
            self._truncated,
            {
                "runtime_kind": "original_game_reference_runtime",
                "evidence": evidence,
                "native_hardware_verified": False,
            },
            self._chain,
        )

    def preview(self) -> dict[str, object] | None:
        if self._receipt is None:
            return None
        state = self._receipt["state"]
        # State projection, not invented pixels or audio; genuine emulator
        # visuals remain owned by the native emulator environment.
        view = {}
        for name in (
            "tick",
            "turn",
            "round",
            "x",
            "y",
            "score",
            "health",
            "credits",
            "gold",
            "cargo",
            "market",
            "position",
            "player",
            "finished",
            "failed",
        ):
            value = state.get(name)
            if type(value) in (str, int, float, bool, list) and len(_json(value)) < 512:
                view[name] = _plain(value)
        frame = {
            "schema_version": "skeleton.game_builder.policy_preview.v1",
            "runtime_kind": "original_game_reference_runtime",
            "editor": self.editor,
            "step": len(self._actions_taken),
            "session_digest": self._receipt["digest"],
            "state": view,
            "pixel_frame_available": False,
            "audio_frame_available": False,
            "game_success_measured_only_from_runtime_state": True,
        }
        telemetry = render_studio_state_telemetry(
            self.editor,
            self._observation,
            state,
            source_session_digest=self._receipt["digest"],
            accepted_action_count=len(self._receipt["trace"]),
        )
        frame.update(telemetry)
        frame["pixel_frame_available"] = False
        frame["telemetry_raster_available"] = True
        scene = render_studio_scene(
            self.editor, state, self.settings, source_session_digest=self._receipt["digest"]
        )
        if scene is not None:
            frame.update(scene)
            frame["pixel_frame_available"] = True
            frame["telemetry_raster_available"] = False
            frame.pop("pixels_base64", None)
            frame["controls"] = list(self.actions)
        frame["attempted_action_count"] = len(self._actions_taken)
        frame["last_action_accepted"] = self._invalid is None
        _json(frame, MAX_PREVIEW_BYTES)
        return frame

    def snapshot(self) -> dict[str, object]:
        if self._receipt is None or self._seed is None:
            raise StudioEnvironmentError("reset before snapshotting")
        result = {
            "schema_version": SNAPSHOT_SCHEMA,
            "environment_digest": self.spec.environment_digest,
            "seed": self._seed,
            "engine_seed": self._engine_seed,
            "actions": list(self._actions_taken),
            "source_session_digest": self._receipt["digest"],
            "source_head_digest": self._receipt["head_digest"],
            "observation": dict(self._observation),
            "invalid_action": self._invalid,
            "terminated": self._terminated,
            "truncated": self._truncated,
            "transition_digest": self._chain,
        }
        _json(result)
        return {**result, "digest": _digest(result)}

    def restore(self, snapshot: Mapping[str, object]) -> Mapping[str, float]:
        if (
            not isinstance(snapshot, Mapping)
            or set(snapshot)
            != {
                "schema_version",
                "environment_digest",
                "seed",
                "engine_seed",
                "actions",
                "source_session_digest",
                "source_head_digest",
                "observation",
                "invalid_action",
                "terminated",
                "truncated",
                "transition_digest",
                "digest",
            }
            or snapshot["schema_version"] != SNAPSHOT_SCHEMA
        ):
            raise StudioEnvironmentError("invalid exact studio policy snapshot schema")
        _json(snapshot)
        payload = {key: value for key, value in snapshot.items() if key != "digest"}
        if (
            _digest(payload) != snapshot["digest"]
            or snapshot["environment_digest"] != self.spec.environment_digest
        ):
            raise StudioEnvironmentError("foreign or modified studio snapshot")
        commands = snapshot["actions"]
        if (
            type(commands) is not list
            or len(commands) > self.max_steps
            or any(type(cmd) is not str or cmd not in self.actions for cmd in commands)
        ):
            raise StudioEnvironmentError("invalid bounded studio action replay")
        candidate = type(self)(self.source, max_steps=self.max_steps)
        candidate.reset(snapshot["seed"])
        for command in commands:
            if candidate.done:
                raise StudioEnvironmentError("snapshot action log continued beyond terminal state")
            candidate.step(command)
        if candidate.snapshot() != _plain(snapshot):
            raise StudioEnvironmentError("snapshot state differs from independently executed game")
        self.__dict__.update(candidate.__dict__)
        return dict(self._observation)

    def close(self) -> None:
        self._receipt = None
        self._observation = None
        self._seed = None


def studio_source_target(tree: Mapping[str, str]) -> str:
    """Resolve an admitted studio engine without a console-target fallback."""
    source = _parse_tree(tree)
    return "studio:" + source["editor"]


def _parse_tree(tree: Mapping[str, str]) -> dict[str, object]:
    if (
        not isinstance(tree, Mapping)
        or set(tree) != {"game/studio/session.json"}
        or not isinstance(tree["game/studio/session.json"], str)
    ):
        raise StudioEnvironmentError("exact original-game learning source tree required")
    encoded = tree["game/studio/session.json"].encode("utf-8")
    if len(encoded) > MAX_SOURCE_BYTES:
        raise StudioEnvironmentError("studio source file exceeds byte budget")

    def pairs(rows):
        result = {}
        for key, value in rows:
            if key in result:
                raise StudioEnvironmentError("duplicate original studio source key")
            result[key] = value
        return result

    try:
        source = json.loads(
            encoded,
            object_pairs_hook=pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(StudioEnvironmentError("nonfinite studio source")),
        )
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise StudioEnvironmentError("invalid bounded original studio JSON") from exc
    return parse_studio_source(source)


def create_studio_game_environment(
    tree: Mapping[str, str], *, target_id: str, max_steps: int = 64
) -> StudioGameEnvironment:
    source = _parse_tree(tree)
    if target_id != "studio:" + source["editor"]:
        raise StudioEnvironmentError("requested engine identity differs from original source")
    return StudioGameEnvironment(source, max_steps=max_steps)


__all__ = [
    "SNAPSHOT_SCHEMA",
    "SOURCE_SCHEMA",
    "StudioEnvironmentError",
    "StudioGameEnvironment",
    "create_studio_game_environment",
    "make_studio_source",
    "parse_studio_source",
    "studio_request_tree",
    "studio_source_target",
]
