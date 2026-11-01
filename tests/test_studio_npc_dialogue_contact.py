"""NPC dialogue is only previewable at a replayed playable contact point."""
from __future__ import annotations

from copy import deepcopy
import json

import pytest

from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_npc_dialogue_contact import (
    FILENAME, compile_npc_dialogue_contact, replay_npc_dialogue_contact,
    publish_npc_dialogue_contact, restore_npc_dialogue_contact,
)

SOURCE = "a" * 64
WALK = "b" * 64
QUEST = "c" * 64


@pytest.fixture
def harness(monkeypatch):
    import skeleton.ai.game_builder.studio_npc_dialogue_contact as impl
    import skeleton.ai.agents.jeeves.studio_npc_dialogue_contact_tool as adapter
    contact = {
        "project_id": "original", "source_digest": SOURCE,
        "npc_id": "archivist", "authored_knowledge": "The gate is sealed.",
        "playable_contact_eligible": True,
    }
    card = {
        "npc_id": "archivist", "scene_id": "first", "status": "available",
        "authored_alternatives": ["listen", "leave"],
        "authored_cues": [{"kind": "npc_knowledge", "text": "The gate is sealed."}],
    }
    previews = [
        {"npc_id": "archivist", "scene_id": "first", "alternative": alt,
         "choice_committed": False}
        for alt in card["authored_alternatives"]
    ]
    card["card_digest"] = "d" * 64
    summary = {
        "npc_id": "archivist", "scene_id": "first", "status": "available",
        "card_digest": card["card_digest"],
        "available_alternatives": ["listen", "leave"],
    }
    preview = {
        "source_digest": SOURCE, "project_id": "original",
        "session_digest": QUEST, "choice_committed": False,
        "file_write_performed": False, "cards": [summary], "previews": previews,
    }
    staging = {
        "source_digest": SOURCE, "session_digest": QUEST, "cards": [card],
    }
    session = type("Session", (), {"digest": QUEST, "project_id": "original"})()
    walk = {
        "schema": "skeleton.game_builder.studio_walk_replay.v1",
        "project_id": "original", "source_digest": SOURCE,
        "events": [], "scene_index": 0, "position": [1, 1],
        "choices": [], "accepted_moves": 0, "session_digest": WALK,
        "external_evidence_verified": False,
        "native_genre_runtime_verified": False, "release_certified": False,
    }
    monkeypatch.setattr(impl, "_bounded_walk_receipt", lambda value: impl._canonical(value))
    monkeypatch.setattr(impl, "compile_npc_contact_handoff", lambda *a, **kw: deepcopy(contact))
    monkeypatch.setattr(impl, "replay_quest", lambda *a, **kw: session)
    monkeypatch.setattr(impl, "preview_dialogue_choices", lambda *a, **kw: deepcopy(preview))
    monkeypatch.setattr(impl, "compile_dialogue_staging", lambda *a, **kw: deepcopy(staging))
    monkeypatch.setattr(adapter, "read_blueprint", lambda _: {"original": True})
    return {"original": True}, walk, contact, preview, card, session


def make(harness, **changes):
    docs, walk, *_ = harness
    args = {
        "npc_id": "archivist", "scene_id": "first", "quest_actions": [],
        "authorized": True, "expected_source_digest": SOURCE,
        "expected_walk_digest": WALK, "expected_quest_digest": QUEST,
    }
    args.update(changes)
    return compile_npc_dialogue_contact(docs, walk, **args)


def test_contact_and_quest_replay_are_both_required(harness):
    result = make(harness)
    assert result["authored_alternative_count"] == 2
    assert result["playable_proximity_verified"]
    assert result["quest_unlock_replay_verified"]
    assert not result["dialogue_spoken_verified"]
    assert not result["quest_choice_committed"]
    assert not result["release_certified"]
    assert replay_npc_dialogue_contact(
        harness[0], result, authorized=True,
        expected_source_digest=SOURCE, expected_walk_digest=WALK,
        expected_quest_digest=QUEST,
    ) == result


def test_wrong_npc_locked_scene_and_knowledge_drift_fail(harness):
    harness[3]["cards"][0]["npc_id"] = "stranger"
    with pytest.raises(StudioQuestError, match="different NPC"):
        make(harness)
    harness[3]["cards"][0]["npc_id"] = "archivist"
    harness[3]["cards"][0]["status"] = "locked"
    with pytest.raises(StudioQuestError, match="locked"):
        make(harness)
    harness[3]["cards"][0]["status"] = "available"
    harness[2]["authored_knowledge"] = "forged"
    with pytest.raises(StudioQuestError, match="knowledge"):
        make(harness)


def test_missing_choices_forged_preview_and_stale_quest_fail(harness, monkeypatch):
    import skeleton.ai.game_builder.studio_npc_dialogue_contact as impl
    harness[3]["previews"].pop()
    with pytest.raises(StudioQuestError, match="alternatives"):
        make(harness)
    harness[3]["previews"].append({
        "npc_id": "archivist", "scene_id": "first",
        "alternative": "leave", "choice_committed": False,
    })
    with pytest.raises(StudioQuestError, match="stale"):
        make(harness, expected_quest_digest="d" * 64)
    result = make(harness)
    forged = deepcopy(result)
    forged["choice_previews"][0]["choice_committed"] = True
    with pytest.raises(StudioQuestError, match="canonical replay"):
        replay_npc_dialogue_contact(
            harness[0], forged, authorized=True,
            expected_source_digest=SOURCE, expected_walk_digest=WALK,
            expected_quest_digest=QUEST,
        )


def test_authority_type_budget_and_scene_validation(harness):
    with pytest.raises(PermissionError):
        make(harness, authorized=False)
    with pytest.raises(StudioQuestError, match="scene"):
        make(harness, scene_id="../\n")
    with pytest.raises(StudioQuestError, match="actions"):
        make(harness, quest_actions=[["x", "y"]] * 65)
    with pytest.raises(StudioQuestError, match="action"):
        make(harness, quest_actions=[["x", True]])


def test_private_publish_restore_and_forgery(harness, tmp_path):
    result = make(harness)
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    params = {
        "authorized": True, "expected_source_digest": SOURCE,
        "expected_walk_digest": WALK, "expected_quest_digest": QUEST,
    }
    publication = publish_npc_dialogue_contact(harness[0], result, private, **params)
    assert publication["file_write_performed"]
    assert restore_npc_dialogue_contact(harness[0], private, **params) == result
    with pytest.raises(FileExistsError):
        publish_npc_dialogue_contact(harness[0], result, private, **params)
    target = private / FILENAME
    target.write_text('{"schema":"a","schema":"b"}')
    target.chmod(0o600)
    with pytest.raises(StudioQuestError, match="duplicate"):
        restore_npc_dialogue_contact(harness[0], private, **params)
    target.unlink()
    target.symlink_to(private / "missing")
    with pytest.raises(OSError):
        restore_npc_dialogue_contact(harness[0], private, **params)


def test_typed_jeeves_router_and_cli_parity(harness, monkeypatch, capsys):
    import skeleton.ai.agents.jeeves.studio_npc_dialogue_contact_tool as adapter
    import scripts.studio_npc_dialogue_contact_cli as cli
    from skeleton.ai.agents.jeeves.studio_world_tool_router import route_world_tool
    monkeypatch.setattr(cli, "read_blueprint", lambda _: harness[0])
    request = {
        "schema": adapter.REQUEST_SCHEMA, "project_id": "original",
        "expected_source_digest": SOURCE, "expected_walk_digest": WALK,
        "expected_quest_digest": QUEST, "walk_receipt": harness[1],
        "npc_id": "archivist", "scene_id": "first", "quest_actions": [],
    }
    direct = adapter.execute_npc_dialogue_contact_tool(request, authorized=True)
    routed = route_world_tool(
        {"tool": "studio_original_npc_dialogue_contact", "arguments": request},
        authorized=True,
    )
    assert routed["result"] == direct
    assert routed["file_write_performed"] is False
    assert cli.main([
        "--project", "original", "--expected-source", SOURCE,
        "--expected-walk", WALK, "--expected-quest", QUEST,
        "--walk-json", json.dumps(harness[1]), "--npc-id", "archivist",
        "--scene-id", "first",
    ]) == 0
    assert json.loads(capsys.readouterr().out)["npc_dialogue"] == direct["detail"]
    with pytest.raises(PermissionError):
        adapter.execute_npc_dialogue_contact_tool(request, authorized=False)
    with pytest.raises(StudioQuestError, match="authority"):
        route_world_tool(
            {"tool": "studio_original_npc_dialogue_contact",
             "arguments": {**request, "authorized": True}},
            authorized=True,
        )
