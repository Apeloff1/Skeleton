"""Malformed in-memory backup graphs must fail closed before slot publication."""
from __future__ import annotations

import pytest

from skeleton.game.gameplay.ridge_rescue.consumer_backup import BackupError, verify_backup
from skeleton.game.gameplay.ridge_rescue.consumer_store import SlotStore, StoreError


def test_cyclic_backup_mapping_is_rejected_without_recursion_escape(tmp_path):
    store = SlotStore(tmp_path / "saves")
    baseline = store.new("original")
    cycle = {}
    cycle["payload"] = cycle
    cycle["sha256"] = "0" * 64
    from skeleton.game.gameplay.ridge_rescue.consumer_store import _source
    with pytest.raises(BackupError, match="invalid backup object graph"):
        verify_backup(cycle, _source())
    assert store.load("original")["head"] == baseline["head"]
    with pytest.raises(StoreError, match="does not exist"):
        store.load("untrusted")


def test_excessively_nested_backup_mapping_fails_closed(tmp_path):
    from skeleton.game.gameplay.ridge_rescue.consumer_store import _source
    nested = {}
    for _ in range(1500):
        nested = {"child": nested}
    envelope = {"payload": nested, "sha256": "0" * 64}
    with pytest.raises(BackupError, match="invalid backup object graph"):
        verify_backup(envelope, _source())


def test_nonfinite_in_memory_backup_mapping_fails_closed(tmp_path):
    from skeleton.game.gameplay.ridge_rescue.consumer_store import _source
    envelope = {"payload": {"bad": float("inf")}, "sha256": "0" * 64}
    with pytest.raises(BackupError, match="invalid backup object graph"):
        verify_backup(envelope, _source())
