"""Regression: save-slot identifiers cannot escape consumer custody."""
from __future__ import annotations

import pytest

from skeleton.game.gameplay.ridge_rescue.consumer_store import SlotStore, StoreError


@pytest.mark.parametrize("name", [
    "../escape", "UPPER", "", "a/b", "a\\\\b", ".hidden",
    "a" * 33, " space", "a\\x00b", "a.b",
])
def test_rejected_slot_name_never_creates_an_export(tmp_path, name):
    store = SlotStore(tmp_path / "private")
    with pytest.raises(StoreError, match="invalid save slot name"):
        store.new(name)
    assert not (tmp_path / "escape").exists()
    assert not (tmp_path / "private" / "exports").exists()


def test_rejected_slot_name_does_not_affect_valid_save(tmp_path):
    store = SlotStore(tmp_path / "private")
    valid = store.new("journey")
    with pytest.raises(StoreError, match="invalid save slot name"):
        store.load("../journey")
    assert store.load("journey")["head"] == valid["head"]
