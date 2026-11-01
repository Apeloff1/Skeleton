"""Deterministic weather-caravan trade settlement on canonical deliveries.

The weather/delivery engines retain authority over movement, inventory,
deadlines and gross earned rewards. This economic layer applies authored
commissions and earned reputation to replay-verified delivery outcomes.
It cannot invent a delivery or claim more currency than the canonical engine.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_travel import SceneTravelError, _id, _json, _limit, _object
from skeleton.game.gameplay.scene_weather import _export
from skeleton.game.gameplay.scene_weather_delivery import (
    advance_deliveries, new_deliveries, normalize_deliveries,
    original_deliveries, verify_deliveries,
)

SCHEMA = "skeleton.weather_market.v1"
PACKAGE_SCHEMA = "skeleton.weather_market_package.v1"
MAX_MARKET_STEPS = 64
MAX_FEE_BPS = 5000
MAX_REPUTATION_BONUS = 100
MAX_REPUTATION = 1600


def normalize_market(raw: Any) -> dict[str, Any]:
    obj = _object(raw, {"schema_version", "deliveries", "contracts"},
                  "weather market source")
    if obj["schema_version"] != SCHEMA:
        raise SceneTravelError("unsupported weather market schema")
    deliveries = normalize_deliveries(obj["deliveries"])
    contracts = obj["contracts"]
    required_ids = {
        entry["delivery_id"] for entry in deliveries["deliveries"]
    }
    if type(contracts) is not list or len(contracts) != len(required_ids):
        raise SceneTravelError("market requires one contract per delivery")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_entry in contracts:
        item = _object(raw_entry, {
            "delivery_id", "commission_bps", "early_by_ticks",
            "early_reputation",
        }, "market contract")
        delivery_id = _id(item["delivery_id"], "market delivery_id")
        if delivery_id not in required_ids or delivery_id in seen:
            raise SceneTravelError("unknown or duplicate market delivery")
        seen.add(delivery_id)
        normalized.append({
            "delivery_id": delivery_id,
            "commission_bps": _limit(
                item["commission_bps"], "commission_bps", 0, MAX_FEE_BPS,
            ),
            "early_by_ticks": _limit(
                item["early_by_ticks"], "early_by_ticks", 1, MAX_MARKET_STEPS,
            ),
            "early_reputation": _limit(
                item["early_reputation"], "early_reputation",
                0, MAX_REPUTATION_BONUS,
            ),
        })
    normalized.sort(key=lambda item: item["delivery_id"])
    result = {"schema_version": SCHEMA, "deliveries": deliveries,
              "contracts": normalized}
    _export(result)
    return result


def _save(source: dict[str, Any], delivery: dict[str, Any],
          state: dict[str, Any], parent: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "schema_version": "skeleton.weather_market_save.v1",
        "source_digest": dig(source),
        "delivery_save_digest": dig(delivery["save"]),
        "state_digest": dig(state),
        "tick": len(state["journal"]),
        "parent_digest": None if parent is None else dig(parent),
    }


def _snapshot(source: dict[str, Any], delivery: dict[str, Any],
              state: dict[str, Any], parent: dict[str, Any] | None) -> dict[str, Any]:
    result = {
        "schema_version": SCHEMA, "source": source,
        "source_digest": dig(source), "delivery_session": delivery,
        "state": state, "state_digest": dig(state),
        "save": _save(source, delivery, state, parent),
    }
    _export(result)
    return result


def new_market(source: Any) -> dict[str, Any]:
    spec = normalize_market(source)
    delivery = new_deliveries(spec["deliveries"])
    state = {
        "phase": "active", "gross": 0, "fees": 0, "net": 0,
        "reputation": 0, "journal": [],
    }
    return _snapshot(spec, delivery, state, None)


def _advance(snapshot: dict[str, Any], action: Any) -> dict[str, Any]:
    if snapshot["state"]["phase"] != "active":
        raise SceneTravelError("weather market journey already terminal")
    if len(snapshot["state"]["journal"]) >= MAX_MARKET_STEPS:
        raise SceneTravelError("weather market step budget exceeded")
    before = snapshot["delivery_session"]
    delivery = advance_deliveries(before, action)
    step = delivery["state"]["journal"][-1]
    contracts = {item["delivery_id"]: item
                 for item in snapshot["source"]["contracts"]}
    definitions = {
        item["delivery_id"]: item
        for item in snapshot["source"]["deliveries"]["deliveries"]
    }
    tick = delivery["weather_session"]["state"]["tick"]
    previous = snapshot["state"]
    gross, fees, reputation = (
        previous["gross"], previous["fees"], previous["reputation"]
    )
    settlements: list[dict[str, Any]] = []
    for change in step["changes"]:
        delivery_id = change["delivery_id"]
        contract = contracts[delivery_id]
        definition = definitions[delivery_id]
        status = change["status"]
        amount = change["reward"]
        if status not in ("delivered", "expired"):
            raise SceneTravelError("unsupported delivery market outcome")
        if status == "expired" and amount != 0:
            raise SceneTravelError("expired market delivery earned reward")
        fee = amount * contract["commission_bps"] // 10000
        net = amount - fee
        early = (
            status == "delivered"
            and definition["deadline"] - tick >= contract["early_by_ticks"]
        )
        bonus = contract["early_reputation"] if early else 0
        gross += amount
        fees += fee
        reputation += bonus
        if reputation > MAX_REPUTATION:
            raise SceneTravelError("weather market reputation budget exceeded")
        settlements.append({
            "delivery_id": delivery_id, "status": status,
            "arrival_tick": tick,
            "gross": amount, "fee": fee, "net": net,
            "early": early, "reputation": bonus,
        })
    state = {
        "phase": delivery["state"]["phase"],
        "gross": gross, "fees": fees, "net": gross - fees,
        "reputation": reputation,
        "journal": [*previous["journal"], {
            "action": step["action"],
            "delivery_state_digest": delivery["state_digest"],
            "settlements": settlements,
            "gross_after": gross, "fees_after": fees,
            "net_after": gross - fees, "reputation_after": reputation,
        }],
    }
    if gross != delivery["state"]["earned"]:
        raise SceneTravelError("weather market gross reward mismatch")
    return _snapshot(snapshot["source"], delivery, state, snapshot["save"])


def verify_market(raw: Any) -> dict[str, Any]:
    obj = _object(raw, {
        "schema_version", "source", "source_digest", "delivery_session",
        "state", "state_digest", "save",
    }, "weather market session")
    if obj["schema_version"] != SCHEMA:
        raise SceneTravelError("unsupported weather market save schema")
    _export(obj)
    journal = obj["state"].get("journal") if type(obj["state"]) is dict else None
    if type(journal) is not list or len(journal) > MAX_MARKET_STEPS:
        raise SceneTravelError("invalid weather market journal")
    rebuilt = new_market(obj["source"])
    for item in journal:
        if type(item) is not dict or "action" not in item:
            raise SceneTravelError("malformed weather market journal entry")
        rebuilt = _advance(rebuilt, item["action"])
    if rebuilt != obj:
        raise SceneTravelError("weather market replay or save lineage mismatch")
    return rebuilt


def advance_market(raw: Any, action: Any) -> dict[str, Any]:
    return _advance(verify_market(raw), action)


def resume_market(raw: Any, actions: Any) -> dict[str, Any]:
    session = verify_market(raw)
    if (type(actions) is not list
            or len(session["state"]["journal"]) + len(actions) > MAX_MARKET_STEPS):
        raise SceneTravelError("weather market action batch exceeds step budget")
    for action in actions:
        session = _advance(session, action)
    return verify_market(session)


def market_summary(raw: Any) -> dict[str, Any]:
    session = verify_market(raw)
    settlements = {
        item["delivery_id"]: item
        for step in session["state"]["journal"] for item in step["settlements"]
    }
    return {
        "schema_version": SCHEMA,
        "source_digest": session["source_digest"],
        "state_digest": session["state_digest"],
        "phase": session["state"]["phase"],
        "gross": session["state"]["gross"],
        "fees": session["state"]["fees"],
        "net": session["state"]["net"],
        "reputation": session["state"]["reputation"],
        "contracts": [
            {"delivery_id": contract["delivery_id"],
             "status": settlements.get(contract["delivery_id"], {}).get(
                 "status", "pending"),
             "settlement": settlements.get(contract["delivery_id"])}
            for contract in session["source"]["contracts"]
        ],
    }


def package_market(raw: Any) -> dict[str, Any]:
    verified = verify_market(raw)
    report = {
        "schema_version": PACKAGE_SCHEMA,
        "snapshot": verified,
        "manifest": {
            "source_digest": verified["source_digest"],
            "state_digest": verified["state_digest"],
            "delivery_save_digest": dig(verified["delivery_session"]["save"]),
            "phase": verified["state"]["phase"],
            "gross": verified["state"]["gross"],
            "fees": verified["state"]["fees"],
            "net": verified["state"]["net"],
            "reputation": verified["state"]["reputation"],
            "tick": len(verified["state"]["journal"]),
        },
        "claim": "offline_replay_checked_not_authenticated",
    }
    report["receipt"] = dig(report)
    _export(report)
    return report


def verify_market_package(raw: Any) -> dict[str, Any]:
    obj = _object(raw, {
        "schema_version", "snapshot", "manifest", "claim", "receipt",
    }, "weather market package")
    if (obj["schema_version"] != PACKAGE_SCHEMA
            or obj["claim"] != "offline_replay_checked_not_authenticated"):
        raise SceneTravelError("unsupported weather market package")
    _export(obj)
    expected = package_market(obj["snapshot"])
    if expected != obj:
        raise SceneTravelError("weather market package or replay mismatch")
    return expected


def original_market() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    deliveries, actions = original_deliveries()
    return {
        "schema_version": SCHEMA,
        "deliveries": deliveries,
        "contracts": [
            {"delivery_id": "gate_supply", "commission_bps": 1000,
             "early_by_ticks": 1, "early_reputation": 2},
            {"delivery_id": "lantern_supply", "commission_bps": 500,
             "early_by_ticks": 1, "early_reputation": 3},
        ],
    }, actions


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m skeleton weather-market",
        description="Play, settle and replay offline weather caravan trade",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    start = sub.add_parser("start")
    start.add_argument("--source-json", required=True)
    advance = sub.add_parser("advance")
    advance.add_argument("--session-json", required=True)
    advance.add_argument("--action-json", required=True)
    resume = sub.add_parser("resume")
    resume.add_argument("--session-json", required=True)
    resume.add_argument("--actions-json", required=True)
    for command in ("verify", "summary", "pack"):
        item = sub.add_parser(command)
        item.add_argument("--session-json", required=True)
    unpack = sub.add_parser("unpack")
    unpack.add_argument("--package-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            source, actions = original_market()
            result = resume_market(new_market(source), actions)
        elif args.command == "start":
            result = new_market(_json(args.source_json, "market source"))
        elif args.command == "unpack":
            result = verify_market_package(_json(args.package_json, "market package"))
        else:
            saved = _json(args.session_json, "market session")
            if args.command == "advance":
                result = advance_market(saved, _json(args.action_json, "market action"))
            elif args.command == "resume":
                result = resume_market(saved, _json(args.actions_json, "market actions"))
            elif args.command == "verify":
                result = verify_market(saved)
            elif args.command == "summary":
                result = market_summary(saved)
            else:
                result = package_market(saved)
        print(_export(result))
        return 0
    except (SceneTravelError, KeyError, TypeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
