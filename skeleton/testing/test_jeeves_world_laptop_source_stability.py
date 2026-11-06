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
    calls = 0

    def changed(self, world_id):
        nonlocal calls
        calls += 1
        value = original(self, world_id)
        if calls > 1:
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


def test_malformed_source_digest_fails_closed(tmp_path, monkeypatch):
    ready(tmp_path)
    original = LaptopFlow.diagnose

    def corrupted(self, world_id, slot=None):
        report = original(self, world_id, slot)
        report["source_digest"] = "not-a-sha256"
        return report

    monkeypatch.setattr(LaptopFlow, "diagnose", corrupted)
    result = inspect_recovery(tmp_path, "lighthouse")
    assert result["source_handoff_verified"] is False
    assert result["checks"]["source_digest_integrity"]["error"] == "source_digest_invalid"


def test_invalid_final_snapshot_fails_closed(tmp_path, monkeypatch):
    ready(tmp_path)
    original = LaptopFlow.inspect
    calls = 0

    def malformed(self, world_id):
        nonlocal calls
        calls += 1
        if calls > 1:
            return {"source_digest": None}
        return original(self, world_id)

    monkeypatch.setattr(LaptopFlow, "inspect", malformed)
    result = inspect_recovery(tmp_path, "lighthouse")
    assert result["source_handoff_verified"] is False
    assert result["checks"]["source_stability"]["error"] == "source_changed_during_diagnostic"


def test_non_mapping_final_snapshot_fails_closed(tmp_path, monkeypatch):
    ready(tmp_path)
    original = LaptopFlow.inspect
    calls = 0

    def malformed(self, world_id):
        nonlocal calls
        calls += 1
        if calls > 1:
            return None
        return original(self, world_id)

    monkeypatch.setattr(LaptopFlow, "inspect", malformed)
    result = inspect_recovery(tmp_path, "lighthouse")
    assert result["source_handoff_verified"] is False
    assert result["checks"]["source_stability"]["error"] == "source_recheck_invalid"


def test_diagnostic_checks_are_not_mutated(tmp_path, monkeypatch):
    ready(tmp_path)
    original = LaptopFlow.diagnose
    observed = {}

    def malformed(self, world_id, slot=None):
        report = original(self, world_id, slot)
        observed["checks"] = report["checks"]
        report["checks"]["builder"] = "broken"
        return report

    monkeypatch.setattr(LaptopFlow, "diagnose", malformed)
    result = inspect_recovery(tmp_path, "lighthouse")
    assert result["source_handoff_verified"] is False
    assert result["checks"]["builder"]["error"] == "laptop_recovery_stage_invalid"
    assert observed["checks"]["builder"] == "broken"
    assert result["next_action"] == "inspect_canonical_custody_without_overwriting_artifacts"
