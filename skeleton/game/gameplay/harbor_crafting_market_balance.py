"""Source-bound playable economy editing and replay-proven balance comparison."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import HarborError, MAX_BUNDLE_BYTES, _keys, canonical, digest, validate_source
from .harbor_crafting_authoring import author_revision, verify_revision
from .harbor_crafting_market import market_report, verify_market_report
from .harbor_crafting_missions import solve_missions, validate_board, verify_mission_report

SCHEMA = "skeleton.game.harbor.market-balance.v1"
MAX_BYTES = MAX_BUNDLE_BYTES * 8
ALLOWED_EDITS = {"stock", "merchant_price", "recipe", "delivery"}


def _earned_run(source: dict[str, Any], board: dict[str, Any], choice: str) -> dict[str, Any]:
    mission = solve_missions(source, board, choice=choice)
    verify_mission_report(mission, require_all=True)
    market = market_report(mission["bundle"])
    totals = verify_market_report(market)
    if totals["ending"] is None or not totals["delivered"]:
        raise HarborError("market balance did not earn victory")
    return {
        "mission": mission,
        "market": market,
        "terminal_digest": mission["bundle"]["terminal_digest"],
        "ending": totals["ending"],
        "points": mission["points"],
        "coin_end": totals["coin_end"],
        "coin_spent": totals["coin_spent"],
        "ticks": mission["bundle"]["state"]["tick"],
    }


def balance_market(
    source: Any, board: Any, operations: Any, *,
    expected_source_digest: str, choice: str = "signal",
) -> dict[str, Any]:
    """Edit an authored economy and prove both before/after games remain playable.

    Invalid, unplayable or non-economic edits fail closed. This is a bounded
    source revision, not a mutable live-save economy modification.
    """
    original = validate_source(source)
    authored = validate_board(board, original)
    if not isinstance(operations, list) or not operations:
        raise HarborError("market balance requires edits")
    if any(not isinstance(op, dict) or op.get("op") not in ALLOWED_EDITS for op in operations):
        raise HarborError("market balance forbids non-economic edits")
    revision = author_revision(original, operations, expected_source_digest=expected_source_digest)
    edited = verify_revision(revision)
    validate_board(authored, edited)
    before = _earned_run(original, authored, choice)
    after = _earned_run(edited, authored, choice)
    result = {
        "schema": SCHEMA,
        "revision": revision,
        "board": deepcopy(authored),
        "board_digest": digest(authored),
        "choice": choice,
        "before": before,
        "after": after,
        "delta": {
            "points": after["points"] - before["points"],
            "coin_end": after["coin_end"] - before["coin_end"],
            "coin_spent": after["coin_spent"] - before["coin_spent"],
            "ticks": after["ticks"] - before["ticks"],
        },
    }
    result["comparison_digest"] = digest(result)
    if len(canonical(result)) > MAX_BYTES:
        raise HarborError("market balance comparison exceeds byte limit")
    return result


def verify_market_balance(comparison: Any) -> dict[str, Any]:
    _keys(comparison, {
        "schema", "revision", "board", "board_digest", "choice",
        "before", "after", "delta", "comparison_digest",
    }, "market balance comparison")
    if comparison["schema"] != SCHEMA or len(canonical(comparison)) > MAX_BYTES:
        raise HarborError("unsupported or oversized market balance comparison")
    if comparison["comparison_digest"] != digest({
        k: v for k, v in comparison.items() if k != "comparison_digest"
    }):
        raise HarborError("market balance comparison digest mismatch")
    revision = comparison["revision"]
    verify_revision(revision)
    if comparison["board_digest"] != digest(comparison["board"]):
        raise HarborError("market balance board mismatch")
    recreated = balance_market(
        revision["parent"], comparison["board"], revision["operations"],
        expected_source_digest=revision["parent_digest"], choice=comparison["choice"],
    )
    if recreated != comparison:
        raise HarborError("market balance gameplay replay mismatch")
    return {
        "source_digest": revision["source_digest"],
        "before_ending": recreated["before"]["ending"],
        "after_ending": recreated["after"]["ending"],
        "delta": deepcopy(recreated["delta"]),
    }
