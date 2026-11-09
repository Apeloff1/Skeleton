"""Original character arcs: closure, authored beats and fail-closed replay."""
from __future__ import annotations

import copy
import pytest

from skeleton.jeeves.worlds.cast import approve_cast, propose_cast
from skeleton.jeeves.worlds.character_arcs import (
    approve_arcs, compile_arcs, edit_arcs, propose_arcs,
    prove_arcs, replay_arcs,
)
from skeleton.jeeves.worlds.world_canon import CanonError, propose, digest


def fixture():
    world = propose(world_id="harbor", premise="Original harbor journey.",
                    protagonist="Ari", region="Harbor", goal="Find the pier.")
    cast = propose_cast(world, npc_id="guide", npc_name="Mira",
                        npc_line="I know a path to the pier.")
    cast = approve_cast(cast, world, "Reviewed original cast.")
    arcs = propose_arcs(
        world, cast, prompt="Mira learns to trust travelers.",
        actor="guide", desire="Guide travelers safely.",
        starting_belief="Outsiders cannot be trusted.",
        resolved_belief="Trust can be earned.",
        choice="pursue_goal", text="Mira trusts Ari at the pier.")
    return world, cast, arcs


def test_original_prompt_ending_closure_and_replay():
    world, cast, arcs = fixture()
    assert arcs["approved"] is False
    proof = prove_arcs(arcs, world, cast)
    assert proof["ending_witnesses"] == {"resolution": ["pursue_goal"]}
    assert proof["exercised_beats"] == ["resolution"]
    before = replay_arcs(arcs, world, cast, [])
    assert before["beliefs"]["guide"] == "Outsiders cannot be trusted."
    after = replay_arcs(arcs, world, cast, ["pursue_goal"])
    assert after["beliefs"]["guide"] == "Trust can be earned."
    assert after["completed"] == ["guide"]
    assert after["ending"] == "Find the pier."
    with pytest.raises(CanonError, match="arcs_review_required"):
        compile_arcs(arcs, world, cast)
    approved = approve_arcs(arcs, world, cast, "Reviewed original character arc.")
    recipe, playable = compile_arcs(approved, world, cast)
    assert recipe["world_digest"] == digest(world)
    assert recipe["cast_digest"] == digest(cast)
    assert "script-src 'sha256-" in playable.decode()
    assert "Mira trusts Ari" in playable.decode()


@pytest.mark.parametrize("mutate,code", [
    (lambda a: a.update(world_digest="0" * 64),
     "arcs_source_lease_mismatch"),
    (lambda a: a.update(cast_digest="0" * 64),
     "arcs_source_lease_mismatch"),
    (lambda a: a["arcs"][0].update(actor="unknown"), "arcs_invalid_actor"),
    (lambda a: a["arcs"][0].update(beats=[]), "arcs_missing_resolution"),
    (lambda a: a["arcs"][0]["beats"][0].update(choice="unknown"),
     "arcs_unknown_choice"),
    (lambda a: a["arcs"][0]["beats"][0].update(stage="unreviewed"),
     "arcs_invalid_stage"),
    (lambda a: a["arcs"][0]["beats"].append(
        copy.deepcopy(a["arcs"][0]["beats"][0])), "arcs_duplicate_beat"),
    (lambda a: a.update(approved="yes"), "arcs_invalid_approval"),
    (lambda a: a.update(review_note="forged"), "arcs_unreviewed_note"),
])
def test_invalid_original_arcs_refused(mutate, code):
    world, cast, arcs = fixture()
    mutate(arcs)
    with pytest.raises(CanonError, match=code):
        prove_arcs(arcs, world, cast)


def test_every_reachable_ending_path_requires_resolution():
    world, cast, arcs = fixture()
    world["choices"].append({
        "id": "detour", "from": "opening", "to": "resolution",
        "label": "Leave Mira behind", "requires": [], "grants": [],
    })
    arcs["world_digest"] = digest(world)
    cast["world_digest"] = digest(world)
    arcs["cast_digest"] = digest(cast)
    with pytest.raises(CanonError, match="arcs_unclosed_ending"):
        prove_arcs(arcs, world, cast)


def test_typed_edits_reset_approval():
    world, cast, arcs = fixture()
    approved = approve_arcs(arcs, world, cast, "Reviewed.")
    updated = edit_arcs(approved, world, cast, {
        "action": "upsert_beat",
        "value": {"actor": "guide", "beat": {
            "id": "turn", "choice": "pursue_goal",
            "stage": "turn", "text": "Mira reconsiders her fear.",
        }},
    })
    assert updated["approved"] is False
    assert updated["review_note"] == ""
    assert prove_arcs(updated, world, cast)["exercised_beats"] == [
        "resolution", "turn"]
    with pytest.raises(CanonError, match="arcs_missing_resolution"):
        edit_arcs(arcs, world, cast, {
            "action": "remove_beat",
            "value": {"actor": "guide", "beat_id": "resolution"}})
    with pytest.raises(CanonError, match="arcs_unknown_actor"):
        edit_arcs(arcs, world, cast, {
            "action": "upsert_beat",
            "value": {"actor": "forged", "beat": {
                "id": "turn", "choice": "pursue_goal",
                "stage": "turn", "text": "A forged beat.",
            }},
        })
