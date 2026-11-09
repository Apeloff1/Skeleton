"""Safe market action preview using the real game transition engine.

A preview is not a committed save. Invalid gameplay yields a bounded,
explicit rejection without mutating the verified source or checkpoint.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import (
    HarborError, MAX_BUNDLE_BYTES, _keys, canonical, digest,
    normalize_action, step, verify_bundle,
)
from .harbor_crafting_market import market_report
from .harbor_crafting_sessions import resume_bundle

SCHEMA = "skeleton.game.harbor.market-preview.v1"
MAX_PREVIEW_ACTIONS = 16
MAX_BYTES = MAX_BUNDLE_BYTES * 2


def preview_market(bundle: Any, actions: Any) -> dict[str, Any]:
    """Preview legal action prefixes and first collision/stock/cost failure."""
    verify_bundle(bundle)
    if not isinstance(actions, list) or not 1 <= len(actions) <= MAX_PREVIEW_ACTIONS:
        raise HarborError("market preview action count invalid")
    if len(actions) > bundle["source"]["max_ticks"] - len(bundle["events"]):
        raise HarborError("market preview exceeds tick budget")
    normalized = [normalize_action(action) for action in actions]
    state = deepcopy(bundle["state"])
    accepted: list[dict[str, Any]] = []
    rejected_at: int | None = None
    reason: str | None = None
    for index, action in enumerate(normalized):
        try:
            updated = step(bundle["source"], state, action)
        except HarborError as exc:
            rejected_at = index
            reason = str(exc)
            break
        accepted.append({
            "sequence": len(bundle["events"]) + index,
            "action": deepcopy(action),
            "before": digest(state),
            "after": digest(updated),
            "inventory_delta": {
                item: updated["inventory"].get(item, 0) - state["inventory"].get(item, 0)
                for item in sorted(set(updated["inventory"]) | set(state["inventory"]))
                if updated["inventory"].get(item, 0) != state["inventory"].get(item, 0)
            },
            "coin_delta": updated["coins"] - state["coins"],
        })
        state = updated
    result = {
        "schema": SCHEMA,
        "bundle": deepcopy(bundle),
        "source_digest": bundle["source_digest"],
        "expected_terminal_digest": bundle["terminal_digest"],
        "actions": normalized,
        "accepted": accepted,
        "rejected_at": rejected_at,
        "reason": reason,
        "preview_state": deepcopy(state),
        "preview_terminal_digest": digest(state),
    }
    result["preview_digest"] = digest(result)
    if len(canonical(result)) > MAX_BYTES:
        raise HarborError("market preview exceeds byte limit")
    return result


def verify_market_preview(preview: Any) -> dict[str, Any]:
    _keys(preview, {
        "schema", "bundle", "source_digest", "expected_terminal_digest",
        "actions", "accepted", "rejected_at", "reason", "preview_state",
        "preview_terminal_digest", "preview_digest",
    }, "market preview")
    if preview["schema"] != SCHEMA or len(canonical(preview)) > MAX_BYTES:
        raise HarborError("unsupported or oversized market preview")
    if preview["preview_digest"] != digest({k: v for k, v in preview.items() if k != "preview_digest"}):
        raise HarborError("market preview digest mismatch")
    recreated = preview_market(preview["bundle"], preview["actions"])
    if recreated != preview:
        raise HarborError("market preview replay mismatch")
    return {
        "accepted": len(recreated["accepted"]),
        "rejected_at": recreated["rejected_at"],
        "reason": recreated["reason"],
        "terminal_digest": recreated["preview_terminal_digest"],
    }


def apply_market_preview(preview: Any, *, expected_terminal_digest: str, require_win: bool = False) -> dict[str, Any]:
    """Commit a fully legal preview only against the exact source-bound lease."""
    verify_market_preview(preview)
    if expected_terminal_digest != preview["expected_terminal_digest"]:
        raise HarborError("stale market preview lease")
    if preview["rejected_at"] is not None:
        raise HarborError("cannot apply rejected market preview")
    resumed = resume_bundle(
        preview["bundle"], preview["actions"],
        expected_terminal_digest=expected_terminal_digest, require_win=require_win,
    )
    if digest(resumed["state"]) != preview["preview_terminal_digest"]:
        raise HarborError("market preview apply divergence")
    return market_report(resumed)
