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
            "actions": AUTHORING_ACTIONS, "action_count": 50,
            "persistence_owner": "canonical_game_learning_workspace",
            "source_file": SOURCE_PATH}
