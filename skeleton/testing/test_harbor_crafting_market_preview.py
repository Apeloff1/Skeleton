"""User-reachable market preview, rejection and optimistic application."""
from __future__ import annotations

from copy import deepcopy
import pytest

from skeleton.game.gameplay.harbor_crafting import (
    HarborError, demo_actions, digest, export_bundle, load_source,
)
from skeleton.game.gameplay.harbor_crafting_cli import DEFAULT_WORLD
from skeleton.game.gameplay.harbor_crafting_market_preview import (
    apply_market_preview, preview_market, verify_market_preview,
)


@pytest.fixture
def prefix():
    source = load_source(DEFAULT_WORLD)
    actions = demo_actions()
    return export_bundle(source, actions[:-1]), [actions[-1]]


def test_preview_commit_earned_ending(prefix):
    bundle, actions = prefix
    preview = preview_market(bundle, actions)
    assert verify_market_preview(preview)["accepted"] == 1
    assert preview["rejected_at"] is None
    report = apply_market_preview(
        preview, expected_terminal_digest=bundle["terminal_digest"], require_win=True)
    assert report["totals"]["ending"] == "beacon"
    assert report["bundle"]["events"][:-1] == bundle["events"]


def test_illegal_action_preview_is_safe_and_nonmutating(prefix):
    bundle, _ = prefix
    before = deepcopy(bundle)
    preview = preview_market(bundle, [{"op": "gather"}])
    assert preview["rejected_at"] == 0
    assert preview["reason"]
    assert preview["accepted"] == []
    assert preview["preview_state"] == bundle["state"]
    assert bundle == before
    assert verify_market_preview(preview)["rejected_at"] == 0
    with pytest.raises(HarborError, match="rejected"):
        apply_market_preview(preview, expected_terminal_digest=bundle["terminal_digest"])


def test_preview_rejects_stale_lease(prefix):
    bundle, actions = prefix
    preview = preview_market(bundle, actions)
    with pytest.raises(HarborError, match="stale"):
        apply_market_preview(preview, expected_terminal_digest="0" * 64)


def test_preview_rejects_forged_success_even_after_rehash(prefix):
    bundle, actions = prefix
    preview = preview_market(bundle, actions)
    preview["accepted"][0]["coin_delta"] = 100
    preview["preview_digest"] = digest({k: v for k, v in preview.items() if k != "preview_digest"})
    with pytest.raises(HarborError, match="replay"):
        verify_market_preview(preview)


def test_preview_invalid_shape_and_budget(prefix):
    bundle, _ = prefix
    for actions in (None, [], [{"op": "teleport"}], [{"op": "wait"}] * 17):
        with pytest.raises(HarborError):
            preview_market(bundle, actions)
