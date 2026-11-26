"""Source-bound GameForge -> quest -> actual abstract player-event replay.

The archived conductor owns the world topology and prototype manifest. The
recovered quest runtime owns objective state and rewards. This bridge admits
only graph-legal travel and location/NPC-bound objective completion. None of
its receipts are native engine, asset, model, device or release evidence.
"""
from __future__ import annotations

from collections import deque
import hashlib
from typing import Any

from skeleton.ai.game_builder.quest_objective_runtime import QuestDefinition, QuestRuntime
from skeleton.app.original_quest_cli import (
    REQUEST_SCHEMA as QUEST_SCHEMA,
    QuestRequestError,
    _encode,
    _integer,
    _object,
    _require,
    _strings,
    _text,
    build_receipt as build_quest,
)
from skeleton.gameforge.conductor import ConductorConfig, GameForgeConductor
from skeleton.gameforge.errors import GameForgeError
from skeleton.gameforge.manifest import verify_manifest
from skeleton.gameforge.plans import EXPORT_TARGETS, GENRES, STEPS, WorldPlan
from skeleton.gameforge.safety import screen_text

REQUEST_SCHEMA = "skeleton.gameforge.quest_bridge.request.v1"
DESIGN_SCHEMA = "skeleton.gameforge.quest_bridge.design.v1"
SESSION_SCHEMA = "skeleton.gameforge.quest_bridge.session.v1"
MAX_ACTIONS = 8192
MAX_ARTIFACT_BYTES = 2 * 1024 * 1024
GRAPH_SEMANTICS = "undirected_conductor_world_plan_v1"


def _hash(value: Any) -> str:
    return hashlib.sha256(_encode(value)).hexdigest()


def _admit(source: Any) -> tuple[dict, ConductorConfig, dict]:
    _encode(source)
    data = _object(source, {"schema", "vision", "quest"}, {"config"})
    _require(data["schema"] == REQUEST_SCHEMA, "unsupported bridge request")
    raw = _object(data["vision"], {"title", "pitch", "genre"},
                  {"era", "pillars", "target_minutes"})
    title = _text(raw["title"], 256)
    pitch = _text(raw["pitch"], 4000)
    genre = _text(raw["genre"], 32)
    _require(genre in GENRES, "unsupported conductor genre")
    pillars = list(_strings(raw.get("pillars", ["fun"]), 5, 96, nonempty=True))
    _require(all(p == p.strip() for p in pillars)
             and len({p.lower() for p in pillars}) == len(pillars),
             "pillar identities collide after normalization")
    vision = {
        "title": title, "pitch": pitch, "genre": genre,
        "era": _text(raw.get("era", "HOUSE_ERA"), 64), "pillars": pillars,
        "target_minutes": _integer(raw.get("target_minutes", 10), 1, 600),
    }
    cfg = _object(data.get("config", {}), set(), {"budget_bytes", "regions", "target"})
    target = _text(cfg.get("target", "web"), 32)
    _require(target in EXPORT_TARGETS, "unsupported conductor target")
    config = ConductorConfig(
        budget_bytes=_integer(cfg.get("budget_bytes", 1_000_000), 1, 1_000_000),
        regions=_integer(cfg.get("regions", 5), 1, 64),
        target=target,
    )
    quest = _object(data["quest"], {"packs", "pack_ids", "policy", "seed"},
                    {"quest_length", "quest_title", "overrides", "npcs"})
    _integer(quest["seed"], -(2**63), 2**63 - 1)
    _integer(quest.get("quest_length", 3), 1, 128)
    screen_text("quest", _text(quest.get("quest_title", "An Original Adventure"), 256))
    return vision, config, quest


def _world(plan: WorldPlan, npcs: Any) -> dict:
    """Match the conductor's own undirected reachability contract exactly."""
    _require(isinstance(plan, WorldPlan) and 1 <= len(plan.regions) <= 64,
             "invalid conductor world plan")
    edges: dict[str, set[str]] = {}
    for region in plan.regions:
        key = _text(region.key, 64)
        _require(key not in edges, "duplicate generated region")
        edges[key] = set()
    _require(plan.start in edges, "missing generated spawn")
    for region in plan.regions:
        for link in region.neighbors:
            _require(link in edges and link != region.key, "invalid generated world edge")
            edges[region.key].add(link)
            edges[link].add(region.key)
    _require(type(npcs) is dict and len(npcs) <= 256, "invalid NPC placement")
    placements = {_text(name, 128): _text(location, 64) for name, location in npcs.items()}
    _require(all(location in edges for location in placements.values()), "NPC outside generated world")
    screen_text("quest", *placements.keys())
    adjacency = {key: sorted(links) for key, links in sorted(edges.items())}
    # Validate actual graph connectivity independently of the owner's validator.
    reached = {plan.start}
    queue = deque([plan.start])
    while queue:
        for neighbor in adjacency[queue.popleft()]:
            if neighbor not in reached:
                reached.add(neighbor)
                queue.append(neighbor)
    _require(reached == set(adjacency), "generated world is disconnected")
    return {"start": plan.start, "edges": adjacency, "npcs": placements}


def _route(edges: dict[str, list[str]], start: str, end: str) -> list[str]:
    _require(start in edges and end in edges, "route outside generated world")
    queue = deque([start])
    parent: dict[str, str | None] = {start: None}
    while queue and end not in parent:
        node = queue.popleft()
        for neighbor in edges[node]:
            if neighbor not in parent:
                parent[neighbor] = node
                queue.append(neighbor)
    _require(end in parent, "objective location cannot be reached from current region")
    result = [end]
    while parent[result[-1]] is not None:
        previous = parent[result[-1]]
        assert previous is not None
        result.append(previous)
    return list(reversed(result))


def _steps(artifact: dict) -> list[dict]:
    return artifact["world_quest"]["quest"]["steps"]


def _witness(world: dict, artifact: dict) -> list[dict]:
    actions: list[dict] = []
    location = world["start"]
    for step in _steps(artifact):
        path = _route(world["edges"], location, step["location"])
        actions.extend({"type": "move", "to": region} for region in path[1:])
        actions.append({"type": "resolve", "objective": step["id"], "npc": step["npc"]})
        location = step["location"]
    _require(1 <= len(actions) <= MAX_ACTIONS, "route witness exceeds action ceiling")
    return actions


def _replay(world: dict, artifact: dict, actions: Any) -> dict:
    """Validate every actual player action against the generated world and ledger."""
    _require(type(actions) is list and len(actions) <= MAX_ACTIONS, "invalid action ledger")
    _encode(actions)
    definition = QuestDefinition.from_mapping(artifact["quest_definition"])
    runtime = QuestRuntime(definition)
    steps = {step["id"]: step for step in _steps(artifact)}
    location = world["start"]
    moves = 0
    resolutions = 0
    for raw in actions:
        _require(runtime.status == "in_progress", "action after terminal quest state")
        _require(type(raw) is dict, "invalid player action")
        kind = raw.get("type")
        if kind == "move":
            action = _object(raw, {"type", "to"})
            destination = _text(action["to"], 64)
            _require(destination in world["edges"][location], "travel is not adjacent")
            location = destination
            moves += 1
        elif kind == "resolve":
            action = _object(raw, {"type", "objective", "npc"})
            objective = _text(action["objective"], 128)
            _require(objective in steps, "unknown objective")
            step = steps[objective]
            npc = action["npc"]
            if npc is not None:
                _text(npc, 128)
            _require(location == step["location"] and npc == step["npc"],
                     "objective location or NPC mismatch")
            _require(npc is None or world["npcs"].get(npc) == location,
                     "NPC is not present in current region")
            runtime.advance(objective)
            resolutions += 1
        else:
            raise QuestRequestError("unknown player action")
    # Derive action choices from current authoritative state, not submitted metadata.
    legal: list[dict] = []
    if runtime.status == "in_progress":
        legal.extend({"type": "move", "to": neighbor} for neighbor in world["edges"][location])
        for oid, step in steps.items():
            if (runtime.states[oid].value == "active" and step["location"] == location
                    and (step["npc"] is None or world["npcs"].get(step["npc"]) == location)):
                legal.append({"type": "resolve", "objective": oid, "npc": step["npc"]})
    return {
        "location": location, "status": runtime.status,
        "moves": moves, "resolutions": resolutions,
        "earned_rewards": runtime.earned_rewards(),
        "quest_snapshot": runtime.snapshot(), "legal_actions": legal,
    }


def build_design(source: Any) -> dict:
    """Run the seven-stage conductor plus quest synthesis and full route replay."""
    vision, config, quest = _admit(source)
    run = GameForgeConductor(config=config).run(vision)
    _require(run.ok and run.manifest is not None and tuple(run.completed) == STEPS,
             "conductor did not complete all seven stages")
    manifest = run.manifest.to_dict()
    _require(tuple(manifest["steps"]) == STEPS and len(manifest["receipts"]) == len(STEPS),
             "incomplete conductor manifest")
    _require(all(row["step"] == step and row["era"] == manifest["era"]
                 for step, row in zip(STEPS, manifest["receipts"])),
             "conductor receipt authority mismatch")
    artifact_bytes = sum(len(blob) for blob in run.artifacts.values())
    _require(artifact_bytes <= MAX_ARTIFACT_BYTES, "generated placeholder byte ceiling exceeded")
    verify_manifest(manifest, run.artifacts)
    world = _world(run.plans["world"], quest.get("npcs", {}))
    quest_source = {
        **{key: value for key, value in quest.items() if key != "npcs"},
        "schema": QUEST_SCHEMA,
        "slice_id": manifest["game_id"],
        "world": world,
    }
    quest_receipt = build_quest(quest_source)
    artifact = quest_receipt["artifact"]
    actions = _witness(world, artifact)
    replay = _replay(world, artifact, actions)
    _require(replay["status"] == "completed"
             and replay["earned_rewards"] == artifact["proof"]["rewards"]
             and replay["quest_snapshot"] == artifact["proof"]["snapshot"],
             "graph-bound witness diverged from canonical objective replay")
    body = {
        "schema": DESIGN_SCHEMA, "source_digest": _hash(source),
        "graph_semantics": GRAPH_SEMANTICS,
        "conductor_manifest": manifest,
        "placeholder_artifact_bytes": artifact_bytes,
        "world": world, "quest_receipt": quest_receipt,
        "route_witness": actions, "route_replay": replay,
        "abstract_route_verified": True,
        "native_qualified": False, "release_qualified": False,
    }
    result = {**body, "design_digest": _hash(body)}
    _encode({"request": source, "receipt": result})
    return result


def _session(source: Any, design: dict, actions: Any) -> dict:
    replay = _replay(design["world"], design["quest_receipt"]["artifact"], actions)
    body = {
        "schema": SESSION_SCHEMA, "source_digest": design["source_digest"],
        "design_digest": design["design_digest"], "actions": actions,
        "state": replay, "native_qualified": False, "release_qualified": False,
    }
    result = {**body, "session_digest": _hash(body)}
    # Round-trip to detach caller-owned mutable nested action/payload values.
    import json
    _encode({"request": source, "receipt": result})
    return json.loads(_encode(result))


def play(source: Any, actions: Any) -> dict:
    """Replay an explicit ledger; the design witness is never auto-applied."""
    return _session(source, build_design(source), actions)


def verify_design(source: Any, receipt: Any) -> bool:
    try:
        return _encode(receipt) == _encode(build_design(source))
    except (GameForgeError, ValueError, TypeError, KeyError, OverflowError, RecursionError):
        return False


def verify_session(source: Any, receipt: Any) -> bool:
    try:
        return _encode(receipt) == _encode(play(source, receipt["actions"]))
    except (GameForgeError, ValueError, TypeError, KeyError, OverflowError, RecursionError):
        return False


def resume(source: Any, previous: Any, additional: Any) -> dict:
    """Verify an older ledger under the same source; then replay append only."""
    _encode({"request": source, "receipt": previous, "additional": additional})
    design = build_design(source)
    _require(type(previous) is dict and "actions" in previous, "missing checkpoint ledger")
    _require(_encode(previous) == _encode(_session(source, design, previous["actions"])),
             "checkpoint differs from independent replay")
    _require(type(additional) is list and 1 <= len(additional) <= MAX_ACTIONS,
             "resume requires bounded additional actions")
    actions = previous["actions"] + additional
    return _session(source, design, actions)


__all__ = [
    "REQUEST_SCHEMA", "DESIGN_SCHEMA", "SESSION_SCHEMA", "MAX_ACTIONS",
    "build_design", "verify_design", "play", "verify_session", "resume",
]
