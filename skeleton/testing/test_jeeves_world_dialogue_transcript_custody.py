"""Private transcript begin/append/commit/cancel with exact world leases."""
from __future__ import annotations

import json
import os
import pytest

from skeleton.jeeves.worlds.cast import CastStore, approve_cast, propose_cast
from skeleton.jeeves.worlds.dialogue_graph import DialogueStore, propose_dialogue
from skeleton.jeeves.worlds.dialogue_transcript import DialogueTranscriptStore
from skeleton.jeeves.worlds.session import SessionStore
from skeleton.jeeves.worlds.world_canon import CanonError, WorldStore, propose


def fixture(tmp_path):
    world = propose(world_id="harbor", premise="Original harbor.",
                    protagonist="Ari", region="Harbor", goal="Reach shore.")
    WorldStore(tmp_path).publish(world, create=True)
    cast = approve_cast(propose_cast(
        world, npc_id="guide", npc_name="Mira",
        npc_line="The pier is safe."), world, "Reviewed original cast.")
    CastStore(tmp_path).publish("harbor", cast, create=True)
    dialogue = DialogueStore(tmp_path)
    source = propose_dialogue(
        world, cast, prompt="Ask Mira for directions.",
        conversation_id="directions", actor="guide", scene="opening",
        text="Follow the pier?", response_id="yes",
        label="I will.", world_choice="pursue_goal")
    lease = dialogue.publish("harbor", source, create=True)
    approved = dialogue.approve("harbor", lease, "Reviewed dialogue.")
    session = SessionStore(tmp_path)
    start = session.create("harbor", "saveone")
    return DialogueTranscriptStore(tmp_path), session, approved, start


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored custody")
def test_resume_and_atomic_commit_with_receipt(tmp_path):
    store, session, approved, start = fixture(tmp_path)
    begun = store.begin(
        "harbor", "saveone", "directions",
        expected_session_digest=start["session_digest"],
        expected_dialogue_digest=approved)
    assert begun["transcript"]["revision"] == 0
    assert store.inspect("harbor", "saveone")["transcript_digest"] == (
        begun["transcript_digest"])
    with pytest.raises(CanonError, match="dialogue_transcript_incomplete"):
        store.commit("harbor", "saveone", begun["transcript_digest"])
    advanced = store.append(
        "harbor", "saveone", "yes", begun["transcript_digest"])
    assert advanced["replay"]["world_choice"] == "pursue_goal"
    with pytest.raises(CanonError, match="dialogue_transcript_already_complete"):
        store.append("harbor", "saveone", "yes", advanced["transcript_digest"])
    receipt = store.commit("harbor", "saveone", advanced["transcript_digest"])
    assert receipt["world_choice"] == "pursue_goal"
    assert session.read("harbor", "saveone")["choices"] == ["pursue_goal"]
    assert store.verify_receipt("harbor", "saveone") == receipt
    receipt_path = tmp_path / "harbor.saveone.dialogue.transcript.receipt.json"
    saved = receipt_path.read_text()
    forged = json.loads(saved)
    forged["chain_head"] = "0" * 64
    receipt_path.write_text(json.dumps(forged))
    with pytest.raises(CanonError, match="dialogue_transcript_receipt_chain_mismatch"):
        store.verify_receipt("harbor", "saveone")
    receipt_path.write_text(saved)
    assert store.verify_receipt("harbor", "saveone") == receipt
    with pytest.raises(CanonError, match="not_found"):
        store.inspect("harbor", "saveone")


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored custody")
def test_stale_lease_cancel_and_tamper(tmp_path):
    store, session, approved, start = fixture(tmp_path)
    with pytest.raises(CanonError, match="dialogue_transcript_stale_lease"):
        store.begin("harbor", "saveone", "directions",
                    expected_session_digest="0" * 64,
                    expected_dialogue_digest=approved)
    begun = store.begin(
        "harbor", "saveone", "directions",
        expected_session_digest=start["session_digest"],
        expected_dialogue_digest=approved)
    with pytest.raises(CanonError, match="dialogue_transcript_already_exists"):
        store.begin("harbor", "saveone", "directions",
                    expected_session_digest=start["session_digest"],
                    expected_dialogue_digest=approved)
    with pytest.raises(CanonError, match="dialogue_transcript_stale_edit"):
        store.append("harbor", "saveone", "yes", "0" * 64)
    path = tmp_path / "harbor.saveone.dialogue.transcript.json"
    data = json.loads(path.read_text())
    data["revision"] = 2
    path.write_text(json.dumps(data))
    with pytest.raises(CanonError, match="dialogue_transcript_revision_mismatch"):
        store.inspect("harbor", "saveone")
    path.write_text(json.dumps(begun["transcript"]))
    store.cancel("harbor", "saveone", begun["transcript_digest"])
    assert session.read("harbor", "saveone")["choices"] == []
    assert not path.exists()
