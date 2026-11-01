"""Original scene asset bindings: source, visual, replay, persistence, CLI."""
import json
from hashlib import sha256

import pytest

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_canon_proof import audit_canon_source
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError, replay_quest
from skeleton.ai.game_builder.studio_ecosystem_scene_asset_bindings import (
    SCHEMA, compile_scene_asset_bindings, publish_scene_asset_bindings,
    verify_scene_asset_bindings,
)
from skeleton.ai.agents.jeeves.studio_scene_asset_binding_tool import (
    REQUEST_SCHEMA, execute_scene_asset_binding_tool,
)
from skeleton.ai.agents.jeeves.studio_world_tool_router import (
    route_world_tool, world_tool_catalog,
)

PROJECT = "studio_arena_fighting_glacial_fjord"


def fixture(project=PROJECT):
    docs = read_blueprint(project)
    source = audit_canon_source(docs, authorized=True)["source_digest"]
    visual = sha256(json.dumps(
        docs["visual"], sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False).encode("ascii")).hexdigest()
    session = replay_quest(docs, [], authorized=True)
    recipes = docs["visual"].get("jobs") or docs["visual"]["asset_recipes"]
    first = recipes[0]["id"]
    assignments = {
        scene["id"]: {key: first for key in (
            scene.get("assets", []) + scene.get("interactive_objects", []))}
        for scene in docs["scene"]["episode_plan"]
    }
    return docs, source, visual, session, assignments


@pytest.mark.parametrize("project", [
    "studio_arena_fighting_glacial_fjord",
    "studio_puzzle_expedition_copper_mesa",
])
def test_exact_scene_asset_coverage_with_original_recipe_work_orders(project):
    docs, source, visual, session, assignments = fixture(project)
    original = json.dumps(docs, sort_keys=True)
    result = compile_scene_asset_bindings(
        docs, [], assignments, authorized=True,
        expected_source_digest=source, expected_visual_digest=visual,
        expected_session_digest=session.digest)
    assert result["schema"] == SCHEMA
    assert result["scene_count"] == len(assignments)
    assert result["binding_count"] == sum(map(len, assignments.values()))
    assert result["used_recipe_count"] == 1
    assert result["replay_verified"] is True
    assert result["native_asset_verified"] is False
    assert result["rights_verified"] is False
    assert result["release_certified"] is False
    assert json.dumps(docs, sort_keys=True) == original
    assert result == compile_scene_asset_bindings(
        docs, [], assignments, authorized=True,
        expected_source_digest=source, expected_visual_digest=visual,
        expected_session_digest=session.digest)


def test_stale_leases_forged_assignments_and_authority_fail_closed():
    docs, source, visual, session, assignments = fixture()
    for overrides in (
        {"expected_source_digest": "0" * 64},
        {"expected_visual_digest": "0" * 64},
        {"expected_session_digest": "0" * 64},
        {"expected_source_digest": True},
    ):
        kwargs = dict(authorized=True, expected_source_digest=source,
                      expected_visual_digest=visual,
                      expected_session_digest=session.digest)
        kwargs.update(overrides)
        with pytest.raises(StudioQuestError):
            compile_scene_asset_bindings(docs, [], assignments, **kwargs)
    forged = json.loads(json.dumps(assignments))
    first = next(iter(forged))
    forged[first][next(iter(forged[first]))] = "unregistered_recipe"
    with pytest.raises(StudioQuestError):
        compile_scene_asset_bindings(docs, [], forged, authorized=True,
                                     expected_source_digest=source,
                                     expected_visual_digest=visual)
    with pytest.raises(PermissionError):
        compile_scene_asset_bindings(docs, [], assignments, authorized=False,
                                     expected_source_digest=source,
                                     expected_visual_digest=visual)


def test_private_publication_restore_and_tamper(tmp_path):
    docs, source, visual, session, assignments = fixture()
    receipt = compile_scene_asset_bindings(
        docs, [], assignments, authorized=True,
        expected_source_digest=source, expected_visual_digest=visual)
    published = publish_scene_asset_bindings(receipt, tmp_path, authorized=True)
    assert published["file_write_performed"] is True
    path = tmp_path / "scene_asset_bindings.json"
    assert path.is_file() and path.stat().st_mode & 0o077 == 0
    assert verify_scene_asset_bindings(
        docs, [], tmp_path, authorized=True,
        expected_source_digest=source, expected_visual_digest=visual) == receipt
    with pytest.raises(FileExistsError):
        publish_scene_asset_bindings(receipt, tmp_path, authorized=True)
    altered = dict(receipt)
    altered["binding_count"] += 1
    path.write_text(json.dumps(altered))
    with pytest.raises(StudioQuestError):
        verify_scene_asset_bindings(
            docs, [], tmp_path, authorized=True,
            expected_source_digest=source, expected_visual_digest=visual)


def test_jeeves_router_and_cli_exact_parity(capsys):
    from scripts.studio_scene_asset_cli import main
    docs, source, visual, session, assignments = fixture()
    request = {
        "schema": REQUEST_SCHEMA, "project_id": PROJECT,
        "expected_source_digest": source, "expected_visual_digest": visual,
        "expected_session_digest": session.digest,
        "actions": [], "assignments": assignments,
    }
    direct = execute_scene_asset_binding_tool(request, authorized=True)
    routed = route_world_tool({"tool": "studio_authored_scene_asset_bindings",
                               "arguments": request}, authorized=True)
    assert routed["result"] == direct
    assert routed["file_write_performed"] is False
    assert any(x["name"] == "studio_authored_scene_asset_bindings"
               for x in world_tool_catalog()["tools"])
    assert main(["--project", PROJECT, "--expected-source", source,
                 "--expected-visual", visual, "--expected-session", session.digest,
                 "--assignments", json.dumps(assignments)]) == 0
    assert json.loads(capsys.readouterr().out) == direct["detail"]
    with pytest.raises(StudioQuestError):
        execute_scene_asset_binding_tool({**request, "authorized": True},
                                         authorized=True)
    with pytest.raises(PermissionError):
        execute_scene_asset_binding_tool(request, authorized=False)
    with pytest.raises(SystemExit):
        main(["--project", PROJECT, "--expected-source", source,
              "--expected-visual", visual,
              "--assignments", '{"origin":{},"origin":{}}'])
