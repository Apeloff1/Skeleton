"""NPC trust effects are authored, bounded and canonically replayed."""
from __future__ import annotations

import copy
import json
import os
import pytest

from skeleton.ai.game_builder.studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program, start_quest,
)
from skeleton.ai.game_builder.studio_quest_npc_relationships import (
    FILENAME, PROMPT, propose_quest_npc_relationships,
    compile_quest_npc_relationships, replay_quest_npc_relationships,
    compile_npc_relationship_handoff, publish_npc_relationships,
    restore_npc_relationships, render_npc_relationship_editor_html,
)
from tests.test_studio_quest_branch_review import source


def fixture():
    docs = source()
    program = compile_quest_program(docs)
    initial = start_quest(docs, authorized=True)
    plan = propose_quest_npc_relationships(
        docs, PROMPT, ["captain", "healer"],
        [["gate", "help"], ["harbor", "sail"]], "rescue",
        authorized=True, expected_source_digest=program.source_digest,
        expected_initial_session_digest=initial.digest)
    plan["actors"][0]["name"] = "Captain of the North"
    plan["actors"][0]["reviewed"] = True
    plan["actors"][1]["reviewed"] = True
    plan["effects"] = [
        {"stage_id": "gate", "choice": "help", "actor_id": "captain",
         "delta": 12, "reason": "The captain witnessed a rescue", "reviewed": True},
        {"stage_id": "gate", "choice": "ignore", "actor_id": "captain",
         "delta": -10, "reason": "The captain witnessed refusal", "reviewed": True},
        {"stage_id": "harbor", "choice": "sail", "actor_id": "healer",
         "delta": 5, "reason": "The healer joined the voyage", "reviewed": True},
    ]
    return docs, program, initial, plan


def compile_plan(docs, program, initial, plan):
    return compile_quest_npc_relationships(
        docs, plan, authorized=True,
        expected_source_digest=program.source_digest,
        expected_initial_session_digest=initial.digest)


def test_original_trust_only_follows_canonical_actions():
    docs, program, initial, plan = fixture()
    receipt = compile_plan(docs, program, initial, plan)
    assert receipt["final_trust"] == [
        {"actor_id": "captain", "trust": 12},
        {"actor_id": "healer", "trust": 5},
    ]
    assert len(receipt["applied"]) == 2
    assert receipt["all_authoring_reviewed"] is True
    assert receipt["playable_handoff_allowed"] is True
    handoff = compile_npc_relationship_handoff(docs, receipt, authorized=True)
    assert handoff["canonical_choices"] == [["gate", "help"], ["harbor", "sail"]]
    assert handoff["npc_behavior_observed"] is False
    assert handoff["release_certified"] is False


def test_unreviewed_and_ineligible_branches_cannot_handoff():
    docs, program, initial, plan = fixture()
    plan["effects"][0]["reviewed"] = False
    receipt = compile_plan(docs, program, initial, plan)
    assert receipt["playable_handoff_allowed"] is False
    with pytest.raises(StudioQuestError):
        compile_npc_relationship_handoff(docs, receipt, authorized=True)
    plan["effects"][0]["reviewed"] = True
    plan["actions"] = [["gate", "ignore"], ["harbor", "stay"]]
    receipt = compile_plan(docs, program, initial, plan)
    assert receipt["target_ending_eligible"] is False
    with pytest.raises(StudioQuestError):
        compile_npc_relationship_handoff(docs, receipt, authorized=True)


@pytest.mark.parametrize("field,value", [
    ("delta", 26), ("delta", 0), ("delta", True),
    ("actor_id", "phantom"), ("stage_id", "future"),
    ("choice", "invented"), ("reason", "bad\nreason"),
    ("reviewed", 1),
])
def test_invalid_authored_effect_rejected(field, value):
    docs, program, initial, plan = fixture()
    plan["effects"][0][field] = value
    with pytest.raises((StudioQuestError, ValueError)):
        compile_plan(docs, program, initial, plan)


def test_duplicate_effect_and_overflow_rejected():
    docs, program, initial, plan = fixture()
    plan["effects"].append(copy.deepcopy(plan["effects"][0]))
    with pytest.raises(StudioQuestError):
        compile_plan(docs, program, initial, plan)
    plan["effects"].pop()
    plan["actors"][0]["initial_trust"] = 50
    plan["effects"][0]["delta"] = 25
    plan["effects"].append({
        "stage_id": "harbor", "choice": "sail", "actor_id": "captain",
        "delta": 25, "reason": "Additional earned trust", "reviewed": True,
    })
    receipt = compile_plan(docs, program, initial, plan)
    assert receipt["final_trust"][0]["trust"] == 100
    plan["effects"][0]["delta"] = 26
    with pytest.raises(StudioQuestError):
        compile_plan(docs, program, initial, plan)


def test_tamper_source_drift_and_authorization():
    docs, program, initial, plan = fixture()
    receipt = compile_plan(docs, program, initial, plan)
    forged = copy.deepcopy(receipt)
    forged["final_trust"][0]["trust"] = 100
    with pytest.raises(StudioQuestError):
        replay_quest_npc_relationships(docs, forged, authorized=True)
    changed = copy.deepcopy(docs)
    changed["quest"]["stage_graph"][0]["reward"] = "new"
    with pytest.raises(StudioQuestError):
        replay_quest_npc_relationships(changed, receipt, authorized=True)
    with pytest.raises(PermissionError):
        compile_plan(docs, program, initial, plan) if False else replay_quest_npc_relationships(
            docs, receipt, authorized=False)


def test_private_publish_restore_and_symlink(tmp_path):
    docs, program, initial, plan = fixture()
    receipt = compile_plan(docs, program, initial, plan)
    result = publish_npc_relationships(docs, receipt, tmp_path, authorized=True)
    assert result["file_write_performed"] is True
    assert restore_npc_relationships(
        docs, tmp_path, authorized=True,
        expected_source_digest=program.source_digest) == receipt
    with pytest.raises(FileExistsError):
        publish_npc_relationships(docs, receipt, tmp_path, authorized=True)
    (tmp_path / FILENAME).unlink()
    (tmp_path / FILENAME).symlink_to(tmp_path / "missing")
    with pytest.raises((StudioQuestError, OSError)):
        restore_npc_relationships(
            docs, tmp_path, authorized=True,
            expected_source_digest=program.source_digest)


def test_html_escapes_and_cli_compiles_handoff(tmp_path, monkeypatch, capsys):
    from scripts import studio_quest_npc_relationships_cli as cli
    docs, program, initial, plan = fixture()
    plan["actors"][0]["name"] = "</script><img src=x>"
    receipt = compile_plan(docs, program, initial, plan)
    html = render_npc_relationship_editor_html(
        docs, receipt, authorized=True)
    assert b"connect-src 'none'" in html
    assert b"\\u003c/script>" in html
    assert b"</script><img" not in html
    monkeypatch.setattr(cli, "read_blueprint", lambda _: docs)
    path = tmp_path / "npc-plan.json"
    path.write_text(json.dumps(plan))
    os.chmod(path, 0o600)
    assert cli.main(["--project", "branch_demo", "--plan", str(path),
                     "--handoff"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["playable_handoff"]["final_trust"][0]["trust"] == 12
