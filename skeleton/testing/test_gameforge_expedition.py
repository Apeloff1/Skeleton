"""Recovered local crafting and generated campaign integration acceptance fixtures."""
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys

import pytest

from skeleton.app.gameforge_campaign import REQUEST_SCHEMA as CAMPAIGN_SCHEMA
from skeleton.app.gameforge_quest_bridge import REQUEST_SCHEMA as QUEST_SCHEMA
from skeleton.app.gameforge_expedition import (
    REQUEST_SCHEMA, build_expedition, play_expedition, resume_expedition, verify_expedition,
)
from skeleton.app.gameforge_expedition_board import (
    episode_evidence, expedition_board, turn, verify_board, verify_evidence,
)
from skeleton.app.gameforge_expedition_cli import main
from skeleton.game.gameplay import harbor_crafting as harbor


def request():
    dialogue = json.loads((Path(__file__).parent / "fixtures" /
                           "dialogue_original_lantern_harbor.json").read_text(encoding="utf-8"))
    local = json.loads((Path(harbor.__file__).parent / "fixtures" /
                        "harbor_lantern_quay.json").read_text(encoding="utf-8"))
    return {
        "schema": REQUEST_SCHEMA,
        "campaign": {
            "schema": CAMPAIGN_SCHEMA,
            "quest_request": {
                "schema": QUEST_SCHEMA,
                "vision": {"title": "Lantern Harbor", "pitch": "Restore the coastal lantern",
                           "genre": "adventure", "pillars": ["exploration", "story"]},
                "config": {"regions": 6, "budget_bytes": 200000},
                "quest": {
                    "packs": [{"id": "movement", "provides": ["movement"]},
                              {"id": "quest", "provides": ["quests"], "requires": ["movement"]}],
                    "pack_ids": ["quest", "movement"],
                    "policy": {"allowed_reward_kinds": ["gold"], "max_reward_per_step": 2,
                               "max_total_reward": 12},
                    "seed": 31, "quest_length": 4, "npcs": {"keeper": "r00"},
                },
            },
            "dialogues": [{"npc": "keeper", "source": dialogue,
                           "gates": {"s0": "restore-western-lens"},
                           "witness": ["listen", "promise-repair"]}],
        },
        "episodes": [{"objective": "s0", "source": local, "required_ending": "beacon",
                      "witness": harbor.demo_actions()}],
    }


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("ascii")


def rehash(value, key):
    value[key] = hashlib.sha256(canonical({k: v for k, v in value.items() if k != key})).hexdigest()


def invoke(command, value, database=None):
    out, err = io.StringIO(), io.StringIO()
    args = [command] + (["--database", str(database)] if database is not None else [])
    code = main(args, stdin=io.BytesIO(canonical(value)), stdout=out, stderr=err)
    return code, json.loads(out.getvalue()) if out.getvalue() else None, err.getvalue()


def portal(witness):
    return next(i for i, event in enumerate(witness) if event["type"] == "harbor")


def first_resolve(witness):
    return next(i for i, event in enumerate(witness) if event["type"] == "resolve")


def test_actual_harbor_and_campaign_handoff_completes_independent_engines():
    source = request()
    design = build_expedition(source)
    actions = design["witness"]
    before = portal(actions)
    finish = first_resolve(actions)
    assert before < finish
    assert [a["action"] for a in actions[before:finish]] == harbor.demo_actions()
    expected = harbor.export_bundle(source["episodes"][0]["source"], harbor.demo_actions(), require_win=True)
    summary = design["witness_state"]["episodes"]["s0"]
    assert summary["state"] == expected["state"]
    assert summary["bundle_digest"] == expected["bundle_digest"]
    assert summary["gate_satisfied"] and summary["state"]["ending"] == "beacon"
    assert summary["state"]["delivered"] and summary["state"]["inventory"] == {}
    assert design["witness_state"]["status"] == "completed"
    assert len(design["witness_state"]["earned_rewards"]) == 4
    assert design == build_expedition(deepcopy(source))
    assert verify_expedition(source, design)
    complete = play_expedition(source, actions)
    assert complete["state"] == design["witness_state"]
    assert verify_expedition(source, complete, session=True)
    assert not complete["native_qualified"] and not complete["release_qualified"]


def test_empty_and_partial_play_do_not_award_design_witness():
    source = request()
    actions = build_expedition(source)["witness"]
    start = portal(actions)
    end = first_resolve(actions)
    empty = play_expedition(source, [])
    assert not empty["state"]["earned_rewards"]
    assert empty["state"]["episodes"]["s0"]["event_count"] == 0
    assert not empty["state"]["episodes"]["s0"]["gate_satisfied"]
    partial = play_expedition(source, actions[:start + 3])
    episode = partial["state"]["episodes"]["s0"]
    assert episode["state"]["inventory"] == {"wood": 2}
    assert episode["state"]["tick"] == 3
    assert not partial["state"]["earned_rewards"]
    ready = resume_expedition(source, partial, actions[start + 3:end])
    assert ready["state"]["episodes"]["s0"]["gate_satisfied"]
    assert not ready["state"]["earned_rewards"]  # local victory does not resolve the outer objective
    result = resume_expedition(source, ready, actions[end:])
    assert result == play_expedition(source, actions)
    assert result["state"]["status"] == "completed"
    assert partial["state"]["episodes"]["s0"]["state"]["tick"] == 3


def test_quest_resolution_cannot_skip_local_game_or_dialogue():
    source = request()
    actions = build_expedition(source)["witness"]
    start, end = portal(actions), first_resolve(actions)
    with pytest.raises(ValueError, match="ending"):
        play_expedition(source, actions[:start] + actions[end:end + 1])
    with pytest.raises(ValueError):
        play_expedition(source, [actions[start]])
    with pytest.raises(ValueError):
        play_expedition(source, actions[:start] + [
            {"type": "harbor", "objective": "s1", "action": {"op": "wait"}}])
    assert play_expedition(source, actions[:start])["state"]["earned_rewards"] == []


def test_canonical_collision_resource_crafting_and_delivery_cannot_be_forged():
    source = request()
    actions = build_expedition(source)["witness"]
    start = portal(actions)
    for impossible in ({"op": "gather"}, {"op": "move", "direction": "west"},
                       {"op": "craft", "recipe": "lantern"}, {"op": "deliver"},
                       {"op": "trade", "item": "food"}, {"op": "choose", "choice": "signal"},
                       {"op": "grant", "amount": 900}):
        with pytest.raises(ValueError):
            play_expedition(source, actions[:start] + [
                {"type": "harbor", "objective": "s0", "action": impossible}])
    with pytest.raises(ValueError):
        play_expedition(source, actions[:start + 3] + [
            {"type": "harbor", "objective": "s0", "action": {"op": "gather"}}])


def test_alternate_earned_local_ending_is_real_but_not_the_required_gate():
    source = request()
    actions = build_expedition(source)["witness"]
    end = first_resolve(actions)
    alternate = deepcopy(actions[:end])
    alternate[-1]["action"]["choice"] = "shelter"
    saved = play_expedition(source, alternate)
    assert saved["state"]["episodes"]["s0"]["state"]["ending"] == "safe_harbor"
    assert not saved["state"]["episodes"]["s0"]["gate_satisfied"]
    assert saved["state"]["blockers"][0]["reason"] == "alternate_ending"
    assert saved["state"]["earned_rewards"] == []
    with pytest.raises(ValueError, match="ending"):
        resume_expedition(source, saved, [actions[end]])
    assert verify_expedition(source, saved, session=True)


def test_board_projects_only_combined_legal_actions_and_exact_turn():
    source = request()
    actions = build_expedition(source)["witness"]
    start = portal(actions)
    ready = play_expedition(source, actions[:start])
    current = expedition_board(source, ready)
    assert current["campaign_view"]["legal_actions"] == current["legal_actions"]
    assert not any(a["type"] == "resolve" for a in current["legal_actions"])
    assert current["episodes"][0]["active_here"]
    assert sum(row.count("@") for row in current["episodes"][0]["grid"]) == 1
    selected = current["legal_actions"].index(actions[start])
    result = turn(source, ready, current["board_digest"], selected)
    assert result["receipt"] == play_expedition(source, actions[:start + 1])
    assert result["board"]["episodes"][0]["tick"] == 1
    with pytest.raises(ValueError, match="board changed"):
        turn(source, result["receipt"], current["board_digest"], selected)
    assert verify_board(source, ready, current)


def test_portable_evidence_requires_outer_source_and_earned_canonical_bundle():
    source = request()
    design = build_expedition(source)
    checkpoint = play_expedition(source, design["witness"])
    evidence = episode_evidence(source, checkpoint, "s0")
    assert evidence["gate_satisfied"]
    assert harbor.verify_bundle(evidence["bundle"], require_win=True)["ending"] == "beacon"
    assert verify_evidence(source, checkpoint, evidence)
    forged = deepcopy(evidence)
    forged["bundle"]["state"]["coins"] = 999
    forged["bundle"]["bundle_digest"] = harbor.digest({
        k: v for k, v in forged["bundle"].items() if k != "bundle_digest"})
    rehash(forged, "evidence_digest")
    assert not verify_evidence(source, checkpoint, forged)
    forged_checkpoint = deepcopy(checkpoint)
    forged_checkpoint["state"]["episodes"]["s0"]["state"]["coins"] = 999
    rehash(forged_checkpoint, "session_digest")
    assert not verify_expedition(source, forged_checkpoint, session=True)
    changed = deepcopy(source)
    changed["episodes"][0]["source"]["initial_coins"] += 1
    assert not verify_expedition(changed, checkpoint, session=True)
    assert not verify_evidence(changed, checkpoint, evidence)


@pytest.mark.parametrize("edit", [
    lambda d: d["episodes"][0].update(objective="missing"),
    lambda d: d["episodes"][0].update(required_ending="safe_harbor"),
    lambda d: d["episodes"][0].update(witness=[{"op": "wait"}]),
    lambda d: d["episodes"][0]["source"].update(max_ticks=257),
    lambda d: d["episodes"].append(deepcopy(d["episodes"][0])),
])
def test_bad_episode_contract_fails_before_receipt(edit):
    source = request()
    edit(source)
    code, value, error = invoke("build", source)
    assert code == 1 and value is None and error.startswith("expedition rejected:")


def test_two_bound_episodes_have_distinct_ledgers_and_never_share_inventory():
    source = request()
    second = deepcopy(source["episodes"][0])
    second["objective"] = "s2"
    second["required_ending"] = "safe_harbor"
    second["witness"][-1]["choice"] = "shelter"
    source["episodes"].append(second)
    design = build_expedition(source)
    final = design["witness_state"]["episodes"]
    assert final["s0"]["state"]["ending"] == "beacon"
    assert final["s2"]["state"]["ending"] == "safe_harbor"
    assert final["s0"]["bundle_digest"] != final["s2"]["bundle_digest"]
    first_episode_end = first_resolve(design["witness"])
    partial = play_expedition(source, design["witness"][:first_episode_end + 1])
    assert partial["state"]["episodes"]["s2"]["state"]["inventory"] == {}
    assert partial["state"]["episodes"]["s2"]["event_count"] == 0
    assert len(partial["state"]["earned_rewards"]) == 1


def test_cli_source_to_play_board_resume_export_and_module_dispatch():
    source = request()
    code, design, _ = invoke("build", source)
    assert code == 0
    assert invoke("verify", {"request": source, "receipt": design})[0] == 0
    code, empty, _ = invoke("play", {"request": source, "actions": []})
    assert code == 0
    current = invoke("board", {"request": source, "receipt": empty})[1]
    assert invoke("verify-board", {"request": source, "receipt": empty, "board": current})[0] == 0
    code, complete, _ = invoke("resume", {"request": source, "receipt": empty,
                                          "additional": design["witness"]})
    assert code == 0
    assert invoke("verify-play", {"request": source, "receipt": complete})[0] == 0
    evidence = invoke("evidence", {"request": source, "receipt": complete, "objective": "s0"})[1]
    assert invoke("verify-evidence", {"request": source, "receipt": complete,
                                     "evidence": evidence})[0] == 0
    proc = subprocess.run([sys.executable, "-m", "skeleton", "gameforge-expedition", "build"],
                          input=canonical(source), capture_output=True, timeout=90, check=True)
    assert json.loads(proc.stdout) == design


def mission_request():
    source = request()
    board = json.loads((Path(harbor.__file__).parent / "fixtures" /
                        "harbor_lantern_quay_missions.json").read_text(encoding="utf-8"))
    source["episodes"][0].update(mission_board=board, required_missions=["dispatch"])
    return source


def test_mission_gates_reuse_actual_harbor_mission_owner():
    from skeleton.game.gameplay.harbor_crafting_missions import mission_report, verify_mission_report
    source = mission_request()
    design = build_expedition(source)
    completed = play_expedition(source, design["witness"])
    summary = completed["state"]["episodes"]["s0"]["missions"]
    assert summary["completed"] == ["salvage", "workshop", "dispatch"]
    assert summary["points"] == 60 and summary["required"] == ["dispatch"]
    assert summary["satisfied"]
    evidence = episode_evidence(source, completed, "s0")
    expected = mission_report(evidence["bundle"], source["episodes"][0]["mission_board"], require_all=True)
    assert evidence["mission_report"] == expected
    assert verify_mission_report(expected, require_all=True)["points"] == 60
    assert summary["report_digest"] == expected["report_digest"]
    assert verify_evidence(source, completed, evidence)
    board = expedition_board(source, completed)
    assert board["episodes"][0]["missions"] == summary


def test_required_mission_deadline_is_a_real_gate_even_with_earned_ending():
    from skeleton.app.gameforge_expedition_recovery import plan_expedition
    source = mission_request()
    source["episodes"][0]["mission_board"]["missions"][0]["deadline"] = 5
    # The unchanged authorized demo earns salvage at tick 5, so the
    # request remains playable. One explicit wait forfeits that deadline.
    design = build_expedition(source)
    actions = design["witness"]
    start, end = portal(actions), first_resolve(actions)
    delayed = actions[:start] + [
        {"type": "harbor", "objective": "s0", "action": {"op": "wait"}}
    ] + actions[start:end]
    # A moving merchant may affect traversability; the fixture's demo
    # follows the west/south route that avoids the merchant tiles.
    terminal = play_expedition(source, delayed)
    mission = terminal["state"]["episodes"]["s0"]
    assert mission["state"]["ending"] == "beacon"
    assert not mission["gate_satisfied"] and not mission["missions"]["satisfied"]
    assert terminal["state"]["blockers"][0]["reason"] == "required_missions_missing"
    assert terminal["state"]["earned_rewards"] == []
    with pytest.raises(ValueError, match="missions"):
        resume_expedition(source, terminal, [actions[end]])
    result = plan_expedition(source, terminal)
    assert result["status"] == "local_required_missions_missing"
    assert not result["additional"]


def test_recovery_uses_actual_partial_local_inventory_and_explicit_wait_splice():
    from skeleton.app.gameforge_expedition_recovery import plan_expedition, verify_plan
    source = mission_request()
    actions = build_expedition(source)["witness"]
    start = portal(actions)
    partial_actions = actions[:start + 3] + [
        {"type": "harbor", "objective": "s0", "action": {"op": "wait"}}
    ]
    partial = play_expedition(source, partial_actions)
    frozen = deepcopy(partial)
    plan = plan_expedition(source, partial)
    assert plan["status"] == "completion_witness"
    local = plan["local_results"]["s0"]
    assert local["strategy"] == "verified_wait_splice"
    assert local["completion_missions"]["satisfied"]
    assert verify_plan(source, partial, plan)
    final = resume_expedition(source, partial, plan["additional"])
    assert final["state"]["status"] == "completed"
    assert final["session_digest"] == plan["completion_digest"]
    assert final["state"]["episodes"]["s0"]["missions"]["points"] == 60
    assert partial == frozen
    assert plan_expedition(source, final)["status"] == "already_completed"


def test_mission_deadline_prunes_recovery_without_guessing_grants():
    from skeleton.app.gameforge_expedition_local_recovery import recover_local, verify_local_recovery
    source = mission_request()["episodes"][0]
    board = source["mission_board"]
    board["missions"][0]["deadline"] = 5
    prefix = [{"op": "wait"}] * 5
    plan = recover_local(source["source"], prefix, "beacon", witness=source["witness"],
                         mission_board=board, required_missions=["dispatch"])
    assert plan["status"] == "mission_deadline_exhausted"
    assert plan["additional"] == [] and plan["expanded"] == 0
    assert verify_local_recovery(source["source"], prefix, plan, witness=source["witness"],
                                 mission_board=board, required_missions=["dispatch"])


def test_local_search_ceiling_is_not_proof_of_unreachability():
    from skeleton.app.gameforge_expedition_local_recovery import recover_local
    source = request()["episodes"][0]["source"]
    result = recover_local(source, [], "beacon", max_states=1)
    assert result["status"] == "budget_exhausted" and result["additional"] == []
    assert result["expanded"] <= 1
    with pytest.raises(ValueError):
        recover_local(source, [], "beacon", max_states=True)


def test_bounded_transition_search_completes_real_near_terminal_state():
    from skeleton.app.gameforge_expedition_local_recovery import recover_local
    ep = mission_request()["episodes"][0]
    prefix = ep["witness"][:-1]
    local = recover_local(ep["source"], prefix, "beacon", max_states=32,
                          mission_board=ep["mission_board"], required_missions=["dispatch"])
    assert local["status"] == "completion_witness"
    assert local["additional"] == [{"op": "choose", "choice": "signal"}]
    assert local["strategy"] == "bounded_transition_search"


def test_recovery_comparison_and_forged_plan_are_source_fenced():
    from skeleton.app.gameforge_expedition_recovery import compare_expeditions, verify_comparison, plan_expedition, verify_plan
    source = mission_request()
    actions = build_expedition(source)["witness"]
    end = first_resolve(actions)
    branch = deepcopy(actions[:end])
    branch[-1]["action"]["choice"] = "shelter"
    left = play_expedition(source, branch)
    right = play_expedition(source, actions)
    comparison = compare_expeditions(source, left, right)
    assert comparison["common_prefix"] == end - 1
    row = comparison["episodes"]["s0"]
    assert row["left_ending"] == "safe_harbor" and row["right_ending"] == "beacon"
    assert row["mission_outcomes"]["points_delta"] == 30
    assert comparison["left_recovery"]["status"] == "local_alternate_ending"
    assert comparison["right_recovery"]["status"] == "already_completed"
    assert verify_comparison(source, left, right, comparison)
    initial = play_expedition(source, [])
    plan = plan_expedition(source, initial)
    forged = deepcopy(plan)
    forged["additional"] = []
    rehash(forged, "recovery_digest")
    assert not verify_plan(source, initial, forged)
    altered = deepcopy(comparison)
    altered["episodes"]["s0"]["coin_delta"] = 100
    rehash(altered, "comparison_digest")
    assert not verify_comparison(source, left, right, altered)


def test_new_mission_bindings_are_strict_and_witness_must_earn_them():
    source = mission_request()
    bad = deepcopy(source)
    bad["episodes"][0].pop("required_missions")
    assert invoke("build", bad)[0] == 1
    bad = deepcopy(source)
    bad["episodes"][0]["required_missions"] = ["nonexistent"]
    assert invoke("build", bad)[0] == 1
    bad = deepcopy(source)
    bad["episodes"][0]["mission_board"]["missions"][0]["deadline"] = 1
    assert invoke("build", bad)[0] == 1
    bad = deepcopy(source)
    bad["episodes"][0]["mission_board"]["source_id"] = "foreign-world"
    assert invoke("build", bad)[0] == 1


def test_durable_expedition_fork_restore_and_namespace_isolation(tmp_path):
    import sqlite3
    from skeleton.app.gameforge_expedition_store import ExpeditionStore
    from skeleton.app.gameforge_campaign_store import CampaignStore, RevisionConflict, CampaignStoreError
    source = request()
    design = build_expedition(source)
    witness = design["witness"]
    start, end = portal(witness), first_resolve(witness)
    path = tmp_path / "journal.sqlite"
    with sqlite3.connect(path) as db:
        narratives = CampaignStore(db)
        campaigns = narratives.create("shared", source["campaign"], "init")
        store = ExpeditionStore(db)
        genesis = store.create("shared", source, "init")
        assert genesis["receipt"]["schema"] != campaigns["receipt"]["schema"]
        partial = store.append("shared", source, 0, "partial", witness[:start + 3])
        assert partial["receipt"]["state"]["episodes"]["s0"]["state"]["inventory"] == {"wood": 2}
        assert store.append("shared", source, 0, "partial", witness[:start + 3]) == partial
        with pytest.raises(RevisionConflict):
            store.append("shared", source, 0, "stale", witness[:1])
        with pytest.raises(CampaignStoreError):
            store.read("shared", source["campaign"])
    with sqlite3.connect(path) as db:
        store = ExpeditionStore(db, initialize=False)
        assert store.read("shared", source) == partial
        remainder = deepcopy(witness[start + 3:end])
        branch = deepcopy(remainder)
        branch[-1]["action"]["choice"] = "shelter"
        alternate = store.append("shared", source, 1, "alternate", branch)
        forked = store.fork("shared", source, 1, partial["receipt"]["session_digest"], "successful")
        assert forked["child"]["receipt"] == partial["receipt"]
        completed = store.append("successful", source, 1, "finish", witness[start + 3:])
        assert completed["receipt"]["state"]["status"] == "completed"
        assert store.read("shared", source) == alternate
        archive = store.snapshot("successful", source)
        assert archive["namespace"] == "expedition" and archive["head"] == 2
        assert "receipt" not in archive["operations"][1]
        restored = store.restore("restored", source, archive)
        assert restored["receipt"] == completed["receipt"]
        assert store.history("restored", source)["revisions"] == store.history("successful", source)["revisions"]
        assert CampaignStore(db, initialize=False).read("shared", source["campaign"]) == campaigns
        with pytest.raises(CampaignStoreError):
            CampaignStore(db, initialize=False).restore("wrong", source["campaign"], archive)


def test_archive_restore_forgery_and_capacity_are_atomic(tmp_path, monkeypatch):
    import sqlite3
    import skeleton.app.gameforge_campaign_store as journal
    from skeleton.app.gameforge_expedition_store import ExpeditionStore
    source = request()
    witness = build_expedition(source)["witness"]
    with sqlite3.connect(tmp_path / "archive.sqlite") as db:
        store = ExpeditionStore(db)
        store.create("source", source, "init")
        store.append("source", source, 0, "first", witness[:1])
        archive = store.snapshot("source", source)
        forged = deepcopy(archive)
        forged["operations"][1]["receipt_digest"] = "f" * 64
        rehash(forged, "archive_digest")
        with pytest.raises(journal.CampaignStoreError, match="independent replay"):
            store.restore("forged", source, forged)
        assert db.execute("SELECT slot FROM gf_expedition_slots_v1").fetchall() == [("source",)]
        forged = deepcopy(archive)
        forged["operations"][1]["operation"] = "init"
        rehash(forged, "archive_digest")
        with pytest.raises(journal.CampaignStoreError, match="duplicate"):
            store.restore("duplicated", source, forged)
        monkeypatch.setattr(journal, "MAX_TOTAL_BYTES", 1)
        with pytest.raises(journal.CampaignStoreError, match="storage ceiling"):
            store.restore("full", source, archive)
        assert store.snapshot("source", source) == archive


def test_durable_cli_board_turn_recovery_and_lost_response_retries(tmp_path):
    source = request()
    path = tmp_path / "game.sqlite"
    slot = {"request": source, "slot": "play"}
    zero = invoke("create-slot", {**slot, "operation": "init"}, path)[1]
    current = invoke("board-slot", slot, path)[1]
    action = {"type": "dialogue", "npc": "keeper", "choice": "listen"}
    index = current["board"]["legal_actions"].index(action)
    selected = {**slot, "operation": "listen", "expected_revision": 0,
                "board_digest": current["board"]["board_digest"], "index": index}
    first = invoke("turn-slot", selected, path)[1]
    assert first["revision"] == 1 and first["receipt"]["actions"] == [action]
    assert invoke("turn-slot", selected, path)[1] == first
    assert invoke("turn-slot", {**selected, "operation": "stale"}, path)[0] == 1
    fork = invoke("fork-slot", {**slot, "parent_revision": 0,
                               "expected_digest": zero["receipt"]["session_digest"],
                               "child_slot": "other"}, path)[1]
    assert fork["child"]["revision"] == 0
    recovery = invoke("assist-slot", slot, path)[1]["recovery"]
    assert recovery["status"] == "completion_witness"
    forged = deepcopy(recovery)
    forged["additional"] = []
    rehash(forged, "recovery_digest")
    operation = {**slot, "operation": "recover", "expected_revision": 1}
    assert invoke("apply-recovery-slot", {**operation, "recovery": forged}, path)[0] == 1
    assert invoke("read-slot", slot, path)[1] == first
    complete = invoke("apply-recovery-slot", {**operation, "recovery": recovery}, path)[1]
    assert complete["receipt"]["state"]["status"] == "completed"
    assert invoke("apply-recovery-slot", {**operation, "recovery": recovery}, path)[1] == complete
    snapshot = invoke("snapshot-slot", slot, path)[1]
    second_path = tmp_path / "restored.sqlite"
    restored = invoke("restore-slot", {**slot, "archive": snapshot}, second_path)[1]
    assert restored == complete
    comparison = invoke("compare-slots", {**slot, "other_slot": "other"}, path)[1]
    assert comparison["left_revision"] == 2 and comparison["right_revision"] == 0
    assert comparison["comparison"]["left_status"] == "completed"
    assert comparison["comparison"]["right_status"] == "in_progress"


def test_two_connections_reject_stale_expedition_write(tmp_path):
    import sqlite3
    from skeleton.app.gameforge_expedition_store import ExpeditionStore
    from skeleton.app.gameforge_campaign_store import RevisionConflict
    source = request()
    action = build_expedition(source)["witness"][:1]
    path = tmp_path / "game.sqlite"
    with sqlite3.connect(path) as a, sqlite3.connect(path) as b:
        first = ExpeditionStore(a)
        first.create("slot", source, "init")
        second = ExpeditionStore(b, initialize=False)
        assert second.read("slot", source)["revision"] == 0
        first.append("slot", source, 0, "write", action)
        with pytest.raises(RevisionConflict):
            second.append("slot", source, 0, "racing", action)
        assert second.read("slot", source)["revision"] == 1


def test_canonical_legacy_distribution_is_recovered_as_unplayed_expedition():
    from skeleton.app.gameforge_expedition_author import AUTHOR_SCHEMA, author_expedition, verify_authoring
    from skeleton.game.gameplay.harbor_crafting_package import build_package
    source = mission_request()
    ep = source["episodes"][0]
    author = {"schema": AUTHOR_SCHEMA, "campaign": source["campaign"],
              "bindings": [{"objective": "s0", "world": ep["source"],
                            "mission_board": ep["mission_board"], "choice": "signal",
                            "required_missions": ["dispatch"]}]}
    result = author_expedition(author)
    assert verify_authoring(author, result)
    package = build_package(ep["source"], ep["mission_board"], choice="signal")
    imported = deepcopy(author)
    imported["bindings"][0]["package"] = package
    recovered = author_expedition(imported)
    assert recovered["request"] == result["request"]
    assert recovered["design_digest"] == result["design_digest"]
    assert recovered["package_custody"] == result["package_custody"]
    assert recovered["package_custody"][0]["package_digest"] == package["package_digest"]
    assert recovered["package_custody"][0]["demo_points"] == 60
    initial = play_expedition(result["request"], [])
    assert initial["session_digest"] == result["genesis_digest"]
    assert initial["state"]["earned_rewards"] == []
    assert initial["state"]["episodes"]["s0"]["missions"]["points"] == 0
    design = build_expedition(result["request"])
    assert design["witness_state"]["status"] == "completed"
    assert invoke("author", author)[1] == result
    assert invoke("verify-author", {"request": author, "composition": result})[0] == 0
    changed = deepcopy(imported)
    changed["bindings"][0]["world"]["initial_coins"] += 1
    assert invoke("author", changed)[0] == 1
    forged = deepcopy(result)
    forged["package_custody"][0]["demo_points"] = 999
    rehash(forged, "author_digest")
    assert not verify_authoring(author, forged)
