"""Real shelter economy: finite stock, bounded credits, no buy-sell minting."""
from pathlib import Path
import pytest
from skeleton.game.gameplay.ridge_rescue.schema import parse_world
from skeleton.game.gameplay.ridge_rescue.engine import apply, available_actions, initial_state, RescueError
from skeleton.game.gameplay.ridge_rescue.economy import price, trades, execute_trade, EconomyError

WORLD = parse_world((Path(__file__).resolve().parents[1] / "game/gameplay/ridge_rescue/cinder_ridge_acceptance.json").read_bytes())

def test_trading_requires_shelter_and_owned_item():
    state = initial_state(WORLD)
    state["inventory"]["wood"] = 1
    assert trades(state, False) == []
    with pytest.raises(RescueError):
        apply(WORLD, state, {"verb": "trade", "side": "sell", "item": "wood"})

def test_sell_and_buy_have_no_profitable_round_trip():
    state = initial_state(WORLD)
    state["position"] = list(WORLD.shelter)
    state["inventory"]["wood"] = 1
    initial = state["credits"]
    sold = apply(WORLD, state, {"verb": "trade", "side": "sell", "item": "wood"})
    assert sold["inventory"]["wood"] == 0
    assert sold["credits"] > initial
    assert sold["market"]["wood"] == 3
    assert {"verb": "trade", "side": "buy", "item": "wood"} not in available_actions(WORLD, sold)
    assert price(sold["market"], "buy", "wood") > sold["credits"]

def test_trade_purchase_consumes_credits_and_stock():
    state = initial_state(WORLD)
    state["position"] = list(WORLD.shelter)
    state["credits"] = 10
    bought = apply(WORLD, state, {"verb": "trade", "side": "buy", "item": "ore"})
    assert bought["inventory"]["ore"] == 1
    assert bought["market"]["ore"] == 1
    assert bought["credits"] < 10
    assert state["credits"] == 10

def test_invalid_price_and_stock_refused():
    with pytest.raises(EconomyError):
        price({"wood": -1}, "buy", "wood")
    with pytest.raises(EconomyError):
        execute_trade({"market": {"wood": 2}, "inventory": {"wood": 0}, "credits": 0}, "sell", "wood")
