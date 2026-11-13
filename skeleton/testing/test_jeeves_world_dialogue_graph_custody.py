"""Dialogue source custody, review and exact-artifact tamper resistance."""
from __future__ import annotations

import copy
import os
import pytest

from skeleton.jeeves.worlds.cast import CastStore, approve_cast, propose_cast
from skeleton.jeeves.worlds.dialogue_graph import DialogueStore, propose_dialogue
from skeleton.jeeves.worlds.world_canon import CanonError, WorldStore, digest, propose


def fixture(tmp_path):
    world = propose(world_id="harbor", premise="Original harbor.",
                    protagonist="Ari", region="Harbor", goal="Reach shore.")
    WorldStore(tmp_path).publish(world, create=True)
    cast = approve_cast(propose_cast(
        world, npc_id="guide", npc_name="Mira",
        npc_line="The harbor is safe."), world, "Reviewed original cast.")
    CastStore(tmp_path).publish("harbor", cast, create=True)
    source = propose_dialogue(
        world, cast, prompt="Ask Mira for a route.",
        conversation_id="directions", actor="guide", scene="opening",
        text="Follow the lighthouse?", response_id="yes",
        label="I will.", world_choice="pursue_goal")
    return DialogueStore(tmp_path), world, cast, source


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored custody")
def test_review_compile_verify_and_tamper(tmp_path):
    store, world, cast, source = fixture(tmp_path)
    lease = store.publish("harbor", source, create=True)
    assert store.inspect("harbor")["proof"]["node_visits"] == 1
    with pytest.raises(CanonError, match="dialogue_approval_requires_review"):
        store.publish("harbor", {**source, "approved": True,
                                "review_note": "forged"}, expected_digest=lease)
    with pytest.raises(CanonError, match="dialogue_stale_edit"):
        store.approve("harbor", "0" * 64, "Reviewed.")
    approved = store.approve("harbor", lease, "Reviewed original dialogue.")
    receipt = store.compile("harbor", approved)
    assert store.verify("harbor") == receipt
    (tmp_path / "harbor.dialogue.playable.html").write_text("tampered")
    with pytest.raises(CanonError, match="dialogue_playable_mismatch"):
        store.verify("harbor")
    store.compile("harbor", approved)
    (tmp_path / "harbor.dialogue.engine.json").write_text("{}")
    with pytest.raises(CanonError, match="dialogue_recipe_mismatch"):
        store.verify("harbor")


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored custody")
def test_symlinked_artifact_and_stale_cast(tmp_path):
    store, world, cast, source = fixture(tmp_path)
    lease = store.publish("harbor", source, create=True)
    approved = store.approve("harbor", lease, "Reviewed.")
    store.compile("harbor", approved)
    path = tmp_path / "harbor.dialogue.playable.html"
    path.unlink()
    path.symlink_to(tmp_path / "harbor.json")
    with pytest.raises((CanonError, OSError)):
        store.verify("harbor")
    path.unlink()
    store.compile("harbor", approved)
    changed = copy.deepcopy(cast)
    changed["lines"][0]["text"] = "A newly revised original line."
    CastStore(tmp_path).publish("harbor", changed, expected_digest=digest(cast))
    with pytest.raises(CanonError, match="dialogue_source_lease_mismatch"):
        store.verify("harbor")


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored custody")
def test_editor_export_and_optimistic_edit(tmp_path):
    store, world, cast, source = fixture(tmp_path)
    lease = store.publish("harbor", source, create=True)
    page = store.editor("harbor", lease)
    html = (tmp_path / page["html_file"]).read_text()
    assert "Export unapproved JSON" in html
    assert "Content-Security-Policy" in html
    with pytest.raises(CanonError, match="dialogue_stale_edit"):
        store.editor("harbor", "0" * 64)
    changed = store.edit("harbor", lease, {
        "action": "upsert_node",
        "value": {"conversation": "directions", "node": {
            "id": "opening", "text": "Revised original dialogue.",
            "responses": [{
                "id": "yes", "label": "I will.",
                "next_node": None, "world_choice": "pursue_goal",
            }],
        }},
    })
    assert changed != lease
    assert store.inspect("harbor")["dialogue"]["approved"] is False
    with pytest.raises(CanonError, match="dialogue_stale_edit"):
        store.edit("harbor", lease, {
            "action": "remove_conversation",
            "value": {"id": "directions"}})
