"""Original-game Director campaign production from Jeeves and approved Dragon evidence.

The local generator produces a reviewable, executable *logic* world using the
canonical Director runtime. It does not certify authored quality, engine frames,
user approval, installations, or trained model checkpoints.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any

CANDIDATE_SCHEMA = "skeleton.jeeves.director_candidate.v1"
PROMOTED_SCHEMA = "skeleton.jeeves.director_campaign_source.v1"
HEX = re.compile(r"[0-9a-f]{64}\Z")
IDENT = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
MAX_CANDIDATE_BYTES = 2 * 1024 * 1024


def _digest(doc: object) -> str:
    return sha256(json.dumps(doc, sort_keys=True, separators=(",", ":"),
                             allow_nan=False, ensure_ascii=True).encode()).hexdigest()


def _project(root: Path) -> tuple[dict[str, str], str, str]:
    from skeleton.developer.game_cli import _load
    from skeleton.developer.jeeves_game_authoring import _config_identity
    cfg = _load(root)
    project_id = cfg["name"].lower().replace("-", "_")
    if not IDENT.fullmatch(project_id):
        raise ValueError("Director project name must normalize to a lowercase identifier")
    return cfg, project_id, _config_identity(cfg)


def _split(value: str | None, *, name: str, min_count: int, max_count: int
           ) -> tuple[str, ...]:
    if not isinstance(value, str):
        raise ValueError(name + " is required")
    result = tuple(value.split(","))
    if not min_count <= len(result) <= max_count or any(
        not IDENT.fullmatch(item) for item in result
    ) or len(result) != len(set(result)):
        raise ValueError(name + " needs unique lowercase identifiers separated by commas")
    return result


def _safe_design(root: Path) -> Path:
    folder = root / "design"
    if root.is_symlink() or folder.is_symlink() or not folder.is_dir():
        raise ValueError("Director requires a non-symlinked existing design directory")
    return folder


def _candidate(root: Path, source: str) -> tuple[dict[str, Any], str, Any]:
    from skeleton.developer.jeeves_game_quality import _read
    from skeleton.ai.game_builder.quest_scene_forge import compile_director_blueprint
    packet, source_sha = _read(root, source, MAX_CANDIDATE_BYTES)
    expected = {"schema", "project", "config_sha256", "director_world",
                "dragon_handoff_sha256", "generator", "receipt_sha256"}
    if set(packet) != expected or packet.get("schema") != CANDIDATE_SCHEMA:
        raise ValueError("unsupported original Director candidate")
    receipt = packet["receipt_sha256"]
    if not isinstance(receipt, str) or not HEX.fullmatch(receipt):
        raise ValueError("invalid Director candidate identity")
    if _digest({k: v for k, v in packet.items() if k != "receipt_sha256"}) != receipt:
        raise ValueError("modified Director candidate; review newly authored source")
    cfg, project, config_hash = _project(root)
    if packet["project"] != cfg["name"] or packet["config_sha256"] != config_hash:
        raise ValueError("game project changed since candidate generation")
    if packet["generator"] != "canonical-seeded-director-v1":
        raise ValueError("unrecognized Director forge engine")
    handoff_id = packet["dragon_handoff_sha256"]
    if handoff_id is not None:
        from skeleton.developer.jeeves_game_dragon import load_handoff
        if not isinstance(handoff_id, str) or not HEX.fullmatch(handoff_id):
            raise ValueError("malformed Dragon handoff dependency")
        load_handoff(root, handoff_id)
    world = compile_director_blueprint(packet["director_world"], human_reviewed=True)
    if world.project_id != project or packet["director_world"] != world.payload():
        raise ValueError("Director world differs from canonical source or project")
    return packet, source_sha, world


def draft(root: Path, *, seed: int, regions: str, quest_types: str,
          stages: int = 3, goal: str | None = None,
          dragon_digest: str | None = None) -> dict[str, Any]:
    from skeleton.ai.game_builder.quest_scene_forge import forge_director
    from skeleton.ai.game_builder.quest_scene_engine import ARCHETYPES
    from skeleton.developer.jeeves_game_authoring import _create_only
    cfg, project, config_hash = _project(root)
    _safe_design(root)
    sites = _split(regions, name="--regions", min_count=4, max_count=24)
    arcs = _split(quest_types, name="--quest-types", min_count=1, max_count=48)
    if arcs[0] != "main_story" or any(item not in ARCHETYPES for item in arcs):
        raise ValueError("--quest-types must begin with main_story and use Director archetypes")
    if type(seed) is not int or not 0 <= seed <= 2**63 - 1:
        raise ValueError("seed must be an unsigned 63-bit integer")
    if type(stages) is not int or not 2 <= stages <= 12:
        raise ValueError("stages must be 2..12")
    if goal is None:
        goal = cfg["vision"]
    if not isinstance(goal, str) or not 1 <= len(goal) <= 220 or (
        goal != goal.strip() or any(ord(c) < 32 for c in goal)
    ):
        raise ValueError("invariant story goal must be short, printable and nonblank")
    if dragon_digest is not None:
        from skeleton.developer.jeeves_game_dragon import load_handoff
        handoff = load_handoff(root, dragon_digest)
        if handoff["project"] != cfg["name"]:
            raise ValueError("Dragon handoff belongs to another project")
    world = forge_director(project, seed=seed, regions=sites,
                           quest_types=arcs, stages=stages, main_goal=goal)
    packet = {
        "schema": CANDIDATE_SCHEMA, "project": cfg["name"],
        "config_sha256": config_hash, "director_world": world.payload(),
        "dragon_handoff_sha256": dragon_digest,
        "generator": "canonical-seeded-director-v1",
    }
    packet["receipt_sha256"] = _digest(packet)
    from skeleton.developer.jeeves_game_quality import _read
    name = "design/director_candidate_" + packet["receipt_sha256"][:16] + ".json"
    path = _safe_design(root) / name.split("/")[-1]
    encoded = (json.dumps(packet, ensure_ascii=True, sort_keys=True,
                          indent=2, allow_nan=False) + "\n").encode()
    if len(encoded) > MAX_CANDIDATE_BYTES:
        raise ValueError("Director campaign candidate exceeds local source inspection capacity")
    _create_only(path, encoded)
    return {"ok": True, "action": "director-draft",
            "source": name, "source_sha256": sha256(path.read_bytes()).hexdigest(),
            "candidate_sha256": packet["receipt_sha256"],
            "director_world_sha256": world.digest, "scenes": len(world.scenes),
            "quests": len(world.quests), "stages": sum(len(q.stages) for q in world.quests),
            "approved_by_user": False, "native_game_built": False,
            "next": "director-examine --source " + name}


def examine(root: Path, *, source: str, routes: int = 3) -> dict[str, Any]:
    from skeleton.ai.game_builder.quest_campaign_completion import compare_campaign_branches
    if type(routes) is not int or not 2 <= routes <= 8:
        raise ValueError("Director campaign scrutiny requires 2..8 independent routes")
    packet, source_sha, world = _candidate(root, source)
    result = compare_campaign_branches(world, routes=routes)
    if not result["ok"] or not result["all_routes_completed"]:
        raise ValueError("Director world did not complete all replayed campaign routes")
    from skeleton.developer.jeeves_game_quality import _read
    if _read(root, source, MAX_CANDIDATE_BYTES)[1] != source_sha:
        raise ValueError("Director candidate changed during replay")
    return {
        "ok": True, "action": "director-examine", "source": source,
        "source_sha256": source_sha, "candidate_sha256": packet["receipt_sha256"],
        "world_sha256": world.digest, "scenes": len(world.scenes),
        "quests": len(world.quests),
        "quest_stages": sum(len(quest.stages) for quest in world.quests),
        "cutscenes": sum(len(scene.cutscenes) for scene in world.scenes),
        "route_count": result["route_count"],
        "all_routes_completed": result["all_routes_completed"],
        "distinct_outcome_stage_count": result["distinct_outcome_stage_count"],
        "replay_state_sha256": [
            row["final_director_state_sha256"] for row in result["route_reports"]
        ],
        "dragon_handoff_sha256": packet["dragon_handoff_sha256"],
        "read_only_inspection": True, "operator_approval_verified": False,
        "headless_engine_playtest_performed": False,
        "quality_independently_qualified": False,
    }


def promote(root: Path, *, source: str, approved_digest: str | None,
            routes: int = 3) -> dict[str, Any]:
    """Approve the exact examined logic candidate; create-only canonical input."""
    from skeleton.developer.jeeves_game_quality import _read
    from skeleton.developer.jeeves_game_authoring import _create_only
    audit = examine(root, source=source, routes=routes)
    if approved_digest != audit["candidate_sha256"]:
        raise ValueError("--approve must match the full examined Director candidate receipt")
    packet, source_sha, world = _candidate(root, source)
    if audit["source_sha256"] != source_sha:
        raise ValueError("Director candidate changed between inspection and approval")
    dest = _safe_design(root) / "director_campaign_source.json"
    payload = {
        "schema": PROMOTED_SCHEMA, "director_world": world.payload(),
        "author_review_acknowledged": True,
    }
    if _read(root, source, MAX_CANDIDATE_BYTES)[1] != source_sha:
        raise ValueError("Director candidate changed while promoting")
    _create_only(dest, (json.dumps(payload, sort_keys=True, indent=2,
                                   allow_nan=False) + "\n").encode())
    return {"ok": True, "action": "director-promote", "source": source,
            "path": str(dest), "candidate_sha256": packet["receipt_sha256"],
            "director_world_sha256": world.digest,
            "eligible_for_canonical_logic_replay": True,
            "operator_approval_independently_verified": False,
            "real_native_game_verified": False,
            "next": "direction-campaign --source design/director_campaign_source.json"}
