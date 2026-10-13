"""Counterfactual economic mirror with real, source-verified game outcomes.

The mirror performs bounded competing actions inside the real original economy
engine. Every candidate must pay real material, money and route costs. Outcomes
are evaluated by independent deterministic replay, never invented forecasts,
automatic model-weight promotions or live market recommendations.
"""
from __future__ import annotations

from hashlib import sha256
import json

from .advanced_gameplay_runtime import (
    AdvancedRuntimeError, run_advanced_session, verify_advanced_session,
)
from .advanced_level_scenes import validate_advanced_scene
from .system_editors import make_editor_document

SCHEMA = "skeleton.game_builder.original_economy_mirror.v1"
METRICS = (
    "player_cash", "household_liquidity", "public_treasury",
    "market_inventory", "remaining_reserves", "households_served",
    "manufactured_units", "imported_deliveries", "audited_markets",
    "total_money", "consumption_expenditure", "transport_expenditure",
)
PARETO_GOALS = (
    "households_served", "manufactured_units", "imported_deliveries",
    "household_liquidity", "remaining_reserves", "player_cash",
)


class EconomyMirrorError(ValueError):
    """Counterfactual proof is malformed, impossible or source-mismatched."""


def _digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=True, allow_nan=False).encode()).hexdigest()


def _metrics(state):
    markets = state["markets"]
    result = {
        "player_cash": state["cash"],
        "household_liquidity": sum(m["household_cash"] for m in markets),
        "public_treasury": sum(m["treasury"] for m in markets),
        "market_inventory": sum(sum(m["inventory"]) for m in markets) +
                            sum(state["cargo"]),
        "remaining_reserves": sum(m["reserves"] for m in markets),
        "households_served": state["household_consumed"],
        "manufactured_units": state["manufactured"],
        "imported_deliveries": state["imports_sold"],
        "audited_markets": len(state["audited"]),
        "total_money": (state["cash"] + sum(
            m["household_cash"] + m["treasury"] for m in markets)),
        "consumption_expenditure": state["household_spend"],
        "transport_expenditure": state["transport_fees"],
    }
    return result


def _score(metrics, reference):
    # Fixed *relative* strategy score. Model performance, future price forecasts
    # and market truth cannot be inferred from a single generated game world.
    return (
        8 * (metrics["households_served"] - reference["households_served"]) +
        6 * (metrics["imported_deliveries"] - reference["imported_deliveries"]) +
        4 * (metrics["manufactured_units"] - reference["manufactured_units"]) +
        2 * (metrics["audited_markets"] - reference["audited_markets"]) +
        (metrics["household_liquidity"] - reference["household_liquidity"]) // 20 +
        (metrics["player_cash"] - reference["player_cash"]) // 5 +
        (metrics["remaining_reserves"] - reference["remaining_reserves"]) // 20
    )


def _candidates(horizon, available_goods, market_count):
    proposals = [("passive_reference", [])]
    for name, actions in (
        ("finite_regional_harvest", ["harvest"]),
        ("material_conversion", ["manufacture"]),
        ("production_recovery", ["manufacture", "rest"]),
        ("public_relief_after_demand", ["wait", "wait", "relief"]),
        ("physical_import_delivery", ["buy", "travel:1", "sell"]),
        ("audited_import_delivery", ["audit", "buy", "travel:1", "audit", "sell"]),
        ("earned_cooperation", ["audit", "manufacture", "focus:2", "buy",
                                "travel:1", "audit", "sell", "checkpoint"]),
        ("two_import_deliveries", ["buy", "travel:1", "sell",
                                   "travel:0", "buy", "travel:1", "sell"]),
        ("material_and_relief", ["manufacture", "harvest", "wait",
                                 "wait", "relief"]),
        ("market_recovery", ["harvest", "manufacture", "rest", "wait"]),
    ):
        if len(actions) <= horizon:
            proposals.append((name, actions))
    for good in range(min(available_goods, 8)):
        strategy = [f"focus:{good}", "buy", "travel:1", "sell"]
        if len(strategy) <= horizon:
            proposals.append((f"original_good_{good}_import", strategy))
        # Return routes carry real movement costs and cannot teleport.
        if market_count >= 3:
            strategy = [f"focus:{good}", "buy", "travel:1", "travel:2", "sell"]
            if len(strategy) <= horizon:
                proposals.append((f"original_good_{good}_long_route", strategy))
    return [(name, base + ["wait"] * (horizon - len(base)))
            for name, base in proposals if len(base) <= horizon]


def _dominates(a, b):
    return all(a["metrics"][key] >= b["metrics"][key] for key in PARETO_GOALS) and any(
        a["metrics"][key] > b["metrics"][key] for key in PARETO_GOALS
    )


def analyze_original_economy(scene, settings=None, *,
                             horizon=12, max_scenarios=32):
    if type(horizon) is not int or not 1 <= horizon <= 48:
        raise EconomyMirrorError("original economy mirror horizon must be 1..48 turns")
    if type(max_scenarios) is not int or not 1 <= max_scenarios <= 40:
        raise EconomyMirrorError("original economy evaluation budget must be 1..40 scenarios")
    config = make_editor_document("economy", settings)
    source = validate_advanced_scene(scene, config["settings"])
    if source["editor"] != "economy":
        raise EconomyMirrorError("source must be an original economy world")
    rules = config["settings"]

    reference = run_advanced_session(
        "economy", rules, ["wait"] * horizon, seed=source["seed"], scene=source
    )
    if not verify_advanced_session(reference, rules):
        raise EconomyMirrorError("baseline did not independently replay")
    original = run_advanced_session("economy", rules, seed=source["seed"],
                                     scene=source)["state"]
    initial_money = _metrics(original)["total_money"]
    initial_stock = _metrics(original)["market_inventory"]
    baseline = _metrics(reference["state"])

    evaluated = []
    refused = []
    seen = set()
    attempts = 0
    for name, actions in _candidates(horizon, len(original["active_goods"]),
                                      len(original["markets"])):
        if attempts >= max_scenarios:
            break
        fingerprint = tuple(actions)
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        attempts += 1
        try:
            receipt = run_advanced_session(
                "economy", rules, actions, seed=source["seed"], scene=source
            )
        except AdvancedRuntimeError as exc:
            refused.append({"strategy": name,
                            "reason": "source_action_infeasible",
                            "first_error": str(exc)})
            continue
        if not verify_advanced_session(receipt, rules):
            raise EconomyMirrorError("counterfactual candidate failed independent replay")
        state = receipt["state"]
        metrics = _metrics(state)
        expected_stock = (initial_stock + state["harvested"] -
                          (rules["ore_per_tool"] - 1) * state["manufactured"] -
                          state["household_consumed"])
        if metrics["total_money"] != initial_money:
            raise EconomyMirrorError("real economic counterfactual fabricated cash")
        if metrics["market_inventory"] != expected_stock:
            raise EconomyMirrorError("economic candidate fabricated or lost physical inventory")
        item = {
            "strategy": name, "actions": actions, "metrics": metrics,
            "delta_vs_passive": {key: metrics[key] - baseline[key] for key in METRICS},
            "relative_policy_score": _score(metrics, baseline),
            "gameplay_session_digest": receipt["digest"],
            "gameplay_head_digest": receipt["head_digest"],
            "earned_nonterminal_checkpoint": state["checkpoint"],
            "was_independently_replayed": True,
        }
        evaluated.append(item)

    # The reference is always safe, but if the caller's budget allows just one,
    # it is still one genuine counterfactual rather than a fabricated search.
    if not evaluated:
        raise EconomyMirrorError("bounded mirror could not verify even the baseline")
    pareto = [item["strategy"] for item in evaluated if not any(
        _dominates(other, item) for other in evaluated if other is not item
    )]
    sorted_recommendations = sorted(
        evaluated, key=lambda x: (-x["relative_policy_score"], x["strategy"])
    )
    report = {
        "schema": SCHEMA, "editor": "economy",
        "source_digest": source["digest"], "settings_digest": config["digest"],
        "seed": source["seed"], "horizon": horizon,
        "max_scenarios": max_scenarios, "scenarios_attempted": attempts,
        "scenarios_verified": len(evaluated), "scenarios_infeasible": len(refused),
        "baseline_session_digest": reference["digest"], "baseline_metrics": baseline,
        "evaluated": evaluated, "refused": refused,
        "pareto_frontier": pareto,
        "top_relative_policy": sorted_recommendations[0]["strategy"],
        "modeled_markets": original["active_market_count"],
        "unmodeled_markets": original["unmodeled_market_nodes"],
        "modeled_goods": len(original["active_goods"]),
        "unmodeled_goods": original["unmodeled_good_families"],
        "comparison_is_simulated_game_only": True,
        "weights_promoted": False, "native_hardware_verified": False,
        "production_release_certified": False, "complete_search_proved": False,
    }
    return {**report, "digest": _digest(report)}


def verify_original_economy_mirror(report, scene, settings=None):
    if type(report) is not dict or report.get("schema") != SCHEMA:
        raise EconomyMirrorError("exact deterministic original economy mirror required")
    expected = analyze_original_economy(
        scene, settings, horizon=report.get("horizon"),
        max_scenarios=report.get("max_scenarios")
    )
    if report != expected:
        raise EconomyMirrorError("counterfactual scenarios, rankings or receipts were forged")
    return True


__all__ = [
    "SCHEMA", "METRICS", "PARETO_GOALS", "EconomyMirrorError",
    "analyze_original_economy", "verify_original_economy_mirror",
]
