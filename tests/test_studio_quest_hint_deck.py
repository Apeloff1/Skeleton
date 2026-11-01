"""Source-replayed quest accessibility hint deck end-to-end contracts."""
from __future__ import annotations

from hashlib import sha256
import json

import pytest

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_canon_proof import audit_canon_source
from skeleton.ai.game_builder.studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program, replay_quest, available_stages,
)
from skeleton.ai.game_builder.studio_quest_hint_deck import (
    PROMPT, compile_quest_hint_deck, propose_quest_hint_deck,
    replay_quest_hint_deck, render_quest_hint_html,
    compile_quest_hint_playable, publish_quest_hint_deck,
    restore_quest_hint_deck,
)
from skeleton.ai.game_builder.studio_quest_hint_editor import (
    EXPORT_SCHEMA, render_quest_hint_editor, publish_quest_hint_editor,
    load_quest_hint_editor_export,
)
from skeleton.ai.agents.jeeves.studio_quest_hint_tool import (
    REQUEST_SCHEMA, execute_quest_hint_tool,
)
from skeleton.ai.agents.jeeves.studio_world_tool_router import (
    route_world_tool, world_tool_catalog,
)

PROJECT = "studio_arena_fighting_glacial_fjord"


def fixture():
    docs = read_blueprint(PROJECT)
    source = audit_canon_source(docs, authorized=True)["source_digest"]
    program = compile_quest_program(docs)
    session = replay_quest(docs, [], authorized=True)
    available = list(available_stages(session, docs))
    assert available
    return docs, source, program, available[0]


def test_prompt_source_replay_and_spoiler_boundary():
    docs, source, program, first = fixture()
    report = propose_quest_hint_deck(
        docs, [], PROMPT, authorized=True, expected_source_digest=source)
    assert report == propose_quest_hint_deck(
        docs, [], PROMPT, authorized=True, expected_source_digest=source)
    assert report["hint_count"] == report["available_stage_count"]
    assert report["completed_stage_count"] == 0
    assert report["release_certified"] is False
    assert replay_quest_hint_deck(docs, report, authorized=True) == report
    assert all(card["stage_id"] == first or card["stage_id"] in
               available_stages(replay_quest(docs, [], authorized=True), docs)
               for card in report["hints"])


def test_authoring_and_locked_stage_fail_closed():
    docs, source, program, first = fixture()
    authored = {"hints": [{
        "stage_id": first, "text": "Explore the available scene.",
        "audience": "available",
    }]}
    report = compile_quest_hint_deck(
        docs, [], authored, authorized=True, expected_source_digest=source)
    assert report["hint_count"] == 1
    html = render_quest_hint_html(docs, report, authorized=True)
    assert b"Content-Security-Policy" in html
    assert b"Explore the available scene." in html
    locked = next((stage.key for stage in program.stages
                   if stage.key not in available_stages(
                       replay_quest(docs, [], authorized=True), docs)), None)
    if locked is not None:
        with pytest.raises(StudioQuestError):
            compile_quest_hint_deck(
                docs, [], {"hints": [{
                    "stage_id": locked, "text": "Spoiler.", "audience": "available",
                }]}, authorized=True, expected_source_digest=source)
    for bad in (
        {"hints": [{"stage_id": first, "text": "bad\n", "audience": "available"}]},
        {"hints": [{"stage_id": first, "text": "okay", "audience": "completed"}]},
        {"hints": [{"stage_id": first, "text": "okay", "audience": "available"}] * 2},
        {"hints": [{"stage_id": first, "text": "okay", "audience": "available",
                    "authorized": True}]},
        {"hints": [{"stage_id": first, "text": "okay", "audience": "available"}] * 65},
    ):
        with pytest.raises(StudioQuestError):
            compile_quest_hint_deck(
                docs, [], bad, authorized=True, expected_source_digest=source)


def test_completed_stage_and_session_replay():
    docs, source, program, first = fixture()
    stage = next(s for s in program.stages if s.key == first)
    actions = [[first, stage.alternatives[0]]]
    session = replay_quest(docs, actions, authorized=True)
    report = compile_quest_hint_deck(
        docs, actions, {"hints": [{
            "stage_id": first, "text": "You completed this stage.",
            "audience": "completed",
        }]}, authorized=True, expected_source_digest=source,
        expected_session_digest=session.digest)
    assert report["completed_stage_count"] == 1
    assert replay_quest_hint_deck(docs, report, authorized=True) == report
    with pytest.raises(StudioQuestError):
        compile_quest_hint_deck(
            docs, actions, report["authoring"], authorized=True,
            expected_source_digest=source, expected_session_digest="0" * 64)


def test_forged_receipt_and_authority():
    docs, source, program, first = fixture()
    report = propose_quest_hint_deck(
        docs, [], PROMPT, authorized=True, expected_source_digest=source)
    for forged in (
        {**report, "release_certified": True},
        {**report, "hint_count": 999},
        {**report, "hint_deck_digest": "0" * 64},
        {**report, "actions": [[first, "forged"]]},
    ):
        with pytest.raises(StudioQuestError):
            replay_quest_hint_deck(docs, forged, authorized=True)
    with pytest.raises(PermissionError):
        propose_quest_hint_deck(
            docs, [], PROMPT, authorized=False, expected_source_digest=source)


def test_private_immutable_publication_restore(tmp_path):
    docs, source, program, first = fixture()
    report = propose_quest_hint_deck(
        docs, [], PROMPT, authorized=True, expected_source_digest=source)
    assert publish_quest_hint_deck(
        docs, report, tmp_path, authorized=True)["file_write_performed"]
    path = tmp_path / "quest_hint_deck.json"
    assert path.stat().st_mode & 0o077 == 0
    assert restore_quest_hint_deck(
        docs, tmp_path, authorized=True, expected_source_digest=source) == report
    with pytest.raises(FileExistsError):
        publish_quest_hint_deck(docs, report, tmp_path, authorized=True)
    path.write_text('{"schema":"a","schema":"b"}')
    with pytest.raises(StudioQuestError):
        restore_quest_hint_deck(
            docs, tmp_path, authorized=True, expected_source_digest=source)
    path.unlink()
    path.symlink_to(tmp_path / "missing")
    with pytest.raises(OSError):
        restore_quest_hint_deck(
            docs, tmp_path, authorized=True, expected_source_digest=source)


def test_jeeves_router_and_cli(capsys):
    from scripts.studio_quest_hint_cli import main
    docs, source, program, first = fixture()
    request = {
        "schema": REQUEST_SCHEMA, "project_id": PROJECT,
        "expected_source_digest": source, "actions": [], "prompt": PROMPT,
    }
    direct = execute_quest_hint_tool(request, authorized=True)
    routed = route_world_tool(
        {"tool": "studio_original_quest_hints", "arguments": request},
        authorized=True)
    assert routed["result"] == direct
    assert any(row["name"] == "studio_original_quest_hints"
               for row in world_tool_catalog()["tools"])
    assert main(["--project", PROJECT, "--expected-source", source,
                 "--actions", "[]", "--prompt"]) == 0
    assert json.loads(capsys.readouterr().out)["hint_deck"] == direct["detail"]
    with pytest.raises(PermissionError):
        execute_quest_hint_tool(request, authorized=False)


def test_offline_editor_export_import(tmp_path, capsys):
    from scripts.studio_quest_hint_cli import main
    docs, source, program, first = fixture()
    report = propose_quest_hint_deck(
        docs, [], PROMPT, authorized=True, expected_source_digest=source)
    html, proof = render_quest_hint_editor(docs, report, authorized=True)
    assert sha256(html).hexdigest() == proof["html_sha256"]
    assert b"Content-Security-Policy" in html
    assert publish_quest_hint_editor(
        docs, report, tmp_path, authorized=True)["file_write_performed"]
    with pytest.raises(FileExistsError):
        publish_quest_hint_editor(docs, report, tmp_path, authorized=True)
    record = {
        "schema": EXPORT_SCHEMA, "project_id": PROJECT,
        "source_digest": source, "session_digest": report["session_digest"],
        "baseline_hint_deck_digest": report["hint_deck_digest"],
        "authoring": report["authoring"],
    }
    path = tmp_path / "quest_hint_edit.json"
    path.write_text(json.dumps(record))
    path.chmod(0o600)
    kwargs = {
        "authorized": True, "expected_project_id": PROJECT,
        "expected_source_digest": source,
        "expected_session_digest": report["session_digest"],
        "expected_baseline_digest": report["hint_deck_digest"],
    }
    assert load_quest_hint_editor_export(path, **kwargs) == report["authoring"]
    assert main([
        "--project", PROJECT, "--expected-source", source,
        "--actions", "[]", "--baseline-deck", json.dumps(report),
        "--import-authoring", str(path),
    ]) == 0
    assert json.loads(capsys.readouterr().out)["hint_deck"] == report
    path.write_text(json.dumps({**record, "session_digest": "0" * 64}))
    with pytest.raises(StudioQuestError):
        load_quest_hint_editor_export(path, **kwargs)
