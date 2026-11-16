"""Narrative integration uses actual archived dialogue and quest owners."""
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from skeleton.app.gameforge_campaign import (
    REQUEST_SCHEMA, append_actions, build_campaign, play_campaign,
    verify_campaign, verify_session,
)
from skeleton.app.gameforge_campaign_cli import main
from skeleton.app.gameforge_campaign_store import CampaignStore, CampaignStoreError, RevisionConflict
from skeleton.app.gameforge_quest_bridge import REQUEST_SCHEMA as QUEST_SCHEMA
from skeleton.game.gameplay.dialogue_graph import replay


def spec():
    authored = json.loads((Path(__file__).parent / "fixtures" /
                           "dialogue_original_lantern_harbor.json").read_text(encoding="utf-8"))
    return {
        "schema": REQUEST_SCHEMA,
        "quest_request": {
            "schema": QUEST_SCHEMA,
            "vision": {"title": "Lantern Harbor", "pitch": "Restore the beacon",
                       "genre": "adventure", "pillars": ["exploration", "story"]},
            "config": {"regions": 6, "budget_bytes": 200000},
            "quest": {
                "packs": [{"id": "movement", "provides": ["movement"]},
                          {"id": "quest", "provides": ["quests"], "requires": ["movement"]}],
                "pack_ids": ["quest", "movement"],
                "policy": {"allowed_reward_kinds": ["gold"],
                           "max_reward_per_step": 2, "max_total_reward": 12},
                "seed": 31, "quest_length": 4, "npcs": {"keeper": "r00"},
            },
        },
        "dialogues": [{"npc": "keeper", "source": authored,
                       "gates": {"s0": "restore-western-lens"},
                       "witness": ["listen", "promise-repair"]}],
    }


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("ascii")


def rehash(value, field):
    value[field] = hashlib.sha256(encoded({k: v for k, v in value.items() if k != field})).hexdigest()


def invoke(command, data, database=None):
    args = [command] + (["--database", str(database)] if database is not None else [])
    output, error = io.StringIO(), io.StringIO()
    code = main(args, stdin=io.BytesIO(encoded(data)), stdout=output, stderr=error)
    return code, json.loads(output.getvalue()) if output.getvalue() else None, error.getvalue()


def test_archived_dialogue_runtime_controls_generated_quest():
    source = spec()
    design = build_campaign(source)
    witness = design["witness"]
    assert witness[:2] == [
        {"type": "dialogue", "npc": "keeper", "choice": "listen"},
        {"type": "dialogue", "npc": "keeper", "choice": "promise-repair"},
    ]
    assert design["witness_state"]["status"] == "completed"
    assert design["witness_state"]["dialogues"]["keeper"] == replay(
        source["dialogues"][0]["source"], ["listen", "promise-repair"]
    )
    assert len(design["witness_state"]["earned_rewards"]) == 4
    assert design == build_campaign(deepcopy(source))
    assert verify_campaign(source, design)
    assert not design["native_qualified"] and not design["release_qualified"]
    empty = play_campaign(source, [])
    assert not empty["state"]["earned_rewards"]
    assert empty["state"]["status"] == "in_progress"
    assert empty["state"]["dialogues"]["keeper"]["state"]["phase"] == "active"
    assert verify_session(source, empty)
    first = play_campaign(source, witness[:1])
    assert first["state"]["dialogues"]["keeper"]["state"]["reputation"] == 2
    assert not first["state"]["earned_rewards"]
    complete = append_actions(source, first, witness[1:])
    assert complete == play_campaign(source, witness)
    assert complete["state"] == design["witness_state"]


def test_departure_is_a_real_alternative_and_cannot_fabricate_grant():
    source = spec()
    actions = build_campaign(source)["witness"]
    depart = {"type": "dialogue", "npc": "keeper", "choice": "depart"}
    previous = play_campaign(source, [depart])
    assert previous["state"]["dialogues"]["keeper"]["state"]["reputation"] == -2
    assert not previous["state"]["dialogues"]["keeper"]["state"]["quests"]
    assert not previous["state"]["earned_rewards"]
    with pytest.raises(ValueError, match="grant"):
        append_actions(source, previous, actions[2:])
    with pytest.raises(ValueError, match="terminal"):
        append_actions(source, previous, actions[:1])
    assert verify_session(source, previous)


def test_no_conversation_teleportation_and_gate_cannot_be_skipped():
    source = spec()
    design = build_campaign(source)
    with pytest.raises(ValueError, match="grant"):
        play_campaign(source, design["witness"][2:])
    neighbor = design["world"]["edges"]["r00"][0]
    with pytest.raises(ValueError, match="location"):
        play_campaign(source, [{"type": "move", "to": neighbor}, design["witness"][0]])
    with pytest.raises(ValueError):
        play_campaign(source, [{"type": "dialogue", "npc": "keeper", "choice": "promise-repair"}])


def test_every_witness_event_is_legal_when_offered():
    source = spec()
    actions = build_campaign(source)["witness"]
    for index, event in enumerate(actions):
        before = play_campaign(source, actions[:index])
        assert event in before["state"]["legal_actions"]
    assert play_campaign(source, actions)["state"]["legal_actions"] == []


@pytest.mark.parametrize("edit", [
    lambda d: d["dialogues"][0]["source"].update(world_id="wrong-world"),
    lambda d: d["dialogues"][0].update(npc="missing"),
    lambda d: d["dialogues"][0].update(witness=["depart"]),
    lambda d: d["dialogues"][0].update(gates={"s0": "unearned"}),
    lambda d: d["dialogues"][0].update(gates={"s99": "restore-western-lens"}),
    lambda d: d["dialogues"].append(deepcopy(d["dialogues"][0])),
])
def test_unbound_dialogue_contracts_denied(edit):
    source = spec()
    edit(source)
    code, data, _ = invoke("build", source)
    assert code == 1 and data is None


def test_rehashed_dialogue_reputation_and_progress_fail_replay():
    source = spec()
    receipt = play_campaign(source, [])
    forged = deepcopy(receipt)
    forged["state"]["dialogues"]["keeper"]["state"]["quests"] = ["restore-western-lens"]
    rehash(forged, "session_digest")
    assert not verify_session(source, forged)
    with pytest.raises(ValueError):
        append_actions(source, forged, build_campaign(source)["witness"])
    changed = deepcopy(source)
    changed["dialogues"][0]["source"]["nodes"][0]["text"] += " Changed."
    assert not verify_session(changed, receipt)
    assert not verify_campaign(changed, build_campaign(source))


def test_persistent_reopen_idempotency_and_cas(tmp_path):
    source = spec()
    witness = build_campaign(source)["witness"]
    path = tmp_path / "campaign.sqlite"
    with sqlite3.connect(path) as db:
        first = CampaignStore(db).create("slot-a", source, "create-1")
        assert first["revision"] == 0
    with sqlite3.connect(path) as db:
        store = CampaignStore(db)
        assert store.read("slot-a", source) == first
        assert store.create("slot-a", source, "create-1") == first
        second = store.append("slot-a", source, 0, "listen-1", witness[:1])
        assert second["revision"] == 1
        assert store.append("slot-a", source, 0, "listen-1", witness[:1]) == second
        with pytest.raises(RevisionConflict):
            store.append("slot-a", source, 0, "stale", witness[:1])
        with pytest.raises(RevisionConflict):
            store.append("slot-a", source, 0, "listen-1", witness[:2])
        done = store.append("slot-a", source, 1, "complete", witness[1:])
        assert done["receipt"]["state"]["status"] == "completed"
        assert store.read("slot-a", source, 0) == first
        assert store.append("slot-a", source, 0, "listen-1", witness[:1]) == second
        assert [row["revision"] for row in store.history("slot-a", source)["revisions"]] == [0, 1, 2]
        assert store.read("slot-a", source) == done
        changed = deepcopy(source)
        changed["quest_request"]["quest"]["seed"] += 1
        with pytest.raises(CampaignStoreError):
            store.read("slot-a", changed)


def test_failed_append_is_atomic_and_operations_are_scoped(tmp_path):
    source = spec()
    witness = build_campaign(source)["witness"]
    with sqlite3.connect(tmp_path / "campaign.sqlite") as db:
        store = CampaignStore(db)
        zero = store.create("one", source, "same")
        store.create("two", source, "same")
        with pytest.raises(ValueError):
            store.append("one", source, 0, "retry", witness[2:])
        assert store.read("one", source) == zero
        assert len(store.history("one", source)["revisions"]) == 1
        assert store.append("one", source, 0, "retry", witness[:1])["revision"] == 1
        assert store.read("two", source)["revision"] == 0


def test_competing_connection_cannot_advance_stale_head(tmp_path):
    source = spec()
    witness = build_campaign(source)["witness"]
    path = tmp_path / "campaign.sqlite"
    with sqlite3.connect(path) as a, sqlite3.connect(path) as b:
        left, right = CampaignStore(a), CampaignStore(b)
        left.create("slot", source, "create")
        assert right.read("slot", source)["revision"] == 0
        left.append("slot", source, 0, "left", witness[:1])
        with pytest.raises(RevisionConflict):
            right.append("slot", source, 0, "right", witness[:1])
        assert right.read("slot", source)["revision"] == 1


def test_modified_database_receipt_or_lineage_fails_closed(tmp_path):
    source = spec()
    witness = build_campaign(source)["witness"]
    with sqlite3.connect(tmp_path / "campaign.sqlite") as db:
        store = CampaignStore(db)
        store.create("slot", source, "create")
        second = store.append("slot", source, 0, "one", witness[:1])
        db.execute("UPDATE gf_campaign_revisions_v1 SET previous_digest=? WHERE revision=1", ("0"*64,))
        db.commit()
        with pytest.raises(CampaignStoreError):
            store.read("slot", source)
        with pytest.raises(CampaignStoreError):
            store.history("slot", source)
        receipt = deepcopy(second["receipt"])
        receipt["state"]["earned_rewards"] = [{"kind": "gold", "amount": 99}]
        rehash(receipt, "session_digest")
        db.execute("UPDATE gf_campaign_revisions_v1 SET receipt=?,receipt_digest=? WHERE revision=1",
                   (encoded(receipt), receipt["session_digest"]))
        db.commit()
        with pytest.raises(CampaignStoreError):
            store.read("slot", source)


def test_cli_persistent_roundtrip_and_canonical_entrypoint(tmp_path):
    source = spec()
    path = tmp_path / "campaign.sqlite"
    code, design, _ = invoke("build", source)
    assert code == 0
    assert invoke("verify", {"request": source, "receipt": design})[0] == 0
    body = {"request": source, "slot": "a", "operation": "create"}
    assert invoke("create-slot", body, path)[0] == 0
    code, complete, _ = invoke("append-slot", {"request": source, "slot": "a",
        "operation": "win", "expected_revision": 0, "additional": design["witness"]}, path)
    assert code == 0 and complete["receipt"]["state"]["status"] == "completed"
    assert invoke("read-slot", {"request": source, "slot": "a"}, path)[1] == complete
    assert invoke("history", {"request": source, "slot": "a"}, path)[1]["head"] == 1
    proc = subprocess.run([sys.executable, "-m", "skeleton", "gameforge-campaign", "build"],
                          input=encoded(source), capture_output=True, timeout=60, check=True)
    assert json.loads(proc.stdout) == design


def test_cli_does_not_create_db_during_read(tmp_path):
    path = tmp_path / "absent.sqlite"
    assert invoke("read-slot", {"request": spec(), "slot": "a"}, path)[0] == 1
    assert not path.exists()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX file mode requirement")
def test_cli_refuses_symlink_and_public_parent(tmp_path):
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    target = private / "actual.sqlite"
    target.touch(mode=0o600)
    link = private / "link.sqlite"
    link.symlink_to(target)
    data = {"request": spec(), "slot": "a", "operation": "new"}
    assert invoke("create-slot", data, link)[0] == 1
    public = tmp_path / "public"
    public.mkdir(mode=0o755)
    assert invoke("create-slot", data, public / "db.sqlite")[0] == 1


def test_read_never_initializes_unrelated_database(tmp_path):
    path = tmp_path / "other.sqlite"
    path.touch(mode=0o600)
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE unrelated (value TEXT)")
    assert invoke("read-slot", {"request": spec(), "slot": "a"}, path)[0] == 1
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() == [("unrelated",)]


def test_head_rollback_and_nonobject_receipt_are_detected(tmp_path):
    source = spec()
    with sqlite3.connect(tmp_path / "campaign.sqlite") as db:
        store = CampaignStore(db)
        store.create("slot", source, "create")
        action = build_campaign(source)["witness"][:1]
        store.append("slot", source, 0, "advance", action)
        db.execute("UPDATE gf_campaign_slots_v1 SET head=0")
        db.commit()
        with pytest.raises(CampaignStoreError, match="journal disagree"):
            store.read("slot", source)
        db.execute("UPDATE gf_campaign_slots_v1 SET head=1")
        db.execute("UPDATE gf_campaign_revisions_v1 SET receipt=? WHERE revision=1", (b"[]",))
        db.commit()
        with pytest.raises(CampaignStoreError):
            store.read("slot", source)


def test_completion_search_replays_actual_partial_dialogue_and_is_nonmutating():
    from skeleton.app.gameforge_campaign_assist import plan_completion, verify_assistance
    source = spec()
    witness = build_campaign(source)["witness"]
    checkpoint = play_campaign(source, witness[:1])
    frozen = deepcopy(checkpoint)
    plan = plan_completion(source, checkpoint)
    assert plan["status"] == "completion_witness"
    assert plan["next_action"] == witness[1]
    assert plan["expanded"] <= plan["search_budget"]
    assert verify_assistance(source, checkpoint, plan)
    finished = append_actions(source, checkpoint, plan["additional"])
    assert finished["state"]["status"] == "completed"
    assert finished["session_digest"] == plan["completion_digest"]
    assert checkpoint == frozen
    assert plan_completion(source, finished)["status"] == "already_completed"


def test_decline_is_proven_dialogue_blocker_not_fabricated_success():
    from skeleton.app.gameforge_campaign_assist import plan_completion
    source = spec()
    declined = play_campaign(source, [{"type": "dialogue", "npc": "keeper", "choice": "depart"}])
    result = plan_completion(source, declined)
    assert result["status"] == "dialogue_unreachable"
    assert result["blocker"]["npc"] == "keeper"
    assert result["blocker"]["required_grants"] == ["restore-western-lens"]
    assert result["additional"] == [] and result["completion_digest"] is None
    assert declined["state"]["status"] == "in_progress"


def test_bounded_search_does_not_assert_impossibility_on_exhaustion():
    from skeleton.app.gameforge_campaign_assist import plan_completion
    source = spec()
    start = play_campaign(source, [])
    result = plan_completion(source, start, max_expansions=1)
    assert result["status"] == "budget_exhausted"
    assert result["expanded"] <= 1 and result["additional"] == []
    assert plan_completion(source, start)["status"] == "completion_witness"
    with pytest.raises(ValueError):
        plan_completion(source, start, max_expansions=True)


def test_assistance_forgery_and_altered_source_are_rejected():
    from skeleton.app.gameforge_campaign_assist import plan_completion, verify_assistance
    source = spec()
    start = play_campaign(source, [])
    result = plan_completion(source, start)
    tampered = deepcopy(result)
    tampered["additional"] = []
    rehash(tampered, "assistance_digest")
    assert not verify_assistance(source, start, tampered)
    forged = deepcopy(start)
    forged["state"]["dialogues"]["keeper"]["state"]["quests"] = ["restore-western-lens"]
    rehash(forged, "session_digest")
    with pytest.raises(ValueError):
        plan_completion(source, forged)


def test_branch_comparison_reports_real_grants_rewards_and_reputation():
    from skeleton.app.gameforge_campaign_board import compare_branches, verify_comparison
    source = spec()
    design = build_campaign(source)
    left = play_campaign(source, [{"type": "dialogue", "npc": "keeper", "choice": "depart"}])
    right = play_campaign(source, design["witness"])
    comparison = compare_branches(source, left, right)
    assert comparison["common_prefix"] == 0
    assert comparison["left_first_divergence"]["choice"] == "depart"
    assert comparison["right_first_divergence"]["choice"] == "listen"
    assert comparison["dialogue_outcomes"]["keeper"]["reputation_delta"] == 9
    assert comparison["left_completion"]["status"] == "dialogue_unreachable"
    assert comparison["right_completion"]["status"] == "already_completed"
    assert comparison["reward_delta_right_minus_left"]["gold"] == sum(
        row["amount"] for row in right["state"]["earned_rewards"])
    assert comparison["objective_changes"]["s0"]["right"] == "completed"
    assert verify_comparison(source, left, right, comparison)
    forged = deepcopy(comparison)
    forged["reward_delta_right_minus_left"]["gold"] = 999
    rehash(forged, "comparison_digest")
    assert not verify_comparison(source, left, right, forged)


def test_board_only_exposes_replayed_legal_actions_and_escapes_authored_html():
    from skeleton.app.gameforge_campaign_board import board, render_html, verify_board
    source = spec()
    source["dialogues"][0]["source"]["nodes"][0]["text"] = '<img src=x onerror="alert(1)">'
    initial = play_campaign(source, [])
    result = board(source, initial)
    assert result["legal_actions"] == initial["state"]["legal_actions"]
    assert result["earned_totals"] == {}
    assert result["nearby_npcs"][0]["text"].startswith("<img")
    assert verify_board(source, initial, result)
    assert all(not row.get("dialogue_gate", {}).get("satisfied") for row in result["objectives"])
    html = render_html(source, initial)
    assert "&lt;img" in html and "<img" not in html
    assert "Content-Security-Policy" in html and "<script" not in html
    assert initial["session_digest"] in html
    assert render_html(source, initial) == html


def test_historical_fork_copies_prefix_and_branches_without_losing_original(tmp_path):
    from skeleton.app.gameforge_campaign_assist import plan_completion
    source = spec()
    witness = build_campaign(source)["witness"]
    with sqlite3.connect(tmp_path / "timeline.sqlite") as db:
        store = CampaignStore(db)
        zero = store.create("original", source, "genesis")
        first = store.append("original", source, 0, "listen", witness[:1])
        ending = store.append("original", source, 1, "decline", [
            {"type": "dialogue", "npc": "keeper", "choice": "decline"}])
        child = store.fork("original", source, 1, first["receipt"]["session_digest"], "alternate")
        assert child["child"]["receipt"] == first["receipt"]
        assert child["child"]["revision"] == 1
        assert store.read("alternate", source, 0)["receipt"] == zero["receipt"]
        plan = plan_completion(source, child["child"]["receipt"])
        won = store.append("alternate", source, 1, "win", plan["additional"])
        assert won["receipt"]["state"]["status"] == "completed"
        assert store.read("original", source) == ending
        assert len(store.history("alternate", source)["revisions"]) == 3
        assert plan_completion(source, ending["receipt"])["status"] == "dialogue_unreachable"
        with pytest.raises(CampaignStoreError):
            store.fork("original", source, 1, first["receipt"]["session_digest"], "alternate")


def test_fork_wrong_digest_or_capacity_rolls_back_entire_child(tmp_path, monkeypatch):
    import skeleton.app.gameforge_campaign_store as implementation
    source = spec()
    with sqlite3.connect(tmp_path / "timeline.sqlite") as db:
        store = CampaignStore(db)
        zero = store.create("original", source, "genesis")
        with pytest.raises(RevisionConflict):
            store.fork("original", source, 0, "0"*64, "wrong")
        monkeypatch.setattr(implementation, "MAX_TOTAL_BYTES", 1)
        with pytest.raises(CampaignStoreError, match="storage ceiling"):
            store.fork("original", source, 0, zero["receipt"]["session_digest"], "full")
        assert db.execute("SELECT slot FROM gf_campaign_slots_v1").fetchall() == [("original",)]
        assert store.read("original", source) == zero


def test_helpers_via_canonical_cli_and_historical_fork(tmp_path):
    source = spec()
    start = play_campaign(source, [])
    bundle = {"request": source, "receipt": start}
    code, plan, _ = invoke("assist", bundle)
    assert code == 0 and plan["status"] == "completion_witness"
    assert invoke("verify-assist", {**bundle, "assistance": plan})[0] == 0
    assert invoke("board", bundle)[1]["checkpoint_digest"] == start["session_digest"]
    assert invoke("compare", {"request": source, "left": start, "right": start})[1]["common_prefix"] == 0
    out, err = io.StringIO(), io.StringIO()
    assert main(["html"], stdin=io.BytesIO(encoded(bundle)), stdout=out, stderr=err) == 0
    assert out.getvalue().startswith("<!doctype html>")
    path = tmp_path / "campaign.sqlite"
    assert invoke("create-slot", {"request": source, "slot": "a", "operation": "genesis"}, path)[0] == 0
    code, forked, _ = invoke("fork-slot", {"request": source, "slot": "a",
        "parent_revision": 0, "expected_digest": start["session_digest"], "child_slot": "b"}, path)
    assert code == 0 and forked["child"]["receipt"] == start
