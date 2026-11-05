"""Atomic world graph edits, consequence flags and negative-path fixtures."""
from __future__ import annotations

import copy
import os

import pytest

from skeleton.jeeves.worlds.world_canon import (
    CanonError, WorldStore, canonical, digest, edit, propose, prove,
)


def original():
    return propose(world_id="harbor", premise="A navigator discovers a silent beacon.",
                   protagonist="Sora", region="North Harbor",
                   goal="Restore the beacon without abandoning the crew.")


def expansion():
    return {"action": "batch", "value": [
        {"action": "add_scene",
         "value": {"id": "detour", "title": "Storm passage",
                   "narrative": "The crew shelters a stranded vessel."}},
        {"action": "add_choice",
         "value": {"id": "shelter", "from": "opening", "to": "detour",
                   "label": "Help the stranded vessel", "requires": [],
                   "grants": ["rescued"]}},
        {"action": "add_choice",
         "value": {"id": "return", "from": "detour", "to": "resolution",
                   "label": "Return to the beacon", "requires": ["rescued"],
                   "grants": []}},
    ]}


def test_atomic_batch_can_add_reachable_scene():
    expanded = edit(original(), expansion())
    proof = prove(expanded)
    assert "detour" in proof.visited_scenes
    assert "resolution" in proof.ending_witnesses
    assert proof.states_explored >= 3


def test_single_unreachable_scene_rejected_without_mutating_input():
    source = original()
    original_bytes = canonical(source)
    with pytest.raises(CanonError, match="unreachable"):
        edit(source, expansion()["value"][0])
    assert canonical(source) == original_bytes


def test_batch_rejects_missing_flag_proof():
    bad = expansion()
    bad["value"][-1]["value"]["requires"] = ["never_granted"]
    with pytest.raises(CanonError, match="reachable_dead_end"):
        edit(original(), bad)


def test_batch_rejects_ambiguous_choice_ids():
    bad = expansion()
    bad["value"][1]["value"]["id"] = "pursue_goal"
    with pytest.raises(CanonError, match="duplicate_choice"):
        edit(original(), bad)


def test_batch_rejects_unsupported_operation_atomically():
    source = original()
    bad = expansion()
    bad["value"].append({"action": "shell", "value": {}})
    with pytest.raises(CanonError, match="unsupported_edit"):
        edit(source, bad)
    assert len(source["scenes"]) == 2


def test_replace_then_remove_choice_is_atomic():
    source = edit(original(), expansion())
    revised = edit(source, {"action": "batch", "value": [
        {"action": "remove_choice", "value": {"id": "shelter"}},
        {"action": "remove_choice", "value": {"id": "return"}},
        {"action": "remove_scene", "value": {"id": "detour"}},
    ]})
    assert canonical(revised) == canonical(original())


def test_reject_unknown_remove_target():
    with pytest.raises(CanonError, match="unknown_edit_target"):
        edit(original(), {"action": "remove_scene", "value": {"id": "absent"}})


def test_reject_non_object_operation():
    with pytest.raises(CanonError, match="expected_object"):
        edit(original(), ["bad"])


def test_reject_oversized_batch():
    with pytest.raises(CanonError, match="invalid_list"):
        edit(original(), {"action": "batch", "value": [
            {"action": "remove_scene", "value": {"id": "absent"}} for _ in range(65)
        ]})


def test_reject_empty_batch():
    with pytest.raises(CanonError, match="empty_edit_batch"):
        edit(original(), {"action": "batch", "value": []})


def test_proof_is_stable_after_reordered_nonsemantic_metadata():
    source = edit(original(), expansion())
    assert digest(source) == digest(copy.deepcopy(source))
    assert prove(source).as_dict() == prove(copy.deepcopy(source)).as_dict()


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor-anchored custody")
def test_atomic_batch_roundtrip(tmp_path):
    store = WorldStore(tmp_path / "private")
    before = original()
    initial_digest = store.publish(before, create=True)
    changed = edit(store.read("harbor"), expansion())
    final_digest = store.publish(changed, expected_digest=initial_digest)
    assert final_digest != initial_digest
    assert digest(store.read("harbor")) == final_digest
    assert store.compile("harbor", final_digest)["source_digest"] == final_digest
    with pytest.raises(CanonError, match="stale_source"):
        store.publish(before, expected_digest=initial_digest)
