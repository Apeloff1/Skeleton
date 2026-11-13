"""Deterministic merchant opening hours over canonical earned-currency market play.

The canonical market remains the only authority for balances, stock, positions,
crafting and delivery. This overlay adds authored merchant availability and
reputation prerequisites, with replay-proven save and portable export.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_market import (
    _action as market_action, _advance as advance_market, _at,
    _bounded, _json, new_market, normalize_market, original_market,
    verify_market,
)
from skeleton.game.gameplay.scene_tile_walk import MAX_STEPS
from skeleton.game.gameplay.scene_travel import SceneTravelError, _id, _limit, _object

SCHEMA = "skeleton.scene_market_hours.v1"
BUNDLE = "skeleton.scene_market_hours_bundle.v1"
BOARD = "skeleton.scene_market_hours_board.v1"
MAX_WINDOWS = 96
MAX_EDITS = 32


def normalize_hours(raw: Any) -> dict[str, Any]:
    """Validate authored windows before any gameplay or editor publication."""
    _bounded(raw, 256 * 1024)
    obj = _object(raw, {"schema_version", "market_source", "windows"}, "hours source")
    if obj["schema_version"] != SCHEMA:
        raise SceneTravelError("unsupported merchant hours schema")
    market = normalize_market(obj["market_source"])
    markets = {item["market_id"] for item in market["markets"]}
    windows = obj["windows"]
    if type(windows) is not list or not 1 <= len(windows) <= MAX_WINDOWS:
        raise SceneTravelError("invalid merchant opening window count")
    cleaned: list[dict[str, Any]] = []
    for entry in windows:
        item = _object(entry, {
            "market_id", "opens_at", "closes_at", "min_reputation",
        }, "merchant window")
        market_id = _id(item["market_id"], "merchant market")
        if market_id not in markets:
            raise SceneTravelError("opening window references unknown merchant")
        start = _limit(item["opens_at"], "opening tick", 1, MAX_STEPS)
        end = _limit(item["closes_at"], "closing tick", 1, MAX_STEPS)
        if start > end:
            raise SceneTravelError("merchant opening window is reversed")
        cleaned.append({
            "market_id": market_id, "opens_at": start, "closes_at": end,
            "min_reputation": _limit(
                item["min_reputation"], "merchant reputation", 0, 3200,
            ),
        })
    cleaned.sort(key=lambda x: (x["market_id"], x["opens_at"]))
    seen: set[str] = set()
    previous: dict[str, int] = {}
    for item in cleaned:
        ident = item["market_id"]
        if item["opens_at"] <= previous.get(ident, 0):
            raise SceneTravelError("overlapping merchant opening windows")
        previous[ident] = item["closes_at"]
        seen.add(ident)
    if seen != markets:
        raise SceneTravelError("every merchant requires an authored opening window")
    return {"schema_version": SCHEMA, "market_source": market, "windows": cleaned}


def _save(source: dict[str, Any], state: dict[str, Any],
          parent: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "source_digest": dig(source), "state_digest": dig(state),
        "tick": state["tick"],
        "parent_save_digest": dig(parent) if parent is not None else None,
    }


def new_hours(source: Any) -> dict[str, Any]:
    spec = normalize_hours(source)
    market = new_market(spec["market_source"])
    state = {
        "tick": 0, "market": market, "purchases_by_merchant": {},
        "phase": market["state"]["phase"],
    }
    result = {
        "schema_version": SCHEMA, "source": spec, "source_digest": dig(spec),
        "state": state, "state_digest": dig(state), "journal": [],
        "save": _save(spec, state),
    }
    _bounded(result)
    return result


def _market_for_offer(source: dict[str, Any], offer_id: str) -> dict[str, Any]:
    for merchant in source["market_source"]["markets"]:
        if any(offer["offer_id"] == offer_id for offer in merchant["offers"]):
            return merchant
    raise SceneTravelError("unknown merchant offer")


def _open_window(source: dict[str, Any], market_id: str,
                 tick: int) -> dict[str, Any] | None:
    return next((
        window for window in source["windows"]
        if window["market_id"] == market_id
        and window["opens_at"] <= tick <= window["closes_at"]
    ), None)


def _advance(session: dict[str, Any], raw: Any) -> dict[str, Any]:
    old = session["state"]
    if old["phase"] != "active" or old["tick"] >= MAX_STEPS:
        raise SceneTravelError("merchant campaign terminal or turn budget exhausted")
    action = market_action(raw)
    market_id = None
    if action["kind"] == "buy":
        merchant = _market_for_offer(session["source"], action["offer_id"])
        market_id = merchant["market_id"]
        window = _open_window(session["source"], market_id, old["tick"] + 1)
        if window is None:
            raise SceneTravelError("merchant closed at purchase tick")
        if old["market"]["state"]["reputation"] < window["min_reputation"]:
            raise SceneTravelError("merchant reputation gate not earned")
    # The canonical reducer enforces location, earned money and finite stock.
    market = advance_market(old["market"], action)
    if market["state"]["tick"] != old["tick"] + 1:
        raise SceneTravelError("merchant and canonical market clocks diverged")
    purchases = dict(old["purchases_by_merchant"])
    if market_id is not None:
        purchases[market_id] = purchases.get(market_id, 0) + 1
    state = {
        "tick": market["state"]["tick"], "market": market,
        "purchases_by_merchant": dict(sorted(purchases.items())),
        "phase": market["state"]["phase"],
    }
    event = {
        "sequence": old["tick"], "action": market["journal"][-1]["action"],
        "before": session["state_digest"], "after": dig(state),
    }
    event["receipt"] = dig(event)
    result = {
        "schema_version": SCHEMA, "source": session["source"],
        "source_digest": session["source_digest"], "state": state,
        "state_digest": dig(state),
        "journal": [*session["journal"], event],
        "save": _save(session["source"], state, session["save"]),
    }
    _bounded(result)
    return result


def verify_hours(payload: Any) -> dict[str, Any]:
    _bounded(payload)
    obj = _object(payload, {
        "schema_version", "source", "source_digest", "state", "state_digest",
        "journal", "save",
    }, "merchant session")
    if obj["schema_version"] != SCHEMA:
        raise SceneTravelError("unsupported merchant save schema")
    if type(obj["journal"]) is not list or len(obj["journal"]) > MAX_STEPS:
        raise SceneTravelError("invalid merchant journal length")
    rebuilt = new_hours(obj["source"])
    for event in obj["journal"]:
        if type(event) is not dict or "action" not in event:
            raise SceneTravelError("invalid merchant replay event")
        rebuilt = _advance(rebuilt, event["action"])
        if rebuilt["journal"][-1] != event:
            raise SceneTravelError("merchant replay receipt mismatch")
    if rebuilt != obj or verify_market(rebuilt["state"]["market"]) != rebuilt["state"]["market"]:
        raise SceneTravelError("merchant save or source lineage mismatch")
    return rebuilt


def resume_hours(payload: Any, actions: Any) -> dict[str, Any]:
    current = verify_hours(payload)
    if type(actions) is not list or len(actions) + len(current["journal"]) > MAX_STEPS:
        raise SceneTravelError("invalid merchant action batch")
    for action in actions:
        current = _advance(current, action)
    return current


def simulate_hours(source: Any, actions: Any) -> dict[str, Any]:
    return resume_hours(new_hours(source), actions)


def export_hours(payload: Any) -> dict[str, Any]:
    session = verify_hours(payload)
    bundle = {
        "schema_version": BUNDLE, "session": session,
        "source_digest": session["source_digest"],
        "state_digest": session["state_digest"],
    }
    bundle["checksum"] = dig(bundle)
    _bounded(bundle)
    return bundle


def import_hours(payload: Any) -> dict[str, Any]:
    _bounded(payload)
    obj = _object(payload, {
        "schema_version", "session", "source_digest", "state_digest", "checksum",
    }, "merchant portable bundle")
    if obj["schema_version"] != BUNDLE:
        raise SceneTravelError("unsupported merchant bundle schema")
    if obj["checksum"] != dig({k: v for k, v in obj.items() if k != "checksum"}):
        raise SceneTravelError("merchant bundle checksum mismatch")
    session = verify_hours(obj["session"])
    if (obj["source_digest"] != session["source_digest"]
            or obj["state_digest"] != session["state_digest"]):
        raise SceneTravelError("merchant bundle lineage mismatch")
    return session


def merchant_board(payload: Any) -> dict[str, Any]:
    """Read-only, replay-derived view of available purchases at the next turn."""
    session = verify_hours(payload)
    market = session["state"]["market"]
    tick = session["state"]["tick"] + 1
    reputation = market["state"]["reputation"]
    credits = market["state"]["credits"]
    merchants = []
    for merchant in session["source"]["market_source"]["markets"]:
        window = _open_window(session["source"], merchant["market_id"], tick)
        is_open = window is not None and reputation >= window["min_reputation"]
        at_market = _at(market["state"]["tile"], merchant)
        offers = [{
            "offer_id": offer["offer_id"],
            "remaining_stock": offer["stock"] - market["state"]["purchases"].get(
                offer["offer_id"], 0,
            ),
            "affordable": credits >= offer["price"],
            "purchasable": (
                session["state"]["phase"] == "active" and is_open and at_market
                and credits >= offer["price"]
                and market["state"]["purchases"].get(offer["offer_id"], 0) < offer["stock"]
            ),
        } for offer in merchant["offers"]]
        merchants.append({
            "market_id": merchant["market_id"], "open": is_open,
            "at_market": at_market,
            "required_reputation": window["min_reputation"] if window else None,
            "next_open_tick": next((
                w["opens_at"] for w in session["source"]["windows"]
                if w["market_id"] == merchant["market_id"] and w["opens_at"] > tick
            ), None),
            "offers": offers,
        })
    result = {
        "schema_version": BOARD, "source_digest": session["source_digest"],
        "state_digest": session["state_digest"], "next_tick": tick,
        "credits": credits, "reputation": reputation, "merchants": merchants,
    }
    result["checksum"] = dig(result)
    _bounded(result)
    return result


def verify_merchant_board(payload: Any, board: Any) -> dict[str, Any]:
    _bounded(board)
    expected = merchant_board(payload)
    if type(board) is not dict or board != expected:
        raise SceneTravelError("merchant board witness mismatch")
    return expected


def edit_hours(source: Any, operations: Any) -> dict[str, Any]:
    """Transactional authoring; every operation is validated before publication."""
    current = normalize_hours(source)
    if type(operations) is not list or not 1 <= len(operations) <= MAX_EDITS:
        raise SceneTravelError("invalid merchant edit batch")
    windows = [dict(item) for item in current["windows"]]
    for raw in operations:
        if type(raw) is not dict:
            raise SceneTravelError("invalid merchant edit")
        kind = raw.get("kind")
        if kind == "add":
            item = _object(raw, {
                "kind", "market_id", "opens_at", "closes_at", "min_reputation",
            }, "add merchant window")
            windows.append({k: v for k, v in item.items() if k != "kind"})
        elif kind == "remove":
            item = _object(raw, {"kind", "market_id", "opens_at"}, "remove merchant window")
            count = len(windows)
            windows = [w for w in windows if not (
                w["market_id"] == item["market_id"] and w["opens_at"] == item["opens_at"]
            )]
            if len(windows) == count:
                raise SceneTravelError("merchant edit window not found")
        else:
            raise SceneTravelError("unsupported merchant edit")
    return normalize_hours({
        "schema_version": SCHEMA, "market_source": current["market_source"],
        "windows": windows,
    })


def original_hours() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    market, actions = original_market()
    return {
        "schema_version": SCHEMA, "market_source": market,
        "windows": [{
            "market_id": item["market_id"], "opens_at": 1,
            "closes_at": MAX_STEPS, "min_reputation": 0,
        } for item in market["markets"]],
    }, actions


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-market-hours")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    simulate = sub.add_parser("simulate")
    simulate.add_argument("--source-json", required=True)
    simulate.add_argument("--actions-json", required=True)
    resume = sub.add_parser("resume")
    resume.add_argument("--session-json", required=True)
    resume.add_argument("--actions-json", required=True)
    for cmd in ("verify", "export", "board"):
        sub.add_parser(cmd).add_argument("--session-json", required=True)
    sub.add_parser("import").add_argument("--bundle-json", required=True)
    edit = sub.add_parser("edit")
    edit.add_argument("--source-json", required=True)
    edit.add_argument("--operations-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            source, actions = original_hours()
            result = simulate_hours(source, actions)
        elif args.command == "simulate":
            result = simulate_hours(_json(args.source_json), _json(args.actions_json))
        elif args.command == "resume":
            result = resume_hours(_json(args.session_json), _json(args.actions_json))
        elif args.command == "verify":
            result = verify_hours(_json(args.session_json))
        elif args.command == "export":
            result = export_hours(_json(args.session_json))
        elif args.command == "import":
            result = import_hours(_json(args.bundle_json))
        elif args.command == "board":
            result = merchant_board(_json(args.session_json))
        else:
            result = edit_hours(_json(args.source_json), _json(args.operations_json))
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
