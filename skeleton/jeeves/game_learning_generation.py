"""Original bounded game projects driven by grounded features and local policy.

Console profiles constrain the existing compiled engine planes. The playable
output is an original portable browser game, not a cartridge or a console
binary. Source bundles contribute descriptive features, never uploaded bytes,
code, art, or music. Tenant ownership and current rights belong to the backend
admission owner, not to this pure generator.
"""

from __future__ import annotations

import base64
import colorsys
import hashlib
import html
import json
import math
import random
import re
import struct
import zlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from skeleton.forge.eras import ERA_IDS, era_pack

from .game_console_catalog import resolve_console
from .game_engine_assets import AssetKind, SourceAsset, asset_policy
from .game_engine_lab import (
    EngineEra,
    GameEngineLabError,
    SandboxPatch,
    VirtualFileTree,
    engine_era_profile,
)
from .game_engine_physics import (
    BodyRecipe,
    PhysicsSceneSource,
    ShapeKind,
    Vec3,
    physics_policy,
)
from .game_engine_project import ExecutableGameProjectLab, GameProjectSandbox
from .game_engine_scripts import ScriptInstruction, ScriptOp, ScriptSource

GENERATION_SCHEMA = "skeleton.game_generation.v1"
GAME_CONFIG_SCHEMA = "skeleton.original_portable_game.v1"
MAX_SOURCE_FEATURE_BYTES = 131_072
MAX_SOURCES = 64
GENERATED_PREFIX = "game/generated/"
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")

_FAMILIES = {
    "extraction_now": "adventure",
    "soulslike": "arena",
    "boomer_shooter": "arena",
    "arcade_golden_age": "arena",
    "cozy_wholesome": "adventure",
    "modern_aaa": "adventure",
    "horror_survival": "adventure",
    "indie_experimental": "puzzle",
    "metroidvania": "platformer",
    "roguelike": "adventure",
    "jrpg": "tactics",
    "crpg": "tactics",
    "immersive_sim": "adventure",
    "stealth": "adventure",
    "tactics_grid": "tactics",
    "fighting_game": "arena",
    "bullet_heaven": "arena",
    "deckbuilder": "cards",
    "battle_royale": "arena",
    "mmorpg": "adventure",
    "visual_novel": "story",
    "walking_sim": "adventure",
    "grand_strategy": "management",
    "city_builder": "management",
}
_ALIASES = {
    "platformer": "metroidvania",
    "arena": "arcade_golden_age",
    "adventure": "immersive_sim",
    "runner": "arcade_golden_age",
    "tactics": "tactics_grid",
    "puzzle": "indie_experimental",
    "story": "visual_novel",
    "management": "city_builder",
    "cards": "deckbuilder",
}
_OVERRIDES = {
    "speed": (1.0, 8.0),
    "enemy_count": (0, 24),
    "pickup_count": (1, 24),
    "health": (1, 10),
    "time_limit": (20, 600),
    "wall_density": (0.0, 0.25),
}


def _canonical(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError, RecursionError) as exc:
        raise GameEngineLabError("game generation input must be finite canonical JSON") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _bounded_json(value: Any, *, limit: int, name: str) -> Any:
    # Reject recursive and pathological container graphs before serialisation.
    stack = [(value, 0)]
    nodes = 0
    while stack:
        node, depth = stack.pop()
        nodes += 1
        if nodes > 16_384 or depth > 12:
            raise GameEngineLabError(f"{name} exceeds structural bounds")
        if isinstance(node, Mapping):
            if len(node) > 4096 or any(not isinstance(key, str) for key in node):
                raise GameEngineLabError(f"{name} has invalid object keys")
            stack.extend((child, depth + 1) for child in node.values())
        elif isinstance(node, (list, tuple)):
            if len(node) > 4096:
                raise GameEngineLabError(f"{name} exceeds sequence bounds")
            stack.extend((child, depth + 1) for child in node)
        elif isinstance(node, str):
            if len(node.encode("utf-8")) > limit:
                raise GameEngineLabError(f"{name} contains oversized text")
        elif node is not None and type(node) not in (bool, int, float):
            raise GameEngineLabError(f"{name} contains unsupported values")
    encoded = _canonical(value)
    if len(encoded.encode("utf-8")) > limit:
        raise GameEngineLabError(f"{name} exceeds byte bound")
    return json.loads(encoded)


@dataclass(frozen=True, slots=True)
class GameGenerationRequest:
    project_id: str
    title: str
    engine_era: EngineEra | str
    genre: str = "arcade_golden_age"
    seed: int = 1
    hardware_target: str | None = None
    complexity: int = 2
    design_overrides: Mapping[str, int | float] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.project_id, str) or not _ID.fullmatch(self.project_id):
            raise GameEngineLabError("project id must be bounded and path-safe")
        if (
            not isinstance(self.title, str)
            or not 1 <= len(self.title) <= 120
            or any(ord(char) < 32 for char in self.title)
        ):
            raise GameEngineLabError("title must be 1..120 printable characters")
        if type(self.seed) is not int or not 0 <= self.seed <= 0xFFFFFFFF:
            raise GameEngineLabError("game seed must be an unsigned 32-bit integer")
        if type(self.complexity) is not int or not 1 <= self.complexity <= 5:
            raise GameEngineLabError("game complexity must be within [1, 5]")
        target = resolve_console(self.engine_era)
        object.__setattr__(self, "engine_era", target.era)
        if self.hardware_target is not None:
            hardware = resolve_console(self.hardware_target)
            if hardware.era != target.era:
                raise GameEngineLabError("hardware target and engine era must match")
            object.__setattr__(self, "hardware_target", hardware.target_id)
        if not isinstance(self.genre, str) or self.genre not in set(ERA_IDS) | set(_ALIASES):
            raise GameEngineLabError("genre must name a registered Forge dialect or supported controller")
        overrides = self.design_overrides or {}
        if not isinstance(overrides, Mapping) or len(overrides) > len(_OVERRIDES):
            raise GameEngineLabError("design overrides must be a bounded object")
        clean: dict[str, int | float] = {}
        for key, value in overrides.items():
            if key not in _OVERRIDES or type(value) not in (int, float):
                raise GameEngineLabError("unsupported or non-finite design override")
            low, high = _OVERRIDES[key]
            if not low <= value <= high or not math.isfinite(value):
                raise GameEngineLabError(f"{key} override exceeds supported range")
            if key not in {"speed", "wall_density"} and type(value) is not int:
                raise GameEngineLabError(f"{key} override must be an integer")
            clean[key] = value
        # A detached immutable JSON representation prevents mutation after admission.
        from types import MappingProxyType

        object.__setattr__(self, "design_overrides", MappingProxyType(clean))

    def as_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "title": self.title,
            "engine_era": self.engine_era.value,
            "genre": self.genre,
            "seed": self.seed,
            "hardware_target": self.hardware_target,
            "complexity": self.complexity,
            "design_overrides": dict(self.design_overrides or {}),
        }


def _source_features(values: Iterable[Any]) -> tuple[dict[str, Any], ...]:
    sources: list[dict[str, Any]] = []
    total = 0
    seen: set[tuple[str, str]] = set()
    for index, value in enumerate(values):
        if index >= MAX_SOURCES:
            raise GameEngineLabError("game source feature count exceeds limit")
        if hasattr(value, "to_dict"):
            value = value.to_dict()
        if not isinstance(value, Mapping):
            raise GameEngineLabError("game sources must be ingested feature objects")
        source_id = value.get("bundle_id", value.get("source_id"))
        if not isinstance(source_id, str) or not 1 <= len(source_id) <= 256:
            raise GameEngineLabError("source feature bundle identity is required")
        source_digest = value.get("source_digest", value.get("content_digest"))
        bundle_digest = value.get("bundle_digest", source_digest)
        if any(
            not isinstance(item, str) or not _SHA.fullmatch(item) for item in (source_digest, bundle_digest)
        ):
            raise GameEngineLabError("source and bundle SHA-256 identities are required")
        identity = (source_id, bundle_digest)
        if identity in seen:
            raise GameEngineLabError("source bundle identities must be unique")
        seen.add(identity)
        features = _bounded_json(value.get("features", {}), limit=16_384, name="source features")
        if not isinstance(features, dict):
            raise GameEngineLabError("source features must be an object")
        # Deliberately exclude documents, assets, original source/ROM bytes and
        # free-form source text. Only classified feature evidence is projected.
        clean_features: dict[str, Any] = {}
        for kind in ("genres", "mechanics"):
            entries = features.get(kind, [])
            if not isinstance(entries, list) or len(entries) > 64:
                raise GameEngineLabError("source cue sequence exceeds limit")
            clean_entries = []
            for entry in entries:
                if not isinstance(entry, dict):
                    raise GameEngineLabError("source cues must include classified evidence")
                text = entry.get("value")
                evidence = entry.get("evidence_ref")
                classification = entry.get("classification")
                if (
                    not isinstance(text, str)
                    or not 1 <= len(text) <= 80
                    or not isinstance(evidence, str)
                    or not 1 <= len(evidence) <= 2048
                    or classification not in {"declared", "lexical_cue"}
                ):
                    raise GameEngineLabError("source cue classification or evidence is invalid")
                clean_entries.append(
                    {"value": text, "evidence_ref": evidence, "classification": classification}
                )
            clean_features[kind] = clean_entries
        project = features.get("project", {})
        if not isinstance(project, dict):
            raise GameEngineLabError("source project features must be an object")
        dimension_evidence = project.get("map_dimensions")
        dimensions = dimension_evidence.get("value") if isinstance(dimension_evidence, dict) else None
        if (
            isinstance(dimensions, (list, tuple))
            and len(dimensions) in (2, 3)
            and all(type(item) is int and 1 <= item <= 4096 for item in dimensions)
        ):
            classification = dimension_evidence.get("classification")
            evidence_ref = dimension_evidence.get("evidence_ref")
            if (
                classification != "declared"
                or not isinstance(evidence_ref, str)
                or not 1 <= len(evidence_ref) <= 2048
            ):
                raise GameEngineLabError("map dimension feature lacks declared evidence")
            clean_features["project"] = {
                "map_dimensions": {
                    "value": dimensions[:2],
                    "classification": classification,
                    "evidence_ref": evidence_ref,
                }
            }
        sources.append(
            {
                "bundle_id": source_id,
                "source_digest": source_digest,
                "bundle_digest": bundle_digest,
                "source_kind": str(value.get("source_kind", "feature_metadata"))[:80],
                "features": clean_features,
            }
        )
        total += len(_canonical(sources[-1]).encode("utf-8"))
        if total > MAX_SOURCE_FEATURE_BYTES:
            raise GameEngineLabError("source feature corpus exceeds byte bound")
    return tuple(sorted(sources, key=lambda item: (item["bundle_id"], item["bundle_digest"])))


def _policy_snapshot(policy: Any) -> tuple[Any, dict[str, Any] | None]:
    if policy is None:
        return None, None
    from .game_learning import GamePolicyLearner

    if isinstance(policy, Mapping):
        snapshot = _bounded_json(policy, limit=128_000, name="learned policy")
        learner = GamePolicyLearner.from_snapshot(snapshot)
    elif isinstance(policy, GamePolicyLearner):
        learner = policy
        snapshot = _bounded_json(learner.snapshot(), limit=128_000, name="learned policy")
        # Reload through the authoritative learner validator rather than trust
        # an arbitrary object implementing predict/snapshot.
        learner = GamePolicyLearner.from_snapshot(snapshot)
    else:
        raise GameEngineLabError("generation policy must be the local measured GamePolicyLearner")
    if snapshot.get("committed_updates", 0) < 1 or snapshot.get("committed_episodes", 0) < 1:
        raise GameEngineLabError("generation policy must contain actual committed learning updates")
    return learner, snapshot


def _design(
    request: GameGenerationRequest,
    sources: tuple[dict[str, Any], ...],
    learner: Any,
    policy_environment: Any = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    dialect = _ALIASES.get(request.genre, request.genre)
    family = "runner" if request.genre == "runner" else _FAMILIES[dialect]
    pack = era_pack(dialect)
    feature_digest = _digest(sources)
    rng = random.Random(
        _digest(
            {
                "seed": request.seed,
                "era": request.engine_era.value,
                "genre": request.genre,
                "features": feature_digest,
            }
        )
    )
    width, height = 20 + request.complexity * 2, 12 + request.complexity
    cues = {
        entry["value"].lower().replace("-", "_").replace(" ", "_")
        for source in sources
        for kind in ("genres", "mechanics")
        for entry in source["features"].get(kind, [])
    }
    map_dimensions = [
        source["features"]["project"]["map_dimensions"]["value"]
        for source in sources
        if "project" in source["features"]
    ]
    if map_dimensions:
        # Preserve only coarse aspect ratio, never imported map layout.
        dw, dh = map_dimensions[0]
        width = max(16, min(30, round(height * dw / dh)))
    values: dict[str, Any] = {
        "speed": round(max(1.5, min(6.0, float(pack["player"]["speed"]) / 65)), 3),
        "enemy_count": min(18, 2 + request.complexity * 2),
        "pickup_count": 3 + request.complexity,
        "health": max(1, min(8, round(float(pack["player"]["max_health"]) / 35))),
        "time_limit": 90 + request.complexity * 30,
        "wall_density": round(0.035 + request.complexity * 0.015, 3),
    }
    influence = []
    if cues & {"stealth", "avoidance", "sneaking"}:
        values["enemy_count"] = max(1, values["enemy_count"] - 2)
        influence.append("classified avoidance cues reduce enemy density")
    if cues & {"collect", "collection", "crafting", "exploration", "quest"}:
        values["pickup_count"] += 2
        influence.append("classified collection cues increase original collectible goals")
    if cues & {"platformer", "jump", "jumping", "metroidvania"} and family == "platformer":
        values["wall_density"] *= 0.65
        influence.append("classified jumping cues widen original platform routes")
    if dialect in {
        "cozy_wholesome",
        "walking_sim",
        "visual_novel",
        "city_builder",
        "grand_strategy",
        "deckbuilder",
        "indie_experimental",
    }:
        values["enemy_count"] = 0
    if family in {"puzzle", "story", "management", "cards"}:
        values["health"] = 5
    values.update(request.design_overrides or {})
    profile = engine_era_profile(request.engine_era)
    values["enemy_count"] = min(
        values["enemy_count"], max(0, profile.entity_budget - values["pickup_count"] - 4), 24
    )
    policy_evidence: dict[str, Any] = {
        "mode": "seeded_untrained",
        "design_role": "Forge mechanics and classified source cues",
    }
    if learner is not None:
        policy_evidence = _probe_policy(learner, request, policy_environment)
        # Adapt actual density to the measured control return. The Q-table does
        # not predict genres: it predicts actions in its admitted environment.
        signal = policy_evidence.get("probe_return_scaled_design_signal", 0.0)
        values["enemy_count"] = min(24, max(0, round(values["enemy_count"] * (0.65 + 0.35 * signal))))
        values["health"] = min(10, max(1, round(values["health"] * (1.2 - 0.4 * signal))))
        values["time_limit"] = min(600, max(20, round(values["time_limit"] * (1.15 - 0.3 * signal))))
        influence.append(
            "actual learned-policy return adjusts bounded enemy density, health and task duration"
        )
    spawn = [1, height - 2] if family in {"platformer", "runner"} else [1, 1]
    goal = [width - 2, height - 2]
    walls = [
        [x, y] for y in range(height) for x in range(width) if x in (0, width - 1) or y in (0, height - 1)
    ]
    protected = (
        {(x, spawn[1]) for x in range(1, width - 1)}
        | {(width - 2, y) for y in range(1, height - 1)}
        | {(1, y) for y in range(1, height - 1)}
    )
    for y in range(2, height - 2):
        for x in range(2, width - 2):
            if (x, y) not in protected and rng.random() < values["wall_density"]:
                walls.append([x, y])
    if family in {"platformer", "runner"}:
        walls = (
            [[x, height - 1] for x in range(width)]
            + [[0, y] for y in range(height)]
            + [[width - 1, y] for y in range(height)]
        )
        for x in range(4, width - 4, 5):
            walls.extend([[x + offset, height - 4 - (x // 5) % 3] for offset in range(3)])
    blocked = {tuple(cell) for cell in walls} | {tuple(spawn), tuple(goal)}
    free = [[x, y] for y in range(1, height - 1) for x in range(1, width - 1) if (x, y) not in blocked]
    if family in {"platformer", "runner"}:
        free = [[x, height - 2] for x in range(3, width - 3)]
    else:
        # Mandatory collectibles cannot be trapped in random wall islands.
        reachable = {tuple(spawn)}
        queue = [tuple(spawn)]
        wall_cells = {tuple(cell) for cell in walls}
        for x, y in queue:
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                cell = (x + dx, y + dy)
                if (
                    0 < cell[0] < width - 1
                    and 0 < cell[1] < height - 1
                    and cell not in wall_cells
                    and cell not in reachable
                ):
                    reachable.add(cell)
                    queue.append(cell)
        free = [cell for cell in free if tuple(cell) in reachable]
    rng.shuffle(free)
    puzzle_switches = [list(cell) for cell in free[:3]]
    puzzle_target = [rng.randrange(2) for _ in range(3)]
    if puzzle_target == [0, 0, 0]:
        puzzle_target[rng.randrange(3)] = 1
    pickups = free[: values["pickup_count"]]
    enemies = [
        {
            "id": f"guardian_{index}",
            "x": cell[0],
            "y": cell[1],
            "phase": rng.randrange(4),
            "health": 2 if dialect == "soulslike" else 1,
        }
        for index, cell in enumerate(
            free[values["pickup_count"] : values["pickup_count"] + values["enemy_count"]]
        )
    ]
    hue = rng.randrange(360)
    palette = {
        "background": f"hsl({hue},35%,9%)",
        "walls": f"hsl({(hue+25)%360},35%,28%)",
        "player": f"hsl({(hue+165)%360},90%,70%)",
        "pickup": f"hsl({(hue+60)%360},90%,67%)",
        "enemy": f"hsl({(hue+270)%360},80%,63%)",
    }
    config = {
        "schema_version": GAME_CONFIG_SCHEMA,
        "project_id": request.project_id,
        "title": request.title,
        "seed": request.seed,
        "genre": dialect,
        "controller": family,
        "grid": {"width": width, "height": height, "walls": walls},
        "spawn": spawn,
        "goal": goal,
        "pickups": pickups,
        "enemies": enemies,
        "palette": palette,
        "mechanics": {
            **values,
            "attack": family in {"arena", "adventure", "platformer", "tactics"}
            and dialect not in {"walking_sim", "cozy_wholesome", "stealth"},
            "turn_based": family in {"tactics", "cards"},
            "auto_attack": dialect == "bullet_heaven",
            "shrinking_arena": dialect == "battle_royale",
            "stealth": dialect in {"stealth", "horror_survival"},
            "keys_required": family in {"adventure", "platformer", "runner"},
            "permadeath": float(pack["meta"].get("permadeath", 0.0)) >= 0.8,
            "resource_growth": family == "management",
        },
        "story": [
            {
                "speaker": "Caretaker",
                "text": f"An original expedition through sector {rng.randrange(100, 999)}. Choose a route and gather the scattered signals.",
                "choices": ["Restore the beacon", "Chart a new path"],
            },
            {
                "speaker": "Navigator",
                "text": "Your choice changes the reserve available for the final crossing.",
                "choices": ["Spend a reserve", "Keep a reserve"],
            },
            {
                "speaker": "Caretaker",
                "text": "The expedition leaves a new signal for the next traveler.",
                "choices": ["Complete the expedition"],
            },
        ],
        "cards": [
            {"name": "Pulse", "cost": 1, "damage": 3, "guard": 0},
            {"name": "Shelter", "cost": 1, "damage": 0, "guard": 3},
            {"name": "Surge", "cost": 2, "damage": 5, "guard": 0},
        ],
        "puzzle": {"switches": puzzle_switches, "target": puzzle_target},
        "source_feature_digest": feature_digest,
        "feature_influence": influence,
        "policy_evidence": policy_evidence,
    }
    return config, policy_evidence


def _probe_policy(
    learner: Any, request: GameGenerationRequest, supplied_environment: Any = None
) -> dict[str, Any]:
    # The runtime owner supplies the exact observed environment, not fabricated
    # observation dictionaries or caller-provided control scores.
    from .game_learning import GamePolicyLearner
    from .game_learning_runtime import GameLearningEnvironment

    snapshot = learner.snapshot()
    spec = snapshot.get("environment")
    if not isinstance(spec, Mapping):
        raise GameEngineLabError("learned policy lacks its admitted environment spec")
    if supplied_environment is not None:
        permitted_types = (GameLearningEnvironment, GeneratedGameEnvironment)
        try:
            from .game_rom_runtime import GameBoyROMEnvironment

            permitted_types += (GameBoyROMEnvironment,)
        except ImportError:
            pass
        try:
            from .game_dragon_runtime import DragonThumbyEnvironment

            permitted_types += (DragonThumbyEnvironment,)
        except ImportError:
            pass
        if type(supplied_environment) not in permitted_types:
            raise GameEngineLabError("policy probe requires a genuine existing environment owner")
        environment = supplied_environment
    else:
        environment = None
        for dialect in (None, _ALIASES.get(request.genre, request.genre)):
            candidate = GameLearningEnvironment(
                spec["environment_id"], max_steps=spec["max_episode_steps"], gameplay_dialect=dialect
            )
            if candidate.spec.as_dict() == spec:
                environment = candidate
                break
        if environment is None:
            raise GameEngineLabError("policy requires its exact admitted project environment for generation")
    # Revalidate the genuine environment and policy together before any step.
    learner = GamePolicyLearner.from_snapshot(snapshot, expected_spec=environment.spec)
    reference_target = (
        environment.target
        if isinstance(environment, GeneratedGameEnvironment)
        else resolve_console(
            "game_boy" if spec["environment_id"].startswith("game_boy:rom:") else spec["environment_id"]
        )
    )
    if reference_target.era != request.engine_era:
        raise GameEngineLabError("learned policy engine era does not match generated project")
    observation = environment.reset(request.seed)
    actions = []
    reward = 0.0
    done = False
    for _ in range(128):
        choice = learner.predict(observation)
        action = choice["action"]
        transition = environment.step(action)
        observation = transition.observation
        reward += sum(transition.reward_components.values())
        actions.append(
            {"action": action, "state": choice["state"], "observation_digest": _digest(dict(observation))}
        )
        done = transition.terminated or transition.truncated
        if done:
            break
    return {
        "mode": "measured_tabular_control",
        "policy_digest": snapshot["snapshot_digest"],
        "environment_spec_digest": _digest(spec),
        "probe_seed": request.seed,
        "probe_steps": len(actions),
        "probe_return": round(reward, 8),
        "probe_return_scaled_design_signal": max(0.0, min(1.0, reward)),
        "design_signal_definition": "clamp(actual admitted-task return, 0, 1); not a success probability",
        "probe_trace_digest": _digest(actions),
        "probe_action_histogram": {
            action: sum(row["action"] == action for row in actions) for action in spec["actions"]
        },
        "design_role": "actual learned control in its original environment adapts generated enemy density",
        "measurement_scope": "original admitted reference/ROM task; generated browser game is a distinct unmeasured controller",
    }


def _compiled_project(request: GameGenerationRequest, config: Mapping[str, Any]) -> GameProjectSandbox:
    era = request.engine_era
    ap = asset_policy(era)
    kind = (
        AssetKind.PRIMITIVE
        if AssetKind.PRIMITIVE in ap.allowed
        else AssetKind.SPRITE if AssetKind.SPRITE in ap.allowed else ap.allowed[0]
    )
    fingerprint = _digest(config)
    assets = tuple(
        SourceAsset(
            f"original_{name}_{fingerprint[:8]}",
            kind,
            width=16,
            height=16,
            colors=min(ap.palette_limit, 4),
            metadata=(("generation", fingerprint), ("role", name), ("source_copy", "false")),
        )
        for name in ("traveler", "guardian", "signal")
    )
    movement = ScriptSource(
        "original_movement",
        (
            ScriptInstruction(ScriptOp.LOAD_STATE, (0, 0)),
            ScriptInstruction(ScriptOp.CONST, (1, config["mechanics"]["speed"])),
            ScriptInstruction(ScriptOp.ADD, (0, 0, 1)),
            ScriptInstruction(ScriptOp.STORE_STATE, (0, 0)),
            ScriptInstruction(ScriptOp.EMIT, ("original_move", 0)),
            ScriptInstruction(ScriptOp.HALT),
        ),
    )
    pp = physics_policy(era)
    z = 0.0 if pp.dimensions == 2 else 50.0
    physics = PhysicsSceneSource(
        Vec3(100.0, 100.0, 100.0),
        Vec3(0.0, -9.8 if config["controller"] in {"platformer", "runner"} else 0.0, 0.0),
        (
            BodyRecipe(
                "original_floor",
                ShapeKind.AABB,
                Vec3(50.0, 5.0, z),
                half_extent=Vec3(50.0, 5.0, 50.0),
                static=True,
                friction=0.6,
            ),
            BodyRecipe(
                "original_traveler",
                ShapeKind.AABB,
                Vec3(20.0, 25.0, z),
                Vec3(config["mechanics"]["speed"], 0.0, 0.0),
                half_extent=Vec3(1.0, 1.0, 1.0),
            ),
            BodyRecipe(
                "original_guardian",
                ShapeKind.AABB,
                Vec3(70.0, 25.0, z),
                Vec3(-1.0, 0.0, 0.0),
                half_extent=Vec3(1.0, 1.0, 1.0),
            ),
        ),
    )
    return ExecutableGameProjectLab().create(
        era, _ALIASES.get(request.genre, request.genre), sources=assets, scripts=(movement,), physics=physics
    )


@dataclass(frozen=True, slots=True)
class GeneratedGameProject:
    sandbox: GameProjectSandbox
    request: GameGenerationRequest
    _manifest_json: str
    _config_json: str
    _sources_json: str
    _policy_json: str

    @property
    def tree(self) -> VirtualFileTree:
        return self.sandbox.tree

    @property
    def manifest(self) -> dict[str, Any]:
        return json.loads(self._manifest_json)

    @property
    def config(self) -> dict[str, Any]:
        return json.loads(self._config_json)

    @property
    def novelty_fingerprint(self) -> str:
        return self.manifest["novelty_fingerprint"]

    @property
    def source_lineage(self) -> list[dict[str, Any]]:
        return self.manifest["source_lineage"]

    def as_dict(self, *, include_files: bool = False) -> dict[str, Any]:
        result = {
            "schema_version": GENERATION_SCHEMA,
            "project_id": self.request.project_id,
            "title": self.request.title,
            "tree_digest": self.tree.digest,
            "novelty_fingerprint": self.novelty_fingerprint,
            "manifest": self.manifest,
            "config": self.config,
            "files": [
                {"path": path, "bytes": len(content.encode("utf-8")), "digest": self.tree.file_digest(path)}
                for path, content in sorted(self.tree.files.items())
            ],
        }
        if include_files:
            result["file_contents"] = dict(self.tree.files)
        return result

    def snapshot(self) -> dict[str, Any]:
        body = {
            "schema_version": GENERATION_SCHEMA,
            "request": self.request.as_dict(),
            "source_features": json.loads(self._sources_json),
            "policy": json.loads(self._policy_json),
            "tree_digest": self.tree.digest,
            "novelty_fingerprint": self.novelty_fingerprint,
        }
        return {**body, "digest": _digest(body)}

    def build_package(self):
        """Use the existing measured project-quality/package owner on demand.

        Generation itself never runs or fabricates that quality gate. The
        portable browser renderer is explicitly outside those measured planes.
        """
        from .game_engine_export import build_project_package

        return build_project_package(self.sandbox, require_quality=True)

    def archive(self):
        from .game_engine_export import archive_project_package

        return archive_project_package(self.build_package())


def generate_game_project(
    request: GameGenerationRequest | Mapping[str, Any],
    *,
    policy: Any = None,
    source_features: Iterable[Any] = (),
    policy_environment: Any = None,
) -> GeneratedGameProject:
    if isinstance(request, Mapping):
        request = GameGenerationRequest(**request)
    if not isinstance(request, GameGenerationRequest):
        raise GameEngineLabError("game generation requires a typed request")
    sources = _source_features(source_features)
    learner, snapshot = _policy_snapshot(policy)
    config, policy_evidence = _design(request, sources, learner, policy_environment)
    sprite = _sprite_svg(config)
    novelty = _digest(
        {
            "controller": config["controller"],
            "grid": config["grid"],
            "spawn": config["spawn"],
            "goal": config["goal"],
            "pickups": config["pickups"],
            "enemies": config["enemies"],
            "mechanics": config["mechanics"],
            "palette": config["palette"],
            "story": config["story"],
            "cards": config["cards"],
            "puzzle": config["puzzle"],
            "sprite_digest": hashlib.sha256(sprite.encode("utf-8")).hexdigest(),
        }
    )
    lineage = [
        {
            "bundle_id": source["bundle_id"],
            "bundle_digest": source["bundle_digest"],
            "source_digest": source["source_digest"],
            "feature_digest": _digest(source["features"]),
        }
        for source in sources
    ]
    target = resolve_console(request.hardware_target or request.engine_era)
    native_files, native_manifest = _native_source_output(request, config, novelty)
    manifest = {
        "schema_version": GENERATION_SCHEMA,
        "request": request.as_dict(),
        "engine_era": request.engine_era.value,
        "hardware_target": target.as_dict(),
        "actual_output": {
            "runtime": "original_portable_browser_2d",
            "entrypoint": GENERATED_PREFIX + "index.html",
            "engine_planes": "existing era-compiled reference engine project",
            "native_console_binary": "original_dmg_maze" in native_manifest,
            "native_binary_encoding": "base64_text" if "original_dmg_maze" in native_manifest else None,
            "native_execution_checked": False,
            "uploaded_assets_or_code_copied": False,
        },
        "novelty_fingerprint": novelty,
        "novelty_claim": "deterministic identity of original generated mechanics/layout/art; not proof of global uniqueness",
        "source_lineage": lineage,
        "source_authority": "descriptive metadata only; current rights/tenant admission is required by backend",
        "policy_evidence": policy_evidence,
        "native_output": native_manifest,
        "quality": {
            "execution_checked": False,
            "existing_project_gate": "on explicit package export",
            "browser_execution_checked": False,
        },
        "limitations": [
            "Portable play uses a 2D controller even when the canonical engine era supports 3D",
            "Multiplayer, general commercial ROM emulation and uploaded-asset copying are not generated; native source needs its toolchain, and optional original DMG maze bytes remain unexecuted",
            "Learned control evidence does not imply trained genre classification",
        ],
    }
    project = _compiled_project(request, config)
    config_json = _canonical(config)
    files = {
        "game.json": config_json,
        "index.html": _game_html(request.title, config_json),
        "game.js": _BROWSER_RUNTIME,
        "sprites.svg": sprite,
        "simulation.py": _PORTABLE_SIMULATION,
        "manifest.json": _canonical(manifest),
        "README.md": _readme(request, config, native_manifest),
    }
    files.update(native_files)
    project = project.apply(SandboxPatch(GENERATED_PREFIX + path, content) for path, content in files.items())
    return GeneratedGameProject(
        project, request, _canonical(manifest), config_json, _canonical(sources), _canonical(snapshot)
    )


def _native_source_output(
    request: GameGenerationRequest, config: Mapping[str, Any], novelty: str
) -> tuple[dict[str, str], dict[str, Any]]:
    """Reuse the actual Dragon source emitters; never run a toolchain here."""
    if request.hardware_target is None:
        return {}, {"status": "not_requested", "binary_compiled": False}
    target = resolve_console(request.hardware_target)
    native_id = getattr(target, "native_target_id", None)
    if native_id is None:
        native_id = {"gbc": "game_boy_color", "gba": "game_boy_advance", "n64": "nintendo_64"}.get(
            target.target_id, target.target_id
        )
    result: dict[str, str] = {}
    manifest: dict[str, Any] = {
        "target_id": native_id,
        "status": "source_unavailable",
        "binary_compiled": False,
        "hardware_execution_checked": False,
        "requested_genre": config["genre"],
    }
    try:
        from skeleton.ai.webcrawler.dragon_game_mechanics import Mechanic
        from skeleton.ai.webcrawler.dragon_native_projects import (
            EMITTERS,
            render_native_project,
        )
        from skeleton.ai.webcrawler.dragon_native_targets import target_catalog

        row = next((item for item in target_catalog() if item["id"] == native_id), None)
        styles = set(row.get("supported_styles", ())) if row is not None else set()
        style_map = {
            "arcade_golden_age": "arcade_score_attack",
            "boomer_shooter": "first_person_shooter",
            "bullet_heaven": "bullet_hell",
            "metroidvania": "metroidvania",
            "roguelike": "roguelike",
            "cozy_wholesome": "cozy_farming",
            "horror_survival": "survival_horror",
            "immersive_sim": "immersive_sim",
            "tactics_grid": "tactical_rpg",
            "jrpg": "turn_based_rpg",
            "crpg": "turn_based_rpg",
            "indie_experimental": "fixed_screen_puzzle",
            "walking_sim": "top_down_adventure",
            "city_builder": "sandbox_builder",
            "grand_strategy": "real_time_strategy",
            "modern_aaa": "top_down_adventure",
            "extraction_now": "top_down_adventure",
            "stealth": "top_down_adventure",
        }
        style = style_map.get(config["genre"])
        adaptation = None
        if style not in styles:
            if config["controller"] == "platformer" and "side_scrolling_platformer" in styles:
                style = "side_scrolling_platformer"
                adaptation = (
                    "original side-scrolling platform prototype; no full metroidvania progression claim"
                )
            elif config["controller"] == "arena" and "arcade_score_attack" in styles:
                style = "arcade_score_attack"
                adaptation = (
                    "original collectible-chase prototype; full requested combat systems remain portable only"
                )
            else:
                style = None
        if native_id not in EMITTERS:
            manifest.update(
                status="native_emitter_unavailable", toolchain=row.get("toolchain") if row else None
            )
        elif style is None:
            manifest.update(status="requested_style_unavailable", supported_styles=sorted(styles))
        else:
            mechanics = [Mechanic.MOVEMENT, Mechanic.EXPLORATION]
            if config["mechanics"]["attack"]:
                mechanics.append(Mechanic.COMBAT)
            if config["controller"] == "platformer":
                mechanics.append(Mechanic.PLATFORMING)
            if config["controller"] == "puzzle":
                mechanics.append(Mechanic.PUZZLE)
            title = request.title.strip()[:80]
            native = render_native_project(
                title=title if len(title) >= 2 else "Original Game",
                target_id=native_id,
                style=style,
                candidate_id=novelty,
                mechanics=tuple(mechanics),
                authorized=True,
            )
            # Validate the entire emitted path/text graph with the existing
            # virtual tree owner before namespacing it into the game project.
            native_tree = VirtualFileTree(native.files)
            result.update(
                {"native/" + native_id + "/" + path: content for path, content in native_tree.files.items()}
            )
            manifest.update(
                status=native.status,
                source_digest=native.digest,
                source_tree_digest=native_tree.digest,
                native_project_id=native.project_id,
                style=style,
                adaptation=adaptation,
                toolchain=native.toolchain,
                expected_output_extension=native.output,
                supported_mechanics=list(native.supported_mechanics),
                deferred_mechanics=list(native.deferred_mechanics),
                source_files=len(native.files),
            )
    except ImportError:
        manifest.update(status="native_source_dependency_unavailable")
    except (ValueError, PermissionError) as exc:
        manifest.update(status="native_source_unavailable", reason=str(exc)[:256])
    # This separately declared local assembler produces actual original bytes.
    # Its small maze is an explicit adaptation, not the imported game's ROM.
    if native_id == "game_boy" and config["controller"] in {"adventure", "puzzle", "tactics"}:
        from .game_rom_generation import build_original_dmg_game

        cartridge = build_original_dmg_game(seed=request.seed ^ int(novelty[:8], 16), title=request.title)
        cartridge_tree = VirtualFileTree(cartridge["files"])
        for path, content in cartridge_tree.files.items():
            if not path.startswith(GENERATED_PREFIX):
                raise GameEngineLabError("original ROM adapter escaped generated file namespace")
            result[path.removeprefix(GENERATED_PREFIX)] = content
        manifest["original_dmg_maze"] = {
            **cartridge["manifest"],
            "rom_digest": cartridge["rom_digest"],
            "rom_bytes": cartridge["rom_bytes"],
            "hardware_execution_checked": False,
            "adaptation": "original seeded maze distinct from full portable genre rules",
        }
    return result, manifest


def restore_generated_project(
    snapshot: Mapping[str, Any], *, policy_environment: Any = None
) -> GeneratedGameProject:
    value = _bounded_json(snapshot, limit=350_000, name="generated project snapshot")
    expected = {
        "schema_version",
        "request",
        "source_features",
        "policy",
        "tree_digest",
        "novelty_fingerprint",
        "digest",
    }
    if not isinstance(value, dict) or set(value) != expected or value["schema_version"] != GENERATION_SCHEMA:
        raise GameEngineLabError("generated project snapshot schema is invalid")
    body = {key: child for key, child in value.items() if key != "digest"}
    if _digest(body) != value["digest"]:
        raise GameEngineLabError("generated project snapshot digest mismatch")
    project = generate_game_project(
        value["request"],
        policy=value["policy"],
        source_features=value["source_features"],
        policy_environment=policy_environment,
    )
    if (
        project.tree.digest != value["tree_digest"]
        or project.novelty_fingerprint != value["novelty_fingerprint"]
    ):
        raise GameEngineLabError("generated project replay identity mismatch")
    return project


def edit_generated_project(
    project: GeneratedGameProject,
    *,
    expected_tree_digest: str,
    changes: Mapping[str, Any],
    policy_environment: Any = None,
) -> GeneratedGameProject:
    """Apply bounded real design edits through a compare-and-swap rebuild."""
    if not isinstance(project, GeneratedGameProject) or project.tree.digest != expected_tree_digest:
        raise GameEngineLabError("generated project edit has stale tree identity")
    if (
        not isinstance(changes, Mapping)
        or not changes
        or set(changes) - {"title", "genre", "seed", "complexity", "design_overrides"}
    ):
        raise GameEngineLabError("unsupported generated project edit")
    request = {**project.request.as_dict(), **dict(changes)}
    return generate_game_project(
        request,
        policy=json.loads(project._policy_json),
        source_features=json.loads(project._sources_json),
        policy_environment=policy_environment,
    )


class GeneratedGameEnvironment:
    """Actual bounded generated-map rules, with replay-validated recovery.

    This environment uses discrete cell movement. It implements the original
    controller objectives directly, rather than pretending a fixed reference
    scene executes imported game maps or reproduces browser platform physics.
    """

    def __init__(
        self,
        target_id: str | EngineEra,
        config: Mapping[str, Any],
        *,
        max_steps: int = 512,
        tree_digest: str | None = None,
    ) -> None:
        from .game_learning_runtime import GameEnvironmentSpec

        self.target = resolve_console(target_id)
        if type(max_steps) is not int or not 1 <= max_steps <= 4096:
            raise GameEngineLabError("generated environment step limit is invalid")
        self.max_steps = max_steps
        self._config = _validate_game_config(config)
        self._wall_cells = frozenset(tuple(cell) for cell in self._config["grid"]["walls"])
        self.config_digest = _digest(self._config)
        if tree_digest is not None and (not isinstance(tree_digest, str) or not _SHA.fullmatch(tree_digest)):
            raise GameEngineLabError("generated environment tree identity is invalid")
        self.tree_digest = tree_digest
        self._code_digest = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        self._descriptor = {
            "schema_version": "skeleton.generated_game_environment.v1",
            "target_id": self.target.target_id,
            "engine_era": self.target.era.value,
            "runtime_kind": "original_generated_grid_simulation",
            "controller": self._config["controller"],
            "config_digest": self.config_digest,
            "tree_digest": tree_digest,
            "implementation_digest": self._code_digest,
            "max_episode_steps": max_steps,
            "execution_scope": "actual original generated discrete-grid rules; browser continuous physics is separate",
            "rom_execution": False,
            "full_hardware_emulation": False,
        }
        actions = ("noop", "left", "right", "up", "down", "interact")
        if self._config["controller"] == "cards":
            actions = ("noop", "card_1", "card_2", "card_3", "end_turn")
        elif self._config["controller"] == "story":
            actions = ("noop", "choice_1", "choice_2")
        thresholds = (-0.75, -0.5, -0.25, -0.1, 0.0, 0.1, 0.25, 0.5, 0.75)
        features = (
            "x",
            "z",
            "vx",
            "vz",
            "goal_dx",
            "goal_dz",
            "progress",
            "score",
            "alive",
            "health",
            "resources",
        )
        self.spec = GameEnvironmentSpec(
            "generated:" + self.target.target_id + ":" + self.config_digest[:24],
            _digest(self._descriptor),
            actions,
            {key: thresholds for key in features},
            ("progress", "score", "damage", "goal", "time"),
            max_steps,
        )
        self._seed: int | None = None
        self._state: dict[str, Any] | None = None
        self._actions: list[str] = []
        self._chain = ""
        self._rng = random.Random(0)

    @property
    def descriptor(self) -> dict[str, Any]:
        return {
            **self._descriptor,
            "environment_digest": self.spec.environment_digest,
            "spec": self.spec.as_dict(),
        }

    @property
    def done(self) -> bool:
        return bool(self._state is not None and (self._state["terminated"] or self._state["truncated"]))

    def _current(self) -> dict[str, Any]:
        if self._state is None:
            raise GameEngineLabError("reset the generated environment before observing")
        return self._state

    def _observe(self) -> dict[str, float]:
        s, c = self._current(), self._config
        width, height = c["grid"]["width"], c["grid"]["height"]
        family = c["controller"]
        if family == "story":
            progress = s["story"] / len(c["story"])
        elif family == "cards":
            progress = (16 - s["enemy_hp"]) / 16
        elif family == "management":
            progress = s["population"] / 6
        elif family == "puzzle":
            progress = (
                sum(left == right for left, right in zip(s["switches"], c["puzzle"]["target"], strict=True))
                / 3
            )
        elif family in {"arena", "tactics"}:
            progress = 1 - sum(enemy["live"] for enemy in s["enemies"]) / max(1, len(s["enemies"]))
        else:
            progress = 1 - len(s["pickups"]) / max(1, len(c["pickups"]))
        clamp = lambda value: max(-1.0, min(1.0, float(value)))
        return {
            "x": clamp(s["position"][0] * 2 / width - 1),
            "z": clamp(s["position"][1] * 2 / height - 1),
            "vx": clamp(s["delta"][0]),
            "vz": clamp(s["delta"][1]),
            "goal_dx": clamp((c["goal"][0] - s["position"][0]) / width),
            "goal_dz": clamp((c["goal"][1] - s["position"][1]) / height),
            "progress": clamp(progress),
            "score": clamp(s["score"] / 24),
            "alive": 1.0 if s["health"] > 0 else 0.0,
            "health": clamp(s["health"] / c["mechanics"]["health"]),
            "resources": clamp(s["resources"] / 20),
        }

    def reset(self, seed: int) -> dict[str, float]:
        if type(seed) is not int or not 0 <= seed <= 2**63 - 1:
            raise GameEngineLabError("generated episode seed is invalid")
        c = self._config
        self._seed, self._rng = seed, random.Random(seed)
        self._actions = []
        self._state = {
            "position": list(c["spawn"]),
            "delta": [0, 0],
            "health": c["mechanics"]["health"],
            "score": 0,
            "steps": 0,
            "pickups": [list(cell) for cell in c["pickups"]],
            "enemies": [
                {**enemy, "phase": (enemy["phase"] + self._rng.randrange(4)) % 4, "live": True}
                for enemy in c["enemies"]
            ],
            "energy": 3,
            "guard": 0,
            "enemy_hp": 16,
            "story": 0,
            "reserve": 0,
            "resources": 8,
            "population": 0,
            "buildings": [],
            "switches": [0, 0, 0],
            "terminated": False,
            "truncated": False,
            "won": False,
        }
        self._chain = _digest(
            {"environment_digest": self.spec.environment_digest, "seed": seed, "state": self._state}
        )
        return self._observe()

    def _blocked(self, cell: list[int]) -> bool:
        grid = self._config["grid"]
        return (
            not (0 <= cell[0] < grid["width"] and 0 <= cell[1] < grid["height"])
            or tuple(cell) in self._wall_cells
        )

    def _enemy_turn(self) -> None:
        s, c = self._current(), self._config
        for enemy in s["enemies"]:
            if not enemy["live"]:
                continue
            if (s["steps"] + enemy["phase"]) % 3 == 0:
                continue
            dx, dy = s["position"][0] - enemy["x"], s["position"][1] - enemy["y"]
            if c["mechanics"]["stealth"] and abs(dx) + abs(dy) > 4:
                direction = (s["steps"] // 2 + enemy["phase"]) % 4
                mx, my = ((1, 0), (0, 1), (-1, 0), (0, -1))[direction]
            elif abs(dx) > abs(dy):
                mx, my = (1 if dx > 0 else -1 if dx < 0 else 0), 0
            else:
                mx, my = 0, (1 if dy > 0 else -1 if dy < 0 else 0)
            target = [enemy["x"] + mx, enemy["y"] + my]
            if not self._blocked(target):
                enemy["x"], enemy["y"] = target

    def _attack(self) -> None:
        s = self._current()
        for enemy in s["enemies"]:
            if enemy["live"] and abs(enemy["x"] - s["position"][0]) + abs(enemy["y"] - s["position"][1]) <= 1:
                enemy["health"] -= 1
                if enemy["health"] <= 0:
                    enemy["live"] = False
                    s["score"] += 3

    def step(self, action: str):
        from .game_learning_runtime import EpisodeStep

        if not isinstance(action, str) or action not in self.spec.actions or self.done:
            raise GameEngineLabError("generated action is invalid or episode is terminal")
        s, c = self._current(), self._config
        before = self._observe()
        before_state = _digest(s)
        prior_health, prior_score = s["health"], s["score"]
        s["steps"] += 1
        family = c["controller"]
        old = list(s["position"])
        dx, dy = {"left": (-1, 0), "right": (1, 0), "up": (0, -1), "down": (0, 1)}.get(action, (0, 0))
        if family == "runner" and action == "noop":
            dx = 1
        if family not in {"cards", "story"}:
            target = [old[0] + dx, old[1] + dy]
            if not self._blocked(target):
                s["position"] = target
            s["delta"] = [s["position"][0] - old[0], s["position"][1] - old[1]]
        if action == "interact":
            if family == "puzzle":
                for index, cell in enumerate(c["puzzle"]["switches"]):
                    if abs(cell[0] - s["position"][0]) + abs(cell[1] - s["position"][1]) <= 1:
                        s["switches"][index] ^= 1
            elif family == "management":
                if s["resources"] >= 3 and s["position"] not in s["buildings"]:
                    s["resources"] -= 3
                    s["buildings"].append(list(s["position"]))
                    s["population"] += 1
                    s["score"] += 4
            elif c["mechanics"]["attack"]:
                self._attack()
        if family == "cards":
            end_turn = action == "end_turn"
            if action.startswith("card_"):
                card = c["cards"][int(action[-1]) - 1]
                if card["cost"] <= s["energy"]:
                    s["energy"] -= card["cost"]
                    s["enemy_hp"] -= card["damage"]
                    s["guard"] += card["guard"]
                    end_turn = s["energy"] == 0
            if s["enemy_hp"] <= 0:
                s["won"] = True
                s["score"] = 20 + s["health"]
            elif end_turn:
                s["health"] -= max(0, 2 - s["guard"])
                s["energy"], s["guard"] = 3, 0
        elif family == "story" and action.startswith("choice_"):
            choice = int(action[-1]) - 1
            if choice < len(c["story"][s["story"]]["choices"]):
                s["reserve"] += choice + 1
                s["story"] += 1
                if s["story"] == len(c["story"]):
                    s["won"] = True
                    s["score"] = s["reserve"] * 3
        elif family not in {"cards", "story"}:
            if s["position"] in s["pickups"]:
                s["pickups"].remove(s["position"])
                s["score"] += 1
            if c["mechanics"]["auto_attack"]:
                self._attack()
            if s["steps"] % 2 == 0:
                self._enemy_turn()
            if any(enemy["live"] and [enemy["x"], enemy["y"]] == s["position"] for enemy in s["enemies"]):
                s["health"] -= 1
            if c["mechanics"]["shrinking_arena"]:
                border = min(4, s["steps"] // 40)
                x, y = s["position"]
                if (
                    x < border + 1
                    or y < border + 1
                    or x >= c["grid"]["width"] - border - 1
                    or y >= c["grid"]["height"] - border - 1
                ):
                    s["health"] -= 1
            if family == "management" and s["steps"] % 3 == 0:
                s["resources"] += s["population"] + 1
            if family == "puzzle":
                s["won"] = s["switches"] == c["puzzle"]["target"]
            elif family == "management":
                s["won"] = s["population"] >= 6
            elif family in {"arena", "tactics"}:
                s["won"] = not any(enemy["live"] for enemy in s["enemies"])
            else:
                s["won"] = s["position"] == c["goal"] and (
                    not c["mechanics"]["keys_required"] or not s["pickups"]
                )
        s["terminated"] = s["won"] or s["health"] <= 0
        s["truncated"] = s["steps"] >= self.max_steps and not s["terminated"]
        after = self._observe()
        rewards = {
            "progress": after["progress"] - before["progress"],
            "score": (s["score"] - prior_score) * 0.1,
            "damage": min(0.0, (s["health"] - prior_health) * 0.1),
            "goal": 1.0 if s["won"] else 0.0,
            "time": -0.001,
        }
        evidence = {
            "environment_digest": self.spec.environment_digest,
            "seed": self._seed,
            "episode_step": s["steps"],
            "action": action,
            "state_before_digest": before_state,
            "state_after_digest": _digest(s),
            "observation": after,
            "reward_components": rewards,
            "terminated": s["terminated"],
            "truncated": s["truncated"],
            "won": s["won"],
            "parent_digest": self._chain,
        }
        self._chain = _digest(evidence)
        self._actions.append(action)
        return EpisodeStep(
            after,
            rewards,
            s["terminated"],
            s["truncated"],
            {
                "runtime_kind": "original_generated_grid_simulation",
                "won": s["won"],
                "state_digest": evidence["state_after_digest"],
                "measurement_scope": "generated discrete-grid rules; separate from browser continuous physics",
            },
            self._chain,
        )

    def preview(self) -> dict[str, Any] | None:
        if self._state is None:
            return None
        s, c = self._state, self._config
        commands = [
            {"kind": "tile", "x": cell[0], "y": cell[1], "role": "wall"} for cell in c["grid"]["walls"]
        ]
        commands.extend(
            {"kind": "sprite", "x": cell[0], "y": cell[1], "role": "signal"} for cell in s["pickups"]
        )
        commands.extend(
            {"kind": "sprite", "x": enemy["x"], "y": enemy["y"], "role": "guardian"}
            for enemy in s["enemies"]
            if enemy["live"]
        )
        commands.append({"kind": "sprite", "x": s["position"][0], "y": s["position"][1], "role": "traveler"})
        raster = _generated_raster(c, s)
        return {
            "schema_version": "skeleton.generated_game_frame.v1",
            "runtime_kind": "original_generated_grid_simulation",
            "tick": s["steps"],
            "width": c["grid"]["width"],
            "height": c["grid"]["height"],
            "palette": dict(c["palette"]),
            "commands": commands,
            "state_digest": _digest(s),
            "frame_digest": _digest(
                {
                    "commands": commands,
                    "palette": c["palette"],
                    "width": c["grid"]["width"],
                    "height": c["grid"]["height"],
                    "state_digest": _digest(s),
                    "png_digest": raster["png_digest"],
                }
            ),
            "raster": raster,
            "data_uri": raster["data_uri"],
        }

    def snapshot(self) -> dict[str, Any]:
        s = self._current()
        body = {
            "schema_version": "skeleton.generated_game_snapshot.v1",
            "environment_digest": self.spec.environment_digest,
            "seed": self._seed,
            "actions": list(self._actions),
            "state": json.loads(_canonical(s)),
            "chain_digest": self._chain,
        }
        return {**body, "snapshot_digest": _digest(body)}

    def restore(self, snapshot: Mapping[str, Any]) -> dict[str, float]:
        value = _bounded_json(snapshot, limit=128_000, name="generated environment snapshot")
        fields = {
            "schema_version",
            "environment_digest",
            "seed",
            "actions",
            "state",
            "chain_digest",
            "snapshot_digest",
        }
        if (
            not isinstance(value, dict)
            or set(value) != fields
            or value["schema_version"] != "skeleton.generated_game_snapshot.v1"
            or value["environment_digest"] != self.spec.environment_digest
        ):
            raise GameEngineLabError("generated environment snapshot identity differs")
        if (
            _digest({key: child for key, child in value.items() if key != "snapshot_digest"})
            != value["snapshot_digest"]
        ):
            raise GameEngineLabError("generated environment snapshot digest differs")
        actions = value["actions"]
        if (
            not isinstance(actions, list)
            or len(actions) > self.max_steps
            or any(not isinstance(action, str) or action not in self.spec.actions for action in actions)
        ):
            raise GameEngineLabError("generated replay action prefix is invalid")
        # Rebuild in an isolated owner so malformed snapshots cannot partially
        # overwrite a live environment before complete replay validation.
        candidate = GeneratedGameEnvironment(
            self.target.target_id, self._config, max_steps=self.max_steps, tree_digest=self.tree_digest
        )
        if candidate.spec != self.spec:
            raise GameEngineLabError("generated implementation changed before restore")
        candidate.reset(value["seed"])
        for action in actions:
            candidate.step(action)
        if candidate.snapshot() != value:
            raise GameEngineLabError("generated snapshot state or transition chain fails replay")
        self._seed, self._state = candidate._seed, candidate._state
        self._actions, self._chain, self._rng = candidate._actions, candidate._chain, candidate._rng
        return self._observe()


def _generated_raster(config: Mapping[str, Any], state: Mapping[str, Any]) -> dict[str, Any]:
    """Encode the observed generated-grid state as a bounded real PNG."""
    scale = 8
    width, height = config["grid"]["width"] * scale, config["grid"]["height"] * scale
    colors = {}
    for role, text in config["palette"].items():
        hue, saturation, light = (int(value) for value in re.findall(r"[0-9]+", text))
        colors[role] = bytes(
            round(component * 255)
            for component in colorsys.hls_to_rgb(hue / 360, light / 100, saturation / 100)
        )
    pixels = bytearray(colors["background"] * (width * height))

    def paint(cell: Iterable[int], role: str, inset: int = 0) -> None:
        x, y = cell
        color = colors[role]
        for py in range(y * scale + inset, (y + 1) * scale - inset):
            start = (py * width + x * scale + inset) * 3
            pixels[start : start + (scale - inset * 2) * 3] = color * (scale - inset * 2)

    for cell in config["grid"]["walls"]:
        paint(cell, "walls")
    paint(config["goal"], "pickup", 1)
    for cell in state["pickups"]:
        paint(cell, "pickup", 3)
    for enemy in state["enemies"]:
        if enemy["live"]:
            paint((enemy["x"], enemy["y"]), "enemy", 2)
    for cell in state["buildings"]:
        paint(cell, "pickup", 1)
    if config["controller"] == "puzzle":
        for index, cell in enumerate(config["puzzle"]["switches"]):
            paint(cell, "pickup" if state["switches"][index] else "walls", 1)
    paint(state["position"], "player", 2)
    rows = b"".join(b"\x00" + bytes(pixels[y * width * 3 : (y + 1) * width * 3]) for y in range(height))

    def chunk(kind: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + kind
            + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
        )

    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(rows, 1))
        + chunk(b"IEND", b"")
    )
    return {
        "mime_type": "image/png",
        "width": width,
        "height": height,
        "pixel_digest": hashlib.sha256(pixels).hexdigest(),
        "png_digest": hashlib.sha256(png).hexdigest(),
        "data_uri": "data:image/png;base64," + base64.b64encode(png).decode("ascii"),
        "measurement_scope": "rendered actual generated-grid state, not console hardware output",
    }


def _validate_game_config(config: Mapping[str, Any]) -> dict[str, Any]:
    value = _bounded_json(config, limit=128_000, name="generated game config")
    expected = {
        "schema_version",
        "project_id",
        "title",
        "seed",
        "genre",
        "controller",
        "grid",
        "spawn",
        "goal",
        "pickups",
        "enemies",
        "palette",
        "mechanics",
        "story",
        "cards",
        "puzzle",
        "source_feature_digest",
        "feature_influence",
        "policy_evidence",
    }
    if not isinstance(value, dict) or set(value) != expected or value["schema_version"] != GAME_CONFIG_SCHEMA:
        raise GameEngineLabError("generated game config schema differs")
    if (
        not isinstance(value["project_id"], str)
        or not _ID.fullmatch(value["project_id"])
        or not isinstance(value["title"], str)
        or not 1 <= len(value["title"]) <= 120
        or any(ord(char) < 32 for char in value["title"])
        or type(value["seed"]) is not int
        or not 0 <= value["seed"] <= 0xFFFFFFFF
        or not isinstance(value["genre"], str)
        or value["genre"] not in ERA_IDS
    ):
        raise GameEngineLabError("generated game identity fields are invalid")
    if value["controller"] not in set(_FAMILIES.values()) | {"runner"}:
        raise GameEngineLabError("generated controller is unsupported")
    grid = value["grid"]
    if not isinstance(grid, dict) or set(grid) != {"width", "height", "walls"}:
        raise GameEngineLabError("generated grid is invalid")
    width, height = grid["width"], grid["height"]
    if (
        type(width) is not int
        or type(height) is not int
        or not 8 <= width <= 32
        or not 8 <= height <= 24
        or width * height > 768
    ):
        raise GameEngineLabError("generated grid exceeds dimensions")

    def cell(item: Any) -> bool:
        return (
            isinstance(item, list)
            and len(item) == 2
            and type(item[0]) is int
            and type(item[1]) is int
            and 0 <= item[0] < width
            and 0 <= item[1] < height
        )

    for key, maximum in (("walls", 768),):
        entries = grid[key]
        if (
            not isinstance(entries, list)
            or len(entries) > maximum
            or any(not cell(item) for item in entries)
            or len({tuple(item) for item in entries}) != len(entries)
        ):
            raise GameEngineLabError("generated wall inventory is invalid")
    for key in ("spawn", "goal"):
        if not cell(value[key]) or value[key] in grid["walls"]:
            raise GameEngineLabError("generated spawn or goal is blocked")
    pickups = value["pickups"]
    if (
        not isinstance(pickups, list)
        or len(pickups) > 24
        or any(not cell(item) or item in grid["walls"] for item in pickups)
        or len({tuple(item) for item in pickups}) != len(pickups)
    ):
        raise GameEngineLabError("generated collectible inventory is invalid")
    enemies = value["enemies"]
    if not isinstance(enemies, list) or len(enemies) > 24:
        raise GameEngineLabError("generated enemy inventory exceeds limit")
    for enemy in enemies:
        if (
            not isinstance(enemy, dict)
            or set(enemy) != {"id", "x", "y", "phase", "health"}
            or not isinstance(enemy["id"], str)
            or not _ID.fullmatch(enemy["id"])
            or not cell([enemy["x"], enemy["y"]])
            or [enemy["x"], enemy["y"]] in grid["walls"]
            or type(enemy["phase"]) is not int
            or not 0 <= enemy["phase"] < 4
            or type(enemy["health"]) is not int
            or not 1 <= enemy["health"] <= 10
        ):
            raise GameEngineLabError("generated enemy recipe is invalid")
    if len({enemy["id"] for enemy in enemies}) != len(enemies):
        raise GameEngineLabError("generated enemy identities must be unique")
    mechanics = value["mechanics"]
    flags = {
        "attack",
        "turn_based",
        "auto_attack",
        "shrinking_arena",
        "stealth",
        "keys_required",
        "permadeath",
        "resource_growth",
    }
    if not isinstance(mechanics, dict) or set(mechanics) != set(_OVERRIDES) | flags:
        raise GameEngineLabError("generated mechanics fields differ")
    for key, (low, high) in _OVERRIDES.items():
        item = mechanics[key]
        if (
            type(item) not in (int, float)
            or not low <= item <= high
            or not math.isfinite(item)
            or (key not in {"speed", "wall_density"} and type(item) is not int)
        ):
            raise GameEngineLabError("generated mechanic exceeds bounds")
    if any(type(mechanics[key]) is not bool for key in flags):
        raise GameEngineLabError("generated mechanic flags must be boolean")
    palette = value["palette"]
    if (
        not isinstance(palette, dict)
        or set(palette) != {"background", "walls", "player", "pickup", "enemy"}
        or any(
            not isinstance(color, str)
            or re.fullmatch(r"hsl\([0-9]{1,3},[0-9]{1,3}%,[0-9]{1,3}%\)", color) is None
            for color in palette.values()
        )
    ):
        raise GameEngineLabError("generated palette is invalid")
    for color in palette.values():
        hue, saturation, light = (int(component) for component in re.findall(r"[0-9]+", color))
        if hue > 359 or saturation > 100 or light > 100:
            raise GameEngineLabError("generated palette channel exceeds CSS range")
    puzzle = value["puzzle"]
    if (
        not isinstance(puzzle, dict)
        or set(puzzle) != {"switches", "target"}
        or not isinstance(puzzle["switches"], list)
        or len(puzzle["switches"]) != 3
        or any(not cell(item) for item in puzzle["switches"])
        or not isinstance(puzzle["target"], list)
        or len(puzzle["target"]) != 3
        or any(type(item) is not int or item not in (0, 1) for item in puzzle["target"])
    ):
        raise GameEngineLabError("generated puzzle is invalid")
    cards = value["cards"]
    if not isinstance(cards, list) or len(cards) != 3:
        raise GameEngineLabError("generated card inventory is invalid")
    for card in cards:
        if (
            not isinstance(card, dict)
            or set(card) != {"name", "cost", "damage", "guard"}
            or not isinstance(card["name"], str)
            or not 1 <= len(card["name"]) <= 64
            or any(
                type(card[key]) is not int or not 0 <= card[key] <= 10 for key in ("cost", "damage", "guard")
            )
            or card["cost"] < 1
        ):
            raise GameEngineLabError("generated card recipe is invalid")
    story = value["story"]
    if not isinstance(story, list) or not 1 <= len(story) <= 8:
        raise GameEngineLabError("generated story sequence is invalid")
    for node in story:
        if (
            not isinstance(node, dict)
            or set(node) != {"speaker", "text", "choices"}
            or not isinstance(node["speaker"], str)
            or not 1 <= len(node["speaker"]) <= 64
            or not isinstance(node["text"], str)
            or not 1 <= len(node["text"]) <= 512
            or not isinstance(node["choices"], list)
            or not 1 <= len(node["choices"]) <= 2
            or any(not isinstance(choice, str) or not 1 <= len(choice) <= 120 for choice in node["choices"])
        ):
            raise GameEngineLabError("generated story node is invalid")
    if not isinstance(value["source_feature_digest"], str) or not _SHA.fullmatch(
        value["source_feature_digest"]
    ):
        raise GameEngineLabError("generated feature identity is invalid")
    return value


def _sprite_svg(config: Mapping[str, Any]) -> str:
    rng = random.Random(config["seed"] ^ int(config["source_feature_digest"][:8], 16))
    rects = []
    for role, color in enumerate(
        (config["palette"]["player"], config["palette"]["enemy"], config["palette"]["pickup"])
    ):
        for y in range(8):
            for x in range(4):
                if y in (2, 3, 4, 5) or rng.random() > 0.6:
                    for mirror in {x, 7 - x}:
                        rects.append(
                            f'<rect x="{role * 16 + mirror}" y="{y}" width="1" height="1" fill="{color}"/>'
                        )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="48" height="8" viewBox="0 0 48 8">'
        + "".join(rects)
        + "</svg>"
    )


def _readme(request: GameGenerationRequest, config: Mapping[str, Any], native: Mapping[str, Any]) -> str:
    native_note = (
        "The optional original DMG maze is a real 32 KiB homebrew program encoded in the `.gb.base64` file. Decode that file to `.gb` for explicitly admitted local ROM use. Its maze is a separate adaptation; original hardware execution is unverified."
        if "original_dmg_maze" in native
        else "Native target files, where present, are original source that requires the declared toolchain. No native binary has been compiled or executed."
    )
    return f"""# {request.title}\n\nOpen `index.html` in a browser, or serve this folder with a local static-file server. All play code and assets are local; no hosted provider or network asset is required.\n\nUse arrows/WASD to move, Space to jump/attack/interact, 1/2/3 for card choices, R to restart. Touch buttons provide the same actions. The {config['controller']} controller implements an original simplified {config['genre']} prototype.\n\n`game.json` records the real generated layout, mechanics, classified source influence and learned-control probe identity. `simulation.py` provides a bounded standard-library grid simulation for this layout, distinct from the era-specific compiled engine. The studio's generated-grid environment additionally implements controller objectives and measured learning transitions.\n\nThe console target is a design association. Portable browser/source files and existing compiled reference-engine evidence planes do not establish commercial console compatibility. {native_note}\n\nOriginal uploaded ROM bytes, source code, images and audio are not copied. No automated execution check has been claimed.\n"""


def _game_html(title: str, config_json: str) -> str:
    safe_json = config_json.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'self'; style-src 'unsafe-inline'; img-src 'self'; connect-src 'none'; media-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'">
<title>{html.escape(title)}</title><style>
body{{margin:0;background:#0b1020;color:#e5e7eb;font:16px system-ui,sans-serif}}main{{max-width:1100px;margin:auto;padding:16px}}canvas{{width:100%;background:#111827;border:1px solid #475569;image-rendering:pixelated;touch-action:none}}button{{padding:12px;margin:3px;background:#24324b;color:white;border:1px solid #7383a3;border-radius:5px}}#status{{min-height:3em}}#choices{{display:flex;flex-wrap:wrap}}.controls{{display:flex;flex-wrap:wrap;justify-content:center}}small{{color:#9ca3af}}
</style></head><body><main><h1>{html.escape(title)}</h1><p id="status" aria-live="polite"></p>
<canvas id="game" width="960" height="576" tabindex="0" aria-label="Original playable game"></canvas>
<div id="choices"></div><div class="controls"><button data-key="ArrowLeft">←</button><button data-key="ArrowUp">↑</button><button data-key="ArrowDown">↓</button><button data-key="ArrowRight">→</button><button data-key="Space">Action</button><button id="restart">Restart</button></div>
<p><small>Original portable prototype. Arrows/WASD move; Space acts; R restarts. Console labels describe design targets, not console binary compatibility.</small></p>
<script id="game-config" type="application/json">{safe_json}</script><script src="game.js" defer></script></main></body></html>"""


_BROWSER_RUNTIME = r"""'use strict';
/* Original bounded portable controller. No imports, eval, fetch or host tools. */
(() => {
const cfg=JSON.parse(document.getElementById('game-config').textContent);
const canvas=document.getElementById('game'),ctx=canvas.getContext('2d');
const status=document.getElementById('status'),choices=document.getElementById('choices');
const W=cfg.grid.width,H=cfg.grid.height,T=Math.min(canvas.width/W,canvas.height/H);
const wall=new Set(cfg.grid.walls.map(p=>p.join(','))),held=new Set();
let s,last=0,acc=0,actionLatch=false,turnLatch=false,attackCooldown=0;
function reset(){s={x:cfg.spawn[0]+.5,y:cfg.spawn[1]+.5,vy:0,health:cfg.mechanics.health,score:0,ticks:0,coins:cfg.pickups.map(p=>({x:p[0]+.5,y:p[1]+.5,live:true})),enemies:cfg.enemies.map(e=>({...e,x:e.x+.5,y:e.y+.5,live:true})),over:false,won:false,invuln:0,energy:3,guard:0,enemyHP:16,story:0,reserve:0,resources:8,population:0,buildings:[],switches:[0,0,0]};choices.replaceChildren();attackCooldown=0;acc=0;actionLatch=false;turnLatch=false;held.clear();renderChoices();}
function blocked(x,y){return x<.4||y<.4||x>W-.4||y>H-.4||wall.has(Math.floor(x)+','+Math.floor(y));}
function move(dx,dy){const r=.23;if(!blocked(s.x+dx+(dx>0?r:-r),s.y))s.x+=dx;if(!blocked(s.x,s.y+dy+(dy>0?r:-r)))s.y+=dy;}
function hurt(){if(s.invuln>0||s.over)return;s.health--;s.invuln=60;if(s.health<=0){s.over=true;s.won=false;}}
function finish(){s.over=true;s.won=true;}
function action(){if(s.over)return;const family=cfg.controller;
if(family==='story'){chooseStory(0);return;}if(family==='cards'){playCard(0);return;}
if(family==='management'){const cell=[Math.floor(s.x),Math.floor(s.y)];if(s.resources>=3&&!s.buildings.some(b=>b[0]===cell[0]&&b[1]===cell[1])){s.resources-=3;s.buildings.push(cell);s.population++;s.score+=4;if(s.population>=6)finish();}return;}
if(family==='puzzle'){cfg.puzzle.switches.forEach((p,i)=>{if(Math.hypot(s.x-p[0]-.5,s.y-p[1]-.5)<1.5)s.switches[i]^=1;});if(s.switches.every((v,i)=>v===cfg.puzzle.target[i]))finish();return;}
if(family==='platformer'||family==='runner'){if(blocked(s.x,s.y+.55))s.vy=-8;}
if(cfg.mechanics.attack&&attackCooldown<=0){attackCooldown=18;s.enemies.forEach(e=>{if(e.live&&Math.hypot(e.x-s.x,e.y-s.y)<2.3){e.health--;if(e.health<=0){e.live=false;s.score+=3;}}});}}
function chooseStory(index){if(s.over||!Number.isInteger(index)||index<0||index>=cfg.story[s.story].choices.length)return;s.reserve+=index===0?1:2;s.story++;if(s.story>=cfg.story.length){s.score=s.reserve*3;finish();}renderChoices();}
function playCard(index){if(s.over)return;const card=cfg.cards[index];if(!card||card.cost>s.energy)return;s.energy-=card.cost;s.enemyHP-=card.damage;s.guard+=card.guard;if(s.enemyHP<=0){s.score=20+s.health;finish();return;}if(s.energy===0||index===2){const damage=Math.max(0,2-s.guard);s.health-=damage;s.guard=0;s.energy=3;if(s.health<=0){s.over=true;s.won=false;}}renderChoices();}
function renderChoices(){choices.replaceChildren();if(s.over)return;
if(cfg.controller==='story'){cfg.story[s.story].choices.forEach((text,i)=>{const b=document.createElement('button');b.textContent=text;b.onclick=()=>chooseStory(i);choices.append(b);});}
if(cfg.controller==='cards'){cfg.cards.forEach((card,i)=>{const b=document.createElement('button');b.textContent=(i+1)+'. '+card.name+' ('+card.cost+' energy)';b.onclick=()=>playCard(i);choices.append(b);});const end=document.createElement('button');end.textContent='End turn';end.onclick=()=>{s.health-=Math.max(0,2-s.guard);s.guard=0;s.energy=3;if(s.health<=0)s.over=true;renderChoices();};choices.append(end);}}
function tick(){if(s.over)return;const family=cfg.controller;s.ticks++;s.invuln=Math.max(0,s.invuln-1);attackCooldown=Math.max(0,attackCooldown-1);
if(s.ticks>=cfg.mechanics.time_limit*60){s.over=true;s.won=false;return;}
let dx=(held.has('ArrowRight')||held.has('KeyD')?1:0)-(held.has('ArrowLeft')||held.has('KeyA')?1:0),dy=(held.has('ArrowDown')||held.has('KeyS')?1:0)-(held.has('ArrowUp')||held.has('KeyW')?1:0);
const active=held.has('Space');if(active&&!actionLatch)action();actionLatch=active;
if(family==='story'||family==='cards')return;
if(family==='tactics'){if((dx||dy)&&!turnLatch){move(dx,dy);enemyTurn();}turnLatch=Boolean(dx||dy);}else if(family==='platformer'||family==='runner'){if(family==='runner')dx=1;move(dx*cfg.mechanics.speed/60,0);s.vy=Math.min(10,s.vy+18/60);const prior=s.y;move(0,s.vy/60);if(s.y===prior)s.vy=0;}else{const norm=Math.hypot(dx,dy)||1;move(dx/norm*cfg.mechanics.speed/60,dy/norm*cfg.mechanics.speed/60);}
if(family!=='tactics'&&s.ticks%30===0)enemyTurn();
if(cfg.mechanics.auto_attack&&s.ticks%24===0)action();
s.coins.forEach(c=>{if(c.live&&Math.hypot(c.x-s.x,c.y-s.y)<.7){c.live=false;s.score++;if(cfg.genre==='cozy_wholesome')s.health=Math.min(cfg.mechanics.health,s.health+1);}});
s.enemies.forEach(e=>{if(e.live&&Math.hypot(e.x-s.x,e.y-s.y)<.65)hurt();});
if(cfg.mechanics.shrinking_arena){const edge=Math.min(4,Math.floor(s.ticks/900));if(s.x<edge+1||s.y<edge+1||s.x>W-edge-1||s.y>H-edge-1)hurt();}
if(family==='management'&&s.ticks%180===0){s.resources+=s.population+1;s.score+=s.population;}
if(['arena','tactics'].includes(family)&&s.enemies.every(e=>!e.live)){finish();}
if(['adventure','platformer','runner'].includes(family)&&Math.hypot(s.x-cfg.goal[0]-.5,s.y-cfg.goal[1]-.5)<.8&&(!cfg.mechanics.keys_required||s.coins.every(c=>!c.live)))finish();}
function enemyTurn(){s.enemies.forEach((e,i)=>{if(!e.live)return;let dx=0,dy=0;if(cfg.mechanics.stealth&&Math.hypot(e.x-s.x,e.y-s.y)>4){const phase=(Math.floor(s.ticks/120)+e.phase)%4;dx=phase===0?1:phase===2?-1:0;dy=phase===1?1:phase===3?-1:0;}else{dx=Math.sign(s.x-e.x);dy=Math.sign(s.y-e.y);if(Math.abs(s.x-e.x)>Math.abs(s.y-e.y))dy=0;else dx=0;}const speed=cfg.controller==='tactics'?.65:.28;if(!blocked(e.x+dx*speed,e.y+dy*speed)){e.x+=dx*speed;e.y+=dy*speed;}});}
function draw(){ctx.fillStyle=cfg.palette.background;ctx.fillRect(0,0,canvas.width,canvas.height);ctx.fillStyle=cfg.palette.walls;cfg.grid.walls.forEach(p=>ctx.fillRect(p[0]*T,p[1]*T,T,T));ctx.fillStyle=cfg.palette.pickup;ctx.strokeStyle=cfg.palette.pickup;ctx.strokeRect(cfg.goal[0]*T,cfg.goal[1]*T,T,T);
s.coins.forEach(c=>{if(c.live){ctx.beginPath();ctx.arc(c.x*T,c.y*T,T*.16,0,Math.PI*2);ctx.fill();}});
s.enemies.forEach(e=>{if(e.live){ctx.fillStyle=cfg.palette.enemy;ctx.fillRect((e.x-.25)*T,(e.y-.25)*T,T*.5,T*.5);}});
ctx.fillStyle=s.invuln%12<6?'#fff':cfg.palette.player;ctx.fillRect((s.x-.22)*T,(s.y-.3)*T,T*.44,T*.6);
if(cfg.controller==='puzzle'){cfg.puzzle.switches.forEach((p,i)=>{ctx.fillStyle=s.switches[i]?'#f9fafb':'#64748b';ctx.fillRect(p[0]*T,p[1]*T,T*.8,T*.8);ctx.fillStyle='#111';ctx.fillText(String(cfg.puzzle.target[i]),(p[0]+.3)*T,(p[1]+.6)*T);});}
if(cfg.controller==='management'){ctx.fillStyle=cfg.palette.pickup;s.buildings.forEach(p=>ctx.fillRect(p[0]*T,p[1]*T,T*.8,T*.8));}
if(cfg.controller==='story'||cfg.controller==='cards'){ctx.fillStyle='rgba(0,0,0,.85)';ctx.fillRect(T,T,canvas.width-2*T,canvas.height-2*T);ctx.fillStyle='#fff';ctx.font='20px system-ui';const text=cfg.controller==='story'?(s.over?'Expedition complete':cfg.story[s.story].speaker+': '+cfg.story[s.story].text):'Opponent '+s.enemyHP+' HP · Energy '+s.energy+' · Guard '+s.guard;wrap(text,2*T,3*T,canvas.width-4*T);}
status.textContent=s.over?(s.won?'Expedition complete. ':'Expedition ended. ')+'Score '+s.score+' · Press R to restart.':cfg.controller+' · Health '+s.health+' · Score '+s.score+' · '+Math.max(0,cfg.mechanics.time_limit-Math.floor(s.ticks/60))+'s'+(cfg.controller==='management'?' · Resources '+s.resources+' · Buildings '+s.population+'/6':'')+(cfg.controller==='adventure'||cfg.controller==='platformer'||cfg.controller==='runner'?' · Gather all signals, then reach the outlined exit':'')+(cfg.controller==='puzzle'?' · Space toggles nearby switches; match the displayed target':'');}
function wrap(text,x,y,width){let line='';text.split(' ').forEach(word=>{const next=line+word+' ';if(ctx.measureText(next).width>width){ctx.fillText(line,x,y);line=word+' ';y+=30;}else line=next;});ctx.fillText(line,x,y);}
function frame(now){const dt=last?Math.min(.1,(now-last)/1000):0;last=now;acc+=dt;let steps=0;while(acc>=1/60&&steps<6){tick();acc-=1/60;steps++;}draw();requestAnimationFrame(frame);}
addEventListener('keydown',e=>{if(['ArrowUp','ArrowDown','ArrowLeft','ArrowRight','Space'].includes(e.code))e.preventDefault();held.add(e.code);if(e.code==='KeyR')reset();if(/^Digit[1-3]$/.test(e.code)&&!e.repeat){if(cfg.controller==='cards')playCard(Number(e.code.slice(-1))-1);if(cfg.controller==='story')chooseStory(Number(e.code.slice(-1))-1);}});
addEventListener('keyup',e=>held.delete(e.code));addEventListener('blur',()=>held.clear());
document.querySelectorAll('[data-key]').forEach(b=>{b.addEventListener('pointerdown',e=>{e.preventDefault();b.setPointerCapture(e.pointerId);held.add(b.dataset.key);});const clear=()=>held.delete(b.dataset.key);b.addEventListener('pointerup',clear);b.addEventListener('pointercancel',clear);});
document.getElementById('restart').onclick=reset;reset();requestAnimationFrame(frame);
})();
"""


_PORTABLE_SIMULATION = r'''"""Original generated grid-play simulator; no ROM or uploaded code execution.

This standard-library adapter models bounded grid movement/collection/combat,
not the browser's continuous platform physics or every genre controller.
"""
import hashlib
import json
from pathlib import Path

class Game:
    ACTIONS = ("left", "right", "up", "down", "interact", "wait")
    def __init__(self, config=None):
        self.config = config or json.loads(Path(__file__).with_name("game.json").read_text(encoding="utf-8"))
        if self.config.get("schema_version") != "skeleton.original_portable_game.v1":
            raise ValueError("unsupported generated game config")
        self.reset()
    def reset(self):
        c = self.config
        self.position = list(c["spawn"])
        self.health = c["mechanics"]["health"]
        self.score = self.steps = 0
        self.pickups = {tuple(p) for p in c["pickups"]}
        self.enemies = {(e["x"], e["y"]) for e in c["enemies"]}
        self.done = False
        return self.observe()
    def observe(self):
        return {"position": list(self.position), "goal": list(self.config["goal"]), "health": self.health, "score": self.score, "steps": self.steps, "done": self.done}
    def step(self, action):
        if action not in self.ACTIONS or self.done:
            raise ValueError("invalid action or terminal game")
        if self.steps >= min(4096, self.config["mechanics"]["time_limit"] * 30):
            self.done = True
            return {"observation": self.observe(), "reward": 0.0, "terminated": False, "truncated": True}
        self.steps += 1
        reward = -0.01
        dx, dy = {"left":(-1,0),"right":(1,0),"up":(0,-1),"down":(0,1)}.get(action,(0,0))
        target = (self.position[0]+dx, self.position[1]+dy)
        walls = {tuple(p) for p in self.config["grid"]["walls"]}
        if 0 <= target[0] < self.config["grid"]["width"] and 0 <= target[1] < self.config["grid"]["height"] and target not in walls:
            self.position[:] = target
        current = tuple(self.position)
        if current in self.pickups:
            self.pickups.remove(current); self.score += 1; reward += 1.0
        if action == "interact" and self.config["mechanics"]["attack"]:
            defeated = {e for e in self.enemies if abs(e[0]-current[0])+abs(e[1]-current[1]) <= 1}
            self.enemies -= defeated; self.score += 3*len(defeated); reward += len(defeated)
        if current in self.enemies:
            self.health -= 1; reward -= 1.0
        won = current == tuple(self.config["goal"]) and not self.pickups
        self.done = won or self.health <= 0
        if won: reward += 10.0
        return {"observation": self.observe(), "reward": reward, "terminated": self.done, "truncated": False}
    def snapshot(self):
        value = {"config_digest": hashlib.sha256(json.dumps(self.config,sort_keys=True,separators=(",",":")).encode()).hexdigest(), "observation": self.observe(), "pickups": sorted(self.pickups), "enemies": sorted(self.enemies)}
        return value
'''
