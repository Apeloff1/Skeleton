"""Hash-chained dialogue transcript validation and deterministic replay."""
from __future__ import annotations

import pytest

from skeleton.jeeves.worlds.cast import approve_cast, propose_cast
from skeleton.jeeves.worlds.dialogue_graph import approve_dialogue, propose_dialogue
from skeleton.jeeves.worlds.dialogue_transcript import (
    SCHEMA, _chain, validate_transcript,
)
from skeleton.jeeves.worlds.session import new_session
from skeleton.jeeves.worlds.world_canon import CanonError, digest, propose


def fixture():
    world = propose(world_id="harbor", premise="Original harbor.",
                    protagonist="Ari", region="Harbor", goal="Reach shore.")
    cast = approve_cast(propose_cast(
        world, npc_id="guide", npc_name="Mira",
        npc_line="The pier is safe."), world, "Reviewed cast.")
    dialogue = approve_dialogue(propose_dialogue(
        world, cast, prompt="Ask Mira for directions.",
        conversation_id="directions", actor="guide", scene="opening",
        text="Follow the pier?", response_id="yes",
        label="I will.", world_choice="pursue_goal"),
        world, cast, "Reviewed dialogue.")
    session = new_session(world)
    data = {
        "schema": SCHEMA, "world_id": world["id"],
        "world_digest": digest(world), "cast_digest": digest(cast),
        "dialogue_digest": digest(dialogue),
        "session_digest": digest(session), "slot": "saveone",
        "conversation": "directions", "responses": ["yes"],
        "chain": [], "revision": 1,
    }
    data["chain"] = _chain(data)
    return world, cast, dialogue, session, data


def test_source_bound_chain_and_replay():
    world, cast, dialogue, session, data = fixture()
    assert validate_transcript(data, world, cast, dialogue, session) == data
    assert len(data["chain"]) == 1
    assert len(data["chain"][0]["sha256"]) == 64
    assert data["chain"][0]["response"] == "yes"


@pytest.mark.parametrize("mutate,code", [
    (lambda d: d.update(world_digest="0" * 64),
     "dialogue_transcript_stale_source"),
    (lambda d: d.update(dialogue_digest="0" * 64),
     "dialogue_transcript_stale_source"),
    (lambda d: d.update(revision=2),
     "dialogue_transcript_revision_mismatch"),
    (lambda d: d["chain"][0].update(sha256="0" * 64),
     "dialogue_transcript_chain_mismatch"),
    (lambda d: d["responses"].append("forged"),
     "dialogue_transcript_revision_mismatch"),
    (lambda d: d.update(slot="../../escape"), "invalid_identifier"),
])
def test_forged_transcripts_fail_closed(mutate, code):
    world, cast, dialogue, session, data = fixture()
    mutate(data)
    with pytest.raises(CanonError, match=code):
        validate_transcript(data, world, cast, dialogue, session)
