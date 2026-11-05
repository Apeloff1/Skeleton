"""Replay-derived economic provenance for authored offline scene markets.

This is a read-only witness, never a second source of spendable balances.
The canonical market journal is replayed before any receipt is emitted.
"""
from __future__ import annotations

from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_market import (
    _advance, _bounded, _object, new_market, verify_market,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError

SCHEMA = "skeleton.scene_market_ledger.v1"
BUNDLE = "skeleton.scene_market_ledger_bundle.v1"


def _delta(before: dict[str, int], after: dict[str, int]) -> dict[str, int]:
    return {
        key: after.get(key, 0) - before.get(key, 0)
        for key in sorted(before.keys() | after.keys())
        if after.get(key, 0) != before.get(key, 0)
    }


def _expected_goods(kind: str, action: dict[str, Any],
                    source: dict[str, Any]) -> dict[str, int]:
    if kind == "buy":
        offer = next(
            item for market in source["markets"] for item in market["offers"]
            if item["offer_id"] == action["offer_id"]
        )
        return {offer["item_id"]: 1}
    if kind == "craft":
        recipe = next(
            item for item in source["recipes"]
            if item["recipe_id"] == action["recipe_id"]
        )
        return _delta(recipe["inputs"], recipe["output"])
    if kind == "deliver":
        delivery = next(
            item for item in source["deliveries"]
            if item["delivery_id"] == action["delivery_id"]
        )
        return {key: -count for key, count in delivery["goods"].items()}
    return {}


def _credit_reason(kind: str, action: dict[str, Any],
                   source: dict[str, Any], before: dict[str, Any],
                   after: dict[str, Any]) -> int:
    if kind == "buy":
        offer = next(
            item for market in source["markets"] for item in market["offers"]
            if item["offer_id"] == action["offer_id"]
        )
        return -offer["price"]
    if kind != "tile":
        return 0
    collected_before = set(before["tile"]["state"]["scene"]["state"]["collected"])
    collected_after = set(after["tile"]["state"]["scene"]["state"]["collected"])
    gained = collected_after - collected_before
    return sum(
        coin["amount"] for coin in source["coin_pickups"]
        if coin["pickup"] in gained
    )


def _reputation_reason(kind: str, action: dict[str, Any],
                       source: dict[str, Any]) -> int:
    if kind != "deliver":
        return 0
    delivery = next(
        item for item in source["deliveries"]
        if item["delivery_id"] == action["delivery_id"]
    )
    return delivery["reputation"]


def audit_market_ledger(payload: Any) -> dict[str, Any]:
    """Prove every coin, good and reputation change against canonical replay."""
    session = verify_market(payload)
    source = session["source"]
    replay = new_market(source)
    entries: list[dict[str, Any]] = []
    earned = 0
    spent = 0
    for index, event in enumerate(session["journal"]):
        before = replay["state"]
        action = event["action"]
        replay = _advance(replay, action)
        after = replay["state"]
        kind = action["kind"]
        coins = after["credits"] - before["credits"]
        goods = _delta(before["goods"], after["goods"])
        reputation = after["reputation"] - before["reputation"]
        if (coins != _credit_reason(kind, action, source, before, after)
                or goods != _expected_goods(kind, action, source)
                or reputation != _reputation_reason(kind, action, source)):
            raise SceneTravelError("market ledger conservation mismatch")
        if after["credits"] < 0 or any(v <= 0 for v in after["goods"].values()):
            raise SceneTravelError("market ledger negative or zero inventory")
        if coins > 0:
            earned += coins
        else:
            spent -= coins
        entries.append({
            "sequence": index, "kind": kind,
            "action_digest": dig(action), "event_receipt": event["receipt"],
            "state_digest": replay["state_digest"],
            "credit_delta": coins, "goods_delta": goods,
            "reputation_delta": reputation,
            "credits_after": after["credits"],
            "reputation_after": after["reputation"],
        })
    state = session["state"]
    if (replay != session or earned - spent != state["credits"]
            or sum(entry["reputation_delta"] for entry in entries)
            != state["reputation"]):
        raise SceneTravelError("market ledger terminal state mismatch")
    report = {
        "schema_version": SCHEMA,
        "source_digest": session["source_digest"],
        "state_digest": session["state_digest"],
        "journal_length": len(entries),
        "last_receipt": entries[-1]["event_receipt"] if entries else None,
        "credits_earned": earned, "credits_spent": spent,
        "credits_remaining": state["credits"],
        "goods_remaining": dict(sorted(state["goods"].items())),
        "reputation_earned": state["reputation"],
        "delivered": list(state["delivered"]),
        "phase": state["phase"], "entries": entries,
    }
    report["checksum"] = dig(report)
    _bounded(report)
    return report


def verify_market_ledger(session: Any, report: Any) -> dict[str, Any]:
    """Reject modified witnesses even when their unkeyed checksum is recomputed."""
    _bounded(report)
    expected = audit_market_ledger(session)
    if type(report) is not dict or report != expected:
        raise SceneTravelError("market ledger witness mismatch")
    return expected


def export_market_ledger(session: Any) -> dict[str, Any]:
    """Portable session and recomputable audit witness; not an authentication tag."""
    canonical = verify_market(session)
    report = audit_market_ledger(canonical)
    bundle = {
        "schema_version": BUNDLE, "session": canonical,
        "ledger": report, "source_digest": canonical["source_digest"],
        "state_digest": canonical["state_digest"],
    }
    bundle["checksum"] = dig(bundle)
    _bounded(bundle)
    return bundle


def import_market_ledger(payload: Any) -> dict[str, Any]:
    """Recompute the witness from source and journal; never trust supplied totals."""
    _bounded(payload)
    bundle = _object(payload, {
        "schema_version", "session", "ledger", "source_digest",
        "state_digest", "checksum",
    }, "market ledger bundle")
    if bundle["schema_version"] != BUNDLE:
        raise SceneTravelError("unsupported market ledger bundle")
    if bundle["checksum"] != dig({k: v for k, v in bundle.items()
                                   if k != "checksum"}):
        raise SceneTravelError("market ledger bundle checksum mismatch")
    session = verify_market(bundle["session"])
    if (bundle["source_digest"] != session["source_digest"]
            or bundle["state_digest"] != session["state_digest"]):
        raise SceneTravelError("market ledger bundle source mismatch")
    verify_market_ledger(session, bundle["ledger"])
    return session
