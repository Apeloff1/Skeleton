"""Survival campaign authored leases and previews cannot mint earned wins."""
from __future__ import annotations

import copy

import pytest

from skeleton.game.gameplay.scene_survival_campaign import original_campaign
from skeleton.game.gameplay.scene_survival_campaign_author import (
    apply_author, new_author, preview_author, verify_author,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError


def test_author_preview_does_not_rewrite_the_initial_source():
    source, actions = original_campaign()
    before = copy.deepcopy(source)
    document = new_author(source)
    preview = preview_author(document, actions)
    assert preview["phase"] == "won"
    assert source == before
    assert verify_author(document) == document


def test_stale_revision_fences_transaction_not_just_source_digest():
    source, _ = original_campaign()
    initial = new_author(source)
    edit = {"kind": "set_reward", "stage_id": "quay_crossing", "value": 15}
    changed = apply_author(initial, edit,
                           expected_digest=initial["source_digest"],
                           expected_revision=0)
    assert changed["revision"] == 1
    with pytest.raises(SceneTravelError):
        apply_author(changed, edit,
                     expected_digest=initial["source_digest"],
                     expected_revision=0)
