"""Full-history backup restores the original game, including failed chapter retries."""
from __future__ import annotations

from copy import deepcopy

import pytest

from skeleton.game.gameplay.ridge_rescue.consumer_store import SlotStore, StoreError
from skeleton.game.gameplay.ridge_rescue.consumer_backup import BackupError, verify_backup
from skeleton.game.gameplay.ridge_rescue.acceptance import acceptance_actions
from skeleton.game.gameplay.ridge_rescue.campaign_acceptance import LAST_SIGNAL
from skeleton.game.gameplay.ridge_rescue.custody import canonical, digest
from skeleton.game.gameplay.ridge_rescue.consumer_store import _source


def test_backup_restore_full_campaign_with_exact_history(tmp_path):
    store = SlotStore(tmp_path / "saves")
    state = store.new("original")
    actions = acceptance_actions("protect") + LAST_SIGNAL
    for action in actions:
        state = store.step("original", action, expected_head=state["head"])
    payload = store.backup("original").read_bytes()
    replayed, history = verify_backup(payload, _source())
    assert replayed["head"] == state["head"]
    assert len(history) == len(actions)
    restored = store.restore_backup("copy", payload)
    assert restored["head"] == state["head"]
    assert restored["revision"] == len(actions)
    assert store.audit("copy")["verified"]
    with pytest.raises(StoreError, match="already exists"):
        store.restore_backup("copy", payload)


def test_failed_chapter_retry_chronology_survives_backup(tmp_path):
    store = SlotStore(tmp_path / "saves")
    state = store.new("original")
    attempts = 0
    while state["status"] == "playing" and attempts < 200:
        state = store.step("original", {"verb": "rest"}, expected_head=state["head"])
        attempts += 1
    assert state["status"].startswith("lost:"), "test must earn a genuine failed chapter"
    state = store.retry("original", expected_head=state["head"])
    assert state["retries"][0] == 1
    for action in acceptance_actions("protect") + LAST_SIGNAL:
        state = store.step("original", action, expected_head=state["head"])
    assert state["status"] == "completed"
    backup = store.backup("original").read_bytes()
    replayed, history = verify_backup(backup, _source())
    assert any(item["action"] == {"verb": "retry"} for item in history)
    assert replayed["head"] == state["head"]
    restored = store.restore_backup("copy", backup)
    assert restored["head"] == state["head"]
    assert restored["revision"] == state["revision"]
    assert store.audit("copy")["audit_entries"] == state["revision"]


def test_tampered_backup_is_rejected_before_slot_creation(tmp_path):
    store = SlotStore(tmp_path / "saves")
    state = store.new("original")
    state = store.step("original", state["actions"][0], expected_head=state["head"])
    import json
    payload = json.loads(store.backup("original").read_bytes())
    payload["payload"]["history"][0]["next_head"] = "0" * 64
    payload["sha256"] = digest(payload["payload"])
    with pytest.raises(BackupError, match="broken successor"):
        store.restore_backup("tampered", canonical(payload))
    with pytest.raises(StoreError, match="does not exist"):
        store.load("tampered")
    assert store.audit("original")["verified"]


def test_backup_rejects_foreign_source_and_oversize(tmp_path):
    store = SlotStore(tmp_path / "saves")
    store.new("original")
    payload = store.backup("original").read_bytes()
    with pytest.raises(BackupError, match="byte budget"):
        verify_backup(payload + b" " * 1_000_001, _source())
    with pytest.raises(BackupError, match="another game source"):
        verify_backup(payload, _source().replace(b"Cinder Ridge", b"Other Ridge"))
