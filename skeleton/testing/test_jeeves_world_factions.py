"""Faction authorship, legal replay, CAS custody and playable proof."""
from __future__ import annotations

import copy
import json
import os

import pytest

from skeleton.jeeves.worlds.factions import (
    FactionStore, approve_factions, compile_factions, edit_factions,
    propose_factions, replay_reputation, validate_factions,
)
from skeleton.jeeves.worlds.factions_cli import run
from skeleton.jeeves.worlds.session import SessionStore
from skeleton.jeeves.worlds.world_canon import (
    CanonError, WorldStore, canonical, digest, propose, prove,
)


def world():
    data = propose(
        world_id="ferry", premise="A courier must earn the ferryman's trust.",
        protagonist="Iris", region="River", goal="Reach the far shore.",
    )
    data["scenes"].insert(1, {
        "id": "dock", "title": "Dock", "narrative": "The ferryman waits.",
    })
    data["choices"] = [
        {"id": "pay", "from": "opening", "to": "dock",
         "label": "Pay the ferryman", "requires": [], "grants": ["fare"]},
        {"id": "cross", "from": "dock", "to": "resolution",
         "label": "Cross", "requires": ["fare"], "grants": []},
    ]
    prove(data)
    return data


def factions():
    return propose_factions(
        world(), prompt="Trust must be earned through a legal choice.",
        faction_id="ferrymen", name="Ferrymen", description="River pilots.",
        choice_id="pay", delta=12, reason="Paid the fare.",
    )


def test_prompt_to_typed_proposal_needs_review():
    data = factions()
    assert data["approved"] is False
    assert data["world_digest"] == digest(world())
    with pytest.raises(CanonError, match="faction_review_required"):
        compile_factions(data, world())
    approved = approve_factions(data, world(), "Reviewed original faction rules.")
    handoff = compile_factions(approved, world())
    assert handoff["ending_outcomes"]["resolution"]["reputation"] == {"ferrymen": 12}
    assert handoff["ending_outcomes"]["resolution"]["choice_witness"] == ["pay", "cross"]


def test_player_reputation_only_earned_by_canonical_replay():
    data = factions()
    assert replay_reputation(data, world(), [])["reputation"]["ferrymen"] == 0
    result = replay_reputation(data, world(), ["pay", "cross"])
    assert result["reputation"]["ferrymen"] == 12
    assert result["events"][0]["step"] == 1
    assert result["events"][0]["rule_id"] == "first_effect"
    with pytest.raises(CanonError, match="session_invalid_transition"):
        replay_reputation(data, world(), ["cross"])
    with pytest.raises(CanonError, match="session_after_ending"):
        replay_reputation(data, world(), ["pay", "cross", "pay"])


@pytest.mark.parametrize("bad", [True, 1.5, 0, 21, -21, "10", None])
def test_invalid_delta_rejected(bad):
    data = factions()
    data["rules"][0]["delta"] = bad
    with pytest.raises(CanonError, match="invalid_reputation_delta"):
        validate_factions(data, world())


def test_forged_choice_and_world_revision_rejected():
    data = factions()
    data["rules"][0]["choice_id"] = "not_a_real_choice"
    with pytest.raises(CanonError, match="unknown_faction_choice"):
        validate_factions(data, world())
    data = factions()
    changed = world()
    changed["scenes"][0]["title"] = "Changed source"
    with pytest.raises(CanonError, match="faction_world_lease_mismatch"):
        validate_factions(data, changed)


def test_atomic_edits_revoke_approval_and_preserve_source():
    data = approve_factions(factions(), world(), "Approved.")
    original = canonical(data)
    edited = edit_factions(data, world(), {"action": "batch", "value": [
        {"action": "add_faction", "value": {
            "id": "villagers", "name": "Villagers",
            "description": "Village council.",
        }},
        {"action": "add_rule", "value": {
            "id": "village_payment", "choice_id": "cross",
            "faction_id": "villagers", "delta": 3, "reason": "Reached shore.",
        }},
    ]})
    assert edited["approved"] is False
    assert len(edited["rules"]) == 2
    assert canonical(data) == original
    with pytest.raises(CanonError, match="unsupported_faction_edit"):
        edit_factions(data, world(), {"action": "execute_python", "value": {}})
    with pytest.raises(CanonError, match="unknown_faction"):
        edit_factions(data, world(), {"action": "remove_faction",
                                      "value": {"id": "ferrymen"}})


def test_sorted_ids_duplicate_rules_and_unknown_target_rejected():
    data = factions()
    data["rules"].append(copy.deepcopy(data["rules"][0]))
    with pytest.raises(CanonError, match="noncanonical_faction_rules"):
        validate_factions(data, world())
    with pytest.raises(CanonError, match="unknown_faction_edit_target"):
        edit_factions(factions(), world(), {"action": "replace_rule", "value": {
            "id": "missing", "choice_id": "pay", "faction_id": "ferrymen",
            "delta": 1, "reason": "No such rule.",
        }})


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor-anchored custody")
def test_persist_review_compile_verify_and_player(tmp_path):
    root = tmp_path / "private"
    WorldStore(root).publish(world(), create=True)
    store = FactionStore(root)
    first = store.publish("ferry", factions(), create=True)
    with pytest.raises(CanonError, match="faction_review_required"):
        store.compile("ferry", first)
    second = store.approve("ferry", expected_digest=first, note="Reviewed.")
    receipt = store.compile("ferry", second)
    assert receipt == store.verify("ferry")
    assert (root / "ferry.factions.playable.html").exists()
    session = SessionStore(root)
    session.create("ferry", "one")
    before = store.player("ferry", "one")
    assert before["reputation"]["ferrymen"] == 0
    view = session.read("ferry", "one")
    session.choose("ferry", "one", "pay", digest(view))
    after = store.player("ferry", "one")
    assert after["reputation"]["ferrymen"] == 12


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor-anchored custody")
def test_stale_cas_and_forged_artifacts_fail_closed(tmp_path):
    root = tmp_path / "private"
    WorldStore(root).publish(world(), create=True)
    store = FactionStore(root)
    first = store.publish("ferry", factions(), create=True)
    with pytest.raises(CanonError, match="stale_factions"):
        store.publish("ferry", factions(), expected_digest="0" * 64)
    second = store.approve("ferry", expected_digest=first, note="Reviewed.")
    store.compile("ferry", second)
    (root / "ferry.factions.handoff.json").write_text("{}")
    with pytest.raises(CanonError, match="faction_artifact_mismatch"):
        store.verify("ferry")


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor-anchored custody")
def test_symlink_artifact_and_world_revisions_fail_closed(tmp_path):
    root = tmp_path / "private"
    WorldStore(root).publish(world(), create=True)
    store = FactionStore(root)
    first = store.publish("ferry", factions(), create=True)
    source_digest = store.approve("ferry", expected_digest=first, note="Reviewed.")
    store.compile("ferry", source_digest)
    path = root / "ferry.factions.receipt.json"
    path.unlink()
    path.symlink_to(root / "ferry.json")
    with pytest.raises(OSError):
        store.verify("ferry")
    path.unlink()
    (root / "ferry.json").write_text(json.dumps({**world(), "prompt": "Changed."}))
    with pytest.raises(CanonError, match="faction_world_lease_mismatch"):
        store.read("ferry")


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor-anchored custody")
def test_cli_propose_approve_compile_verify(tmp_path, capsys):
    root = tmp_path / "private"
    WorldStore(root).publish(world(), create=True)
    args = ["--store", str(root)]
    assert run(args + [
        "propose", "--world-id", "ferry", "--prompt", "Earn trust.",
        "--faction-id", "ferrymen", "--name", "Ferrymen",
        "--description", "River pilots.", "--choice-id", "pay",
        "--delta", "12", "--reason", "Paid the fare.",
    ]) == 0
    first = json.loads(capsys.readouterr().out)["factions_digest"]
    assert run(args + ["compile", "--world-id", "ferry",
                       "--expected-digest", first]) == 2
    assert json.loads(capsys.readouterr().out)["error"] == "faction_review_required"
    assert run(args + ["approve", "--world-id", "ferry",
                       "--expected-digest", first, "--note", "Reviewed."]) == 0
    second = json.loads(capsys.readouterr().out)["factions_digest"]
    assert run(args + ["compile", "--world-id", "ferry",
                       "--expected-digest", second]) == 0
    capsys.readouterr()
    assert run(args + ["verify", "--world-id", "ferry"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"]
