"""Automation pause/quarantine fences Actions queue admission and relief."""
from __future__ import annotations

import json
from dataclasses import replace
from unittest.mock import patch

import pytest

from skeleton.automation.automation_safety import (
    AutomationSafety, AutomationSafetyError,
)
from skeleton.automation.traffic_manager import (
    TrafficDecision, TrafficManagerError,
    enforce_operator_safety,
    main,
)


def decision(*, force=True) -> TrafficDecision:
    return TrafficDecision(
        admit=True,
        reason="forced" if force else "capacity",
        lane="supervisor",
        base_sha="a" * 40,
        observed_at=1720000000,
        decision_fingerprint="b" * 64,
        active_runs=17,
        queued_runs=13,
        critical_active=5,
        managed_active=3,
        recent_failures=2,
        blocked_pull_requests=9,
        authorized_issues=4,
        seconds_since_success=900,
        stale_queued_runs=7,
        provider_tombstones=1,
        oldest_queued_age_seconds=2400,
        inventory_saturated=False,
        relieve=True,
        relief_reason="stale-queue-pressure",
        forced=force,
    )


@pytest.mark.parametrize(
    ("safety", "reason"),
    [
        (AutomationSafety(paused=True, quarantined=False, reason="maintenance"), "operator-paused"),
        (AutomationSafety(paused=False, quarantined=True, reason="incident"), "operator-quarantined"),
        (AutomationSafety(paused=True, quarantined=True), "operator-quarantined"),
    ],
)
def test_hold_fences_force_admission_and_queue_relief(safety, reason):
    original = decision()
    stopped = enforce_operator_safety(original, safety)
    assert stopped.admit is False and stopped.relieve is False
    assert stopped.forced is False and stopped.lane == "hold"
    assert stopped.reason == reason and stopped.relief_reason == "operator-hold"
    assert stopped.decision_fingerprint == original.decision_fingerprint
    assert stopped.base_sha == original.base_sha
    assert stopped.active_runs == original.active_runs
    assert stopped.queued_runs == original.queued_runs
    assert stopped.stale_queued_runs == original.stale_queued_runs
    assert original.admit and original.relieve  # immutable input unchanged


def test_active_controls_leave_existing_decision_unchanged():
    original = decision()
    assert enforce_operator_safety(original, AutomationSafety(False, False)) is original


@pytest.mark.parametrize("bad", [None, {}, True, "paused"])
def test_invalid_safety_record_never_falls_through(bad):
    with pytest.raises(TrafficManagerError):
        enforce_operator_safety(decision(), bad)


def test_entrypoint_force_cannot_override_operator_pause(monkeypatch, capsys):
    monkeypatch.setenv("TRAFFIC_FORCE", "1")
    monkeypatch.setenv("SKELETON_AUTOMATION_PAUSED", "true")
    monkeypatch.delenv("SKELETON_AUTOMATION_QUARANTINED", raising=False)
    monkeypatch.setattr("sys.argv", ["traffic_manager"])
    with (
        patch("skeleton.automation.traffic_manager.observe", return_value=object()) as observed,
        patch("skeleton.automation.traffic_manager.evaluate", return_value=decision()) as evaluated,
        patch("skeleton.automation.traffic_manager.write_step_summary") as summary,
    ):
        assert main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert not payload["admit"] and not payload["relieve"] and not payload["forced"]
    assert payload["reason"] == "operator-paused"
    assert payload["decision_fingerprint"] == "b" * 64
    observed.assert_called_once()
    assert evaluated.call_args.kwargs["force"] is True
    assert not summary.call_args.args[0].admit


def test_malformed_hold_fails_before_traffic_observation(monkeypatch):
    monkeypatch.setenv("TRAFFIC_FORCE", "1")
    monkeypatch.setenv("SKELETON_AUTOMATION_PAUSED", "invalid")
    monkeypatch.delenv("SKELETON_AUTOMATION_QUARANTINED", raising=False)
    monkeypatch.setattr("sys.argv", ["traffic_manager"])
    with patch("skeleton.automation.traffic_manager.observe") as observed:
        with pytest.raises(AutomationSafetyError):
            main()
    observed.assert_not_called()
