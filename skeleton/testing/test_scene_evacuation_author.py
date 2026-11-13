"""Author transactions preserve input and enforce canonical digest leases."""
from __future__ import annotations

import copy

import pytest

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_evacuation import (
    demo_actions, normalize_evacuation, original_evacuation,
)
from skeleton.game.gameplay.scene_evacuation_author import edit_evacuation
from skeleton.game.gameplay.scene_travel import SceneTravelError


def test_source_edit_preview_is_atomic_and_not_a_mutation_of_input():
    source = original_evacuation()
    original = copy.deepcopy(source)
    lease = dig(normalize_evacuation(source))
    edits = [{"npc_id": "watch_keeper", "changes": {"reward": 21}}]
    edited = edit_evacuation(
        source, edits, lease, preview_actions=demo_actions(),
    )
    assert source == original
    assert edited["previous_source_digest"] == lease
    assert edited["source_digest"] != lease
    assert edited["edited_npcs"] == ["watch_keeper"]


def test_stale_lease_never_publishes_a_new_source():
    source = original_evacuation()
    with pytest.raises(SceneTravelError):
        edit_evacuation(
            source, [{"npc_id": "watch_keeper",
                      "changes": {"reward": 21}}], "0" * 64,
        )
