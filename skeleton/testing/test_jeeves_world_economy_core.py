"""Resource-economy state proof, adversarial bounds and typed review."""
from __future__ import annotations

import copy
import pytest

from skeleton.jeeves.worlds.economy import (
    approve_economy, edit_economy, propose_economy, prove_economy,
    replay_economy, compile_economy,
)
from skeleton.jeeves.worlds.world_canon import CanonError, propose, digest


def fixture():
    world = propose(world_id="harbor", premise="An original supply voyage.",
                    protagonist="Ari", region="Harbor", goal="Reach shore.")
    source = propose_economy(
        world, prompt="Spend one ration on the passage.", resource_id="rations",
        name="Rations", initial=2, capacity=5, choice_id="pursue_goal",
        cost=1, gain=0)
    return world, source


def test_typed_prompt_and_replay_witness():
    world, source = fixture()
    assert source["approved"] is False
    proof = prove_economy(source, world)
    assert proof["ending_witnesses"] == {"resolution": ["pursue_goal"]}
    assert proof["states_explored"] == 2
    replay = replay_economy(source, world, ["pursue_goal"])
    assert replay["balances"] == {"rations": 1}
    assert replay["ending"] is True
    assert replay["trace"][0]["scene"] == "resolution"
    with pytest.raises(CanonError, match="economy_review_required"):
        compile_economy(source, world)
    approved = approve_economy(source, world, "Original economy reviewed.")
    recipe, playable = compile_economy(approved, world)
    assert recipe["effects"] == approved["effects"]
    assert recipe["world_digest"] == digest(world)
    assert b"Content-Security-Policy" in playable
    assert b"script-src 'sha256-" in playable
    assert b"Rations" in playable


@pytest.mark.parametrize("mutate,code", [
    (lambda d: d["resources"].append(copy.deepcopy(d["resources"][0])),
     "economy_duplicate_resource"),
    (lambda d: d["resources"][0].update(initial=-1),
     "economy_invalid_quantity"),
    (lambda d: d["resources"][0].update(initial=True),
     "economy_invalid_quantity"),
    (lambda d: d["resources"][0].update(capacity=0),
     "economy_invalid_capacity"),
    (lambda d: d["resources"][0].update(initial=6),
     "economy_invalid_capacity"),
    (lambda d: d["effects"][0].update(choice="forged"),
     "economy_invalid_choice_effect"),
    (lambda d: d["effects"][0].update(costs={"forged": 1}),
     "economy_invalid_resource_map"),
    (lambda d: d["effects"][0].update(costs={"rations": 3}),
     "economy_reachable_dead_end"),
    (lambda d: d["effects"][0].update(gains={"rations": 5}),
     "economy_reachable_dead_end"),
    (lambda d: d.update(approved="yes"), "economy_invalid_approval"),
    (lambda d: d.update(review_note="forged"), "economy_unreviewed_note"),
    (lambda d: d.update(world_digest="0" * 64),
     "economy_world_lease_mismatch"),
])
def test_fail_closed_source_validation(mutate, code):
    world, source = fixture()
    mutate(source)
    with pytest.raises(CanonError, match=code):
        prove_economy(source, world)


def test_edits_reset_review_and_reprove():
    world, source = fixture()
    approved = approve_economy(source, world, "Reviewed.")
    updated = edit_economy(approved, world, {
        "action": "upsert_effect",
        "value": {"choice": "pursue_goal",
                  "costs": {"rations": 2}, "gains": {}},
    })
    assert updated["approved"] is False
    assert updated["review_note"] == ""
    assert replay_economy(updated, world, ["pursue_goal"])["balances"] == {
        "rations": 0}
    with pytest.raises(CanonError, match="economy_invalid_resource_map"):
        edit_economy(source, world, {
            "action": "remove_resource", "value": {"id": "rations"}})
    with pytest.raises(CanonError, match="economy_unknown_effect"):
        edit_economy(source, world, {
            "action": "remove_effect", "value": {"choice": "not_present"}})


def test_unaffordable_replay_refused_and_trace_bounded():
    world, source = fixture()
    with pytest.raises(CanonError, match="economy_invalid_transition"):
        replay_economy(source, world, ["not_a_choice"])
    with pytest.raises(CanonError, match="economy_invalid_transition"):
        replay_economy(source, world, ["pursue_goal", "pursue_goal"])
    with pytest.raises(CanonError, match="economy_invalid_trace"):
        replay_economy(source, world, ["pursue_goal"] * 513)
    source["resources"][0]["initial"] = 0
    with pytest.raises(CanonError, match="economy_unaffordable_transition"):
        replay_economy(source, world, ["pursue_goal"])
