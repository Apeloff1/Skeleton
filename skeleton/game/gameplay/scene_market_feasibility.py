"""Conservative authoring diagnostics for source-bound playable markets.

This is an over-approximation, not a game solver: no impossible campaign may
be labeled proven playable. Only demonstrable missing production chains are
classified as unreachable. Exact winning play requires runtime acceptance.
"""
from __future__ import annotations

from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_market import _bounded, normalize_market

SCHEMA = "skeleton.scene_market_feasibility.v1"


def analyze_market_feasibility(raw: Any) -> dict[str, Any]:
    """Find definitely missing goods chains without simulating arbitrary paths."""
    source = normalize_market(raw)
    total_coin_budget = sum(c["amount"] for c in source["coin_pickups"])
    offers = [
        offer for market in source["markets"] for offer in market["offers"]
    ]
    # An individual offer with price above the entire collectible currency
    # budget is provably unaffordable. Other offers remain only potentially
    # affordable; simultaneous purchases may still exceed the shared budget.
    affordable = [offer for offer in offers
                  if offer["price"] <= total_coin_budget]
    unreachable_offers = sorted(
        offer["offer_id"] for offer in offers
        if offer["price"] > total_coin_budget
    )
    potential_goods = {offer["item_id"] for offer in affordable}
    reachable_recipes: set[str] = set()
    # Fixed point is bounded by authored recipe count. This intentionally
    # ignores stock, route cost and input quantities, so it cannot invent
    # a proof of actual completion.
    for _ in range(len(source["recipes"]) + 1):
        grew = False
        for recipe in source["recipes"]:
            if (recipe["recipe_id"] not in reachable_recipes
                    and set(recipe["inputs"]) <= potential_goods):
                reachable_recipes.add(recipe["recipe_id"])
                before = len(potential_goods)
                potential_goods.update(recipe["output"])
                grew = True
                if len(potential_goods) < before:
                    raise AssertionError("monotonic feasibility closure")
        if not grew:
            break
    blocked_recipes = sorted(
        recipe["recipe_id"] for recipe in source["recipes"]
        if recipe["recipe_id"] not in reachable_recipes
    )
    unavailable = sorted(
        delivery["delivery_id"] for delivery in source["deliveries"]
        if not set(delivery["goods"]) <= potential_goods
    )
    required = set(source["required_deliveries"])
    impossible_required = sorted(required & set(unavailable))
    status = ("definitely_unreachable" if impossible_required
              else "potentially_reachable_unproven")
    report = {
        "schema_version": SCHEMA,
        "source_digest": dig(source),
        "status": status,
        "maximum_collectible_credits": total_coin_budget,
        "individually_unaffordable_offers": unreachable_offers,
        "potential_goods": sorted(potential_goods),
        "potential_recipes": sorted(reachable_recipes),
        "blocked_recipes": blocked_recipes,
        "unavailable_deliveries": unavailable,
        "unreachable_required_deliveries": impossible_required,
        "required_delivery_count": len(required),
        "method": "bounded_overapproximation_not_gameplay_proof",
    }
    report["checksum"] = dig(report)
    _bounded(report)
    return report
