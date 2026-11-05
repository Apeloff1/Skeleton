"""Quest prerequisites, authored review, actual player progress and custody."""
from __future__ import annotations

import copy
import json
import os

import pytest

from skeleton.jeeves.worlds.quest import (
    QuestStore, approve_quest, compile_quest, edit_quest, evaluate_quest,
    propose_quest, solve_quest, validate_quest,
)
from skeleton.jeeves.worlds.quest_cli import run
from skeleton.jeeves.worlds.session import SessionStore
from skeleton.jeeves.worlds.world_canon import (
    CanonError, WorldStore, canonical, digest, propose, prove,
)


def world():
    source = propose(
        world_id="marsh", premise="A courier crosses the marsh.",
        protagonist="Iris", region="Marsh", goal="Deliver the letter.",
    )
    source["scenes"].insert(1, {
        "id": "ferry", "title": "Ferry", "narrative": "A boat waits.",
    })
    source["choices"] = [
        {"id": "board", "from": "opening", "to": "ferry",
         "label": "Board", "requires": [], "grants": ["ticket"]},
        {"id": "deliver", "from": "ferry", "to": "resolution",
         "label": "Deliver", "requires": ["ticket"], "grants": []},
    ]
    prove(source)
    return source


def quest():
    return propose_quest(world(), ending="resolution",
                         title="Deliver the letter",
                         description="Keep the letter sealed.")


def test_prompt_to_quest_witness_and_actual_session_progress():
    source = world()
    data = quest()
    assert solve_quest(data, source) == ("board", "deliver")
    assert evaluate_quest(data, source, [])["remaining_required"] == ["primary"]
    assert evaluate_quest(data, source, ["board"])["quest_won"] is False
    progress = evaluate_quest(data, source, ["board", "deliver"])
    assert progress["quest_won"] is True
    assert progress["completed"] == ["primary"]
    with pytest.raises(CanonError, match="quest_review_required"):
        compile_quest(data, source)
    reviewed = approve_quest(data, source, "Original author reviewed.")
    assert compile_quest(reviewed, source)["choice_witness"] == ["board", "deliver"]


def test_dependency_order_is_earned_from_actual_world_trace():
    source = world()
    data = quest()
    data["objectives"].insert(0, {
        "id": "ticket", "title": "Earn ferry ticket",
        "description": "Board the ferry.", "scene": "ferry",
        "requires_flags": ["ticket"], "depends_on": [], "required": True,
    })
    data["objectives"][1]["depends_on"] = ["ticket"]
    assert validate_quest(data, source) is data
    progress = evaluate_quest(data, source, ["board", "deliver"])
    assert progress["completed"] == ["primary", "ticket"]
    assert progress["earned_at"][0]["objective"] == "ticket"


def test_dependency_cycle_and_unknown_id_rejected():
    source = world()
    data = quest()
    data["objectives"][0]["depends_on"] = ["primary"]
    with pytest.raises(CanonError, match="invalid_objective_dependency"):
        validate_quest(data, source)
    data["objectives"][0]["depends_on"] = ["missing"]
    with pytest.raises(CanonError, match="invalid_objective_dependency"):
        validate_quest(data, source)


def test_unearned_flags_cannot_complete_quest():
    source = world()
    data = quest()
    data["objectives"][0]["requires_flags"] = ["ticket"]
    assert evaluate_quest(data, source, [])["completed"] == []
    assert evaluate_quest(data, source, ["board", "deliver"])["quest_won"]


def test_unsupported_edits_do_not_mutate_original():
    source = world()
    data = quest()
    before = canonical(data)
    with pytest.raises(CanonError, match="unsupported_quest_edit"):
        edit_quest(data, source, {"action": "run_code", "value": {}})
    assert canonical(data) == before


def test_batch_edits_are_atomic_and_revoke_approval():
    source = world()
    data = approve_quest(quest(), source, "Reviewed")
    updated = edit_quest(data, source, {"action": "batch", "value": [
        {"action": "add", "value": {
            "id": "ticket", "title": "Board ferry", "description": "Earn ticket",
            "scene": "ferry", "requires_flags": ["ticket"],
            "depends_on": [], "required": True,
        }},
        {"action": "replace", "value": {
            "id": "primary", "title": "Deliver", "description": "Keep sealed",
            "scene": "resolution", "requires_flags": [],
            "depends_on": ["ticket"], "required": True,
        }},
    ]})
    assert updated["approved"] is False
    assert data["approved"] is True
    assert solve_quest(updated, source) == ("board", "deliver")


def test_source_lease_mismatch_fails_closed():
    source = world()
    data = quest()
    source["scenes"][0]["title"] = "Changed"
    with pytest.raises(CanonError, match="quest_world_lease_mismatch"):
        validate_quest(data, source)


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored POSIX custody")
def test_quest_publish_review_compile_verify(tmp_path):
    root = tmp_path / "private"
    WorldStore(root).publish(world(), create=True)
    store = QuestStore(root)
    first = store.publish("marsh", quest(), create=True)
    with pytest.raises(CanonError, match="quest_review_required"):
        store.compile("marsh", first)
    reviewed = approve_quest(quest(), world(), "Reviewed")
    second = store.publish("marsh", reviewed, expected_digest=first)
    receipt = store.compile("marsh", second)
    assert store.verify("marsh") == receipt
    assert (root / "marsh.quest.playable.html").exists()


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored POSIX custody")
def test_quest_tamper_and_stale_cas(tmp_path):
    root = tmp_path / "private"
    WorldStore(root).publish(world(), create=True)
    store = QuestStore(root)
    reviewed = approve_quest(quest(), world(), "Reviewed")
    first = store.publish("marsh", reviewed, create=True)
    with pytest.raises(CanonError, match="stale_quest"):
        store.publish("marsh", reviewed, expected_digest="0" * 64)
    store.compile("marsh", first)
    (root / "marsh.quest.handoff.json").write_text("tampered")
    with pytest.raises(CanonError, match="quest_artifact_mismatch"):
        store.verify("marsh")


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored POSIX custody")
def test_quest_cli_progress_uses_real_player_session(tmp_path, capsys):
    root = tmp_path / "private"
    WorldStore(root).publish(world(), create=True)
    args = ["--store", str(root)]
    assert run(args + ["propose", "--world-id", "marsh",
                       "--ending", "resolution", "--title", "Deliver",
                       "--description", "Deliver original letter."]) == 0
    first = json.loads(capsys.readouterr().out)
    assert run(args + ["approve", "--world-id", "marsh",
                       "--expected-digest", first["quest_digest"],
                       "--note", "Reviewed"]) == 0
    approved = json.loads(capsys.readouterr().out)
    assert run(args + ["compile", "--world-id", "marsh",
                       "--expected-digest", approved["quest_digest"]]) == 0
    capsys.readouterr()
    session = SessionStore(root)
    first_player = session.create("marsh", "slot1")
    second_player = session.choose(
        "marsh", "slot1", "board", first_player["session_digest"])
    session.choose("marsh", "slot1", "deliver", second_player["session_digest"])
    assert run(args + ["progress", "--world-id", "marsh", "--slot", "slot1"]) == 0
    assert json.loads(capsys.readouterr().out)["progress"]["quest_won"] is True

def test_malformed_ending_type_is_typed_failure():
    source = world()
    data = quest()
    data["ending"] = ["resolution"]
    with pytest.raises(CanonError, match="unknown_quest_ending"):
        validate_quest(data, source)
