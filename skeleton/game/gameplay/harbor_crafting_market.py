"""Replay-derived economic custody for the original playable Lantern Quay campaign."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import HarborError, MAX_BUNDLE_BYTES, _keys, canonical, digest, initial_state, step, verify_bundle
from .harbor_crafting_sessions import checkpoint, resume_bundle, verify_portfolio

SCHEMA = "skeleton.game.harbor.market-ledger.v1"
PORTFOLIO_SCHEMA = "skeleton.game.harbor.market-futures.v1"
MAX_BYTES = MAX_BUNDLE_BYTES * 8
OPS = ("move", "gather", "craft", "trade", "deliver", "choose", "wait")


def _delta(before: dict[str, int], after: dict[str, int]) -> dict[str, int]:
    return {k: after.get(k, 0) - before.get(k, 0) for k in sorted(set(before) | set(after)) if before.get(k, 0) != after.get(k, 0)}


def _net(entries: list[dict[str, Any]], key: str) -> dict[str, int]:
    values: dict[str, int] = {}
    for entry in entries:
        for item, count in entry[key].items():
            values[item] = values.get(item, 0) + count
    return {k: v for k, v in sorted(values.items()) if v}


def market_report(bundle: Any) -> dict[str, Any]:
    """Derive every inventory, coin and stock transition from canonical replay."""
    verify_bundle(bundle)
    source = bundle["source"]
    state = initial_state(source)
    entries: list[dict[str, Any]] = []
    operations = {op: 0 for op in OPS}
    spent = 0
    for index, event in enumerate(bundle["events"]):
        action = event["action"]
        updated = step(source, state, action)
        if event["sequence"] != index or event["before"] != digest(state) or event["after"] != digest(updated):
            raise HarborError("market event replay mismatch")
        op = action["op"]
        operations[op] += 1
        coins = updated["coins"] - state["coins"]
        spent += max(0, -coins)
        entry = {
            "sequence": index,
            "event_digest": event["digest"],
            "action": deepcopy(action),
            "before": digest(state),
            "after": digest(updated),
            "inventory_delta": _delta(state["inventory"], updated["inventory"]),
            "resource_delta": _delta(state["stock"], updated["stock"]),
            "merchant_delta": _delta(state["npc_stock"], updated["npc_stock"]),
            "coin_delta": coins,
            "reputation_delta": updated["reputation"] - state["reputation"],
            "delivery_changed": not state["delivered"] and updated["delivered"],
            "ending": updated["ending"],
        }
        if op != "trade" and (coins or entry["merchant_delta"]):
            raise HarborError("unexpected economy mutation")
        if op != "gather" and entry["resource_delta"]:
            raise HarborError("unexpected resource mutation")
        if op != "deliver" and entry["delivery_changed"]:
            raise HarborError("unexpected delivery mutation")
        if op != "choose" and updated["ending"] != state["ending"]:
            raise HarborError("unexpected ending mutation")
        entries.append(entry)
        state = updated
    if state != bundle["state"]:
        raise HarborError("market terminal replay mismatch")
    report = {
        "schema": SCHEMA,
        "bundle": deepcopy(bundle),
        "source_digest": bundle["source_digest"],
        "terminal_digest": bundle["terminal_digest"],
        "entries": entries,
        "totals": {
            "operations": {op: count for op, count in operations.items() if count},
            "coin_start": source["initial_coins"],
            "coin_end": state["coins"],
            "coin_spent": spent,
            "inventory_net": _net(entries, "inventory_delta"),
            "resource_net": _net(entries, "resource_delta"),
            "merchant_net": _net(entries, "merchant_delta"),
            "reputation": state["reputation"],
            "delivered": state["delivered"],
            "ending": state["ending"],
        },
    }
    report["report_digest"] = digest(report)
    if len(canonical(report)) > MAX_BYTES:
        raise HarborError("market report exceeds byte limit")
    return report


def verify_market_report(report: Any) -> dict[str, Any]:
    """Rehashing forged totals never establishes gameplay authority."""
    _keys(report, {"schema", "bundle", "source_digest", "terminal_digest", "entries", "totals", "report_digest"}, "market report")
    if report["schema"] != SCHEMA or len(canonical(report)) > MAX_BYTES:
        raise HarborError("unsupported or oversized market report")
    if report["report_digest"] != digest({k: v for k, v in report.items() if k != "report_digest"}):
        raise HarborError("market report digest mismatch")
    recreated = market_report(report["bundle"])
    if recreated != report:
        raise HarborError("market report replay mismatch")
    return deepcopy(recreated["totals"])


def market_checkpoint(report: Any, tick: int) -> dict[str, Any]:
    verify_market_report(report)
    return market_report(checkpoint(report["bundle"], tick))


def market_resume(report: Any, actions: Any, *, expected_terminal_digest: str, require_win: bool = False) -> dict[str, Any]:
    verify_market_report(report)
    result = market_report(resume_bundle(
        report["bundle"], actions, expected_terminal_digest=expected_terminal_digest,
        require_win=require_win,
    ))
    if result["entries"][:len(report["entries"])] != report["entries"]:
        raise HarborError("market continuation rewrote history")
    return result


def market_futures(portfolio: Any) -> dict[str, Any]:
    endings = verify_portfolio(portfolio)
    entries = []
    for branch in portfolio["entries"]:
        report = market_report(branch["bundle"])
        totals = verify_market_report(report)
        if totals["ending"] != endings[branch["name"]]:
            raise HarborError("market ending mismatch")
        entries.append({
            "name": branch["name"],
            "terminal_digest": branch["terminal_digest"],
            "ledger": report,
            "totals": totals,
        })
    result = {
        "schema": PORTFOLIO_SCHEMA,
        "portfolio": deepcopy(portfolio),
        "portfolio_digest": portfolio["portfolio_digest"],
        "entries": entries,
    }
    result["report_digest"] = digest(result)
    if len(canonical(result)) > MAX_BYTES * 4:
        raise HarborError("market futures exceed byte limit")
    return result


def verify_market_futures(report: Any) -> list[dict[str, Any]]:
    _keys(report, {"schema", "portfolio", "portfolio_digest", "entries", "report_digest"}, "market futures")
    if report["schema"] != PORTFOLIO_SCHEMA or len(canonical(report)) > MAX_BYTES * 4:
        raise HarborError("unsupported or oversized market futures")
    if report["report_digest"] != digest({k: v for k, v in report.items() if k != "report_digest"}):
        raise HarborError("market futures digest mismatch")
    if not isinstance(report["portfolio"], dict) or report["portfolio_digest"] != report["portfolio"].get("portfolio_digest"):
        raise HarborError("market futures root mismatch")
    recreated = market_futures(report["portfolio"])
    if recreated != report:
        raise HarborError("market futures replay mismatch")
    return [{"name": x["name"], "totals": deepcopy(x["totals"]), "terminal_digest": x["terminal_digest"]} for x in recreated["entries"]]
