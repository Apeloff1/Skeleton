"""Contracts for the #807 economy simulation slice (currencies, items, faucets, sinks)."""

from __future__ import annotations

import pytest

from skeleton.simulation.economy.sim import (
    BURN_ACCOUNT,
    MARKET_TAX_SINK,
    VENDOR_FAUCET,
    VENDOR_SINK,
    CurrencySpec,
    EconomySim,
    EconomySimError,
    FaucetSpec,
    ItemSpec,
    SinkSpec,
)


def _sim(**kw):
    sim = EconomySim(
        currencies=[CurrencySpec("isk", supply_cap=kw.pop("cap", None)), CurrencySpec("lp", tradeable=False)],
        items=[
            ItemSpec("ore", "isk", max_stack=100, vendor_buy_price=10, vendor_sell_price=9),
            ItemSpec("blade", "isk", max_stack=1, vendor_buy_price=500, vendor_sell_price=200),
            ItemSpec("badge", "lp", max_stack=1, tradeable=False),
        ],
        faucets=[
            FaucetSpec("bounty", "isk", amount=1_000, cooldown_ticks=10, window_ticks=100, window_cap=3_000),
            FaucetSpec("mission_lp", "lp", amount=50),
        ],
        sinks=[SinkSpec("repair", "isk", flat=25, bps=1_000), SinkSpec("respec", "lp", flat=40)],
        market_tax_bps=kw.pop("tax", 200),
        default_slots=kw.pop("slots", 4),
    )
    for owner in ("ana", "bo"):
        sim.open_account(owner)
    return sim


def test_faucet_mints_with_cooldown_and_window_cap():
    sim = _sim()
    assert sim.grant("bounty", "ana", tick=0) == 1_000
    with pytest.raises(EconomySimError, match="cooldown"):
        sim.grant("bounty", "ana", tick=5)
    sim.grant("bounty", "ana", tick=10)
    sim.grant("bounty", "ana", tick=20)
    with pytest.raises(EconomySimError, match="window cap"):
        sim.grant("bounty", "ana", tick=30)
    assert sim.balance("ana", "isk") == 3_000
    sim.grant("bounty", "ana", tick=100)  # tick-0 grant has rolled out of the window
    assert sim.balance("ana", "isk") == 4_000
    with pytest.raises(EconomySimError, match="backwards"):
        sim.grant("bounty", "ana", tick=50)
    assert sim.grant("bounty", "bo", tick=30) == 1_000  # caps are per owner


def test_supply_cap_fails_closed():
    sim = _sim(cap=1_500)
    sim.grant("bounty", "ana", tick=0)
    with pytest.raises(EconomySimError, match="supply cap"):
        sim.grant("bounty", "bo", tick=0)
    assert sim.balance("bo", "isk") == 0
    assert sim.audit()["ok"]


def test_sink_burns_flat_plus_ceiled_bps():
    sim = _sim()
    sim.grant("bounty", "ana", tick=0)
    assert sim.charge("repair", "ana", base=101) == 25 + 11  # 10% of 101 rounds up
    assert sim.balance("ana", "isk") == 1_000 - 36
    with pytest.raises(EconomySimError, match="insufficient"):
        sim.charge("respec", "ana")
    report = sim.flow_report("isk")
    assert report["burned"] == 36 and report["by_sink"] == {"repair": 36}
    assert report["circulating"] == 964


def test_vendor_loop_is_net_sink_and_respects_inventory():
    sim = _sim(slots=2)
    sim.grant("bounty", "ana", tick=0)
    assert sim.vendor_buy("ana", "ore", 80) == 800
    with pytest.raises(EconomySimError, match="insufficient"):
        sim.vendor_buy("ana", "blade")
    sim.grant("bounty", "ana", tick=10)
    sim.vendor_buy("ana", "blade")
    before = (sim.balance("ana", "isk"), sim.inventory("ana").stacks)
    with pytest.raises(EconomySimError, match="inventory full"):
        sim.vendor_buy("ana", "ore", 30)  # 110 ore needs a second stack slot
    assert (sim.balance("ana", "isk"), sim.inventory("ana").stacks) == before
    assert sim.vendor_sell("ana", "ore", 80) == 720
    with pytest.raises(EconomySimError, match="not enough"):
        sim.vendor_sell("ana", "ore", 1)
    assert sim.inventory("ana").stacks == {"blade": 1}
    report = sim.flow_report("isk")
    assert report["by_sink"] == {VENDOR_SINK: 1_300}
    assert report["by_faucet"] == {"bounty": 2_000, VENDOR_FAUCET: 720}
    assert sim.audit()["ok"]


def test_vendor_spread_rejects_profitable_or_thin_loops():
    with pytest.raises(EconomySimError, match="spread"):
        ItemSpec("gem", "isk", vendor_buy_price=100, vendor_sell_price=100)
    with pytest.raises(EconomySimError, match="spread"):
        ItemSpec("gem", "isk", vendor_buy_price=100, vendor_sell_price=96)
    assert ItemSpec("gem", "isk", vendor_buy_price=100, vendor_sell_price=95).vendor_sell_price == 95


def test_player_trade_moves_money_and_burns_market_tax():
    sim = _sim(tax=250)
    sim.grant("bounty", "bo", tick=0)
    sim.grant("bounty", "ana", tick=0)
    sim.vendor_buy("ana", "ore", 50)
    fill = sim.trade("ana", "bo", "ore", 20, price=401)
    assert fill == {"price": 401, "tax": 11, "seller_net": 390}
    assert sim.balance("bo", "isk") == 1_000 - 401
    assert sim.balance("ana", "isk") == 1_000 - 500 + 390
    assert sim.inventory("bo").stacks == {"ore": 20}
    assert sim.inventory("ana").stacks == {"ore": 30}
    assert sim.flow_report("isk")["by_sink"][MARKET_TAX_SINK] == 11
    assert sim.audit()["ok"]


def test_trade_refusals_leave_books_untouched():
    sim = _sim()
    sim.grant("bounty", "ana", tick=0)
    sim.vendor_buy("ana", "ore", 10)
    sim.open_account("cy", slots=1)
    sim.grant("bounty", "cy", tick=0)
    sim.vendor_buy("cy", "blade")
    digest = sim.digest()
    with pytest.raises(EconomySimError, match="wash"):
        sim.trade("ana", "ana", "ore", 1, price=5)
    with pytest.raises(EconomySimError, match="insufficient"):
        sim.trade("ana", "bo", "ore", 1, price=5)
    with pytest.raises(EconomySimError, match="seller lacks"):
        sim.trade("ana", "cy", "ore", 11, price=5)
    with pytest.raises(EconomySimError, match="buyer inventory full"):
        sim.trade("ana", "cy", "ore", 1, price=5)
    with pytest.raises(EconomySimError, match="not tradeable"):
        sim.trade("ana", "bo", "badge", 1, price=5)
    assert sim.digest() == digest


def test_soft_currency_faucet_and_sink_are_isolated():
    sim = _sim()
    sim.grant("mission_lp", "ana", tick=0)
    sim.grant("mission_lp", "ana", tick=0)  # no cooldown declared
    assert sim.charge("respec", "ana") == 40
    assert sim.balance("ana", "lp") == 60
    assert sim.balance("ana", "isk") == 0
    assert sim.flow_report("isk")["minted"] == 0
    assert sim.flow_report("lp")["sink_to_faucet_bps"] == 4_000


def test_replay_is_deterministic():
    def run():
        sim = _sim()
        sim.grant("bounty", "ana", tick=0)
        sim.vendor_buy("ana", "ore", 40)
        sim.grant("bounty", "bo", tick=3)
        sim.trade("ana", "bo", "ore", 15, price=200)
        sim.charge("repair", "bo", base=200)
        return sim.digest(), sim.flow_report("isk")

    assert run() == run()


def test_spec_and_reference_validation_fails_closed():
    with pytest.raises(EconomySimError):
        CurrencySpec("ISK")
    with pytest.raises(EconomySimError):
        CurrencySpec("isk", supply_cap=0)
    with pytest.raises(EconomySimError, match="remove something"):
        SinkSpec("noop", "isk")
    with pytest.raises(EconomySimError, match="window_ticks"):
        FaucetSpec("f", "isk", amount=1, window_cap=10)
    with pytest.raises(EconomySimError, match="unknown currency"):
        EconomySim([CurrencySpec("isk")], faucets=[FaucetSpec("f", "gold", amount=1)])
    with pytest.raises(EconomySimError, match="duplicate"):
        EconomySim([CurrencySpec("isk"), CurrencySpec("isk")])
    with pytest.raises(EconomySimError, match="reserved"):
        EconomySim([CurrencySpec("isk")], sinks=[SinkSpec(MARKET_TAX_SINK, "isk", flat=1)])
    with pytest.raises(EconomySimError, match="ceiling"):
        EconomySim([CurrencySpec("isk")], market_tax_bps=6_000)
    sim = _sim()
    with pytest.raises(EconomySimError, match="owner"):
        sim.open_account(BURN_ACCOUNT)
    with pytest.raises(EconomySimError, match="no such owner"):
        sim.grant("bounty", "zed", tick=0)
    with pytest.raises(EconomySimError, match="no such faucet"):
        sim.grant("nope", "ana", tick=0)
    with pytest.raises(EconomySimError):
        sim.vendor_buy("ana", "ore", 0)
    with pytest.raises(EconomySimError, match="does not sell"):
        sim.vendor_buy("ana", "badge")


def test_audit_reconciles_burn_account_with_flows():
    sim = _sim()
    sim.grant("bounty", "ana", tick=0)
    sim.charge("repair", "ana", base=0)
    audit = sim.audit()
    assert audit["ok"]
    assert audit["currencies"]["isk"] == {"held": 975, "minted": 1_000, "burned": 25, "balanced": True}
