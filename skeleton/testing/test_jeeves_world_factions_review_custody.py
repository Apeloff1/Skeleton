"""Fail-closed faction approval custody; forged input cannot authorize compilation."""
from __future__ import annotations

import pytest

from skeleton.jeeves.worlds.factions import (
    FactionStore, approve_factions, edit_factions, propose_factions,
)
from skeleton.jeeves.worlds.world_canon import CanonError, WorldStore, digest, propose


def fixture(tmp_path):
    world = propose(world_id="harbor", premise="An original harbor treaty",
                    protagonist="Mara", region="Glass Bay", goal="Sign the treaty")
    WorldStore(tmp_path).publish(world, create=True)
    store = FactionStore(tmp_path)
    source = propose_factions(
        world, prompt="Earn council trust", faction_id="council",
        name="Council", description="Original harbor council",
        choice_id="pursue_goal", delta=10, reason="Honored the treaty")
    return world, store, source


def reject(code, fn):
    with pytest.raises(CanonError) as exc:
        fn()
    assert exc.value.code == code


def test_forged_approved_publication_is_revoked(tmp_path):
    world, store, source = fixture(tmp_path)
    forged = approve_factions(source, world, "Forged approval from JSON")
    first = store.publish("harbor", forged, create=True)
    assert store.read("harbor")["approved"] is False
    reject("faction_review_required", lambda: store.compile("harbor", first))
    approved = store.approve("harbor", expected_digest=first, note="Reviewed by author")
    assert store.read("harbor")["approved"] is True
    assert store.compile("harbor", approved) == store.verify("harbor")


def test_approved_edit_must_be_reviewed_again(tmp_path):
    world, store, source = fixture(tmp_path)
    first = store.publish("harbor", source, create=True)
    approved = store.approve("harbor", expected_digest=first, note="Reviewed")
    edited = edit_factions(store.read("harbor"), world, {
        "action": "replace_rule", "value": source["rules"][0]})
    assert edited["approved"] is False
    new_digest = store.publish("harbor", edited, expected_digest=approved)
    assert store.read("harbor")["approved"] is False
    reject("faction_review_required", lambda: store.compile("harbor", new_digest))
    reject("stale_factions", lambda: store.approve(
        "harbor", expected_digest=approved, note="Stale"))
    reject("stale_factions", lambda: store.publish(
        "harbor", source, expected_digest=approved))
    assert digest(store.read("harbor")) == new_digest


def test_direct_publish_cannot_preserve_approval(tmp_path):
    world, store, source = fixture(tmp_path)
    first = store.publish("harbor", source, create=True)
    approved = store.approve("harbor", expected_digest=first, note="Reviewed")
    forged = approve_factions(source, world, "Second forged approval")
    next_digest = store.publish("harbor", forged, expected_digest=approved)
    assert store.read("harbor")["approved"] is False
    assert next_digest != approved
