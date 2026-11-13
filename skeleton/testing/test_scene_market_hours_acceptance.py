"""Merchant acceptance derives receipts from canonical earned purchases."""
from __future__ import annotations

import copy

import pytest

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_market_hours import (
    original_hours, simulate_hours,
)
from skeleton.game.gameplay.scene_market_hours_acceptance import (
    accept_hours, verify_hours_acceptance,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError


def test_completed_merchant_audit_is_source_bound():
    source, actions = original_hours()
    session = simulate_hours(source, actions)
    witness = accept_hours(session, include_editor=False)
    assert witness["status"] == "accepted_offline_witness"
    assert witness["state_digest"] == session["state_digest"]
    assert witness["journal_length"] == len(actions)
    assert verify_hours_acceptance(session, witness) == witness


def test_manipulated_receipts_fail_despite_fresh_checksum():
    source, actions = original_hours()
    session = simulate_hours(source, actions)
    authentic = accept_hours(session, include_editor=False)
    forged = copy.deepcopy(authentic)
    forged["merchant_purchases"] = {}
    assert forged != authentic
    forged["checksum"] = dig(
        {k: v for k, v in forged.items() if k != "checksum"}
    )
    with pytest.raises(SceneTravelError):
        verify_hours_acceptance(session, forged)
