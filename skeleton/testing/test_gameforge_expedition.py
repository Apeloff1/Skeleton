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
