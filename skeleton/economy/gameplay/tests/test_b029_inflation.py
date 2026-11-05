"""B029: anti-inflation PI controller over circulating supply."""

from __future__ import annotations

import pytest

from skeleton.economy.gameplay.inflation import InflationController
from skeleton.economy.gameplay.tests.conftest import build_econ
from skeleton.simulation.economy.sim import EconomySimError


def test_supply_growth_raises_tax_and_throttles_faucets():
    econ = build_econ()
    ctl = InflationController("gold", "stabilizer")
    econ.grant("daily", "ana", tick=0)
    assert ctl.observe(econ)["tax_bps"] == 200  # first epoch only records a baseline
    econ.grant("bounty", "ana", tick=1)  # +10% supply
    state = ctl.observe(econ)
    assert state["growth_bps"] == 1_000
    assert state["tax_bps"] == 200 + 500 + 100
    assert ctl.faucet_scale_bps == 7_500
    assert ctl.apply_tax(econ, "ana", 1_000) == 80
    assert econ.flow_report("gold")["by_sink"]["stabilizer"] == 80
    assert econ.audit()["ok"]


def test_deflation_drops_tax_to_floor_and_faucets_stay_full():
    econ = build_econ()
    ctl = InflationController("gold", "stabilizer", min_tax_bps=0)
    econ.grant("daily", "ana", tick=0)
    ctl.observe(econ)
    econ.charge_amount("stabilizer", "ana", 500)  # -50%
    assert ctl.observe(econ)["tax_bps"] == 0
    assert ctl.faucet_scale_bps == 10_000
    assert ctl.apply_tax(econ, "ana", 1_000) == 0


def test_anti_windup_and_clamps():
    econ = build_econ()
    ctl = InflationController("gold", "stabilizer", integral_limit=3_000)
    econ.grant("daily", "ana", tick=0)
    ctl.observe(econ)
    econ.grant("daily", "ana", tick=100)  # +100%
    assert ctl.observe(econ)["tax_bps"] == 2_000  # clamped at max
    assert ctl.integral == 3_000  # clamped integral
    assert ctl.faucet_scale_bps == 2_500
    for _ in range(3):  # flat supply: integral does not keep growing
        ctl.observe(econ)
    assert ctl.integral == 3_000
    assert ctl.tax_bps == 200 + 300  # P term gone, I term bounded


def test_controller_validation():
    econ = build_econ()
    with pytest.raises(EconomySimError, match="declared sink"):
        InflationController("honor", "stabilizer").bind(econ)
    with pytest.raises(EconomySimError, match="min <= base"):
        InflationController("gold", "stabilizer", base_tax_bps=5_000, max_tax_bps=2_000)
    with pytest.raises(EconomySimError):
        InflationController("gold", "stabilizer", target_growth_bps=True)
