"""Typed production plan DAG, dependency gates and source-verified handoff."""
import copy
import os

import pytest

from skeleton.jeeves.worlds.asset_briefs import (
    ASSET_SCHEMA, AssetBriefStore, edit_briefs, propose_asset,
)
from skeleton.jeeves.worlds.bundle import PlayableBundleStore
from skeleton.jeeves.worlds.plan import (
    PlanStore, compile_plan, propose_plan, review_task, topological_tasks,
    validate_plan,
)
from skeleton.jeeves.worlds.timeline import TimelineStore, propose_timeline
from skeleton.jeeves.worlds.world_canon import (
    CanonError, WorldStore, digest, propose, prove,
)


def sources():
    world = propose(world_id="harbor", premise="A navigator discovers a beacon.",
                    protagonist="Sora", region="North Harbor",
                    goal="Restore the beacon.")
    asset = propose_asset(world, asset_id="hero", scene="opening",
                          kind="sprite", description="Original sailor silhouette",
                          alt_text="A sailor in a blue coat")
    assets = {"schema": ASSET_SCHEMA, "world_id": "harbor",
              "world_digest": prove(world).source_digest, "assets": [asset]}
    assets = edit_briefs(assets, world, {"action": "review", "value": {
        "id": "hero", "originality_attested": True,
    }})
    timeline = propose_timeline(world, actor="sora",
                                opening_note="The beacon goes dark.",
                                resolution_note="The light returns.")
    return world, assets, timeline


def approve_all(plan, world, assets, timeline):
    current = plan
    for task_id in topological_tasks(plan["tasks"]):
        current = review_task(current, world, assets, timeline,
                              task_id=task_id, decision="approved",
                              note="Reviewed against canonical source.")
    return current


def test_dynamic_plan_covers_all_real_source_entities():
    world, assets, timeline = sources()
    plan = propose_plan(world, assets, timeline)
    assert len(plan["tasks"]) == (
        len(world["scenes"]) + len(world["choices"]) +
        len(world["endings"]) + len(assets["assets"]) +
        len(timeline["events"]) + 1)
    assert topological_tasks(plan["tasks"])[-1] == "playable_compile"


def test_dependency_cannot_be_approved_before_upstream():
    world, assets, timeline = sources()
    plan = propose_plan(world, assets, timeline)
    with pytest.raises(CanonError, match="unapproved_dependency"):
        review_task(plan, world, assets, timeline, task_id="playable_compile",
                    decision="approved", note="Premature approval")


def test_approved_plan_is_deterministic():
    world, assets, timeline = sources()
    plan = approve_all(propose_plan(world, assets, timeline),
                       world, assets, timeline)
    assert validate_plan(plan, world, assets, timeline) == plan
    assert digest(plan) == digest(copy.deepcopy(plan))


def test_plan_inventory_tamper_rejected():
    world, assets, timeline = sources()
    plan = propose_plan(world, assets, timeline)
    plan["tasks"].pop()
    with pytest.raises(CanonError, match="plan_task_inventory_mismatch"):
        validate_plan(plan, world, assets, timeline)


def test_source_revision_invalidates_plan():
    world, assets, timeline = sources()
    plan = propose_plan(world, assets, timeline)
    changed = copy.deepcopy(world)
    changed["scenes"][0]["title"] = "New title"
    with pytest.raises(CanonError, match="plan_source_lease_mismatch"):
        validate_plan(plan, changed, assets, timeline)


def test_unknown_review_task_rejected():
    world, assets, timeline = sources()
    plan = propose_plan(world, assets, timeline)
    with pytest.raises(CanonError, match="unknown_task"):
        review_task(plan, world, assets, timeline, task_id="unknown",
                    decision="approved", note="Not a real task")


def test_blocked_plan_cannot_compile():
    world, assets, timeline = sources()
    plan = propose_plan(world, assets, timeline)
    plan = review_task(plan, world, assets, timeline, task_id="scene_opening",
                       decision="blocked", note="Continuity needs repair.")
    with pytest.raises(CanonError, match="plan_not_approved"):
        compile_plan(plan, world, assets, timeline, {
            "world_digest": digest(world), "asset_briefs_digest": digest(assets),
            "timeline_digest": digest(timeline),
        })


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor-anchored custody")
def test_complete_plan_persists_and_compiles_only_with_verified_bundle(tmp_path):
    root = tmp_path / "private"
    world, assets, timeline = sources()
    wd = WorldStore(root).publish(world, create=True)
    ad = AssetBriefStore(root).publish("harbor", assets, create=True)
    td = TimelineStore(root).publish("harbor", timeline, create=True)
    store = PlanStore(root)
    plan = propose_plan(world, assets, timeline)
    initial = store.publish("harbor", plan, create=True)
    with pytest.raises(CanonError, match="plan_not_approved"):
        store.compile("harbor", initial)
    approved = approve_all(plan, world, assets, timeline)
    final = store.publish("harbor", approved, expected_digest=initial)
    PlayableBundleStore(root).compile("harbor", world_digest=wd,
                                      asset_digest=ad, timeline_digest=td,
                                      era="eight_bit_tile_1983")
    receipt = store.compile("harbor", final)
    assert receipt["plan_digest"] == final
    assert (root / receipt["compiled_file"]).is_file()
    with pytest.raises(CanonError, match="stale_plan"):
        store.compile("harbor", initial)
