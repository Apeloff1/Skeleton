"""Multi-scene NPC quest transitions require fresh contact proof at each step."""
from __future__ import annotations

from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_npc_dialogue_chain import (
    FILENAME, compile_npc_dialogue_chain, replay_npc_dialogue_chain,
    publish_npc_dialogue_chain, restore_npc_dialogue_chain,
    render_npc_dialogue_chain_html,
)

SOURCE = "a" * 64
WALK = "b" * 64
QUEST = "c" * 64
Q1 = "d" * 64
Q2 = "e" * 64
WALK_RECEIPT = {"walk": "authored"}


def steps():
    return [
        {"npc_id": "archivist", "scene_id": "library", "alternative": "listen"},
        {"npc_id": "guardian", "scene_id": "gate", "alternative": "enter"},
    ]


@pytest.fixture
def harness(monkeypatch):
    import skeleton.ai.game_builder.studio_npc_dialogue_chain as impl
    import skeleton.ai.agents.jeeves.studio_npc_dialogue_chain_tool as adapter
    import scripts.studio_npc_dialogue_chain_cli as cli
    docs = {"original": True}
    calls = []

    def quest(source, actions, *, authorized):
        if source != docs or authorized is not True:
            raise StudioQuestError("invalid chain source or authority")
        if actions == []:
            digest = QUEST
        elif actions == [["stage-0", "listen"]]:
            digest = Q1
        elif actions == [["stage-0", "listen"], ["stage-1", "enter"]]:
            digest = Q2
        else:
            raise StudioQuestError("unknown canonical chain quest history")
        return SimpleNamespace(
            project_id="original", source_digest=SOURCE,
            digest=digest, choices=[tuple(a) for a in actions],
        )

    def contact(source, walk, *, npc_id, scene_id, quest_actions,
                authorized, expected_source_digest, expected_walk_digest,
                expected_quest_digest):
        if (source != docs or walk != WALK_RECEIPT or authorized is not True
                or expected_source_digest != SOURCE or expected_walk_digest != WALK):
            raise StudioQuestError("invalid playable contact")
        if quest( source, quest_actions, authorized=True).digest != expected_quest_digest:
            raise StudioQuestError("stale NPC quest contact")
        index = len(quest_actions)
        calls.append((index, expected_quest_digest, npc_id, scene_id))
        return {
            "receipt_digest": ("1" if index == 0 else "2") * 64,
            "quest_actions": deepcopy(quest_actions),
            "dialogue_card": {"quest_stage": "stage-" + str(index)},
            "npc_id": npc_id, "scene_id": scene_id,
        }

    def choice(source, contact_receipt, *, alternative, authorized,
               expected_contact_digest, expected_source_digest,
               expected_walk_digest, expected_quest_digest):
        actions = contact_receipt["quest_actions"]
        if (source != docs or authorized is not True
                or expected_source_digest != SOURCE or expected_walk_digest != WALK
                or contact_receipt["receipt_digest"] != expected_contact_digest
                or quest(source, actions, authorized=True).digest != expected_quest_digest):
            raise StudioQuestError("invalid chained choice proof")
        after = actions + [[contact_receipt["dialogue_card"]["quest_stage"], alternative]]
        final = quest(source, after, authorized=True)
        return {
            "previous_quest_session_digest": expected_quest_digest,
            "next_quest_session_digest": final.digest,
            "quest_actions": after, "source_digest": SOURCE,
            "walk_session_digest": WALK,
            "playable_proximity_verified": True,
            "quest_choice_replayed": True,
            "dialogue_spoken_verified": False,
            "native_runtime_verified": False, "release_certified": False,
            "receipt_digest": ("3" if len(after) == 1 else "4") * 64,
        }

    monkeypatch.setattr(impl, "replay_quest", quest)
    monkeypatch.setattr(impl, "compile_npc_dialogue_contact", contact)
    monkeypatch.setattr(impl, "compile_npc_dialogue_choice_commit", choice)
    monkeypatch.setattr(adapter, "read_blueprint", lambda _: docs)
    monkeypatch.setattr(cli, "read_blueprint", lambda _: docs)
    return docs, calls


def params():
    return {
        "authorized": True, "expected_source_digest": SOURCE,
        "expected_walk_digest": WALK, "expected_quest_digest": QUEST,
    }


def make(harness, **changes):
    arguments = {
        "initial_quest_actions": [], "steps": steps(), **params(),
    }
    arguments.update(changes)
    return compile_npc_dialogue_chain(harness[0], WALK_RECEIPT, **arguments)


def test_chain_rechecks_contact_against_advanced_quest_at_every_step(harness):
    receipt = make(harness)
    assert receipt["step_count"] == 2
    assert receipt["final_quest_actions"] == [
        ["stage-0", "listen"], ["stage-1", "enter"]]
    assert receipt["initial_quest_session_digest"] == QUEST
    assert receipt["final_quest_session_digest"] == Q2
    assert harness[1] == [
        (0, QUEST, "archivist", "library"),
        (1, Q1, "guardian", "gate"),
    ]
    assert receipt["playable_contact_verified_per_step"]
    assert receipt["sequential_quest_replay_verified"]
    assert not receipt["dialogue_spoken_verified"]
    assert not receipt["native_runtime_verified"]
    assert not receipt["release_certified"]
    assert replay_npc_dialogue_chain(
        harness[0], receipt, **params()) == receipt


def test_unknown_alternative_locked_step_stale_lease_and_authority_fail(harness):
    with pytest.raises(PermissionError):
        make(harness, authorized=False)
    with pytest.raises(StudioQuestError, match="stale"):
        make(harness, expected_quest_digest="0" * 64)
    with pytest.raises(StudioQuestError, match="unknown"):
        make(harness, steps=[
            steps()[0], {**steps()[1], "alternative": "invented"}])
    with pytest.raises(StudioQuestError, match="requires 1..8"):
        make(harness, steps=[])
    with pytest.raises(StudioQuestError, match="requires 1..8"):
        make(harness, steps=steps() * 5)
    with pytest.raises(StudioQuestError, match="invalid typed"):
        make(harness, steps=[{**steps()[0], "unexpected": True}])
    with pytest.raises(StudioQuestError, match="chain npc_id"):
        make(harness, steps=[{**steps()[0], "npc_id": "bad\n"}])


def test_canonical_replay_rejects_forged_final_quest_and_contact_order(harness):
    receipt = make(harness)
    forged = deepcopy(receipt)
    forged["final_quest_session_digest"] = "0" * 64
    with pytest.raises(StudioQuestError, match="canonical replay"):
        replay_npc_dialogue_chain(harness[0], forged, **params())
    forged = deepcopy(receipt)
    forged["steps"].reverse()
    with pytest.raises(StudioQuestError, match="unknown"):
        replay_npc_dialogue_chain(harness[0], forged, **params())
    forged = deepcopy(receipt)
    forged["step_receipts"][0]["next_quest_digest"] = "0" * 64
    with pytest.raises(StudioQuestError, match="canonical replay"):
        replay_npc_dialogue_chain(harness[0], forged, **params())


def test_private_publication_restore_duplicate_json_and_symlink(harness, tmp_path):
    receipt = make(harness)
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    publication = publish_npc_dialogue_chain(
        harness[0], receipt, private, **params())
    assert publication["file_write_performed"]
    assert restore_npc_dialogue_chain(harness[0], private, **params()) == receipt
    with pytest.raises(FileExistsError):
        publish_npc_dialogue_chain(harness[0], receipt, private, **params())
    target = private / FILENAME
    target.write_text('{"schema":"a","schema":"b"}')
    target.chmod(0o600)
    with pytest.raises(StudioQuestError, match="duplicate"):
        restore_npc_dialogue_chain(harness[0], private, **params())
    target.unlink()
    target.symlink_to(private / "missing")
    with pytest.raises(OSError):
        restore_npc_dialogue_chain(harness[0], private, **params())


def test_offline_html_escapes_untrusted_npc_and_jeeves_is_authoring_gated(
    harness, capsys,
):
    from skeleton.ai.agents.jeeves.studio_world_tool_router import route_world_tool
    from skeleton.ai.agents.jeeves.studio_npc_dialogue_chain_tool import (
        REQUEST_SCHEMA, execute_npc_dialogue_chain_tool,
    )
    from scripts.studio_npc_dialogue_chain_cli import main

    receipt = make(harness)
    html = render_npc_dialogue_chain_html(
        harness[0], receipt, **params()).decode("utf-8")
    assert "default-src 'none'" in html
    assert "No spoken dialogue" in html
    request = {
        "schema": REQUEST_SCHEMA, "project_id": "original",
        "walk_receipt": WALK_RECEIPT, "initial_quest_actions": [],
        "steps": steps(), "expected_source_digest": SOURCE,
        "expected_walk_digest": WALK, "expected_quest_digest": QUEST,
    }
    direct = execute_npc_dialogue_chain_tool(request, authorized=True)
    with pytest.raises(PermissionError):
        route_world_tool(
            {"tool": "studio_original_npc_dialogue_chain",
             "arguments": request}, authorized=True)
    routed = route_world_tool(
        {"tool": "studio_original_npc_dialogue_chain",
         "arguments": request}, authorized=True, allow_authoring=True)
    assert routed["result"] == direct
    assert not routed["file_write_performed"]
    assert main([
        "--project", "original", "--expected-source", SOURCE,
        "--expected-walk", WALK, "--expected-quest", QUEST,
        "--walk-json", json.dumps(WALK_RECEIPT),
        "--steps-json", json.dumps(steps()),
    ]) == 0
    assert json.loads(capsys.readouterr().out)["chain"] == direct["detail"]
    with pytest.raises(PermissionError):
        execute_npc_dialogue_chain_tool(request, authorized=False)
    with pytest.raises(StudioQuestError, match="authority"):
        route_world_tool(
            {"tool": "studio_original_npc_dialogue_chain",
             "arguments": {**request, "authorized": True}},
            authorized=True, allow_authoring=True)
