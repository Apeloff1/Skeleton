"""Recovered season and order-chain contracts through the real owner adapters."""
from copy import deepcopy

import pytest

from skeleton.app.gameforge_saga_rounds import solve_delivery, validate_rules
from skeleton.app.gameforge_saga_owners import (
    admit_episode, candidate_actions, replay_episode, report_actions, summarize,
)
from skeleton.app.gameforge_saga_search import search
from skeleton.game.gameplay import harbor_crafting as harbor
from skeleton.game.gameplay.harbor_crafting_season import verify_season_record
from skeleton.game.gameplay.harbor_crafting_contracts import verify_save
from skeleton.testing.test_gameforge_saga import authored, fixture
from skeleton.app.gameforge_saga import build_saga, play_saga, verify_saga
from skeleton.app.gameforge_saga_author import SCHEMA as AUTHOR_SCHEMA, author_saga


def season_episode():
    world = fixture()
    rules = {"season": fixture("_season"), "minimum_points": 20}
    witness = []
    for row in rules["season"]["rounds"]:
        actions = harbor.demo_actions()
        actions[-1]["choice"] = row["course"]["choice"]
        witness.extend({"op": "round", "round": row["id"], "action": action}
                       for action in actions)
    return admit_episode({"objective": "s1", "kind": "timed_season", "source": world,
                          "rules": rules, "witness": witness})


def delivery_episode():
    world = fixture()
    rules = validate_rules("delivery_chain", world, {"board": fixture("_contracts")})
    witness, custody = solve_delivery(world, rules)
    assert len(custody) == 2 and all(len(value) == 64 for value in custody)
    return admit_episode({"objective": "s2", "kind": "delivery_chain",
                          "source": world, "rules": rules, "witness": witness})


@pytest.mark.parametrize("factory", [season_episode, delivery_episode])
def test_round_identity_and_partial_state_cannot_award_completion(factory):
    episode = factory()
    witness = episode["witness"]
    first = witness[0]["round"]
    split = next(i for i, event in enumerate(witness) if event["round"] != first)
    genesis = summarize(episode, replay_episode(episode, []))
    assert genesis["rounds_played"] == 0 and genesis["score"] == 0
    assert genesis["state"]["inventory"] == {}
    with pytest.raises(ValueError):
        replay_episode(episode, [witness[split]])
    with pytest.raises(ValueError):
        replay_episode(episode, witness[:1] + [witness[split]])
    half = replay_episode(episode, witness[:split])
    view = summarize(episode, half)
    assert view["rounds_played"] == 1 and view["round_tick"] == 0
    assert view["state"]["tick"] == split and view["state"]["inventory"] == {}
    assert view["next_round"] == witness[split]["round"]
    assert not view["gate_satisfied"]
    assert all(a["round"] == view["next_round"] for a in candidate_actions(episode, half, view))
    finished = replay_episode(episode, witness)
    final = summarize(episode, finished)
    assert report_actions(episode, finished) == witness
    assert final["gate_satisfied"] and final["terminal"]
    assert final["rounds_played"] == 2 and final["state"]["tick"] == len(witness)
    assert final["remaining"] == []


def test_season_awards_actual_medals_and_distinct_runs():
    episode = season_episode()
    result = replay_episode(episode, episode["witness"])
    assert verify_season_record(result["record"])["total_points"] == 20
    assert [row["report"]["medal"] for row in result["record"]["results"]] == ["gold", "gold"]
    split = next(i for i, event in enumerate(episode["witness"])
                 if event["round"] != episode["witness"][0]["round"])
    wrong = deepcopy(episode["witness"][:split])
    wrong[-1]["action"]["choice"] = "shelter"
    report = replay_episode(episode, wrong)
    status = summarize(episode, report)
    assert status["failed"] and not status["gate_satisfied"] and status["rounds_played"] == 0
    with pytest.raises(ValueError):
        replay_episode(episode, wrong + episode["witness"][split:split+1])


def test_delivery_chain_uses_original_earned_contract_owner():
    episode = delivery_episode()
    report = replay_episode(episode, episode["witness"])
    assert verify_save(report["record"])["complete"]
    assert report["record"]["results"][0]["id"] == "beacon_supply"
    assert report["record"]["results"][1]["id"] == "shelter_relief"
    result = search(episode, episode["witness"][:-1], max_states=16, max_attempts=64)
    assert result["status"] == "completion_witness"
    assert summarize(episode, replay_episode(
        episode, episode["witness"][:-1] + result["additional"]))["gate_satisfied"]


def test_new_round_owners_integrate_with_generated_saga(authored):
    source = deepcopy(authored)
    source["episodes"] = [season_episode(), delivery_episode()]
    design = build_saga(source)
    initial = play_saga(source, [])
    assert initial["state"]["earned_rewards"] == []
    assert initial["state"]["episodes"]["s1"]["points"] == 0
    finished = play_saga(source, design["witness"])
    assert finished["state"]["status"] == "completed"
    assert verify_saga(source, finished, session=True)
    assert finished["state"]["episodes"]["s1"]["points"] == 20
    assert finished["state"]["episodes"]["s2"]["rounds_played"] == 2


def test_delivery_authoring_uses_existing_solver_without_awarding_genesis(authored):
    ep = delivery_episode()
    ep.pop("witness")
    request = {"schema": AUTHOR_SCHEMA, "expedition": authored["expedition"], "bindings": [ep]}
    result = author_saga(request)
    assert result["owner_custody"][0]["witness_origin"] == "canonical_solver"
    assert len(result["owner_custody"][0]["solver_digests"]) == 2
    initial = play_saga(result["request"], [])
    assert initial["session_digest"] == result["genesis_digest"]
    assert initial["state"]["episodes"]["s2"]["rounds_played"] == 0
