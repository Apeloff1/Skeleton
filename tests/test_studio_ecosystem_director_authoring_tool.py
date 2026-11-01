"""Typed Jeeves director import is source-bound and opt-in."""
from __future__ import annotations

from hashlib import sha256
import json

import pytest

from skeleton.ai.agents.jeeves.studio_director_authoring_tool import (
    REQUEST_SCHEMA, execute_director_authoring_tool,
)
from skeleton.ai.agents.jeeves.studio_world_tool_router import (
    route_world_tool, world_tool_catalog,
)
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_canon_proof import audit_canon_source
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError, replay_quest
from skeleton.ai.game_builder.studio_ecosystem_director_authoring import (
    SCHEMA as EXPORT_SCHEMA,
)

PROJECT = "studio_arena_fighting_glacial_fjord"


def request():
    docs = read_blueprint(PROJECT)
    source = audit_canon_source(docs, authorized=True)["source_digest"]
    visual = sha256(json.dumps(
        docs["visual"], sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False).encode("ascii")).hexdigest()
    session = replay_quest(docs, [], authorized=True).digest
    scenes = docs["scene"]["episode_plan"]
    recipe = docs["visual"]["asset_recipes"][0]["id"]
    export = {
        "schema": EXPORT_SCHEMA, "source_digest": source,
        "visual_digest": visual, "session_digest": session,
        "schedule": {
            "scene_ticks": {s["id"]: 5 for s in scenes},
            "npc_turnaround_ticks": 2, "min_start_ticks": {},
        },
        "assignments": {
            s["id"]: {asset: recipe for asset in s["assets"] + s["interactive_objects"]}
            for s in scenes
        },
    }
    return {"schema": REQUEST_SCHEMA, "project_id": PROJECT,
            "actions": [], "export": export}


def test_editor_import_routes_to_real_compiler_with_explicit_authoring_permission():
    req = request()
    result = execute_director_authoring_tool(req, authorized=True)
    assert result["source_replay_verified"] is True
    assert result["detail"]["canonical_html5_gameplay_replay_verified"] is True
    assert result["file_write_performed"] is False
    assert len(result["request_digest"]) == 64
    assert len(result["result_digest"]) == 64
    assert result == execute_director_authoring_tool(req, authorized=True)
    assert result["release_certified"] is False
    catalog = world_tool_catalog()
    descriptor = next(x for x in catalog["tools"]
                      if x["name"] == "studio_original_director_authoring")
    assert descriptor["explicit_authoring_permission_required"] is True
    with pytest.raises(PermissionError):
        route_world_tool({"tool": "studio_original_director_authoring",
                          "arguments": req}, authorized=True)
    routed = route_world_tool({"tool": "studio_original_director_authoring",
                               "arguments": req},
                              authorized=True, allow_authoring=True)
    assert routed["result"] == result


def test_stale_forged_and_untrusted_editor_imports_fail_closed():
    req = request()
    with pytest.raises(PermissionError):
        execute_director_authoring_tool(req, authorized=False)
    for key, value in [
        ("session_digest", "0" * 64),
        ("source_digest", "0" * 64),
        ("visual_digest", "0" * 64),
    ]:
        altered = {**req, "export": {**req["export"], key: value}}
        with pytest.raises(StudioQuestError):
            execute_director_authoring_tool(altered, authorized=True)
    altered = {**req, "export": {**req["export"], "extra": "forged"}}
    with pytest.raises(StudioQuestError):
        execute_director_authoring_tool(altered, authorized=True)
    altered = {**req, "authorized": True}
    with pytest.raises(StudioQuestError):
        execute_director_authoring_tool(altered, authorized=True)
    with pytest.raises(StudioQuestError):
        execute_director_authoring_tool({**req, "schema": "forged"}, authorized=True)
