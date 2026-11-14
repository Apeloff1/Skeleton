"""Bounded state encoding and simulation history regressions."""
import pytest

from skeleton.economy.gameplay.industry import engine, telemetry
from skeleton.economy.gameplay.industry.tests.conftest import stocked
from skeleton.frontier.payloads import json_snapshot


def test_encoded_escape_expansion_respects_requested_budget():
    assert json_snapshot("é", max_bytes=8) == "é"
    with pytest.raises(ValueError, match="byte budget"):
        json_snapshot("é", max_bytes=7)
    assert json_snapshot({"a": [True, None]}, max_bytes=17) == {"a": [True, None]}
    with pytest.raises(ValueError, match="byte budget"):
        json_snapshot("😀" * 100_000, max_bytes=100_000)


def test_command_retention_is_bounded_and_explicit(monkeypatch):
    monkeypatch.setattr(engine, "MAX_RETAINED_COMMANDS", 4)
    system = stocked()
    for tick in range(20):
        system.advance(tick)
    assert len(system.log) == 4
    assert system.dropped_log_commands == 16
    assert system.log[-1] == {"op": "advance", "tick": 19}


def test_telemetry_retention_preserves_lifetime_totals(monkeypatch):
    monkeypatch.setattr(telemetry, "MAX_TELEMETRY_ROWS", 3)
    value = telemetry.IndustryTelemetry(period_ticks=10)
    for period in range(9):
        value.bump(period * 10, install_fees=1)
        value.close(period, 100, None)
    assert [r["period"] for r in value.rows] == [6, 7, 8]
    assert value.totals["install_fees"] == 9
    assert telemetry.IndustryTelemetry.from_state(value.to_state()).to_state() == value.to_state()
    bad = value.to_state()
    bad["totals"]["install_fees"] = 0
    with pytest.raises(ValueError, match="understate"):
        telemetry.IndustryTelemetry.from_state(bad)
