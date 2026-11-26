"""An export cannot publish a revision that advanced after history audit."""
from __future__ import annotations

import pytest

from skeleton.game.gameplay.ridge_rescue.consumer_store import SlotStore, StoreError


def test_export_refuses_concurrent_unaudited_revision(tmp_path, monkeypatch):
    store = SlotStore(tmp_path / "private")
    initial = store.new("journey")
    original_audit = store.audit
    advanced = []

    def concurrent_advance(name):
        report = original_audit(name)
        if not advanced:
            advanced.append(store.step(
                name, initial["actions"][0], expected_head=initial["head"]
            ))
        return report

    monkeypatch.setattr(store, "audit", concurrent_advance)
    with pytest.raises(StoreError, match="changed during export audit"):
        store.export("journey")

    assert store.load("journey")["head"] == advanced[0]["head"]
    exports = store.root / "exports"
    assert not exports.exists() or not list(exports.glob("*.json"))

    # The next invocation audits the new authoritative revision and succeeds.
    monkeypatch.setattr(store, "audit", original_audit)
    from skeleton.game.gameplay.ridge_rescue.campaign import verify_export

    exported = store.export("journey")
    assert verify_export(exported.read_bytes())["head"] == advanced[0]["head"]
