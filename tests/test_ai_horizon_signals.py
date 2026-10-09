from __future__ import annotations

import pytest

from skeleton.ai.runtime.provenance.horizon_signals import (
    SIGNAL_SCHEMA,
    SIGNALS,
    HorizonSignal,
    horizon_manifest,
    signals_for_decade,
)


def test_horizon_signals_cover_every_decade_from_2020s_through_2090s() -> None:
    assert {signal.decade for signal in SIGNALS} == set(range(2020, 2100, 10))
    assert all(len(signals_for_decade(decade)) >= 2 for decade in range(2020, 2100, 10))


def test_horizon_signal_ids_are_unique_and_decade_namespaced() -> None:
    ids = [signal.signal_id for signal in SIGNALS]
    assert len(ids) == len(set(ids))
    assert all(signal.signal_id.startswith(f"h{signal.decade}.") for signal in SIGNALS)


def test_horizon_manifest_is_deterministic_and_self_describing() -> None:
    first = horizon_manifest()
    second = horizon_manifest()
    assert first == second
    assert first["schema"] == SIGNAL_SCHEMA
    assert [row["signal_id"] for row in first["signals"]] == [signal.signal_id for signal in SIGNALS]


def test_horizon_signal_rejects_cross_decade_identity() -> None:
    with pytest.raises(ValueError, match="namespaced"):
        HorizonSignal(2030, "h2040.bad", "contracts", "requirement", "compatibility")


def test_unknown_decade_fails_closed() -> None:
    with pytest.raises(ValueError, match="unsupported decade"):
        signals_for_decade(2100)
