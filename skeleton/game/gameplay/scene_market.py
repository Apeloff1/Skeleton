"""Original source-bound trading posts over the canonical playable tile engine.

Currency can only be minted by collecting authored canonical pickups.
Offers have finite stock, crafting consumes earned goods, and deliveries are
one-shot. Every snapshot is reconstructed from a deterministic action journal.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_tile_walk import (
    MAX_BYTES, MAX_STEPS, _advance as advance_tile, _bounded, _point,
    _reachable, new_tiles, normalize_tiles, original_tiles, verify_tiles,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError, _id, _limit, _object

SCHEMA = "skeleton.scene_market.v1"
BUNDLE = "skeleton.scene_market_bundle.v1"
MAX_MARKETS = 24
MAX_OFFERS = 64
MAX_RECIPES = 32
MAX_DELIVERIES = 32


def _site(raw: Any, areas: dict[str, dict[str, Any]], label: str) -> dict[str, Any]:
    obj = _object(raw, {"scene_id", "at"}, label)
    scene_id = _id(obj["scene_id"], label + " scene")
    if scene_id not in areas:
        raise SceneTravelError(label + " references unknown scene")
    area = areas[scene_id]
    point = _point(obj["at"], area["width"], area["height"])
    walls = {tuple(p) for p in area["walls"]}
    if tuple(point) not in _reachable(
        area["width"], area["height"], area["spawn"], walls,
    ):
        raise SceneTravelError(label + " is not reachable")
    return {"scene_id": scene_id, "at": point}


def _goods(raw: Any, label: str) -> dict[str, int]:
    if type(raw) is not dict or not 1 <= len(raw) <= 8:
        raise SceneTravelError("invalid " + label + " goods")
    goods: dict[str, int] = {}
    for key, count in raw.items():
        name = _id(key, label + " item")
        goods[name] = _limit(count, label + " quantity", 1, 32)
    return dict(sorted(goods.items()))


def normalize_market(raw: Any) -> dict[str, Any]:
    _bounded(raw, 256 * 1024)
    obj = _object(raw, {
        "schema_version", "tile_source", "coin_pickups", "markets",
        "recipes", "deliveries", "required_deliveries",
    }, "market source")
    if obj["schema_version"] != SCHEMA:
        raise SceneTravelError("unsupported market schema")
    tiles = normalize_tiles(obj["tile_source"])
    areas = {area["scene_id"]: area for area in tiles["maps"]}
    authored = {
        area["scene_id"] + ":" + item["id"]
        for area in tiles["maps"] for item in area["pickups"]
    }
    coins = obj["coin_pickups"]
    if type(coins) is not list or len(coins) > 128:
        raise SceneTravelError("invalid coin pickup count")
    cleaned_coins = []
    for raw_coin in coins:
        coin = _object(raw_coin, {"pickup", "amount"}, "coin pickup")
        name = _id(coin["pickup"], "coin pickup")
        if name not in authored:
            raise SceneTravelError("currency must reference authored pickup")
        cleaned_coins.append({
            "pickup": name, "amount": _limit(coin["amount"], "coin value", 1, 100),
        })
    if len({c["pickup"] for c in cleaned_coins}) != len(cleaned_coins):
        raise SceneTravelError("duplicate currency pickup")
    markets = obj["markets"]
    if type(markets) is not list or len(markets) > MAX_MARKETS:
        raise SceneTravelError("invalid market count")
    cleaned_markets = []
    offer_ids: set[str] = set()
    for raw_market in markets:
        entry = _object(raw_market, {"market_id", "scene_id", "at", "offers"}, "market")
        ident = _id(entry["market_id"], "market id")
        site = _site({"scene_id": entry["scene_id"], "at": entry["at"]},
                     areas, "market")
        offers = entry["offers"]
        if type(offers) is not list or not 1 <= len(offers) <= MAX_OFFERS:
            raise SceneTravelError("invalid market offers")
        cleaned_offers = []
        for raw_offer in offers:
            offer = _object(raw_offer, {"offer_id", "item_id", "price", "stock"},
                            "market offer")
            offer_id = _id(offer["offer_id"], "offer id")
            if offer_id in offer_ids:
                raise SceneTravelError("duplicate offer id")
            offer_ids.add(offer_id)
            cleaned_offers.append({
                "offer_id": offer_id, "item_id": _id(offer["item_id"], "item id"),
                "price": _limit(offer["price"], "price", 1, 1000),
                "stock": _limit(offer["stock"], "stock", 1, 32),
            })
        cleaned_markets.append({
            "market_id": ident, **site,
            "offers": sorted(cleaned_offers, key=lambda x: x["offer_id"]),
        })
    if len({m["market_id"] for m in cleaned_markets}) != len(cleaned_markets):
        raise SceneTravelError("duplicate market id")
    recipes = obj["recipes"]
    if type(recipes) is not list or len(recipes) > MAX_RECIPES:
        raise SceneTravelError("invalid recipe count")
    cleaned_recipes = []
    for raw_recipe in recipes:
        recipe = _object(raw_recipe, {
            "recipe_id", "scene_id", "at", "inputs", "output",
        }, "recipe")
        site = _site({"scene_id": recipe["scene_id"], "at": recipe["at"]},
                     areas, "recipe")
        output = _goods(recipe["output"], "recipe output")
        cleaned_recipes.append({
            "recipe_id": _id(recipe["recipe_id"], "recipe id"), **site,
            "inputs": _goods(recipe["inputs"], "recipe inputs"), "output": output,
        })
    if len({r["recipe_id"] for r in cleaned_recipes}) != len(cleaned_recipes):
        raise SceneTravelError("duplicate recipe id")
    deliveries = obj["deliveries"]
    if type(deliveries) is not list or len(deliveries) > MAX_DELIVERIES:
        raise SceneTravelError("invalid delivery count")
    cleaned_deliveries = []
    for raw_delivery in deliveries:
        delivery = _object(raw_delivery, {
            "delivery_id", "scene_id", "at", "goods", "reputation",
        }, "delivery")
        site = _site({"scene_id": delivery["scene_id"], "at": delivery["at"]},
                     areas, "delivery")
        cleaned_deliveries.append({
            "delivery_id": _id(delivery["delivery_id"], "delivery id"), **site,
            "goods": _goods(delivery["goods"], "delivery"),
            "reputation": _limit(delivery["reputation"], "reputation", 1, 100),
        })
    ids = {d["delivery_id"] for d in cleaned_deliveries}
    if len(ids) != len(cleaned_deliveries):
        raise SceneTravelError("duplicate delivery id")
    required = obj["required_deliveries"]
    if type(required) is not list or len(required) > MAX_DELIVERIES:
        raise SceneTravelError("invalid required deliveries")
    required_ids = [_id(item, "required delivery") for item in required]
    if len(set(required_ids)) != len(required_ids) or not set(required_ids) <= ids:
        raise SceneTravelError("required delivery not authored or duplicate")
    return {
        "schema_version": SCHEMA, "tile_source": tiles,
        "coin_pickups": sorted(cleaned_coins, key=lambda x: x["pickup"]),
        "markets": sorted(cleaned_markets, key=lambda x: x["market_id"]),
        "recipes": sorted(cleaned_recipes, key=lambda x: x["recipe_id"]),
        "deliveries": sorted(cleaned_deliveries, key=lambda x: x["delivery_id"]),
        "required_deliveries": sorted(required_ids),
    }


def _save(source: dict[str, Any], state: dict[str, Any],
          parent: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "source_digest": dig(source), "state_digest": dig(state),
        "tick": state["tick"],
        "parent_save_digest": dig(parent) if parent is not None else None,
    }


def new_market(source: Any) -> dict[str, Any]:
    spec = normalize_market(source)
    state = {
        "tick": 0, "tile": new_tiles(spec["tile_source"]),
        "credits": 0, "goods": {}, "purchases": {},
        "crafted": {}, "delivered": [], "reputation": 0, "phase": "active",
    }
    return {
        "schema_version": SCHEMA, "source": spec, "source_digest": dig(spec),
        "state": state, "state_digest": dig(state), "journal": [],
        "save": _save(spec, state),
    }


def _action(raw: Any) -> dict[str, Any]:
    if type(raw) is not dict:
        raise SceneTravelError("invalid market action")
    kind = raw.get("kind")
    if kind == "tile":
        _object(raw, {"kind", "action"}, "market tile action")
        if type(raw["action"]) is not dict:
            raise SceneTravelError("invalid nested tile action")
        return {"kind": "tile", "action": raw["action"]}
    if kind in ("buy", "craft", "deliver"):
        field = {"buy": "offer_id", "craft": "recipe_id",
                 "deliver": "delivery_id"}[kind]
        _object(raw, {"kind", field}, "market action")
        return {"kind": kind, field: _id(raw[field], field)}
    raise SceneTravelError("unsupported market action")


def _at(tile: dict[str, Any], site: dict[str, Any]) -> bool:
    state = tile["state"]
    return (state["scene"]["state"]["scene_id"] == site["scene_id"]
            and state["position"] == site["at"])


def _change(goods: dict[str, int], delta: dict[str, int], sign: int) -> None:
    for item, quantity in delta.items():
        next_count = goods.get(item, 0) + sign * quantity
        if not 0 <= next_count <= 256:
            raise SceneTravelError("insufficient or overflowing earned goods")
        if next_count:
            goods[item] = next_count
        else:
            goods.pop(item, None)


def _advance(session: dict[str, Any], raw: Any) -> dict[str, Any]:
    old, source = session["state"], session["source"]
    if old["phase"] != "active" or old["tick"] >= MAX_STEPS:
        raise SceneTravelError("market already terminal or turn budget exhausted")
    action = _action(raw)
    state = {
        "tick": old["tick"] + 1, "tile": old["tile"],
        "credits": old["credits"], "goods": dict(old["goods"]),
        "purchases": dict(old["purchases"]), "crafted": dict(old["crafted"]),
        "delivered": list(old["delivered"]), "reputation": old["reputation"],
        "phase": "active",
    }
    if action["kind"] == "tile":
        before = old["tile"]["state"]["scene"]["state"]["collected"]
        updated = advance_tile(old["tile"], action["action"])
        after = updated["state"]["scene"]["state"]["collected"]
        state["tile"] = updated
        if action["action"].get("kind") == "collect":
            gained = set(after) - set(before)
            for coin in source["coin_pickups"]:
                if coin["pickup"] in gained:
                    state["credits"] += coin["amount"]
    elif action["kind"] == "buy":
        offer = next((
            (market, item) for market in source["markets"]
            for item in market["offers"] if item["offer_id"] == action["offer_id"]
        ), None)
        if offer is None:
            raise SceneTravelError("unknown market offer")
        market, item = offer
        count = old["purchases"].get(item["offer_id"], 0)
        if not _at(old["tile"], market):
            raise SceneTravelError("purchase requires market position")
        if count >= item["stock"] or state["credits"] < item["price"]:
            raise SceneTravelError("insufficient credits or exhausted stock")
        state["credits"] -= item["price"]
        _change(state["goods"], {item["item_id"]: 1}, 1)
        state["purchases"][item["offer_id"]] = count + 1
    elif action["kind"] == "craft":
        recipe = next((r for r in source["recipes"]
                       if r["recipe_id"] == action["recipe_id"]), None)
        if recipe is None or not _at(old["tile"], recipe):
            raise SceneTravelError("craft requires authored station position")
        _change(state["goods"], recipe["inputs"], -1)
        _change(state["goods"], recipe["output"], 1)
        state["crafted"][recipe["recipe_id"]] = (
            old["crafted"].get(recipe["recipe_id"], 0) + 1
        )
    else:
        delivery = next((d for d in source["deliveries"]
                         if d["delivery_id"] == action["delivery_id"]), None)
        if delivery is None or not _at(old["tile"], delivery):
            raise SceneTravelError("delivery requires authored recipient position")
        if delivery["delivery_id"] in old["delivered"]:
            raise SceneTravelError("delivery reward already earned")
        _change(state["goods"], delivery["goods"], -1)
        state["delivered"].append(delivery["delivery_id"])
        state["delivered"].sort()
        state["reputation"] += delivery["reputation"]
    tile_phase = state["tile"]["state"]["phase"]
    if tile_phase == "won":
        state["phase"] = ("won" if set(source["required_deliveries"])
                          <= set(state["delivered"]) else "lost")
    elif tile_phase != "active":
        state["phase"] = "lost"
    event = {
        "sequence": old["tick"], "action": action,
        "before": session["state_digest"], "after": dig(state),
    }
    event["receipt"] = dig(event)
    journal = [*session["journal"], event]
    result = {
        "schema_version": SCHEMA, "source": source,
        "source_digest": session["source_digest"], "state": state,
        "state_digest": dig(state), "journal": journal,
        "save": _save(source, state, session["save"]),
    }
    _bounded(result)
    return result


def verify_market(payload: Any) -> dict[str, Any]:
    _bounded(payload)
    obj = _object(payload, {
        "schema_version", "source", "source_digest", "state", "state_digest",
        "journal", "save",
    }, "market session")
    if obj["schema_version"] != SCHEMA:
        raise SceneTravelError("unsupported market save schema")
    if type(obj["journal"]) is not list or len(obj["journal"]) > MAX_STEPS:
        raise SceneTravelError("invalid market journal")
    rebuilt = new_market(obj["source"])
    for event in obj["journal"]:
        if type(event) is not dict or "action" not in event:
            raise SceneTravelError("invalid market replay event")
        rebuilt = _advance(rebuilt, event["action"])
        if rebuilt["journal"][-1] != event:
            raise SceneTravelError("market replay receipt mismatch")
    if rebuilt != obj or verify_tiles(rebuilt["state"]["tile"]) != rebuilt["state"]["tile"]:
        raise SceneTravelError("market save or source lineage mismatch")
    return rebuilt


def resume_market(payload: Any, actions: Any) -> dict[str, Any]:
    session = verify_market(payload)
    if type(actions) is not list or len(actions) + len(session["journal"]) > MAX_STEPS:
        raise SceneTravelError("invalid market action batch")
    for action in actions:
        session = _advance(session, action)
    return session


def simulate_market(source: Any, actions: Any) -> dict[str, Any]:
    return resume_market(new_market(source), actions)


def export_market(payload: Any) -> dict[str, Any]:
    session = verify_market(payload)
    bundle = {
        "schema_version": BUNDLE, "source_digest": session["source_digest"],
        "state_digest": session["state_digest"], "session": session,
    }
    bundle["checksum"] = dig(bundle)
    _bounded(bundle)
    return bundle


def import_market(payload: Any) -> dict[str, Any]:
    _bounded(payload)
    obj = _object(payload, {
        "schema_version", "source_digest", "state_digest", "session", "checksum",
    }, "market bundle")
    if obj["schema_version"] != BUNDLE:
        raise SceneTravelError("unsupported market bundle")
    if obj["checksum"] != dig({k: v for k, v in obj.items() if k != "checksum"}):
        raise SceneTravelError("market bundle checksum mismatch")
    session = verify_market(obj["session"])
    if (session["source_digest"] != obj["source_digest"]
            or session["state_digest"] != obj["state_digest"]):
        raise SceneTravelError("market bundle lineage mismatch")
    return session


def original_market() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    tiles, actions = original_tiles()
    source = {
        "schema_version": SCHEMA, "tile_source": tiles,
        "coin_pickups": [{"pickup": "quay:find_key", "amount": 3}],
        "markets": [{
            "market_id": "gate_trader", "scene_id": "gate", "at": [0, 1],
            "offers": [{"offer_id": "copper_badge", "item_id": "badge",
                        "price": 2, "stock": 1}],
        }],
        "recipes": [{
            "recipe_id": "seal_press", "scene_id": "gate", "at": [1, 1],
            "inputs": {"badge": 1}, "output": {"seal": 1},
        }],
        "deliveries": [{
            "delivery_id": "sanctuary_seal", "scene_id": "gate", "at": [2, 1],
            "goods": {"seal": 1}, "reputation": 5,
        }],
        "required_deliveries": ["sanctuary_seal"],
    }
    sequence = [{"kind": "tile", "action": action} for action in actions]
    sequence.insert(5, {"kind": "buy", "offer_id": "copper_badge"})
    sequence.insert(7, {"kind": "craft", "recipe_id": "seal_press"})
    sequence.insert(9, {"kind": "deliver", "delivery_id": "sanctuary_seal"})
    return source, sequence


def _json(raw: str) -> Any:
    if type(raw) is not str or len(raw.encode("utf-8")) > MAX_BYTES:
        raise SceneTravelError("market JSON input budget exceeded")
    try:
        def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            result: dict[str, Any] = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("duplicate JSON key")
                result[key] = value
            return result
        return json.loads(raw, object_pairs_hook=unique,
                          parse_constant=lambda _: (_ for _ in ()).throw(
                              ValueError("nonfinite JSON number")))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise SceneTravelError("invalid market JSON") from exc


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-market")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    for command in ("simulate", "resume"):
        p = sub.add_parser(command)
        p.add_argument("--source-json" if command == "simulate"
                       else "--session-json", required=True)
        p.add_argument("--actions-json", required=True)
    for command in ("verify", "export"):
        sub.add_parser(command).add_argument("--session-json", required=True)
    sub.add_parser("import").add_argument("--bundle-json", required=True)
    for command in ("ledger", "ledger-export"):
        sub.add_parser(command).add_argument("--session-json", required=True)
    sub.add_parser("ledger-import").add_argument("--bundle-json", required=True)
    sub.add_parser("feasibility").add_argument("--source-json", required=True)
    reconcile = sub.add_parser("ledger-reconcile")
    reconcile.add_argument("--before-json", required=True)
    reconcile.add_argument("--after-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            source, actions = original_market()
            result = simulate_market(source, actions)
        elif args.command == "simulate":
            result = simulate_market(_json(args.source_json), _json(args.actions_json))
        elif args.command == "resume":
            result = resume_market(_json(args.session_json), _json(args.actions_json))
        elif args.command == "ledger-reconcile":
            from skeleton.game.gameplay.scene_market_reconciliation import reconcile_market
            result = reconcile_market(
                _json(args.before_json), _json(args.after_json),
            )
        elif args.command == "ledger":
            from skeleton.game.gameplay.scene_market_ledger import audit_market_ledger
            result = audit_market_ledger(_json(args.session_json))
        elif args.command == "ledger-export":
            from skeleton.game.gameplay.scene_market_ledger import export_market_ledger
            result = export_market_ledger(_json(args.session_json))
        elif args.command == "ledger-import":
            from skeleton.game.gameplay.scene_market_ledger import import_market_ledger
            result = import_market_ledger(_json(args.bundle_json))
        elif args.command == "feasibility":
            from skeleton.game.gameplay.scene_market_feasibility import analyze_market_feasibility
            result = analyze_market_feasibility(_json(args.source_json))
        elif args.command == "verify":
            result = verify_market(_json(args.session_json))
        elif args.command == "export":
            result = export_market(_json(args.session_json))
        else:
            result = import_market(_json(args.bundle_json))
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
