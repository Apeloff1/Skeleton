"""Maximal valid identifiers and malformed-source fail-closed regression."""
import json
import os

import pytest

from skeleton.jeeves.worlds.asset_briefs import (
    ASSET_SCHEMA, edit_briefs, propose_asset,
)
from skeleton.jeeves.worlds.editor import WorldEditorStore
from skeleton.jeeves.worlds.plan import (
    propose_plan, topological_tasks, validate_plan,
)
from skeleton.jeeves.worlds.timeline import propose_timeline
from skeleton.jeeves.worlds.world_canon import (
    CanonError, WorldStore, propose, prove,
)


def maximal_source():
    world = propose(world_id="harbor", premise="A navigator discovers a beacon.",
                    protagonist="Sora", region="North Harbor",
                    goal="Restore the beacon.")
    long_scene = "s" * 48
    long_choice = "c" * 48
    long_ending = "e" * 48
    world["scenes"][0]["id"] = long_scene
    world["scenes"][1]["id"] = long_ending
    world["start"] = long_scene
    world["choices"][0]["id"] = long_choice
    world["choices"][0]["from"] = long_scene
    world["choices"][0]["to"] = long_ending
    world["endings"][0]["scene"] = long_ending
    prove(world)
    asset = propose_asset(world, asset_id="hero", scene=long_scene,
                          kind="sprite", description="Original sailor silhouette",
                          alt_text="A sailor")
    assets = {"schema": ASSET_SCHEMA, "world_id": "harbor",
              "world_digest": prove(world).source_digest, "assets": [asset]}
    assets = edit_briefs(assets, world, {"action": "review", "value": {
        "id": "hero", "originality_attested": True,
    }})
    timeline = propose_timeline(world, actor="sora",
                                opening_note="The beacon goes dark.",
                                resolution_note="The light returns.")
    return world, assets, timeline


def test_maximal_ids_produce_bounded_unique_plan_tasks():
    world, assets, timeline = maximal_source()
    plan = propose_plan(world, assets, timeline)
    ids = [t["id"] for t in plan["tasks"]]
    assert all(len(tid) <= 48 for tid in ids)
    assert len(set(ids)) == len(ids)
    assert topological_tasks(plan["tasks"])[-1] == "playable_compile"
    assert validate_plan(plan, world, assets, timeline) == plan


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor-anchored custody")
def test_malformed_persisted_world_fails_closed_in_editor(tmp_path):
    root = tmp_path / "private"
    WorldStore(root)
    (root / "harbor.json").write_text("[]")
    with pytest.raises(CanonError, match="expected_object"):
        WorldEditorStore(root).render("harbor", "0" * 64)
