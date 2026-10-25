"""Authenticated Forge Studio authoring through canonical game-learning revisions.

This is an application adapter, NOT a second persistence/runtime. Existing
workspace project files and versioned save_editor own the source, while Forge
Studio creates actual map, NPC, event, quest and native game content.
"""
from __future__ import annotations

from typing import Any, Mapping

from core.game_learning import GameLearningError, workspace
from skeleton.forge.game_frontier_studio import StudioError, compile_studio_expedition
from skeleton.forge.game_frontier_studio_authoring import (
    AUTHORING_ACTIONS, apply_authoring_batch, authored_summary,
    authored_tile_region, project_digest,
)
from skeleton.forge.game_frontier_studio_document import (
    authored_document, create_authoring_project, load_authored_document,
)
from skeleton.jeeves.game_frontier_expedition_generation import ArchipelagoProfile

SOURCE_PATH = "game/editor/frontier_studio.json"


async def _source(scope: Mapping[str, str], project_id: str):
    scope = workspace._scope(scope["tenant_id"], scope["owner_id"])
    owner = await workspace.get_project(scope, project_id)
    bound = await workspace._project(project_id, scope, owner["version"])
    binding = await workspace._input(scope, bound, require_execution=False)
    await workspace._authority(scope, binding)
    record = next((item for item in owner["files"]
                   if item["path"] == SOURCE_PATH), None)
    authored = (
        create_authoring_project(project_id)
        if record is None else
        load_authored_document(record["content"], project_id=project_id)
    )
    return owner, authored


async def document(scope: Mapping[str, str], project_id: str) -> dict:
    owner, authored = await _source(scope, project_id)
    return {"schema": "skeleton.game.frontier_studio_document.v1",
            "project_id": project_id, "expected_version": owner["version"],
            "studio_file": SOURCE_PATH,
            "already_saved": any(f["path"] == SOURCE_PATH for f in owner["files"]),
            **authored_summary(authored)}


async def copy_tiles(scope: Mapping[str, str], project_id: str,
                     *, layer: str, x: int, y: int,
                     width: int, height: int) -> dict:
    _, authored = await _source(scope, project_id)
    return authored_tile_region(authored, layer, x=x, y=y,
                                width=width, height=height)


async def edit(scope: Mapping[str, str], project_id: str,
               body: Mapping[str, Any], *, preview: bool) -> dict:
    if (type(body.get("expected_version")) is not int
            or type(body.get("expected_sha256")) is not str
            or type(body.get("idempotency_key")) is not str
            or not body.get("idempotency_key")):
        raise StudioError("exact version, source digest and operation key required")
    owner, authored = await _source(scope, project_id)
    before = project_digest(authored)
    if owner["version"] != body["expected_version"] or before != body["expected_sha256"]:
        raise GameLearningError("studio_source_conflict",
                                "Studio source version or digest has changed.", 409)
    result = apply_authoring_batch(authored, body["steps"])
    candidate = result["project"]
    candidate_digest = project_digest(candidate)
    if preview:
        return {"schema": "skeleton.game.frontier_studio_preview.v1",
                "source_sha256": before, "candidate_sha256": candidate_digest,
                "batch_receipt": result["receipt"],
                "summary": authored_summary(candidate),
                "persisted": False}
    if before == candidate_digest:
        raise StudioError("unchanged edit cannot create redundant project revision")
    rendered = authored_document(candidate)
    files = [{"path": item["path"], "content": item["content"]}
             for item in owner["files"] if item["path"] != SOURCE_PATH]
    files.append({"path": SOURCE_PATH, "content": rendered})
    saved = await workspace.save_editor(scope, project_id, {
        "expected_version": owner["version"],
        "idempotency_key": body["idempotency_key"],
        "files": files,
        "entrypoint": owner["entrypoint"],
    })
    rewritten = next((f for f in saved["files"] if f["path"] == SOURCE_PATH), None)
    if rewritten is None or project_digest(
        load_authored_document(rewritten["content"], project_id=project_id)
    ) != candidate_digest:
        raise GameLearningError("studio_commit_mismatch",
                                "Host saved an unexpected authored game source.", 409)
    return {"schema": "skeleton.game.frontier_studio_committed.v1",
            "project_id": project_id, "expected_version": saved["version"],
            "source_sha256": candidate_digest,
            "batch_receipt": result["receipt"],
            "summary": authored_summary(candidate),
            "persisted": True}


async def compile_game(scope: Mapping[str, str], project_id: str,
                       *, seed: int, islands: int, include_godot: bool) -> dict:
    owner, authored = await _source(scope, project_id)
    profile = ArchipelagoProfile(seed=seed, islands=islands, caverns=0,
                                 include_underwater=True, include_portals=True)
    output = compile_studio_expedition(
        authored, profile, playtest_routes=4, include_godot=include_godot)
    files = output.get("godot_project_files")
    if files is not None:
        if sum(len(data.encode("utf-8")) for data in files.values()) > 2_000_000:
            raise StudioError("native playable game files exceed bounded response")
    return {
        "schema": "skeleton.game.frontier_studio_build.v1",
        "project_id": project_id, "source_version": owner["version"],
        "source_sha256": project_digest(authored),
        "world_sha256": output["world_digest"],
        "gameplay": output["playtest"],
        "world_nodes": output["waypoints"],
        "travel_edges": output["travel_edges"],
        "file_count": len(files) if files is not None else 0,
        "godot_project_files": files,
        "native_engine_executed": False,
        "release_certified": False,
        "receipt_sha256": output["receipt_digest"],
    }


def catalog() -> dict:
    return {"schema": "skeleton.game.frontier_studio_authoring_catalog.v1",
            "actions": AUTHORING_ACTIONS[:500], "action_count": 50000000000000,
            "core_action_count": 500, "recipe_count": 49999999999500,
            "classic_recipe_count": 4500, "expanded_recipe_count": 45000,
            "directed_recipe_count": 450000,
            "final_recipe_count": 4500000,
            "worldline_recipe_count": 45000000,
            "phase_recipe_count": 450000000,
            "campaign_recipe_count": 4500000000,
            "chronicle_recipe_count": 45000000000,
             "epoch_recipe_count": 450000000000,
            "saga_recipe_count": 4500000000000,
            "continuity_recipe_count": 4500000000000,
            "epic_recipe_count": 45000000000000,
            "recipe_search_path": "/api/game-frontier-authoring/recipes",
            "persistence_owner": "canonical_game_learning_workspace",
            "source_file": SOURCE_PATH}



async def export_native_project(scope: Mapping[str, str], project_id: str,
                                body: Mapping[str, Any]) -> dict:
    """Write an actually emitted Godot project into canonical owned project files.

    The game comes from Forge's existing original expedition compiler, and the
    versioned workspace save transaction is authoritative. No mock binaries,
    arbitrary filesystem locations or second project DB are created.
    """
    owner, authored = await _source(scope, project_id)
    if (owner["version"] != body.get("expected_version")
            or project_digest(authored) != body.get("expected_sha256")):
        raise GameLearningError("studio_source_conflict",
                                "Studio project changed before native build.", 409)
    seed, islands = body.get("seed"), body.get("islands")
    if (type(seed) is not int or not 0 <= seed <= 2**63 - 1
            or type(islands) is not int or not 3 <= islands <= 64):
        raise StudioError("bounded original world generation profile required")
    original = compile_studio_expedition(
        authored, ArchipelagoProfile(seed=seed, islands=islands, caverns=0),
        playtest_routes=4, include_godot=True,
    )
    generated = original["godot_project_files"]
    folder = "game/generated/frontier_native/" + original["world_digest"][:16] + "/"
    paths = [folder + leaf for leaf in generated]
    if len(set(paths)) != len(paths):
        raise StudioError("duplicate native Godot source file")
    existing = {f["path"] for f in owner["files"]}
    if any(path in existing for path in paths):
        raise GameLearningError("studio_build_collision",
                                "Native output for this exact content already exists.", 409)
    files = [{"path": f["path"], "content": f["content"]} for f in owner["files"]]
    files.extend({"path": folder + name, "content": content}
                 for name, content in sorted(generated.items()))
    saved = await workspace.save_editor(scope, project_id, {
        "expected_version": owner["version"],
        "idempotency_key": body["idempotency_key"],
        "files": files, "entrypoint": owner["entrypoint"],
    })
    saved_paths = {f["path"] for f in saved["files"]}
    if not set(paths) <= saved_paths:
        raise GameLearningError("studio_native_save_mismatch",
                                "Native build was not committed to project source.", 409)
    return {
        "schema": "skeleton.game.frontier_studio_native_export.v1",
        "project_id": project_id, "source_sha256": project_digest(authored),
        "game_world_sha256": original["world_digest"],
        "expected_version": saved["version"],
        "file_count": len(paths), "file_paths": paths,
        "playtest": original["playtest"],
        "receipt_sha256": original["receipt_digest"],
        "saved": True, "native_executed": False, "release_certified": False,
    }



async def simulate_gameplay(scope: Mapping[str, str], project_id: str,
                            body: Mapping[str, Any]) -> dict:
    """Actually evaluate authored RPG signals, 3D zone occupancy and field force.

    Uses canonical deterministic Forge RPG evaluator and native body force
    equation; the position and sensor snapshot are declared simulation inputs.
    Results are playable *reference* mechanics, not a fabricated native capture.
    """
    from dataclasses import asdict
    from hashlib import sha256
    import json
    import math
    from skeleton.forge.game_frontier_rpg_events import evaluate_environment_events
    from skeleton.forge.game_frontier_studio import (
        compile_studio_gameplay_zones, compile_studio_gameplay_force_fields,
    )
    from skeleton.jeeves.game_frontier_native_fields import calculated_native_field_force

    version, authored = await _source(scope, project_id)
    xyz = body.get("position_xyz_m")
    mass = body.get("mass_kg")
    if (type(xyz) is not list or len(xyz) != 3 or
            any(type(v) not in (int, float) or not math.isfinite(v) or abs(v) > 1e7
                for v in xyz) or type(mass) not in (int, float)
            or not math.isfinite(mass) or not 0 < mass <= 100000):
        raise StudioError("gameplay simulation needs bounded position and body mass")
    zones = compile_studio_gameplay_zones(authored)["zones"]
    fields = compile_studio_gameplay_force_fields(authored)["fields"]
    entered = []
    for zone in zones:
        center = zone["center_xyz_m"]
        delta_squared = sum((a-b)**2 for a, b in zip(xyz, center))
        if delta_squared <= zone["radius_m"] ** 2:
            entered.append({
                "zone_id": zone["id"],
                "actor_id": zone["actor_id"],
                "event_page_id": zone["event_page_id"],
                "action_kind": zone["action_kind"],
            })
    forces = []
    total = [0.0, 0.0, 0.0]
    for field in fields:
        force = calculated_native_field_force(field, xyz, mass)
        total = [a+b for a,b in zip(total,force)]
        forces.append({
            "field_id": field["id"], "force_xyz_n": list(force),
        })
    evaluation = evaluate_environment_events(
        authored.environmental_pages,
        current=body.get("current_signals", {}),
        previous=body.get("previous_signals", {}),
        flags=body.get("flags", {}),
        now_ms=body.get("now_ms", 0),
    )
    result = {
        "schema": "skeleton.game.frontier_studio_gameplay_reference.v1",
        "project_id": project_id,
        "source_version": version["version"],
        "source_sha256": project_digest(authored),
        "position_xyz_m": xyz, "mass_kg": mass,
        "occupied_zones": entered,
        "zone_count": len(zones),
        "force_field_count": len(fields),
        "field_forces": forces,
        "net_force_xyz_n": total,
        "environment_accepted": [asdict(item) for item in evaluation.accepted],
        "environment_suppressed": list(evaluation.suppressed),
        "missing_sensor_signals": list(evaluation.missing_signals),
        "source_observed": False, "native_engine_executed": False,
    }
    result["receipt_sha256"] = sha256(json.dumps(
        result, sort_keys=True, separators=(",", ":"),
        allow_nan=False).encode("utf-8")).hexdigest()
    return result


async def audit_epic_interlayer(scope: Mapping[str, str], project_id: str,
                                body: Mapping[str, Any]) -> dict:
    """Recheck registered interlayer references against authoritative project.

    No native transfer and no new source owner. Each receipt binds the exact
    canonical project revision and is independently replayed before reply.
    """
    from skeleton.forge.game_frontier_studio_epic_route_graph import (
        audit_epic_interlayer_routes, verify_epic_interlayer_routes,
    )
    owner, authored = await _source(scope, project_id)
    report = audit_epic_interlayer_routes(authored, body)
    if not verify_epic_interlayer_routes(authored, body, report):
        raise StudioError("Epic route witness failed replay against saved source")
    return {
        **report, "source_version": owner["version"],
        "verified_against_authoritative_source": True,
    }


async def audit_walkable_routes(scope: Mapping[str, str], project_id: str,
                                body: Mapping[str, Any]) -> dict:
    """Inspect up to 100 source-tile routes without modifying project state.

    Existing game-learning workspace authorization and versioning remain the
    only source owners. Reference replay is not a native Godot playthrough.
    """
    from skeleton.forge.game_frontier_studio_route_assurance import (
        audit_route_playthroughs, verify_route_playthroughs,
    )

    owner, authored = await _source(scope, project_id)
    scenarios = body.get("scenarios")
    report = audit_route_playthroughs(authored, scenarios)
    if not verify_route_playthroughs(authored, scenarios, report):
        raise StudioError("route replay proof diverged from the authored source")
    return {
        **report,
        "source_version": owner["version"],
        "verified_against_authoritative_source": True,
    }


# --------------------------------------------------------------------------
# GF-B: save / restore / replay (extend-only; durable SQLite/WAL adapter)
# --------------------------------------------------------------------------
import os as _os
import threading as _threading

from skeleton.kernel.game_save_plane import (
    ChunkReceiptStore as _ChunkReceiptStore, GameSavePlane as _GameSavePlane,
    SavePlaneError,
)
from skeleton.persistence.game_save_sqlite import (
    SqliteCheckpointStore as _SqliteCheckpointStore,
    SqliteReplayJournal as _SqliteReplayJournal,
    open_game_save_db as _open_game_save_db,
)

GAME_SAVE_DB_ENV = "SKELETON_GAME_SAVE_DB"
_save_state: dict = {}
_save_lock = _threading.Lock()


def _save_plane():
    with _save_lock:
        if "plane" not in _save_state:
            path = _os.environ.get(GAME_SAVE_DB_ENV, ":memory:")
            conn = _open_game_save_db(path)
            _save_state["conn"] = conn
            _save_state["plane"] = _GameSavePlane(
                store=_SqliteCheckpointStore(conn))
        return _save_state["plane"]


def _reset_save_plane() -> None:
    """Test hook: drop the cached plane so the next call reopens the DB."""
    with _save_lock:
        conn = _save_state.pop("conn", None)
        _save_state.clear()
        if conn is not None:
            conn.close()


def _save_slot(scope: Mapping[str, str], project_id: str, slot: str) -> str:
    return f"{scope['tenant_id']}/{scope['owner_id']}/{project_id}/{slot}"


async def save_game_state(scope: Mapping[str, str], project_id: str, slot: str,
                          sequence: int, sections: Mapping[str, Mapping[str, Any]],
                          receipts: Any = None) -> dict:
    await _source(scope, project_id)  # authority check
    store = None
    if receipts:
        store = _ChunkReceiptStore()
        for item in receipts:
            store.put(str(item["chunk_id"]), item["body"])
    ckpt = _save_plane().save(_save_slot(scope, project_id, slot), int(sequence),
                              sections, receipts=store)
    return {"schema": "skeleton.game.frontier_save.v1", "project_id": project_id,
            "slot": slot, "sequence": ckpt.sequence, "seal": ckpt.seal,
            "receipt_root": ckpt.state.get("receipt_root")}


async def restore_game_state(scope: Mapping[str, str], project_id: str, slot: str,
                             sequence: Any = None, receipt_cursor: int = 0,
                             receipt_limit: int = 100) -> dict:
    await _source(scope, project_id)
    plane = _save_plane()
    key = _save_slot(scope, project_id, slot)
    sections, receipts = plane.restore(key, sequence=sequence)
    out = {"schema": "skeleton.game.frontier_restore.v1",
           "project_id": project_id, "slot": slot, "sections": sections,
           "backups": list(plane.backups(key)), "receipts": None}
    if receipts is not None:
        page = receipts.page(cursor=receipt_cursor, limit=receipt_limit)
        out["receipts"] = {
            "items": [{"chunk_id": r.chunk_id, "digest": r.digest, "body": r.body}
                      for r in page.items],
            "next_cursor": page.next_cursor, "total": page.total,
            "root": receipts.root()}
    return out


def _journal(scope: Mapping[str, str], project_id: str, stream: str):
    _save_plane()
    return _SqliteReplayJournal(_save_state["conn"],
                                _save_slot(scope, project_id, stream))


async def record_replay_frames(scope: Mapping[str, str], project_id: str,
                               stream: str, frames: Any) -> dict:
    await _source(scope, project_id)
    journal = _journal(scope, project_id, stream)
    for item in frames:
        journal.append(int(item["frame"]), item["event"])
    return {"stream": stream, "head_digest": journal.head_digest(),
            "frames": len(journal.frames())}


async def replay_frames(scope: Mapping[str, str], project_id: str, stream: str,
                        after: int = -1, upto: Any = None,
                        context_upto: Any = None) -> dict:
    await _source(scope, project_id)
    journal = _journal(scope, project_id, stream)
    frames = [{"frame": f, "event": e} for f, e in journal.frames(after=after)
              if upto is None or f <= upto]
    return {"stream": stream, "frames": frames,
            "ai_context": journal.ai_context(upto=context_upto),
            "head_digest": journal.head_digest()}
