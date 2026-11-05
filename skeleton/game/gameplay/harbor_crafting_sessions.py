"""Deterministic Lantern Quay checkpoint, continuation, and alternate-ending custody.

All operations verify the complete original replay before accepting a checkpoint.
No saved state or outer digest is trusted as a gameplay authority.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import (
    HarborError, MAX_BUNDLE_BYTES, canonical, digest, export_bundle,
    normalize_action, verify_bundle,
)

PORTFOLIO_SCHEMA = "skeleton.game.harbor.portfolio.v1"
MAX_BRANCHES = 4


def _verified_actions(bundle: Any) -> tuple[dict[str, Any], list[dict[str, str]]]:
    verify_bundle(bundle)
    return deepcopy(bundle["source"]), [deepcopy(event["action"]) for event in bundle["events"]]


def checkpoint(bundle: Any, tick: int) -> dict[str, Any]:
    """Rebuild a historical checkpoint from source and the verified event prefix."""
    source, actions = _verified_actions(bundle)
    if type(tick) is not int or not 0 <= tick <= len(actions):
        raise HarborError("checkpoint tick outside verified history")
    restored = export_bundle(source, actions[:tick])
    if restored["events"] != bundle["events"][:tick]:
        raise HarborError("checkpoint prefix mismatch")
    return restored


def state_at(bundle: Any, tick: int) -> dict[str, Any]:
    """Return a replay-derived state, never the untrusted embedded save state."""
    return deepcopy(checkpoint(bundle, tick)["state"])


def resume_bundle(
    bundle: Any,
    continuation: Any,
    *,
    expected_terminal_digest: str,
    require_win: bool = False,
) -> dict[str, Any]:
    """Compare-and-swap append, verifying source, original chain, and full result."""
    source, original = _verified_actions(bundle)
    if not isinstance(expected_terminal_digest, str) or expected_terminal_digest != bundle["terminal_digest"]:
        raise HarborError("stale checkpoint terminal digest")
    if not isinstance(continuation, list) or len(continuation) > source["max_ticks"] - len(original):
        raise HarborError("continuation exceeds remaining tick budget")
    additional = [normalize_action(action) for action in continuation]
    output = export_bundle(source, original + additional, require_win=require_win)
    if output["events"][:len(original)] != bundle["events"]:
        raise HarborError("replay continuation rewrote historical events")
    return output


def branch_portfolio(bundle: Any, branches: Any) -> dict[str, Any]:
    """Build independently verifiable alternative futures from one trusted root."""
    _verified_actions(bundle)
    if not isinstance(branches, dict) or not 1 <= len(branches) <= MAX_BRANCHES:
        raise HarborError("invalid branch count")
    if bundle["state"]["ending"] is not None:
        raise HarborError("cannot branch after earned ending")
    from .harbor_crafting import _identifier
    entries: list[dict[str, Any]] = []
    for name in sorted(branches):
        _identifier(name, "branch name")
        additional = branches[name]
        if not isinstance(additional, list):
            raise HarborError("branch actions must be a list")
        resumed = resume_bundle(
            bundle, additional,
            expected_terminal_digest=bundle["terminal_digest"],
        )
        entries.append({
            "name": name,
            "actions": deepcopy(additional),
            "bundle": resumed,
            "terminal_digest": resumed["terminal_digest"],
        })
    portfolio = {
        "schema": PORTFOLIO_SCHEMA,
        "root": deepcopy(bundle),
        "root_digest": bundle["bundle_digest"],
        "entries": entries,
    }
    portfolio["portfolio_digest"] = digest(portfolio)
    if len(canonical(portfolio)) > MAX_BUNDLE_BYTES:
        raise HarborError("portfolio exceeds byte limit")
    return portfolio


def verify_portfolio(portfolio: Any) -> dict[str, str | None]:
    """Recompute each branch; digest-only substitution is never accepted."""
    if not isinstance(portfolio, dict) or set(portfolio) != {
        "schema", "root", "root_digest", "entries", "portfolio_digest"
    }:
        raise HarborError("invalid portfolio fields")
    if portfolio["schema"] != PORTFOLIO_SCHEMA or len(canonical(portfolio)) > MAX_BUNDLE_BYTES:
        raise HarborError("invalid portfolio schema or size")
    if portfolio["portfolio_digest"] != digest({
        key: value for key, value in portfolio.items() if key != "portfolio_digest"
    }):
        raise HarborError("portfolio digest mismatch")
    root = portfolio["root"]
    verify_bundle(root)
    if root["bundle_digest"] != portfolio["root_digest"]:
        raise HarborError("portfolio root mismatch")
    entries = portfolio["entries"]
    if not isinstance(entries, list) or not 1 <= len(entries) <= MAX_BRANCHES:
        raise HarborError("invalid portfolio entries")
    result: dict[str, str | None] = {}
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {
            "name", "actions", "bundle", "terminal_digest"
        }:
            raise HarborError("invalid portfolio entry")
        from .harbor_crafting import _identifier
        name = _identifier(entry["name"], "branch name")
        if name in result:
            raise HarborError("duplicate branch name")
        replayed = resume_bundle(
            root, entry["actions"],
            expected_terminal_digest=root["terminal_digest"],
        )
        if replayed != entry["bundle"] or replayed["terminal_digest"] != entry["terminal_digest"]:
            raise HarborError("branch replay mismatch")
        result[name] = replayed["state"]["ending"]
    if list(result) != sorted(result):
        raise HarborError("noncanonical branch ordering")
    return result
