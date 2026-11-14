"""Deterministic finite shelter market: source-bound resources, no credit creation."""
from __future__ import annotations

BASE = {"wood": 2, "ore": 3, "herb": 2}
STOCK_INITIAL = {"wood": 2, "ore": 2, "herb": 2}
MAX_STOCK = 16
MAX_CREDITS = 999

class EconomyError(ValueError):
    pass

def price(stock: dict[str, int], side: str, item: str) -> int:
    if item not in BASE or side not in {"buy", "sell"}:
        raise EconomyError("invalid market quote")
    quantity = stock[item]
    if type(quantity) is not int or not 0 <= quantity <= MAX_STOCK:
        raise EconomyError("invalid market stock")
    if side == "sell":
        return max(1, BASE[item] - 1)
    return BASE[item] + max(0, 3 - quantity)

def trades(state: dict, at_shelter: bool) -> list[dict]:
    if not at_shelter or state["status"] != "playing":
        return []
    choices = []
    for item in sorted(BASE):
        quantity = state["market"][item]
        if state["inventory"][item] > 0 and quantity < MAX_STOCK and state["credits"] + price(state["market"], "sell", item) <= MAX_CREDITS:
            choices.append({"verb": "trade", "side": "sell", "item": item})
        if quantity > 0 and state["credits"] >= price(state["market"], "buy", item):
            choices.append({"verb": "trade", "side": "buy", "item": item})
    return choices

def execute_trade(state: dict, side: str, item: str) -> None:
    if side not in {"buy", "sell"} or item not in BASE:
        raise EconomyError("invalid trade")
    cost = price(state["market"], side, item)
    if side == "buy":
        if state["market"][item] <= 0 or state["credits"] < cost:
            raise EconomyError("insufficient stock or credits")
        state["credits"] -= cost
        state["market"][item] -= 1
        state["inventory"][item] += 1
    else:
        if state["inventory"][item] <= 0 or state["market"][item] >= MAX_STOCK or state["credits"] + cost > MAX_CREDITS:
            raise EconomyError("insufficient item or market capacity")
        state["inventory"][item] -= 1
        state["market"][item] += 1
        state["credits"] += cost
