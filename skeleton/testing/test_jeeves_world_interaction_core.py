"""Unified original-world interaction proof and cross-plane affordability."""
from __future__ import annotations

import pytest

from skeleton.jeeves.worlds.cast import approve_cast, propose_cast
from skeleton.jeeves.worlds.character_arcs import approve_arcs, propose_arcs
from skeleton.jeeves.worlds.dialogue_graph import approve_dialogue, propose_dialogue
from skeleton.jeeves.worlds.economy import approve_economy, propose_economy
from skeleton.jeeves.worlds.interaction_assembly import (
    compile_interaction, prove_interaction, replay_interaction,
)
from skeleton.jeeves.worlds.session import new_session, apply_choice
from skeleton.jeeves.worlds.world_canon import CanonError, propose


def fixture():
    world = propose(world_id="harbor", premise="Original harbor voyage.",
                    protagonist="Ari", region="Harbor", goal="Reach shore.")
    cast = approve_cast(propose_cast(
        world, npc_id="guide", npc_name="Mira",
        npc_line="Take the safe road."), world, "Reviewed original cast.")
    economy = approve_economy(propose_economy(
        world, prompt="Use one ration.", resource_id="rations",
        name="Rations", initial=1, capacity=3, choice_id="pursue_goal",
        cost=1, gain=0), world, "Reviewed original resource economy.")
    arcs = approve_arcs(propose_arcs(
        world, cast, prompt="Mira learns to trust.",
        actor="guide", desire="Guide Ari", starting_belief="Ari will fail.",
        resolved_belief="Ari is capable.", choice="pursue_goal",
        text="Mira trusts Ari."), world, cast, "Reviewed original arc.")
    dialogue = approve_dialogue(propose_dialogue(
        world, cast, prompt="Mira gives advice.",
        conversation_id="directions", actor="guide", scene="opening",
        text="Take the pier route?", response_id="yes", label="I will.",
        world_choice="pursue_goal"), world, cast, "Reviewed original dialogue.")
    return world, cast, economy, arcs, dialogue


def test_five_plane_proof_recipe_and_playable():
    sources = fixture()
    proof = prove_interaction(*sources)
    assert proof["dialogue_handoff_witnesses"] == {
        "directions:pursue_goal": []}
    manifest, playable = compile_interaction(*sources)
    assert manifest["source_digests"] == proof["source_digests"]
    assert "resources" in manifest
    assert "character_arcs" in manifest
    assert "dialogues" in manifest
    assert b"Content-Security-Policy" in playable
    assert b"script-src 'sha256-" in playable
    assert b"Take the pier route?" in playable
    assert b"Rations" in playable


def test_saved_session_replay_matches_all_planes():
    sources = fixture()
    world = sources[0]
    initial = new_session(world)
    start = replay_interaction(*sources, initial)
    assert start["available_conversations"] == ["directions"]
    assert start["economy"]["balances"] == {"rations": 1}
    final = apply_choice(initial, world, "pursue_goal")
    replay = replay_interaction(*sources, final)
    assert replay["ending"] == "Reach shore."
    assert replay["economy"]["balances"] == {"rations": 0}
    assert replay["arcs"]["completed"] == ["guide"]
    assert replay["available_conversations"] == []


def test_cross_plane_dialogue_must_remain_affordable():
    world, cast, economy, arcs, dialogue = fixture()
    world["choices"].append({
        "id": "spend", "from": "opening", "to": "opening",
        "label": "Spend ration", "requires": [], "grants": [],
    })
    # Rebuild all source leases against the new canonical world.
    from skeleton.jeeves.worlds.world_canon import digest
    cast["world_digest"] = digest(world)
    economy["world_digest"] = digest(world)
    economy["effects"] = [{
        "choice": "spend", "costs": {"rations": 1}, "gains": {},
    }]
    arcs["world_digest"] = digest(world)
    dialogue["world_digest"] = digest(world)
    for source in (economy, arcs, dialogue):
        source["cast_digest"] = digest(cast) if "cast_digest" in source else None
        if source.get("cast_digest") is None:
            source.pop("cast_digest", None)
    dialogue["conversations"][0]["nodes"][0]["responses"][0][
        "world_choice"] = "spend"
    # At the depleted reachable opening state, the only conversation
    # handoff is unaffordable, even though the world has an exit.
    with pytest.raises(CanonError, match="interaction_dialogue_unaffordable_state"):
        prove_interaction(world, cast, economy, arcs, dialogue)
