"""Director handoff integrates real playable HTML, quest, scenes and assets."""
import io
import json
from hashlib import sha256
import zipfile

import pytest

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_canon_proof import audit_canon_source
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError, replay_quest
from skeleton.ai.game_builder.studio_ecosystem_director_handoff import (
    SCHEMA, compile_director_handoff, publish_director_handoff,
    verify_director_handoff,
)
from skeleton.ai.agents.jeeves.studio_director_handoff_tool import (
    REQUEST_SCHEMA, execute_director_handoff_tool,
)
from skeleton.ai.agents.jeeves.studio_world_tool_router import (
    route_world_tool, world_tool_catalog,
)

PROJECT = "studio_arena_fighting_glacial_fjord"


def fixture():
    docs = read_blueprint(PROJECT)
    source = audit_canon_source(docs, authorized=True)["source_digest"]
    visual = sha256(json.dumps(
        docs["visual"], sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False).encode("ascii")).hexdigest()
    session = replay_quest(docs, [], authorized=True)
    scenes = docs["scene"]["episode_plan"]
    schedule = {"scene_ticks": {scene["id"]: 5 for scene in scenes},
                "npc_turnaround_ticks": 2, "min_start_ticks": {}}
    recipe = docs["visual"]["asset_recipes"][0]["id"]
    assignments = {
        scene["id"]: {asset: recipe for asset in (
            scene["assets"] + scene["interactive_objects"])}
        for scene in scenes
    }
    return docs, source, visual, session, schedule, assignments


def test_deterministic_complete_html5_and_editor_handoff():
    docs, source, visual, session, schedule, assignments = fixture()
    args = (docs, [], schedule, assignments)
    kwargs = dict(authorized=True, expected_source_digest=source,
                  expected_visual_digest=visual,
                  expected_session_digest=session.digest)
    manifest, archive = compile_director_handoff(*args, **kwargs)
    assert manifest["schema"] == SCHEMA
    assert manifest["canonical_html5_gameplay_replay_verified"] is True
    assert manifest["canonical_playable_receipt"]["validated_gameplay_proof"] is True
    assert manifest["native_asset_binding_verified"] is False
    assert manifest["npc_dialogue_executed_verified"] is False
    assert manifest["release_certified"] is False
    assert sha256(archive).hexdigest() == manifest["bundle_sha256"]
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        assert sorted(z.namelist()) == sorted([
            "index.html", "director_editor.html", "scene_schedule.json",
            "scene_asset_bindings.json", "director_manifest.json"])
        for name, expected in manifest["file_hashes"].items():
            assert sha256(z.read(name)).hexdigest() == expected
        assert z.read("index.html").lstrip().startswith(b"<!DOCTYPE html") or (
            b"<html" in z.read("index.html")[:1024].lower())
        assert json.loads(z.read("scene_schedule.json"))["replay_verified"] is True
        assert json.loads(z.read("scene_asset_bindings.json"))["native_asset_verified"] is False
    assert (manifest, archive) == compile_director_handoff(*args, **kwargs)


def test_stale_source_and_operator_authority_fail_closed():
    docs, source, visual, session, schedule, assignments = fixture()
    for kwargs in (
        dict(expected_source_digest="0" * 64, expected_visual_digest=visual),
        dict(expected_source_digest=source, expected_visual_digest="0" * 64),
        dict(expected_source_digest=source, expected_visual_digest=visual,
             expected_session_digest="0" * 64),
    ):
        with pytest.raises(StudioQuestError):
            compile_director_handoff(
                docs, [], schedule, assignments, authorized=True, **kwargs)
    with pytest.raises(PermissionError):
        compile_director_handoff(
            docs, [], schedule, assignments, authorized=False,
            expected_source_digest=source, expected_visual_digest=visual)


def test_exclusive_private_bundle_publication_and_replay(tmp_path):
    docs, source, visual, session, schedule, assignments = fixture()
    kwargs = dict(authorized=True, expected_source_digest=source,
                  expected_visual_digest=visual,
                  expected_session_digest=session.digest)
    manifest, bundle = compile_director_handoff(
        docs, [], schedule, assignments, **kwargs)
    publication = publish_director_handoff(manifest, bundle, tmp_path, authorized=True,
                                         documents=docs, actions=[],
                                         schedule=schedule, assignments=assignments)
    assert publication["file_write_performed"] is True
    path = tmp_path / "studio_director_handoff.zip"
    assert path.is_file() and path.stat().st_mode & 0o077 == 0
    assert verify_director_handoff(
        docs, [], schedule, assignments, tmp_path, **kwargs) == manifest
    with pytest.raises(FileExistsError):
        publish_director_handoff(manifest, bundle, tmp_path, authorized=True)
    path.write_bytes(bundle[:-1] + bytes([bundle[-1] ^ 1]))
    with pytest.raises(StudioQuestError):
        verify_director_handoff(
            docs, [], schedule, assignments, tmp_path, **kwargs)


def test_jeeves_router_cli_and_static_authority(capsys):
    from scripts.studio_director_handoff_cli import main
    docs, source, visual, session, schedule, assignments = fixture()
    request = {"schema": REQUEST_SCHEMA, "project_id": PROJECT,
               "expected_source_digest": source, "expected_visual_digest": visual,
               "expected_session_digest": session.digest, "actions": [],
               "schedule": schedule, "assignments": assignments}
    direct = execute_director_handoff_tool(request, authorized=True)
    routed = route_world_tool({"tool": "studio_original_director_handoff",
                               "arguments": request}, authorized=True)
    assert routed["result"] == direct
    assert routed["file_write_performed"] is False
    assert any(x["name"] == "studio_original_director_handoff"
               for x in world_tool_catalog()["tools"])
    assert main(["--project", PROJECT, "--expected-source", source,
                 "--expected-visual", visual, "--expected-session", session.digest,
                 "--schedule", json.dumps(schedule),
                 "--assignments", json.dumps(assignments)]) == 0
    assert json.loads(capsys.readouterr().out) == direct["detail"]
    with pytest.raises(StudioQuestError):
        execute_director_handoff_tool({**request, "forged": True}, authorized=True)
    with pytest.raises(PermissionError):
        execute_director_handoff_tool(request, authorized=False)

def test_rehashed_forged_director_bundle_cannot_be_published(tmp_path):
    docs, source, visual, _, schedule, assignments = fixture()
    manifest, bundle = compile_director_handoff(
        docs, [], schedule, assignments, authorized=True,
        expected_source_digest=source, expected_visual_digest=visual)
    forged = dict(manifest)
    forged["native_asset_binding_verified"] = True
    with pytest.raises(StudioQuestError):
        publish_director_handoff(forged, bundle, tmp_path, authorized=True,
                                 documents=docs, actions=[],
                                 schedule=schedule, assignments=assignments)
    assert not (tmp_path / "studio_director_handoff.zip").exists()

def test_offline_editor_has_csp_safe_embedded_json_and_no_native_claims():
    from skeleton.ai.game_builder.studio_ecosystem_director_editor import (
        render_director_editor,
    )
    from skeleton.ai.game_builder.studio_ecosystem_scene_schedule import (
        compile_scene_schedule,
    )
    from skeleton.ai.game_builder.studio_ecosystem_scene_asset_bindings import (
        compile_scene_asset_bindings,
    )
    docs, source, visual, session, schedule, assignments = fixture()
    timing = compile_scene_schedule(
        docs, [], schedule, authorized=True, expected_source_digest=source)
    assets = compile_scene_asset_bindings(
        docs, [], assignments, authorized=True,
        expected_source_digest=source, expected_visual_digest=visual)
    html, receipt = render_director_editor(timing, assets)
    assert sha256(html).hexdigest() == receipt["html_sha256"]
    assert receipt["authoring_export_only"] is True
    assert b"Content-Security-Policy" in html
    assert b"studio_scene_assignments.json" in html
    assert b"studio_scene_schedule.json" in html
    assert b"native_asset_binding_verified" in html
    assert b"innerHTML" not in html
    assert b"eval(" not in html
    assert b"document.write" not in html
    assert render_director_editor(timing, assets) == (html, receipt)
    altered = dict(assets)
    altered["session_digest"] = "0" * 64
    with pytest.raises(StudioQuestError):
        render_director_editor(timing, altered)
