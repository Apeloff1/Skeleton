"""Recovery diagnostics must reject canonical source changes between stages."""
from __future__ import annotations

from skeleton.jeeves.worlds.laptop_flow import LaptopFlow
from skeleton.jeeves.worlds.laptop_recovery_check import inspect_recovery
from skeleton.jeeves.worlds.world_canon import CanonError
from skeleton.testing.test_jeeves_world_laptop_flow import ready


def test_stable_source_reports_second_snapshot(tmp_path):
    ready(tmp_path)
    result = inspect_recovery(tmp_path, "lighthouse")
    assert result["checks"]["source_stability"] == {"ok": True}
    assert result["source_handoff_verified"] is True


def test_changed_source_during_diagnostic_fails_closed(tmp_path, monkeypatch):
    ready(tmp_path)
    original = LaptopFlow.inspect

    def changed(self, world_id):
        value = original(self, world_id)
        value["source_digest"] = "0" * 64
        return value

    monkeypatch.setattr(LaptopFlow, "inspect", changed)
    result = inspect_recovery(tmp_path, "lighthouse")
    assert result["source_handoff_verified"] is False
    assert result["checks"]["source_stability"]["error"] == "source_changed_during_diagnostic"
    assert result["next_action"] == "restart_diagnostic_after_source_change"


def test_source_recheck_lock_failure_fails_closed(tmp_path, monkeypatch):
    ready(tmp_path)
    original = LaptopFlow.inspect
    calls = 0

    def busy(self, world_id):
        nonlocal calls
        calls += 1
        if calls > 1:
            raise CanonError("lease_busy")
        return original(self, world_id)

    monkeypatch.setattr(LaptopFlow, "inspect", busy)
    result = inspect_recovery(tmp_path, "lighthouse")
    assert result["source_handoff_verified"] is False
    assert result["checks"]["source_stability"]["error"] == "lease_busy"
