"""Unified five-source custody, optimistic compile and tamper rejection."""
from __future__ import annotations

import os
import pytest

from skeleton.jeeves.worlds.cast import CastStore
from skeleton.jeeves.worlds.character_arcs import ArcStore
from skeleton.jeeves.worlds.dialogue_graph import DialogueStore
from skeleton.jeeves.worlds.economy import EconomyStore
from skeleton.jeeves.worlds.interaction_assembly import InteractionStore
from skeleton.jeeves.worlds.session import SessionStore
from skeleton.jeeves.worlds.world_canon import CanonError, WorldStore
from skeleton.testing.test_jeeves_world_interaction_core import fixture


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored custody")
def test_reviewed_compile_verify_and_player(tmp_path):
    world, cast, economy, arcs, dialogue = fixture()
    WorldStore(tmp_path).publish(world, create=True)
    CastStore(tmp_path).publish("harbor", cast, create=True)
    EconomyStore(tmp_path).publish("harbor", {
        **economy, "approved": False, "review_note": ""}, create=True)
    e = EconomyStore(tmp_path)
    e.approve("harbor", e.inspect("harbor")["proof"]["economy_digest"], "Reviewed.")
    ArcStore(tmp_path).publish("harbor", {
        **arcs, "approved": False, "review_note": ""}, create=True)
    a = ArcStore(tmp_path)
    a.approve("harbor", a.inspect("harbor")["proof"]["arcs_digest"], "Reviewed.")
    DialogueStore(tmp_path).publish("harbor", {
        **dialogue, "approved": False, "review_note": ""}, create=True)
    d = DialogueStore(tmp_path)
    d.approve("harbor", d.inspect("harbor")["proof"]["dialogue_digest"], "Reviewed.")
    store = InteractionStore(tmp_path)
    proof = store.inspect("harbor")["proof"]
    with pytest.raises(CanonError, match="interaction_stale_source"):
        store.compile("harbor", {**proof["source_digests"], "world": "0" * 64})
    receipt = store.compile("harbor", proof["source_digests"])
    assert store.verify("harbor") == receipt
    SessionStore(tmp_path).create("harbor", "saveone")
    assert store.player("harbor", "saveone")["player"][
        "available_conversations"] == ["directions"]
    (tmp_path / "harbor.interaction.playable.html").write_text("tampered")
    with pytest.raises(CanonError, match="interaction_playable_mismatch"):
        store.verify("harbor")
    store.compile("harbor", proof["source_digests"])
    (tmp_path / "harbor.interaction.engine.json").write_text("{}")
    with pytest.raises(CanonError, match="interaction_recipe_mismatch"):
        store.verify("harbor")


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored custody")
def test_symlinked_output_rejected(tmp_path):
    world, cast, economy, arcs, dialogue = fixture()
    WorldStore(tmp_path).publish(world, create=True)
    CastStore(tmp_path).publish("harbor", cast, create=True)
    e = EconomyStore(tmp_path)
    lease = e.publish("harbor", {**economy, "approved": False,
                                 "review_note": ""}, create=True)
    e.approve("harbor", lease, "Reviewed.")
    a = ArcStore(tmp_path)
    lease = a.publish("harbor", {**arcs, "approved": False,
                                 "review_note": ""}, create=True)
    a.approve("harbor", lease, "Reviewed.")
    d = DialogueStore(tmp_path)
    lease = d.publish("harbor", {**dialogue, "approved": False,
                                 "review_note": ""}, create=True)
    d.approve("harbor", lease, "Reviewed.")
    store = InteractionStore(tmp_path)
    proof = store.inspect("harbor")["proof"]
    store.compile("harbor", proof["source_digests"])
    path = tmp_path / "harbor.interaction.playable.html"
    path.unlink()
    path.symlink_to(tmp_path / "harbor.json")
    with pytest.raises((CanonError, OSError)):
        store.verify("harbor")
