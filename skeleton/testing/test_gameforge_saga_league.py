"""Recovered league progression and exact-history advanced recovery tests."""
from copy import deepcopy
import sqlite3

import pytest

from skeleton.app.gameforge_saga import build_saga, play_saga, resume_saga, verify_saga
from skeleton.app.gameforge_saga_author import SCHEMA as AUTHOR_SCHEMA, author_saga
from skeleton.app.gameforge_saga_board import board, compare, episode_evidence, recover, verify_derived
from skeleton.app.gameforge_saga_league import solve_witness, validate_rules
from skeleton.app.gameforge_saga_owners import admit_episode, replay_episode, summarize, candidate_actions
from skeleton.app.gameforge_saga_search import search
from skeleton.app.gameforge_saga_store import SagaStore
from skeleton.app.gameforge_expedition_store import ExpeditionStore
from skeleton.app.gameforge_campaign_store import CampaignStore
from skeleton.game.gameplay.harbor_crafting_convoy_league_quests import verify_league_quest_report
from skeleton.testing.test_gameforge_saga import (
    authored, design, fixture, first_episode, resolve_index, invoke,
)


@pytest.fixture(scope="module")
def league_episode():
    world = fixture()
    rules = validate_rules(world, {"league": fixture("_convoy_league"),
                                   "quests": fixture("_convoy_league_quests")})
    witness, proof = solve_witness(world, rules)
    assert proof["complete"]
    return admit_episode({"objective": "s3", "kind": "convoy_league",
                          "source": world, "rules": rules, "witness": witness})


@pytest.fixture(scope="module")
def championship(authored, league_episode):
    source = deepcopy(authored)
    source["episodes"].append(league_episode)
    return source


def test_league_owner_preserves_explicit_round_order_and_earned_resets(league_episode):
    ep = league_episode
    actions = ep["witness"]
    first = actions[0]["round"]
    split = next(i for i, action in enumerate(actions) if action["round"] != first)
    genesis = summarize(ep, replay_episode(ep, []))
    assert genesis["score"] == genesis["points"] == 0
    assert genesis["round_tick"] == 0 and not genesis["gate_satisfied"]
    with pytest.raises(ValueError):
        replay_episode(ep, [actions[split]])
    with pytest.raises(ValueError):
        replay_episode(ep, actions[:1] + actions[split:split+1])
    before = summarize(ep, replay_episode(ep, actions[:split]))
    assert before["rounds_played"] == 1 and before["state"]["tick"] == split
    assert before["round_tick"] == 0 and before["state"]["inventory"] == {}
    assert before["next_round"] == actions[split]["round"]
    legal = candidate_actions(ep, replay_episode(ep, actions[:split]), before)
    assert actions[split] in legal
    assert all(row["round"] == before["next_round"] for row in legal)
    final_report = replay_episode(ep, actions)
    final = summarize(ep, final_report)
    assert final["championship"] and final["gate_satisfied"] and final["terminal"]
    assert final["state"]["tick"] == len(actions)
    assert final["rounds_played"] == final["rounds_total"] == 2
    assert final["points"] == 38 and final["score"] >= final["target_score"]
    assert not final["remaining"]
    assert verify_league_quest_report(final_report, require_all=True)["complete"]


def test_league_is_last_generated_objective_gate(championship):
    design = build_saga(championship)
    witness = design["witness"]
    start, end = first_episode(witness, "s3"), resolve_index(witness, "s3")
    prior = play_saga(championship, witness[:start])
    assert not prior["state"]["episodes"]["s3"]["gate_satisfied"]
    assert witness[end] not in prior["state"]["legal_actions"]
    with pytest.raises(ValueError, match="outcome"):
        resume_saga(championship, prior, [witness[end]])
    complete = resume_saga(championship, prior, witness[start:])
    assert complete["state"]["status"] == "completed"
    assert complete["state"]["episodes"]["s3"]["championship"]
    assert verify_saga(championship, complete, session=True)
    evidence = episode_evidence(championship, complete, "s3")
    assert verify_league_quest_report(evidence["report"], require_all=True)["points"] == 38
    assert verify_derived(championship, complete, evidence, kind="evidence")
    comparison = compare(championship, prior, complete)
    assert comparison["advanced_outcomes"]["s3"]["points_delta"] == 38
    assert comparison["advanced_outcomes"]["s3"]["rounds_played_delta"] == 2


def test_exact_owner_search_can_finish_near_terminal_survey(authored):
    ep = admit_episode(authored["episodes"][0])
    prior = ep["witness"][:-1]
    result = search(ep, prior, max_states=32, max_attempts=128)
    assert result["status"] == "completion_witness"
    assert result["additional"]
    final = summarize(ep, replay_episode(ep, prior + result["additional"]))
    assert final["gate_satisfied"] and final["report_digest"] == result["completion_report_digest"]
    assert result["attempts"] <= 128 and result["retained_states"] <= 32
    assert search(ep, prior, max_states=32, max_attempts=128) == result


def test_search_ceiling_reports_exhaustion_not_impossibility(authored):
    ep = admit_episode(authored["episodes"][0])
    result = search(ep, [], max_states=1, max_attempts=1)
    assert result["status"] == "budget_exhausted"
    assert result["additional"] == [] and result["completion_report_digest"] is None
    assert result["attempts"] == 1 and result["retained_states"] == 1
    with pytest.raises(ValueError):
        search(ep, [], max_states=True)
    with pytest.raises(ValueError):
        search(ep, [], max_attempts=513)


def test_authoring_can_recover_canonical_league_solver(championship):
    request = {"schema": AUTHOR_SCHEMA, "expedition": championship["expedition"],
               "bindings": deepcopy(championship["episodes"])}
    request["bindings"][-1].pop("witness")
    composition = author_saga(request)
    assert composition["owner_custody"][-1]["witness_origin"] == "canonical_solver"
    assert composition["request"]["episodes"][-1]["kind"] == "convoy_league"
    initial = play_saga(composition["request"], [])
    assert initial["state"]["episodes"]["s3"]["score"] == 0
    assert initial["state"]["episodes"]["s3"]["state"]["tick"] == 0
    assert initial["session_digest"] == composition["genesis_digest"]


def test_fixed_journal_schema_initializes_all_three_namespaces(tmp_path):
    path = tmp_path / "namespaces.sqlite"
    with sqlite3.connect(path) as db:
        for cls in (SagaStore, ExpeditionStore, CampaignStore):
            cls(db)
            cls(db, initialize=False)
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert tables == {f"gf_{namespace}_{kind}_v1"
                          for namespace in ("campaign", "expedition", "saga")
                          for kind in ("slots", "revisions")}
        for namespace in ("campaign", "expedition", "saga"):
            foreign = db.execute(f"PRAGMA foreign_key_list(gf_{namespace}_revisions_v1)").fetchall()
            assert foreign[0][2] == f"gf_{namespace}_slots_v1"


def test_search_budget_fenced_in_recovery_receipt(authored):
    initial = play_saga(authored, [])
    result = recover(authored, initial, advanced_states=5, advanced_attempts=30)
    assert result["advanced_states"] == 5 and result["advanced_attempts"] == 30
    assert result["status"] == "completion_witness"
    assert verify_derived(authored, initial, result, kind="recovery")
    assert invoke("assist", {"request": authored, "receipt": initial,
                             "advanced_states": 5, "advanced_attempts": 30})[1] == result
    assert invoke("assist", {"request": authored, "receipt": initial,
                             "advanced_states": 129})[0] == 1
