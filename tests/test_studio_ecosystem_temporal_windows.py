"""Deterministic temporal-window authoring, custody and playable integration."""
from __future__ import annotations

from hashlib import sha256
from io import BytesIO
import json
from zipfile import ZipFile

import pytest

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_canon_proof import audit_canon_source
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_temporal_windows import (
    PROMPT, compile_temporal_windows, propose_temporal_windows,
    replay_temporal_windows, publish_temporal_windows,
    restore_temporal_windows, compile_temporal_playable,
)
from skeleton.ai.agents.jeeves.studio_temporal_windows_tool import (
    REQUEST_SCHEMA, execute_temporal_windows_tool,
)
from skeleton.ai.agents.jeeves.studio_world_tool_router import (
    route_world_tool, world_tool_catalog,
)

PROJECT = "studio_arena_fighting_glacial_fjord"


def fixture():
    docs = read_blueprint(PROJECT)
    source = audit_canon_source(docs, authorized=True)["source_digest"]
    proposal = propose_temporal_windows(
        docs, [], PROMPT, authorized=True, expected_source_digest=source)
    return docs, source, proposal


def test_prompt_replay_and_authored_window_determinism():
    docs, source, proposal = fixture()
    assert proposal == propose_temporal_windows(
        docs, [], PROMPT, authorized=True, expected_source_digest=source)
    report = proposal["detail"]
    assert report["source_replay_verified"] is True
    assert report["native_time_verified"] is False
    assert report == compile_temporal_windows(
        docs, [], proposal["authoring"], authorized=True,
        expected_source_digest=source)
    assert report == replay_temporal_windows(docs, report, authorized=True)
    assert all(row["deadline_slack"] >= 0 for row in report["window_proofs"])


def test_deadline_missed_earliest_and_exclusive_overlap_fail_closed():
    docs, source, proposal = fixture()
    authored = json.loads(json.dumps(proposal["authoring"]))
    first = next(iter(authored["windows"]))
    authored["windows"][first]["latest"] = 0
    with pytest.raises(StudioQuestError):
        compile_temporal_windows(docs, [], authored, authorized=True,
                                 expected_source_digest=source)
    authored = json.loads(json.dumps(proposal["authoring"]))
    authored["windows"][first]["earliest"] = 1000
    with pytest.raises(StudioQuestError):
        compile_temporal_windows(docs, [], authored, authorized=True,
                                 expected_source_digest=source)
    authored = json.loads(json.dumps(proposal["authoring"]))
    scenes = list(authored["windows"])
    if len(scenes) >= 2:
        authored["exclusive_groups"] = [scenes[:2]]
        schedule = proposal["detail"]["window_proofs"]
        if schedule[0]["end_tick"] > schedule[1]["start_tick"]:
            with pytest.raises(StudioQuestError):
                compile_temporal_windows(docs, [], authored, authorized=True,
                                         expected_source_digest=source)


def test_authorization_leases_types_and_forged_replay():
    docs, source, proposal = fixture()
    with pytest.raises(PermissionError):
        propose_temporal_windows(docs, [], PROMPT, authorized=False,
                                 expected_source_digest=source)
    with pytest.raises(StudioQuestError):
        propose_temporal_windows(docs, [], "invent temporal evidence",
                                 authorized=True, expected_source_digest=source)
    with pytest.raises(StudioQuestError):
        compile_temporal_windows(docs, [], proposal["authoring"],
                                 authorized=True, expected_source_digest="0" * 64)
    for change in ({"critical_path_ticks": -1}, {"release_certified": True}):
        forged = {**proposal["detail"], **change}
        with pytest.raises(StudioQuestError):
            replay_temporal_windows(docs, forged, authorized=True)
    authored = json.loads(json.dumps(proposal["authoring"]))
    authored["windows"][next(iter(authored["windows"]))]["earliest"] = True
    with pytest.raises(StudioQuestError):
        compile_temporal_windows(docs, [], authored, authorized=True,
                                 expected_source_digest=source)


def test_private_atomic_publish_restore_and_symlink_fence(tmp_path):
    docs, source, proposal = fixture()
    report = proposal["detail"]
    receipt = publish_temporal_windows(docs, report, tmp_path, authorized=True)
    assert receipt["file_write_performed"] is True
    target = tmp_path / "temporal_windows.json"
    assert target.stat().st_mode & 0o077 == 0
    assert restore_temporal_windows(
        docs, tmp_path, authorized=True, expected_source_digest=source) == report
    with pytest.raises(FileExistsError):
        publish_temporal_windows(docs, report, tmp_path, authorized=True)
    target.write_text(json.dumps({**report, "critical_path_ticks": 999}))
    with pytest.raises(StudioQuestError):
        restore_temporal_windows(
            docs, tmp_path, authorized=True, expected_source_digest=source)
    target.write_text('{"schema":"one","schema":"two"}')
    with pytest.raises(StudioQuestError):
        restore_temporal_windows(
            docs, tmp_path, authorized=True, expected_source_digest=source)
    target.unlink()
    target.symlink_to(tmp_path / "missing")
    with pytest.raises(OSError):
        restore_temporal_windows(
            docs, tmp_path, authorized=True, expected_source_digest=source)


def test_playable_bundle_determinism_and_no_native_claims():
    docs, source, proposal = fixture()
    manifest, payload = compile_temporal_playable(
        docs, proposal["detail"], authorized=True)
    assert sha256(payload).hexdigest() == manifest["bundle_sha256"]
    assert manifest["canonical_html5_quest_included"] is True
    assert manifest["native_timeline_runtime_integrated"] is False
    assert (manifest, payload) == compile_temporal_playable(
        docs, proposal["detail"], authorized=True)
    with ZipFile(BytesIO(payload)) as archive:
        assert b"<html" in archive.read("index.html")
        assert b"Source-replayed scene windows" in archive.read("timeline.html")
        public = json.loads(archive.read("timeline.json"))
        assert public["native_time_verified"] is False
        for name, digest in manifest["files"].items():
            assert sha256(archive.read(name)).hexdigest() == digest


def test_jeeves_router_cli_and_negative_authoring(capsys):
    from scripts.studio_temporal_windows_cli import main
    docs, source, proposal = fixture()
    request = {"schema": REQUEST_SCHEMA, "project_id": PROJECT,
               "expected_source_digest": source, "actions": [], "prompt": PROMPT}
    direct = execute_temporal_windows_tool(request, authorized=True)
    routed = route_world_tool(
        {"tool": "studio_original_temporal_windows", "arguments": request},
        authorized=True)
    assert routed["result"] == direct
    assert any(x["name"] == "studio_original_temporal_windows"
               for x in world_tool_catalog()["tools"])
    assert main(["--project", PROJECT, "--expected-source", source,
                 "--prompt", PROMPT, "--handoff-manifest"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["proposal"] == direct["detail"]
    assert result["playable_handoff"]["canonical_html5_quest_included"] is True
    with pytest.raises(PermissionError):
        execute_temporal_windows_tool(request, authorized=False)
    with pytest.raises(StudioQuestError):
        execute_temporal_windows_tool({**request, "authorized": True},
                                      authorized=True)
