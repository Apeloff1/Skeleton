"""Original branching NPC dialogue graph and canonical handoff proof."""
from __future__ import annotations

import copy
import pytest

from skeleton.jeeves.worlds.cast import approve_cast, propose_cast
from skeleton.jeeves.worlds.dialogue_graph import (
    approve_dialogue, compile_dialogue, edit_dialogue,
    propose_dialogue, prove_dialogues, replay_dialogue,
)
from skeleton.jeeves.worlds.world_canon import CanonError, propose, digest


def fixture():
    world = propose(world_id="harbor", premise="Original harbor encounter.",
                    protagonist="Ari", region="Harbor", goal="Reach the pier.")
    cast = approve_cast(propose_cast(
        world, npc_id="guide", npc_name="Mira",
        npc_line="The pier is open."), world, "Reviewed original NPC.")
    source = propose_dialogue(
        world, cast, prompt="Ask Mira for directions.",
        conversation_id="directions", actor="guide", scene="opening",
        text="Will you take the safe road?", response_id="agree",
        label="Yes, show me the way.", world_choice="pursue_goal")
    return world, cast, source


def test_prompt_proof_replay_and_html_handoff():
    world, cast, source = fixture()
    assert source["approved"] is False
    proof = prove_dialogues(source, world, cast)
    assert proof["world_choice_witnesses"] == {
        "directions": {"pursue_goal": ["agree"]}}
    preview = replay_dialogue(source, world, cast, "directions", [])
    assert preview["world_choice"] is None
    replay = replay_dialogue(source, world, cast, "directions", ["agree"])
    assert replay["world_choice"] == "pursue_goal"
    with pytest.raises(CanonError, match="dialogue_review_required"):
        compile_dialogue(source, world, cast)
    approved = approve_dialogue(source, world, cast, "Reviewed original dialogue.")
    recipe, playable = compile_dialogue(approved, world, cast)
    assert recipe["world_digest"] == digest(world)
    assert b"Content-Security-Policy" in playable
    assert b"script-src 'sha256-" in playable
    assert b"Will you take the safe road?" in playable


def test_nested_dialogue_and_atomic_edit():
    world, cast, source = fixture()
    updated = edit_dialogue(source, world, cast, {
        "action": "batch", "value": [
            {"action": "upsert_node", "value": {
                "conversation": "directions", "node": {
                    "id": "followup", "text": "The tide is low.",
                    "responses": [{
                        "id": "agree", "label": "I understand.",
                        "next_node": None, "world_choice": "pursue_goal",
                    }],
                },
            }},
            {"action": "upsert_node", "value": {
                "conversation": "directions", "node": {
                    "id": "opening", "text": "Will you listen?",
                    "responses": [{
                        "id": "continue", "label": "Tell me more.",
                        "next_node": "followup", "world_choice": None,
                    }],
                },
            }},
        ],
    })
    assert updated["approved"] is False
    proof = prove_dialogues(updated, world, cast)
    assert proof["world_choice_witnesses"]["directions"] == {
        "pursue_goal": ["continue", "agree"]}
    replay = replay_dialogue(updated, world, cast, "directions",
                             ["continue", "agree"])
    assert replay["world_choice"] == "pursue_goal"
    with pytest.raises(CanonError, match="dialogue_after_handoff"):
        replay_dialogue(updated, world, cast, "directions",
                        ["continue", "agree", "agree"])


@pytest.mark.parametrize("mutate,code", [
    (lambda d: d.update(world_digest="0" * 64),
     "dialogue_source_lease_mismatch"),
    (lambda d: d.update(cast_digest="0" * 64),
     "dialogue_source_lease_mismatch"),
    (lambda d: d["conversations"][0].update(actor="forged"),
     "dialogue_actor_absent"),
    (lambda d: d["conversations"][0]["nodes"][0]["responses"][0].update(
        world_choice="forged"), "dialogue_invalid_world_choice"),
    (lambda d: d["conversations"][0]["nodes"][0]["responses"][0].update(
        next_node="opening", world_choice=None), "dialogue_cycle_or_depth"),
    (lambda d: d["conversations"][0]["nodes"][0]["responses"][0].update(
        next_node=None, world_choice=None), "dialogue_invalid_response_target"),
    (lambda d: d["conversations"][0]["nodes"][0]["responses"].append(
        copy.deepcopy(d["conversations"][0]["nodes"][0]["responses"][0])),
     "dialogue_duplicate_response"),
    (lambda d: d.update(approved="yes"), "dialogue_invalid_approval"),
    (lambda d: d.update(review_note="forged"), "dialogue_unreviewed_note"),
])
def test_invalid_graphs_fail_closed(mutate, code):
    world, cast, source = fixture()
    mutate(source)
    with pytest.raises(CanonError, match=code):
        prove_dialogues(source, world, cast)


def test_invalid_response_trace_rejected():
    world, cast, source = fixture()
    with pytest.raises(CanonError, match="dialogue_invalid_transition"):
        replay_dialogue(source, world, cast, "directions", ["forged"])
    with pytest.raises(CanonError, match="dialogue_unknown_conversation"):
        replay_dialogue(source, world, cast, "missing", [])
    with pytest.raises(CanonError, match="dialogue_invalid_trace"):
        replay_dialogue(source, world, cast, "directions", ["agree"] * 129)
