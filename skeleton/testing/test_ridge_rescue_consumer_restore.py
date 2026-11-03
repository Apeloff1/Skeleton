"""Portable Cinder Ridge save restoration: real canonical replay and CAS custody."""
from __future__ import annotations

from copy import deepcopy

import pytest

from skeleton.game.gameplay.ridge_rescue.acceptance import acceptance_actions
from skeleton.game.gameplay.ridge_rescue.campaign_acceptance import LAST_SIGNAL
from skeleton.game.gameplay.ridge_rescue.campaign import export_campaign
from skeleton.game.gameplay.ridge_rescue.consumer_restore import RestoreError, replay_export
from skeleton.game.gameplay.ridge_rescue.consumer_store import SlotStore, StoreError, _source
from skeleton.game.gameplay.ridge_rescue.custody import canonical, digest


def _play(store: SlotStore, name: str, *, full: bool = False):
    current = store.new(name)
    sequence = acceptance_actions("protect") + (LAST_SIGNAL if full else [])
    for action in sequence:
        current = store.step(name, action, expected_head=current["head"])
    return current, sequence


@pytest.mark.parametrize("full", [False, True])
def test_restore_earned_campaign_with_complete_audit(tmp_path, full):
    store = SlotStore(tmp_path / "save")
    original, sequence = _play(store, "original", full=full)
    payload = store.export("original").read_bytes()
    restored = store.restore("recovered", payload)
    assert restored["head"] == original["head"]
    assert restored["revision"] == len(sequence)
    assert restored["status"] == original["status"]
    assert store.audit("recovered")["audit_entries"] == len(sequence)
    with pytest.raises(StoreError, match="already exists"):
        store.restore("recovered", payload)
    assert store.audit("recovered")["verified"]


def test_restore_unfinished_campaign_can_continue_to_real_ending(tmp_path):
    store = SlotStore(tmp_path / "save")
    current = store.new("before")
    actions = acceptance_actions("protect")
    for action in actions[:4]:
        current = store.step("before", action, expected_head=current["head"])
    restored = store.restore("after", store.export("before").read_bytes())
    assert restored["head"] == current["head"]
    for action in actions[4:] + LAST_SIGNAL:
        restored = store.step("after", action, expected_head=restored["head"])
    assert restored["status"] == "completed"
    assert store.audit("after")["verified"]


def test_restore_tampering_rejected_without_creating_slot(tmp_path):
    store = SlotStore(tmp_path / "save")
    _play(store, "original", full=True)
    payload = store.export("original").read_bytes()
    import json
    damaged = json.loads(payload)
    damaged["sha256"] = "0" * 64
    with pytest.raises(ValueError):
        store.restore("damaged", canonical(damaged))
    with pytest.raises(StoreError, match="does not exist"):
        store.load("damaged")
    assert store.audit("original")["verified"]


def test_restore_rejects_retries_without_chronology(tmp_path):
    store = SlotStore(tmp_path / "save")
    original, _ = _play(store, "original")
    changed = deepcopy(original["session"])
    changed["retries"][0] = 1
    changed["head"] = digest({key: value for key, value in changed.items() if key != "head"})
    envelope = export_campaign(changed)
    with pytest.raises(RestoreError, match="retry chronology"):
        store.restore("unsafe", envelope)
    with pytest.raises(StoreError, match="does not exist"):
        store.load("unsafe")


def test_restore_rejects_other_source_even_if_export_self_consistent(tmp_path):
    from skeleton.game.gameplay.ridge_rescue.campaign import open_campaign
    from skeleton.game.gameplay.ridge_rescue.custody import canonical
    import json
    source = json.loads(_source())
    source["title"] = "Untrusted alternate title"
    alternate = open_campaign(source)
    with pytest.raises(RestoreError, match="not bound"):
        SlotStore(tmp_path / "save").restore("foreign", export_campaign(alternate))


def test_restoration_is_exactly_canonical_not_trusting_journal_claims(tmp_path):
    store = SlotStore(tmp_path / "save")
    _play(store, "original", full=True)
    payload = store.export("original").read_bytes()
    replayed, history = replay_export(payload, _source())
    assert len(history) > 20
    assert history[0]["prior_head"] != history[0]["next_head"]
    assert replayed["head"] == store.load("original")["head"]
