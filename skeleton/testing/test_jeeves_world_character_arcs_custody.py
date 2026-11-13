"""Arc custody: optimistic review, source digests, offline UI and tamper."""
from __future__ import annotations

import copy
import os
import pytest

from skeleton.jeeves.worlds.cast import CastStore, approve_cast, propose_cast
from skeleton.jeeves.worlds.character_arcs import ArcStore, propose_arcs
from skeleton.jeeves.worlds.world_canon import CanonError, WorldStore, digest, propose


def fixture(tmp_path):
    world = propose(world_id="harbor", premise="Original voyage.",
                    protagonist="Ari", region="Harbor", goal="Reach shore.")
    WorldStore(tmp_path).publish(world, create=True)
    cast = approve_cast(propose_cast(
        world, npc_id="guide", npc_name="Mira",
        npc_line="I will show you the way."), world, "Reviewed cast.")
    CastStore(tmp_path).publish("harbor", cast, create=True)
    store = ArcStore(tmp_path)
    source = propose_arcs(
        world, cast, prompt="Mira learns to trust.",
        actor="guide", desire="Guide Ari",
        starting_belief="Nobody listens.",
        resolved_belief="Ari listens.",
        choice="pursue_goal", text="Mira finds her courage.")
    return store, world, cast, source


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored custody")
def test_review_compile_verify_and_tamper(tmp_path):
    store, world, cast, source = fixture(tmp_path)
    lease = store.publish("harbor", source, create=True)
    assert store.inspect("harbor")["proof"]["states_explored"] == 2
    with pytest.raises(CanonError, match="arcs_approval_requires_review"):
        store.publish("harbor", {**source, "approved": True,
                                "review_note": "forged"}, expected_digest=lease)
    with pytest.raises(CanonError, match="arcs_stale_edit"):
        store.approve("harbor", "0" * 64, "Reviewed.")
    approved = store.approve("harbor", lease, "Reviewed original arc.")
    receipt = store.compile("harbor", approved)
    assert store.verify("harbor") == receipt
    (tmp_path / "harbor.arcs.playable.html").write_text("tampered")
    with pytest.raises(CanonError, match="arcs_playable_mismatch"):
        store.verify("harbor")
    store.compile("harbor", approved)
    (tmp_path / "harbor.arcs.engine.json").write_text("{}")
    with pytest.raises(CanonError, match="arcs_recipe_mismatch"):
        store.verify("harbor")


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored custody")
def test_stale_cast_and_symlinked_output(tmp_path):
    store, world, cast, source = fixture(tmp_path)
    lease = store.publish("harbor", source, create=True)
    approved = store.approve("harbor", lease, "Reviewed.")
    store.compile("harbor", approved)
    output = tmp_path / "harbor.arcs.playable.html"
    output.unlink()
    output.symlink_to(tmp_path / "harbor.json")
    with pytest.raises((CanonError, OSError)):
        store.verify("harbor")
    output.unlink()
    store.compile("harbor", approved)
    changed = copy.deepcopy(cast)
    changed["lines"][0]["text"] = "A revised original line."
    CastStore(tmp_path).publish("harbor", changed, expected_digest=digest(cast))
    with pytest.raises(CanonError, match="arcs_source_lease_mismatch"):
        store.verify("harbor")


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored custody")
def test_offline_editor_and_optimistic_edit(tmp_path):
    store, world, cast, source = fixture(tmp_path)
    lease = store.publish("harbor", source, create=True)
    page = store.editor("harbor", lease)
    html = (tmp_path / page["html_file"]).read_text()
    assert "Export unapproved JSON" in html
    assert "Content-Security-Policy" in html
    assert "script-src 'sha256-" in html
    with pytest.raises(CanonError, match="arcs_stale_edit"):
        store.editor("harbor", "0" * 64)
    changed = store.edit("harbor", lease, {
        "action": "upsert_beat",
        "value": {"actor": "guide", "beat": {
            "id": "turn", "choice": "pursue_goal", "stage": "turn",
            "text": "Mira changes her mind.",
        }},
    })
    assert changed != lease
    assert store.inspect("harbor")["arcs"]["approved"] is False
    with pytest.raises(CanonError, match="arcs_stale_edit"):
        store.edit("harbor", lease, {
            "action": "remove_beat",
            "value": {"actor": "guide", "beat_id": "turn"}})
