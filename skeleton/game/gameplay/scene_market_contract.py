"""Authored timed delivery contracts on the canonical, replay-verified scene market.

A contract never creates currency or goods: the underlying market reducer is
the only authority for inventory, positions, crafting and delivery. Contracts
award nonspendable campaign score for witnessed delivery milestones.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_market import (
    _advance as advance_market, _bounded, _json, new_market,
    normalize_market, original_market, verify_market,
)
from skeleton.game.gameplay.scene_tile_walk import MAX_STEPS
from skeleton.game.gameplay.scene_travel import SceneTravelError, _id, _limit, _object

SCHEMA = "skeleton.scene_market_contract.v1"
BUNDLE = "skeleton.scene_market_contract_bundle.v1"
MAX_CONTRACTS = 32


def normalize_contract_source(raw: Any) -> dict[str, Any]:
    _bounded(raw, 256 * 1024)
    obj = _object(raw, {
        "schema_version", "market_source", "contracts", "required_contracts",
    }, "market contract source")
    if obj["schema_version"] != SCHEMA:
        raise SceneTravelError("unsupported market contract schema")
    market = normalize_market(obj["market_source"])
    deliveries = {item["delivery_id"] for item in market["deliveries"]}
    contracts = obj["contracts"]
    if type(contracts) is not list or not 1 <= len(contracts) <= MAX_CONTRACTS:
        raise SceneTravelError("invalid market contract count")
    normalized = []
    used_ids: set[str] = set()
    used_deliveries: set[str] = set()
    for raw_contract in contracts:
        item = _object(raw_contract, {
            "contract_id", "delivery_id", "deadline_tick",
            "min_reputation", "reward_score",
        }, "market contract")
        ident = _id(item["contract_id"], "contract id")
        delivery = _id(item["delivery_id"], "contract delivery")
        if ident in used_ids or delivery in used_deliveries:
            raise SceneTravelError("duplicate contract or delivery")
        if delivery not in deliveries:
            raise SceneTravelError("contract must reference authored delivery")
        used_ids.add(ident)
        used_deliveries.add(delivery)
        normalized.append({
            "contract_id": ident, "delivery_id": delivery,
            "deadline_tick": _limit(item["deadline_tick"], "deadline", 1, MAX_STEPS),
            "min_reputation": _limit(
                item["min_reputation"], "minimum reputation", 0, 3200,
            ),
            "reward_score": _limit(item["reward_score"], "score", 1, 1000),
        })
    required = obj["required_contracts"]
    if type(required) is not list or not 1 <= len(required) <= MAX_CONTRACTS:
        raise SceneTravelError("invalid required contract list")
    required_ids = [_id(value, "required contract") for value in required]
    if len(set(required_ids)) != len(required_ids) or not set(required_ids) <= used_ids:
        raise SceneTravelError("required contract not authored or duplicate")
    return {
        "schema_version": SCHEMA, "market_source": market,
        "contracts": sorted(normalized, key=lambda item: item["contract_id"]),
        "required_contracts": sorted(required_ids),
    }


def _save(source: dict[str, Any], state: dict[str, Any],
          parent: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "source_digest": dig(source), "state_digest": dig(state),
        "tick": state["tick"],
        "parent_save_digest": dig(parent) if parent is not None else None,
    }


def new_contract(source: Any) -> dict[str, Any]:
    spec = normalize_contract_source(source)
    market = new_market(spec["market_source"])
    state = {
        "tick": 0, "market": market, "completed": [],
        "score": 0, "phase": "active",
    }
    result = {
        "schema_version": SCHEMA, "source": spec,
        "source_digest": dig(spec), "state": state,
        "state_digest": dig(state), "journal": [],
        "save": _save(spec, state),
    }
    _bounded(result)
    return result


def _advance(session: dict[str, Any], action: Any) -> dict[str, Any]:
    old = session["state"]
    if old["phase"] != "active" or old["tick"] >= MAX_STEPS:
        raise SceneTravelError("contract campaign terminal or turn budget exhausted")
    market = advance_market(old["market"], action)
    tick = market["state"]["tick"]
    if tick != old["tick"] + 1:
        raise SceneTravelError("canonical market turn drift")
    delivered_before = set(old["market"]["state"]["delivered"])
    delivered_after = set(market["state"]["delivered"])
    new_deliveries = delivered_after - delivered_before
    completed = set(old["completed"])
    score = old["score"]
    for contract in session["source"]["contracts"]:
        if (contract["delivery_id"] in new_deliveries
                and tick <= contract["deadline_tick"]
                and market["state"]["reputation"] >= contract["min_reputation"]):
            if contract["contract_id"] in completed:
                raise SceneTravelError("contract reward replayed twice")
            completed.add(contract["contract_id"])
            score += contract["reward_score"]
    required = set(session["source"]["required_contracts"])
    missed = any(
        item["contract_id"] in required
        and item["contract_id"] not in completed
        and tick > item["deadline_tick"]
        for item in session["source"]["contracts"]
    )
    phase = "active"
    if missed or market["state"]["phase"] == "lost":
        phase = "lost"
    elif market["state"]["phase"] == "won":
        phase = "won" if required <= completed else "lost"
    state = {
        "tick": tick, "market": market, "completed": sorted(completed),
        "score": score, "phase": phase,
    }
    event = {
        "sequence": old["tick"],
        "action": market["journal"][-1]["action"],
        "before": session["state_digest"], "after": dig(state),
    }
    event["receipt"] = dig(event)
    result = {
        "schema_version": SCHEMA, "source": session["source"],
        "source_digest": session["source_digest"],
        "state": state, "state_digest": dig(state),
        "journal": [*session["journal"], event],
        "save": _save(session["source"], state, session["save"]),
    }
    _bounded(result)
    return result


def verify_contract(payload: Any) -> dict[str, Any]:
    _bounded(payload)
    obj = _object(payload, {
        "schema_version", "source", "source_digest", "state",
        "state_digest", "journal", "save",
    }, "contract session")
    if obj["schema_version"] != SCHEMA:
        raise SceneTravelError("unsupported contract save schema")
    if type(obj["journal"]) is not list or len(obj["journal"]) > MAX_STEPS:
        raise SceneTravelError("invalid contract replay length")
    rebuilt = new_contract(obj["source"])
    for event in obj["journal"]:
        if type(event) is not dict or "action" not in event:
            raise SceneTravelError("invalid contract journal event")
        rebuilt = _advance(rebuilt, event["action"])
        if rebuilt["journal"][-1] != event:
            raise SceneTravelError("contract replay receipt mismatch")
    if rebuilt != obj:
        raise SceneTravelError("contract source, score or save lineage mismatch")
    if verify_market(rebuilt["state"]["market"]) != rebuilt["state"]["market"]:
        raise SceneTravelError("nested market replay mismatch")
    return rebuilt


def resume_contract(payload: Any, actions: Any) -> dict[str, Any]:
    current = verify_contract(payload)
    if type(actions) is not list or len(actions) + len(current["journal"]) > MAX_STEPS:
        raise SceneTravelError("invalid contract action batch")
    for action in actions:
        current = _advance(current, action)
    return current


def simulate_contract(source: Any, actions: Any) -> dict[str, Any]:
    return resume_contract(new_contract(source), actions)


def export_contract(payload: Any) -> dict[str, Any]:
    session = verify_contract(payload)
    bundle = {
        "schema_version": BUNDLE, "source_digest": session["source_digest"],
        "state_digest": session["state_digest"], "session": session,
    }
    bundle["checksum"] = dig(bundle)
    _bounded(bundle)
    return bundle


def import_contract(payload: Any) -> dict[str, Any]:
    _bounded(payload)
    obj = _object(payload, {
        "schema_version", "source_digest", "state_digest", "session", "checksum",
    }, "contract bundle")
    if obj["schema_version"] != BUNDLE:
        raise SceneTravelError("unsupported contract bundle")
    if obj["checksum"] != dig({k: v for k, v in obj.items() if k != "checksum"}):
        raise SceneTravelError("contract bundle checksum mismatch")
    session = verify_contract(obj["session"])
    if (obj["source_digest"] != session["source_digest"]
            or obj["state_digest"] != session["state_digest"]):
        raise SceneTravelError("contract bundle source or state mismatch")
    return session


def original_contract() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    market, actions = original_market()
    source = {
        "schema_version": SCHEMA, "market_source": market,
        "contracts": [{
            "contract_id": "sanctuary_commission",
            "delivery_id": "sanctuary_seal",
            "deadline_tick": len(actions) + 1,
            "min_reputation": 5, "reward_score": 25,
        }],
        "required_contracts": ["sanctuary_commission"],
    }
    return source, actions


def contract_board(payload: Any) -> dict[str, Any]:
    session = verify_contract(payload)
    state = session["state"]
    board = []
    for item in session["source"]["contracts"]:
        board.append({
            **item, "completed": item["contract_id"] in state["completed"],
            "turns_remaining": max(0, item["deadline_tick"] - state["tick"]),
            "required": item["contract_id"] in session["source"]["required_contracts"],
        })
    result = {
        "schema_version": "skeleton.scene_market_contract_board.v1",
        "source_digest": session["source_digest"],
        "state_digest": session["state_digest"], "tick": state["tick"],
        "phase": state["phase"], "score": state["score"],
        "credits": state["market"]["state"]["credits"],
        "goods": state["market"]["state"]["goods"],
        "reputation": state["market"]["state"]["reputation"],
        "contracts": board,
    }
    result["checksum"] = dig(result)
    _bounded(result)
    return result


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-market-contract")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    for command in ("simulate", "resume"):
        item = sub.add_parser(command)
        item.add_argument("--source-json" if command == "simulate"
                          else "--session-json", required=True)
        item.add_argument("--actions-json", required=True)
    for command in ("verify", "export", "board"):
        sub.add_parser(command).add_argument("--session-json", required=True)
    sub.add_parser("import").add_argument("--bundle-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            source, actions = original_contract()
            result = simulate_contract(source, actions)
        elif args.command == "simulate":
            result = simulate_contract(_json(args.source_json), _json(args.actions_json))
        elif args.command == "resume":
            result = resume_contract(_json(args.session_json), _json(args.actions_json))
        elif args.command == "verify":
            result = verify_contract(_json(args.session_json))
        elif args.command == "export":
            result = export_contract(_json(args.session_json))
        elif args.command == "import":
            result = import_contract(_json(args.bundle_json))
        else:
            result = contract_board(_json(args.session_json))
        _bounded(result)
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (SceneTravelError, ValueError, TypeError, KeyError,
            UnicodeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
