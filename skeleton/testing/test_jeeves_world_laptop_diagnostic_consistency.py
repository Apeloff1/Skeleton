"""Recovery diagnostics must not mix distinct valid world generations."""
from __future__ import annotations

import pytest

from skeleton.jeeves.worlds.laptop_flow import LaptopFlow
from skeleton.jeeves.worlds.world_canon import CanonError, digest
from skeleton.testing.test_jeeves_world_laptop_flow import ready


def test_diagnose_reports_busy_writer_as_retry(tmp_path, monkeypatch):
    flow, _, _, _ = ready(tmp_path)
    original = flow.inspect
    def busy(world_id):
        raise CanonError("lease_busy")
    monkeypatch.setattr(flow, "inspect", busy)
    report = flow.diagnose("lighthouse")
    assert report["checks"]["source"] == {"ok": False, "error": "lease_busy"}
    assert report["next_action"] == "retry_after_current_writer_finishes"
    monkeypatch.setattr(flow, "inspect", original)
    assert flow.diagnose("lighthouse")["checks"]["acceptance"]["ok"]


def test_diagnose_rejects_mixed_source_generations(tmp_path, monkeypatch):
    flow, _, _, _ = ready(tmp_path)
    original = flow.acceptance
    def raced(world_id, slot=None):
        result = original(world_id, slot)
        return {**result, "source_digest": "0" * 64}
    monkeypatch.setattr(flow, "acceptance", raced)
    report = flow.diagnose("lighthouse")
    assert report["checks"]["acceptance"] == {
        "ok": False, "error": "laptop_diagnostic_source_changed"}
    assert report["next_action"] == "restart_diagnostic_after_source_change"


def test_diagnose_rejects_changed_approval_receipt(tmp_path, monkeypatch):
    flow, _, _, _ = ready(tmp_path)
    original = flow.acceptance
    def raced(world_id, slot=None):
        result = original(world_id, slot)
        return {**result, "receipt_digest": "f" * 64}
    monkeypatch.setattr(flow, "acceptance", raced)
    report = flow.diagnose("lighthouse")
    assert report["checks"]["acceptance"]["ok"] is False
    assert report["next_action"] == "restart_diagnostic_after_source_change"


def test_inspect_holds_writer_lock_during_review_read(tmp_path, monkeypatch):
    flow, _, _, _ = ready(tmp_path)
    original = flow.worlds._read
    blocked = []
    def observe(fd, name):
        if name.endswith(".laptop.review.json"):
            world = flow.worlds.read("lighthouse")
            with pytest.raises(CanonError) as error:
                flow.worlds.publish(dict(world, prompt=world["prompt"] + " raced"),
                                    expected_digest=digest(world))
            blocked.append(error.value.code)
        return original(fd, name)
    monkeypatch.setattr(flow.worlds, "_read", observe)
    assert flow.inspect("lighthouse")["reviewed"]
    assert blocked == ["lease_busy"]
    assert not (tmp_path / "lighthouse.lock").exists()


def test_diagnose_normal_save_still_succeeds(tmp_path):
    flow, _, _, _ = ready(tmp_path)
    flow.create_session("lighthouse", "player")
    report = flow.diagnose("lighthouse", "player")
    assert report["checks"]["source"]["ok"]
    assert report["checks"]["review"]["ok"]
    assert report["checks"]["builder"]["ok"]
    assert report["checks"]["session"]["ok"]
    assert report["checks"]["acceptance"]["ok"]
    assert report["next_action"] == "source_playable_handoff_ready_for_engine_validation"
