"""Causal chronology, actor occupancy and verified temporal handoff fixtures."""
import copy
import os

import pytest

from skeleton.jeeves.worlds.timeline import (
    TimelineStore, compile_timeline, edit_timeline, propose_timeline,
    validate_timeline,
)
from skeleton.jeeves.worlds.world_canon import (
    CanonError, WorldStore, digest, propose,
)


def source():
    world = propose(world_id="harbor", premise="A navigator discovers a beacon.",
                    protagonist="Sora", region="North Harbor",
                    goal="Restore the beacon.")
    data = propose_timeline(world, actor="sora",
                            opening_note="The beacon goes dark.",
                            resolution_note="The light returns.")
    return world, data


def test_original_prompt_to_causal_timeline():
    world, data = source()
    assert validate_timeline(data, world) == data
    handoff = compile_timeline(data, world)
    assert handoff["world_digest"] == digest(world)
    assert handoff["events"][0]["kind"] == "setup"
    assert handoff["events"][-1]["kind"] == "resolution"
    assert handoff["playable_proof"]["ending_witnesses"]


def test_world_revision_invalidates_timeline():
    world, data = source()
    changed = copy.deepcopy(world)
    changed["scenes"][0]["narrative"] = "A revised original scene."
    with pytest.raises(CanonError, match="timeline_world_lease_mismatch"):
        validate_timeline(data, changed)


def test_reject_causal_time_paradox():
    world, data = source()
    data["events"][1]["tick"] = 0
    data["events"][1]["actor"] = "other"
    with pytest.raises(CanonError, match="causal_time_paradox"):
        validate_timeline(data, world)


def test_reject_actor_double_booking():
    world, data = source()
    data["events"].append({
        "id": "duplicate_slot", "scene": "opening", "actor": "sora",
        "tick": 0, "kind": "observation", "description": "Another event.",
        "depends_on": [], "requires_flags": [],
    })
    with pytest.raises(CanonError, match="actor_double_booked"):
        validate_timeline(data, world)


def test_reject_unknown_predecessor():
    world, data = source()
    data["events"][1]["depends_on"] = ["missing"]
    with pytest.raises(CanonError, match="unknown_event_predecessor"):
        validate_timeline(data, world)


def test_reject_unannotated_scene():
    world, data = source()
    data["events"] = data["events"][:1]
    with pytest.raises(CanonError, match="unannotated_scene"):
        validate_timeline(data, world)


def test_reject_unreachable_flag_precondition():
    world, data = source()
    data["events"][0]["requires_flags"] = ["never_earned"]
    with pytest.raises(CanonError, match="unreachable_event_precondition"):
        validate_timeline(data, world)


def test_reject_backwards_scene_clock():
    world, data = source()
    data["events"][0]["tick"] = 10
    data["events"][1]["tick"] = 1
    data["events"][1]["depends_on"] = []
    with pytest.raises(CanonError, match="backward_scene_clock"):
        validate_timeline(data, world)


def test_atomic_event_edit_preserves_source():
    world, data = source()
    revised = edit_timeline(data, world, {"action": "replace", "value": {
        "id": "setup", "scene": "opening", "actor": "sora",
        "tick": 0, "kind": "setup", "description": "A new opening.",
        "depends_on": [], "requires_flags": [],
    }})
    assert revised["events"][0]["description"] == "A new opening."
    assert data["events"][0]["description"] != "A new opening."


def test_batch_rejects_invalid_intermediate_final_state():
    world, data = source()
    with pytest.raises(CanonError, match="unannotated_scene"):
        edit_timeline(data, world, {"action": "batch", "value": [
            {"action": "remove", "value": {"id": "resolution_1"}},
        ]})


def test_compile_is_deterministic():
    world, data = source()
    assert compile_timeline(data, world) == compile_timeline(
        copy.deepcopy(data), copy.deepcopy(world))


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor-anchored custody")
def test_persist_revise_compile_with_stale_rejection(tmp_path):
    worlds = WorldStore(tmp_path / "private")
    world, data = source()
    worlds.publish(world, create=True)
    store = TimelineStore(tmp_path / "private")
    first = store.publish("harbor", data, create=True)
    changed = edit_timeline(data, world, {"action": "replace", "value": {
        "id": "setup", "scene": "opening", "actor": "sora",
        "tick": 0, "kind": "setup", "description": "A new opening.",
        "depends_on": [], "requires_flags": [],
    }})
    second = store.publish("harbor", changed, expected_digest=first)
    assert second != first
    assert store.compile("harbor", second)["timeline_digest"] == second
    with pytest.raises(CanonError, match="stale_timeline"):
        store.compile("harbor", first)
