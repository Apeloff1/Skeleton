"""Descriptor-anchored economy publication, tamper rejection and source custody."""
from __future__ import annotations

import copy
import os
import pytest

from skeleton.jeeves.worlds.economy import EconomyStore, propose_economy
from skeleton.jeeves.worlds.world_canon import CanonError, WorldStore, digest, propose


def setup(tmp_path):
    world = propose(world_id="harbor", premise="Original voyage.",
                    protagonist="Ari", region="Harbor", goal="Return safely.")
    WorldStore(tmp_path).publish(world, create=True)
    store = EconomyStore(tmp_path)
    source = propose_economy(
        world, prompt="Spend a ration on the journey.", resource_id="rations",
        name="Rations", initial=1, capacity=3, choice_id="pursue_goal",
        cost=1, gain=0)
    return world, store, source


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored custody")
def test_create_review_compile_verify_and_tamper(tmp_path):
    world, store, source = setup(tmp_path)
    lease = store.publish("harbor", source, create=True)
    assert store.inspect("harbor")["proof"]["states_explored"] == 2
    with pytest.raises(CanonError, match="economy_approval_requires_review"):
        store.publish("harbor", {**source, "approved": True,
                                "review_note": "forged"}, expected_digest=lease)
    with pytest.raises(CanonError, match="economy_stale_edit"):
        store.publish("harbor", source, expected_digest="0" * 64)
    approved = store.approve("harbor", lease, "Reviewed original supplies.")
    receipt = store.compile("harbor", approved)
    assert store.verify("harbor") == receipt
    assert "harbor.economy.playable.html" in receipt["artifacts"]
    assert "harbor.economy.engine.json" in receipt["artifacts"]
    (tmp_path / "harbor.economy.playable.html").write_text("tampered")
    with pytest.raises(CanonError, match="economy_playable_mismatch"):
        store.verify("harbor")
    store.compile("harbor", approved)
    (tmp_path / "harbor.economy.engine.json").write_text("{}")
    with pytest.raises(CanonError, match="economy_recipe_mismatch"):
        store.verify("harbor")


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored custody")
def test_stale_world_and_output_symlink_fail_closed(tmp_path):
    world, store, source = setup(tmp_path)
    lease = store.publish("harbor", source, create=True)
    approved = store.approve("harbor", lease, "Reviewed.")
    store.compile("harbor", approved)
    output = tmp_path / "harbor.economy.playable.html"
    output.unlink()
    output.symlink_to(tmp_path / "harbor.json")
    with pytest.raises((CanonError, OSError)):
        store.verify("harbor")
    output.unlink()
    store.compile("harbor", approved)
    changed = copy.deepcopy(world)
    changed["scenes"][0]["narrative"] = "A revised original voyage."
    WorldStore(tmp_path).publish(changed, expected_digest=digest(world))
    with pytest.raises(CanonError, match="economy_world_lease_mismatch"):
        store.verify("harbor")


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored custody")
def test_stale_edit_and_editor_export(tmp_path):
    world, store, source = setup(tmp_path)
    lease = store.publish("harbor", source, create=True)
    page = store.editor("harbor", lease)
    content = (tmp_path / page["html_file"]).read_text()
    assert "Export unapproved JSON" in content
    assert "Content-Security-Policy" in content
    assert "script-src 'sha256-" in content
    assert page["economy_digest"] == lease
    with pytest.raises(CanonError, match="economy_stale_edit"):
        store.editor("harbor", "0" * 64)
    updated = store.edit("harbor", lease, {
        "action": "upsert_effect",
        "value": {"choice": "pursue_goal", "costs": {},
                  "gains": {"rations": 1}},
    })
    assert updated != lease
    assert store.inspect("harbor")["economy"]["approved"] is False
    with pytest.raises(CanonError, match="economy_stale_edit"):
        store.edit("harbor", lease, {
            "action": "remove_effect", "value": {"choice": "pursue_goal"}})
