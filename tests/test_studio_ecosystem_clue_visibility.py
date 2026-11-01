"""Source-bound clue trail regression fixtures and adversarial custody."""
from __future__ import annotations

from hashlib import sha256
from io import BytesIO
import json
from zipfile import ZipFile

import pytest

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_canon_proof import audit_canon_source
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError, replay_quest
from skeleton.ai.game_builder.studio_ecosystem_clue_visibility import (
    compile_clue_visibility, propose_clue_visibility, compile_clue_playable,
    publish_clue_visibility, restore_clue_visibility,
)
from skeleton.ai.agents.jeeves.studio_clue_visibility_tool import (
    REQUEST_SCHEMA, execute_clue_visibility_tool,
)
from skeleton.ai.agents.jeeves.studio_world_tool_router import route_world_tool, world_tool_catalog

PROJECT = "studio_arena_fighting_glacial_fjord"
PROMPT = "build a source-bound clue trail"


def fixture():
    docs = read_blueprint(PROJECT)
    source = audit_canon_source(docs, authorized=True)["source_digest"]
    session = replay_quest(docs, [], authorized=True)
    return docs, source, session


def test_prompt_determinism_source_custody_and_visibility():
    docs, source, session = fixture()
    before = json.dumps(docs, sort_keys=True)
    proposal = propose_clue_visibility(
        docs, [], PROMPT, authorized=True,
        expected_source_digest=source, expected_session_digest=session.digest)
    assert proposal == propose_clue_visibility(
        docs, [], PROMPT, authorized=True, expected_source_digest=source)
    report = proposal["detail"]
    assert report["hidden_count"] == len(report["clues"])
    assert report["visible_count"] == 0
    assert all(row["text"] is None for row in report["clues"])
    assert report["source_replay_verified"] is True
    assert json.dumps(docs, sort_keys=True) == before
    assert compile_clue_visibility(
        docs, [], proposal["authoring"], authorized=True,
        expected_source_digest=source) == report


def test_unsafe_spoiler_future_stage_rejected():
    docs, source, session = fixture()
    proposal = propose_clue_visibility(
        docs, [], PROMPT, authorized=True, expected_source_digest=source)
    authoring = proposal["authoring"]
    if len(authoring["clues"]) < 2:
        pytest.skip("authored source has only one stage")
    forged = json.loads(json.dumps(authoring))
    forged["clues"][0]["spoils_stage"] = forged["clues"][-1]["visible_after_stage"]
    with pytest.raises(StudioQuestError):
        compile_clue_visibility(docs, [], forged, authorized=True,
                                expected_source_digest=source)
    forged = json.loads(json.dumps(authoring))
    forged["clues"][0]["scene_id"] = "unknown"
    with pytest.raises(StudioQuestError):
        compile_clue_visibility(docs, [], forged, authorized=True,
                                expected_source_digest=source)


def test_permission_stale_leases_and_untrusted_fields():
    docs, source, session = fixture()
    with pytest.raises(PermissionError):
        propose_clue_visibility(docs, [], PROMPT, authorized=False,
                                expected_source_digest=source)
    with pytest.raises(StudioQuestError):
        propose_clue_visibility(docs, [], "invent hidden evidence", authorized=True,
                                expected_source_digest=source)
    with pytest.raises(StudioQuestError):
        propose_clue_visibility(docs, [], PROMPT, authorized=True,
                                expected_source_digest="0" * 64)
    with pytest.raises(StudioQuestError):
        propose_clue_visibility(docs, [], PROMPT, authorized=True,
                                expected_source_digest=source,
                                expected_session_digest="0" * 64)


def test_private_publish_restore_forgery_symlink(tmp_path):
    docs, source, session = fixture()
    report = propose_clue_visibility(
        docs, [], PROMPT, authorized=True, expected_source_digest=source)["detail"]
    receipt = publish_clue_visibility(docs, report, tmp_path, authorized=True)
    assert receipt["file_write_performed"] is True
    target = tmp_path / "clue_visibility.json"
    assert target.stat().st_mode & 0o077 == 0
    assert restore_clue_visibility(
        docs, tmp_path, authorized=True, expected_source_digest=source) == report
    with pytest.raises(FileExistsError):
        publish_clue_visibility(docs, report, tmp_path, authorized=True)
    forged = {**report, "visible_count": 999}
    target.write_text(json.dumps(forged))
    with pytest.raises(StudioQuestError):
        restore_clue_visibility(docs, tmp_path, authorized=True,
                                expected_source_digest=source)
    target.unlink()
    target.symlink_to(tmp_path / "missing")
    with pytest.raises(OSError):
        restore_clue_visibility(docs, tmp_path, authorized=True,
                                expected_source_digest=source)


def test_canonical_playable_bundle_no_hidden_text_leak():
    docs, source, session = fixture()
    proposal = propose_clue_visibility(
        docs, [], PROMPT, authorized=True, expected_source_digest=source)
    manifest, payload = compile_clue_playable(
        docs, proposal["detail"], authorized=True)
    assert sha256(payload).hexdigest() == manifest["bundle_sha256"]
    assert manifest["canonical_html5_quest_included"] is True
    assert manifest["native_clue_ui_integrated"] is False
    with ZipFile(BytesIO(payload)) as archive:
        assert b"<html" in archive.read("index.html")
        public = json.loads(archive.read("clues.json"))
        assert public["visible_clues"] == []
        assert public["hidden_count"] > 0
        for name, digest in manifest["files"].items():
            assert sha256(archive.read(name)).hexdigest() == digest
    with pytest.raises(StudioQuestError):
        compile_clue_playable(docs, {**proposal["detail"], "hidden_count": 0},
                              authorized=True)


def test_jeeves_router_and_cli_parity(capsys):
    from scripts.studio_clue_visibility_cli import main
    docs, source, session = fixture()
    request = {"schema": REQUEST_SCHEMA, "project_id": PROJECT,
               "expected_source_digest": source, "actions": [], "prompt": PROMPT}
    direct = execute_clue_visibility_tool(request, authorized=True)
    routed = route_world_tool(
        {"tool": "studio_original_clue_visibility", "arguments": request},
        authorized=True)
    assert routed["result"] == direct
    assert any(x["name"] == "studio_original_clue_visibility"
               for x in world_tool_catalog()["tools"])
    assert main(["--project", PROJECT, "--expected-source", source,
                 "--prompt", PROMPT, "--handoff-manifest", "yes"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["proposal"] == direct["detail"]
    assert output["playable_handoff"]["canonical_html5_quest_included"] is True
    with pytest.raises(PermissionError):
        execute_clue_visibility_tool(request, authorized=False)
    with pytest.raises(StudioQuestError):
        execute_clue_visibility_tool({**request, "authorized": True},
                                     authorized=True)
