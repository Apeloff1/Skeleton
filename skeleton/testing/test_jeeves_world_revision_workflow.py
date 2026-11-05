"""Prompt-to-playable revision continuity: actual source, saved play and QA.

This is an integration fixture, not a release/device qualification. It proves
that a revised original world can retain a real player checkpoint only through
an explicit operator migration, then compile and verify the exact new source.
"""
from __future__ import annotations

import copy
import os

import pytest

from skeleton.jeeves.worlds.migration import MigrationStore
from skeleton.jeeves.worlds.playtest import PlaytestStore
from skeleton.jeeves.worlds.revision import RevisionStore
from skeleton.jeeves.worlds.session import SessionStore
from skeleton.jeeves.worlds.tools import SCHEMA, invoke_world_tool
from skeleton.jeeves.worlds.world_canon import (
    CanonError, WorldStore, digest, propose, prove,
)


def request(name, args=None):
    return {"schema": SCHEMA, "tool": name, "world_id": "harbor",
            "args": args if args is not None else {}}


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored POSIX custody")
def test_prompt_edit_migrate_playable_and_typed_jeeves_handoff(tmp_path):
    root = tmp_path / "private"
    worlds = WorldStore(root)
    original = propose(
        world_id="harbor", premise="An original courier story at the harbor.",
        protagonist="Rin", region="Harbor", goal="Return the sealed map.",
    )
    first_digest = worlds.publish(original, create=True)
    sessions = SessionStore(root)
    first = sessions.create("harbor", "original")
    finished = sessions.choose(
        "harbor", "original", "pursue_goal", first["session_digest"])
    assert finished["ending"] == "Return the sealed map."
    checkpoint = sessions.export("harbor", "original")

    # The author revises the canonical prose, without silently rewriting the
    # player's earned ending. Old slot is now intentionally source-stale.
    revised = copy.deepcopy(original)
    revised["scenes"][0]["narrative"] = "The harbor has changed after the storm."
    revised_digest = worlds.publish(revised, expected_digest=first_digest)
    assert revised_digest != first_digest
    with pytest.raises(CanonError, match="session_world_lease_mismatch"):
        sessions.inspect("harbor", "original")

    revisions = RevisionStore(str(root))
    impact = revisions.preview("harbor", original)
    assert impact["review_class"] == "presentation_review"
    reviewed = revisions.review(
        "harbor", original, expected_impact_digest=digest(impact),
        note="Reviewed after comparing the authored ending.")
    assert revisions.verify("harbor", original) == reviewed

    migration = MigrationStore(str(root))
    preview = migration.preview("harbor", original, checkpoint, {})
    assert preview["ending"] == "Return the sealed map."
    receipt = migration.apply(
        "harbor", "continued", original, checkpoint, {},
        expected_preview_digest=digest(preview),
        review_note="Operator confirmed earned ending and flags.")
    assert receipt["player"]["ending"] == "Return the sealed map."
    assert sessions.read("harbor", "continued")["world_digest"] == revised_digest

    qa = PlaytestStore(str(root))
    coverage = qa.preview("harbor")
    assert coverage["complete"]
    assert coverage["choice_witnesses"]["pursue_goal"] == ["pursue_goal"]
    compiled = qa.compile("harbor", expected_world_digest=revised_digest)
    assert qa.verify("harbor") == compiled
    page = (root / "harbor.playtest.playable.html").read_text()
    assert "Content-Security-Policy" in page
    assert "connect-src 'none'" in page
    assert "The harbor has changed after the storm." in page

    # The model receives only read-only, digest-bound proof objects.
    for name, args in (
        ("world.playtest_preview", {}),
        ("world.revision_preview", {"old_world": original}),
        ("world.migration_preview", {
            "old_world": original, "checkpoint": checkpoint,
            "choice_map": {},
        }),
    ):
        tool = invoke_world_tool(str(root), request(name, args))
        assert tool["persisted"] is False
        assert tool["authority"] == "read_only_no_mutation"
        assert tool["world_digest"] == revised_digest
        assert tool["result_digest"] == digest(tool["result"])


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored POSIX custody")
def test_stale_review_and_causal_change_cannot_reuse_migration(tmp_path):
    worlds = WorldStore(tmp_path)
    original = propose(
        world_id="harbor", premise="Original harbor narrative.",
        protagonist="Rin", region="Harbor", goal="Save the map.",
    )
    first = worlds.publish(original, create=True)
    sessions = SessionStore(tmp_path)
    sessions.create("harbor", "original")
    checkpoint = sessions.export("harbor", "original")
    revised = copy.deepcopy(original)
    revised["scenes"][0]["narrative"] = "New authored narrative."
    worlds.publish(revised, expected_digest=first)
    migration = MigrationStore(str(tmp_path))
    preview = migration.preview("harbor", original, checkpoint, {})
    review = RevisionStore(str(tmp_path)).preview("harbor", original)

    # A second, causally different revision invalidates both independent
    # optimistic leases. No migration slot or stale review may publish.
    altered = copy.deepcopy(revised)
    altered["choices"][0]["grants"] = ["privilege"]
    worlds.publish(altered, expected_digest=digest(revised))
    with pytest.raises(CanonError, match="migration_stale_preview"):
        migration.apply(
            "harbor", "continued", original, checkpoint, {},
            expected_preview_digest=digest(preview),
            review_note="Reviewed prior source only.")
    with pytest.raises(CanonError, match="revision_stale_preview"):
        RevisionStore(str(tmp_path)).review(
            "harbor", original, expected_impact_digest=digest(review),
            note="Reviewed prior source only.")
    assert not (tmp_path / "harbor.continued.session.json").exists()
    assert not (tmp_path / "harbor.revision.receipt.json").exists()


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored POSIX custody")
def test_no_implicit_model_mutation_or_author_approval(tmp_path):
    world = propose(world_id="harbor", premise="A private harbor story.",
                    protagonist="Rin", region="Harbor", goal="Find the chart.")
    WorldStore(tmp_path).publish(world, create=True)
    proof = invoke_world_tool(str(tmp_path), request("world.playtest_preview"))
    assert proof["persisted"] is False
    assert proof["review_required"] is False
    assert not (tmp_path / "harbor.playtest.receipt.json").exists()
    assert not (tmp_path / "harbor.revision.receipt.json").exists()
    with pytest.raises(CanonError, match="unknown_world_tool"):
        invoke_world_tool(str(tmp_path), request("world.revision_approve"))
