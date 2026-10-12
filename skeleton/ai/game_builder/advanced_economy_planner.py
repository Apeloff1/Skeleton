"""Bounded original-market director; earns milestones only via real gameplay replay.

No model weights, source assets, bank balances or native executables are altered.
The director explores a deterministic route and produces independently verified
evidence, or an honestly inconclusive partial plan.
"""
from __future__ import annotations

from hashlib import sha256
import json

from .advanced_gameplay_runtime import (
    run_advanced_session, verify_advanced_session,
)
from .advanced_level_scenes import validate_advanced_scene
from .advanced_economy_runtime import (
    EconomyActionError, start, apply_scene, step,
)
from .system_editors import make_editor_document

SCHEMA = "skeleton.game_builder.original_trade_plan.v1"


class EconomyPlanningError(ValueError):
    """Unsafe original plan, incompatible scene or altered replay receipt."""


def _digest(obj):
    return sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=True, allow_nan=False).encode()).hexdigest()


def plan_original_trade(scene, settings=None, *, max_actions=100, retire=False):
    if type(max_actions) is not int or not 1 <= max_actions <= 128:
        raise EconomyPlanningError("economy director must have a finite action budget")
    if type(retire) is not bool:
        raise EconomyPlanningError("retirement selection must be exact boolean")
    config = make_editor_document("economy", settings)
    rules = config["settings"]
    authored = validate_advanced_scene(scene, rules)
    if authored["editor"] != "economy":
        raise EconomyPlanningError("an original trade scene is required")
    state = start(rules, authored["seed"])
    apply_scene(state, rules, authored["layout"])
    commands = []

    def act(command):
        if len(commands) >= max_actions:
            raise EconomyActionError("constrained economy plan action budget exhausted")
        step(state, rules, command)
        commands.append(command)

    try:
        act("audit")
        act("manufacture")
        act("focus:2")
        for i in range(state["trade_goal"]):
            # Trade all deliveries through an actual cargo and paid local bid.
            # The source model may run out of warehouse stock or cash; in that
            # case the plan is inconclusive, never a minted perfect route.
            act("buy")
            act("travel:1")
            if i == 0:
                act("audit")
            act("sell")
            if i + 1 < state["trade_goal"]:
                act("travel:0")
        act("checkpoint")
        if retire:
            act("retire")
        if not state["checkpoint"] or (retire and not state["retired"]):
            raise EconomyActionError("trade objective was not earned")
        live = run_advanced_session("economy", rules, commands,
                                    seed=authored["seed"], scene=authored)
        if not live["state"]["checkpoint"] or (
            retire and not live["state"]["retired"]
        ) or not verify_advanced_session(live, rules):
            raise EconomyPlanningError("independent original-trade replay failed")
        report = {
            "schema": SCHEMA, "status": "replay_verified_trade",
            "source_digest": authored["digest"], "settings_digest": config["digest"],
            "actions": list(commands), "action_count": len(commands),
            "imported_deliveries": live["state"]["imports_sold"],
            "manufactured_units": live["state"]["manufactured"],
            "verified_audits": list(live["state"]["audited"]),
            "final_cash": live["state"]["cash"],
            "final_treasuries": [n["treasury"] for n in live["state"]["markets"]],
            "still_playable": not live["state"]["finished"],
            "retired": live["state"]["retired"],
            "replay_digest": live["digest"],
            "max_actions": max_actions, "requested_retirement": retire,
            "independent_replay_verified": True,
            "exhaustive_search_proved": False, "native_hardware_verified": False,
            "publication_certified": False,
        }
        return {**report, "digest": _digest(report)}
    except EconomyActionError as exc:
        # Every inconclusive receipt exposes exactly what was attempted, with
        # no fake independent replay or claimed hardware/source certification.
        report = {
            "schema": SCHEMA, "status": "inconclusive_bounded_trade",
            "source_digest": authored["digest"], "settings_digest": config["digest"],
            "actions": [], "action_count": 0,
            "best_partial_actions": list(commands),
            "best_partial_audits": list(state["audited"]),
            "best_partial_imports": state["imports_sold"],
            "limitation": str(exc), "max_actions": max_actions,
            "requested_retirement": retire,
            "independent_replay_verified": False,
            "exhaustive_search_proved": False, "native_hardware_verified": False,
            "publication_certified": False,
        }
        return {**report, "digest": _digest(report)}


def verify_original_trade_plan(record, scene, settings=None):
    if type(record) is not dict or record.get("schema") != SCHEMA:
        raise EconomyPlanningError("exact original trading-plan evidence required")
    rebuilt = plan_original_trade(
        scene, settings, max_actions=record.get("max_actions"),
        retire=record.get("requested_retirement"),
    )
    if rebuilt != record:
        raise EconomyPlanningError("market source, action or trade outcome was forged")
    return True


__all__ = ["SCHEMA", "EconomyPlanningError",
           "plan_original_trade", "verify_original_trade_plan"]
