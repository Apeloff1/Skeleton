"""Systems and content for a compiled game design spec.

Reuses the forge game-logic, animation, and dialogue pipelines, the
deterministic combat and economy simulators, the room graph already emitted
by Godot materialisation, the render particle contract, and the kinematic
physics body. Numbers the playable loop executes are the encounter, economy,
platform, and narrative tables returned here.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from skeleton.forge.pipelines.animation import AnimationPipeline
from skeleton.forge.pipelines.dialogue import DialogueEdge, DialogueNode, DialogueTree, DialogueWalker
from skeleton.forge.pipelines.game_logic import GameLogicPipeline

CONTENT_SCHEMA = "skeleton.game_content_bundle.v1"

_SCOPE_ENCOUNTERS = {"small": 3, "medium": 5, "large": 8}
_SCOPE_PLATFORMS = {"small": (2, 3, 2), "medium": (2, 3, 2, 3, 2), "large": (2, 2, 3, 2, 3, 2, 2, 3)}
_SCOPE_LEVELS = {"small": 4, "medium": 6, "large": 8}


def _seed(spec_id: str) -> int:
    raw = int.from_bytes(hashlib.sha256(spec_id.encode("utf-8")).digest()[:4], "big")
    return raw & 0x7FFFFFFF


def _levels(files: Mapping[str, str], limit: int) -> list[dict[str, str]]:
    raw = files.get("data/rooms.json") if isinstance(files, Mapping) else None
    rooms: list[Any] = []
    if isinstance(raw, str) and raw.strip():
        try:
            graph = json.loads(raw)
        except json.JSONDecodeError:
            graph = {}
        if isinstance(graph, dict) and isinstance(graph.get("rooms"), list):
            rooms = graph["rooms"]
    levels: list[dict[str, str]] = []
    for index, room in enumerate(rooms):
        if not isinstance(room, dict):
            continue
        room_id = str(room.get("id") or f"r{index:02d}")
        kind = str(room.get("kind") or "combat")
        levels.append({"id": room_id, "kind": kind})
        if len(levels) >= limit:
            break
    if not levels:
        levels = [{"id": f"r{index:02d}", "kind": "combat"} for index in range(limit)]
    return levels


def _encounters(count: int) -> list[dict[str, int | str]]:
    rows: list[dict[str, int | str]] = []
    for index in range(count):
        rows.append({
            "id": f"e{index}",
            "hp": 12,
            "player_damage": 6,
            "enemy_damage": 1,
            "loot": 10,
        })
    return rows


def _platforms(gaps: tuple[int, ...]) -> tuple[list[dict[str, int]], int, int]:
    steps = [{"gap": gap, "height": 1} for gap in gaps]
    return steps, sum(gaps), 4


def _combat_design(seed: int, description: str, *, root) -> dict[str, Any]:
    from skeleton.simulation.game.mechanics_depth.combat_engine import CombatEngine

    logic = GameLogicPipeline(root=root).run(description, title="playable", max_level=8, curve="linear")
    engine = CombatEngine(seed)
    engine.spawn("player", hp=30, atk=8, defense=2, crit=0.0)
    engine.spawn("raider", hp=12, atk=4, defense=1, crit=0.0)
    duel = engine.duel("player", "raider", max_rounds=16)
    designed = logic.to_dict()
    return {
        "formula": designed["combat"]["damage_formula"],
        "stats": designed["combat"]["stats"],
        "base_values": designed["combat"]["base_values"],
        "duel_winner": duel.winner,
        "duel_frames": len(duel.frames),
        "duel_digest": duel.digest,
        "pipeline_run_id": designed["run_id"],
    }


def _economy(seed: int, encounters: list[Mapping[str, Any]], *, currency: str) -> dict[str, Any]:
    from skeleton.simulation.game.mechanics_depth.economy_sim import EconomySim

    starting = 50
    sink = 5
    sim = EconomySim(seed)
    sim.open("player", starting)
    for row in encounters:
        sim.transact("player", int(row["loot"]), "loot")
    sim.transact("player", -sink, "vendor")
    snap = sim.snapshot()
    return {
        "currency": currency,
        "starting_balance": starting,
        "sink_cost": sink,
        "taps": ["loot"],
        "sinks": ["vendor"],
        "closing_balance": int(dict(snap.balances)["player"]),
        "ledger_digest": sim.replay_digest(),
    }


def _narrative(spec: Mapping[str, Any]) -> list[dict[str, str]]:
    fantasy = str(spec.get("fantasy") or "the delve")
    tree = DialogueTree(
        tree_id="core-hook",
        entry="arrive",
        nodes={
            "arrive": DialogueNode(
                "arrive",
                "guide",
                f"The way through {fantasy} is still open.",
                edges=[DialogueEdge("follow the hook", "payoff", effects={"hook": "hook-0"})],
            ),
            "payoff": DialogueNode(
                "payoff",
                "guide",
                "The hook is yours if the rooms are cleared.",
                terminal=True,
            ),
        },
    )
    walker = DialogueWalker(tree)
    walker.choose(0)
    if not walker.finished:
        raise RuntimeError("narrative hook did not reach a terminal line")
    return [{
        "id": "hook-0",
        "speaker": walker.node.speaker,
        "line": walker.node.line,
        "tree_id": tree.tree_id,
    }]


def _animation(description: str, genre: str) -> dict[str, Any]:
    actions = {
        "platformer": ("idle", "walk", "jump", "attack"),
        "rpg_roguelike": ("idle", "walk", "attack", "cast"),
    }.get(genre, ("idle", "walk", "run", "attack"))
    spec = AnimationPipeline().run(description, actions=actions)
    payload = spec.to_dict()
    return {
        "run_id": payload["run_id"],
        "clips": [clip["name"] for clip in payload["clips"]],
        "states": [state["name"] for state in payload["state_machine"]],
        "blend": payload["blend_tree"]["parameter"],
    }


def _vfx(spec_id: str) -> list[dict[str, Any]]:
    from skeleton.game.render.flgb_render_runtime import ParticleEmitter

    catalog = (
        ("muzzle", 250_000, 64, 180),
        ("impact", 180_000, 32, 220),
        ("dust", 90_000, 48, 400),
    )
    rows = []
    for name, rate, limit, life in catalog:
        emitter_id = f"{name}-{spec_id[:8]}"
        digest = hashlib.sha256(emitter_id.encode("utf-8")).hexdigest()
        emitter = ParticleEmitter(
            emitter_id=emitter_id,
            seed_digest=digest,
            rate_milli_per_second=rate,
            max_particles=limit,
            lifetime_ms=life,
        )
        rows.append({
            "emitter_id": emitter.emitter_id,
            "seed_digest": emitter.seed_digest,
            "rate_milli_per_second": emitter.rate_milli_per_second,
            "max_particles": emitter.max_particles,
            "lifetime_ms": emitter.lifetime_ms,
            "burst": emitter.emitted_count(1000),
        })
    return rows


def _vehicle(speed: float) -> dict[str, Any]:
    from skeleton.simulation.physics.body import BodyType, RigidBody
    from skeleton.simulation.physics.math3d import Vec3
    from skeleton.simulation.physics.shapes import SphereShape

    body = RigidBody(
        body_id="skiff",
        shape=SphereShape(0.5),
        body_type=BodyType.KINEMATIC,
        linear_velocity=Vec3(float(speed), 0.0, 0.0),
    )
    dt = 0.1
    steps = 5
    for _ in range(steps):
        body.integrate_velocity(dt)
    return {
        "body_id": body.body_id,
        "kind": "kinematic_vehicle",
        "steps": steps,
        "dt": dt,
        "speed": float(speed),
        "position": [round(body.position.x, 6), round(body.position.y, 6), round(body.position.z, 6)],
    }


def generate_content(spec: Mapping[str, Any], files: Mapping[str, str] | None = None, *, root=None) -> dict[str, Any]:
    """Build the content bundle the genre runtime executes."""
    if not isinstance(spec, Mapping) or spec.get("schema_version") != "skeleton.game_design_spec.v1":
        raise ValueError("a skeleton.game_design_spec.v1 spec is required")
    genre = str(spec.get("genre") or "")
    scope = str(spec.get("scope") or "small")
    if genre not in _LOOP_GENRES():
        raise ValueError(f"unsupported genre {genre!r}")
    if scope not in _SCOPE_ENCOUNTERS:
        raise ValueError(f"unsupported scope {scope!r}")
    spec_id = str(spec.get("spec_id") or "")
    if len(spec_id) != 64:
        raise ValueError("spec_id must be a sha256 hex digest")
    description = str(spec.get("brief") or spec.get("fantasy") or genre)
    seed = _seed(spec_id)
    encounters = _encounters(_SCOPE_ENCOUNTERS[scope])
    platforms, goal_x, jump_reach = _platforms(_SCOPE_PLATFORMS[scope])
    economy = _economy(seed, encounters, currency="salvage" if genre == "top_down_shooter" else "gold")
    bundle = {
        "schema_version": CONTENT_SCHEMA,
        "spec_id": spec_id,
        "genre": genre,
        "scope": scope,
        "player_hp": 100,
        "jump_reach": jump_reach,
        "goal_x": goal_x,
        "platforms": platforms,
        "levels": _levels(files or {}, _SCOPE_LEVELS[scope]),
        "encounters": encounters,
        "economy": economy,
        "combat_design": _combat_design(seed, description, root=root),
        "narrative": _narrative(spec),
        "animation": _animation(description, genre),
        "vfx": _vfx(spec_id),
        "physics": _vehicle(6.0 if genre != "platformer" else 4.5),
    }
    return bundle


def _LOOP_GENRES() -> frozenset[str]:
    return frozenset({"top_down_shooter", "platformer", "rpg_roguelike"})
