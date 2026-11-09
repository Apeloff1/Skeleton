"""Boot phase budget: timing summary structure and budget evaluation.

These tests never run the real 12-phase boot; phases are stubbed.
"""

from __future__ import annotations

import logging

import pytest

from skeleton.bootstrap import genesis as genesis_mod
from skeleton.bootstrap.genesis import (
    BOOT_BUDGET_MS,
    BOOT_CRITICAL_MS,
    BOOT_PHASES,
    Genesis,
    boot_budget_ms,
    evaluate_boot_budget,
    log_boot_summary,
    record_boot_metrics,
)


class _Capture(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def _stub_genesis() -> Genesis:
    """A Genesis whose phases only record their name (no subsystem wiring)."""

    class _Stub(Genesis):
        pass

    for name in BOOT_PHASES:
        def _phase(self, _name=name):
            self.report.phases.append(_name)
        setattr(_Stub, f"_phase_{name}", _phase)
    return _Stub(seed=1)


def test_boot_phases_match_genesis_phase_methods():
    assert len(BOOT_PHASES) == 12
    assert len(set(BOOT_PHASES)) == 12
    defined = {n[len("_phase_"):] for n in dir(Genesis) if n.startswith("_phase_")}
    assert defined == set(BOOT_PHASES)


def test_default_budgets_match_performance_doc(monkeypatch):
    monkeypatch.delenv("SKL_BOOT_BUDGET_MS", raising=False)
    monkeypatch.delenv("SKL_BOOT_CRITICAL_MS", raising=False)
    assert BOOT_BUDGET_MS == 2_000.0
    assert BOOT_CRITICAL_MS == 5_000.0
    assert boot_budget_ms() == (2_000.0, 5_000.0)


def test_env_overrides_and_invalid_values(monkeypatch):
    monkeypatch.setenv("SKL_BOOT_BUDGET_MS", "750")
    monkeypatch.setenv("SKL_BOOT_CRITICAL_MS", "100")  # below budget -> clamped
    assert boot_budget_ms() == (750.0, 750.0)
    monkeypatch.setenv("SKL_BOOT_BUDGET_MS", "not-a-number")
    monkeypatch.setenv("SKL_BOOT_CRITICAL_MS", "-5")
    assert boot_budget_ms() == (BOOT_BUDGET_MS, BOOT_CRITICAL_MS)


@pytest.mark.parametrize(
    ("total", "status"),
    [(100.0, "ok"), (2_000.0, "ok"), (2_000.5, "over_budget"), (5_000.0, "over_budget"), (5_001.0, "critical")],
)
def test_evaluate_boot_budget_status(total, status):
    summary = evaluate_boot_budget(
        {"kernel": 1.0, "support": 2.0}, total_ms=total, budget_ms=2_000.0, critical_ms=5_000.0,
    )
    assert summary["status"] == status
    assert summary["total_ms"] == total


def test_evaluate_boot_budget_structure_and_slowest():
    summary = evaluate_boot_budget(
        {"foundation": 10.0, "support": 2_500.1234, "cortex": 5.0},
        budget_ms=2_000.0,
        critical_ms=5_000.0,
    )
    assert set(summary) == {
        "status", "total_ms", "budget_ms", "critical_ms",
        "phase_ms", "slowest_phase", "slowest_phase_ms",
    }
    assert summary["total_ms"] == pytest.approx(2_515.123, abs=1e-3)
    assert summary["status"] == "over_budget"
    assert summary["slowest_phase"] == "support"
    assert summary["slowest_phase_ms"] == pytest.approx(2_500.123, abs=1e-3)
    assert list(summary["phase_ms"]) == ["foundation", "support", "cortex"]


def test_evaluate_boot_budget_empty_phases():
    summary = evaluate_boot_budget({}, budget_ms=1.0, critical_ms=2.0)
    assert summary["status"] == "ok"
    assert summary["total_ms"] == 0.0
    assert summary["slowest_phase"] is None


@pytest.mark.parametrize(
    ("status", "level"),
    [("ok", logging.INFO), ("over_budget", logging.WARNING), ("critical", logging.ERROR)],
)
def test_log_boot_summary_levels_and_single_line(status, level):
    log = logging.getLogger("test.genesis.boot_budget." + status)
    log.setLevel(logging.DEBUG)
    log.propagate = False
    cap = _Capture()
    log.addHandler(cap)
    try:
        summary = {
            "status": status, "total_ms": 12.0, "budget_ms": 2_000.0,
            "critical_ms": 5_000.0, "phase_ms": {"kernel": 4.0, "cortex": 8.0},
            "slowest_phase": "cortex", "slowest_phase_ms": 8.0,
        }
        assert log_boot_summary(summary, log=log) == level
    finally:
        log.removeHandler(cap)
    assert len(cap.records) == 1
    record = cap.records[0]
    assert record.levelno == level
    message = record.getMessage()
    assert "total_ms=12.0" in message
    assert "kernel=4.0" in message and "cortex=8.0" in message
    assert record.boot_timing["status"] == status


def test_boot_times_every_phase_in_order_without_changing_payload(monkeypatch):
    monkeypatch.delenv("SKL_BOOT_BUDGET_MS", raising=False)
    monkeypatch.delenv("SKL_BOOT_CRITICAL_MS", raising=False)
    seen: list[dict] = []
    monkeypatch.setattr(genesis_mod, "log_boot_summary", lambda summary, **_: seen.append(dict(summary)))

    g = _stub_genesis().boot()

    assert g.report.phases == list(BOOT_PHASES)
    assert list(g.report.phase_ms) == list(BOOT_PHASES)
    assert all(ms >= 0.0 for ms in g.report.phase_ms.values())
    assert g.report.total_ms is not None
    assert g.report.total_ms + 1e-3 >= sum(g.report.phase_ms.values()) - 1e-3
    assert g.report.timing["status"] == "ok"
    assert len(seen) == 1 and seen[0]["phase_ms"] == g.report.phase_ms
    # Timings stay off the journaled bus payload (replay determinism).
    assert set(g.report.to_dict()) == {"phases", "wired", "invariants_registered"}


def test_boot_over_budget_is_fail_soft(monkeypatch):
    monkeypatch.setenv("SKL_BOOT_BUDGET_MS", "0.000001")
    monkeypatch.setenv("SKL_BOOT_CRITICAL_MS", "0.000002")
    seen: list[dict] = []
    monkeypatch.setattr(genesis_mod, "log_boot_summary", lambda summary, **_: seen.append(dict(summary)))
    g = _stub_genesis()

    def _slow_support(self=g):
        self.report.phases.append("support")
        import time as _t
        _t.sleep(0.001)

    monkeypatch.setattr(g, "_phase_support", _slow_support)
    g.boot()  # must not raise
    assert g.report.timing["status"] == "critical"
    assert g.report.timing["slowest_phase"] == "support"
    assert seen[0]["status"] == "critical"


def test_record_boot_metrics_publishes_histogram_and_gauge():
    class _Metrics:
        def __init__(self) -> None:
            self.calls: list[tuple] = []

        def histogram(self, name, value, labels=None):
            self.calls.append(("histogram", name, value, labels))

        def gauge(self, name, value, labels=None):
            self.calls.append(("gauge", name, value, labels))

        def increment(self, name, value=1.0, labels=None):
            self.calls.append(("increment", name, value, labels))

    g = _stub_genesis()
    g.report.phase_ms = {"kernel": 1.5, "cortex": 2.5}
    g.report.total_ms = 4.0
    g.report.timing = {"status": "over_budget"}
    metrics = _Metrics()
    assert record_boot_metrics(metrics, g.report) is True
    assert ("histogram", "genesis_boot_phase_ms", 1.5, {"phase": "kernel"}) in metrics.calls
    assert ("histogram", "genesis_boot_phase_ms", 2.5, {"phase": "cortex"}) in metrics.calls
    assert ("gauge", "genesis_boot_total_ms", 4.0, None) in metrics.calls
    assert ("increment", "genesis_boot_budget_exceeded_total", 1.0, {"status": "over_budget"}) in metrics.calls

    untimed = _Metrics()
    assert record_boot_metrics(untimed, _stub_genesis().report) is False
    assert untimed.calls == []


def test_record_boot_metrics_against_real_collector():
    from skeleton.observability import MetricsCollector

    g = _stub_genesis().boot()
    collector = MetricsCollector()
    assert record_boot_metrics(collector, g.report) is True
    snap = collector.snapshot()
    assert any("genesis_boot_total_ms" in key for key in snap["gauges"])
    phase_keys = [key for key in snap["histograms"] if "genesis_boot_phase_ms" in key]
    assert len(phase_keys) == len(BOOT_PHASES)
