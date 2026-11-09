"""Replay-verified waypoint itinerary: navigate, interact, save and export.

A waypoint is an authored destination followed by one optional canonical
gameplay action. No scripted interaction can bypass collision, resource
availability, merchant stock, earned choices or remaining tick budgets.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import (
    HarborError, MAX_BUNDLE_BYTES, _integer, _keys, canonical, digest,
    normalize_action, verify_bundle,
)
from .harbor_crafting_route import MAX_ROUTE_STEPS, plan_route
from .harbor_crafting_sessions import resume_bundle

SCHEMA = "skeleton.game.harbor.itinerary.v1"
MAX_STOPS = 16
MAX_ITINERARY_BYTES = MAX_BUNDLE_BYTES * 4
FIELDS = {
    "schema", "root", "stops", "max_steps", "actions", "segments",
    "result", "itinerary_digest",
}


def build_itinerary(
    root: Any,
    stops: Any,
    *,
    expected_terminal_digest: str,
    max_steps: int = MAX_ROUTE_STEPS,
) -> dict[str, Any]:
    """Execute a finite, deterministic itinerary from a CAS-verified save."""
    verify_bundle(root)
    _integer(max_steps, 1, MAX_ROUTE_STEPS, "itinerary leg budget")
    if (
        not isinstance(expected_terminal_digest, str)
        or expected_terminal_digest != root["terminal_digest"]
    ):
        raise HarborError("stale itinerary checkpoint")
    if not isinstance(stops, list) or not 1 <= len(stops) <= MAX_STOPS:
        raise HarborError("invalid itinerary stop count")
    if len(canonical(stops)) > MAX_BUNDLE_BYTES:
        raise HarborError("itinerary source exceeds byte limit")
    current = deepcopy(root)
    segments: list[dict[str, Any]] = []
    actions: list[dict[str, str]] = []
    for index, stop in enumerate(stops):
        _keys(stop, {"goal", "action"}, "itinerary stop")
        if current["state"]["ending"] is not None:
            raise HarborError("itinerary continues after ending")
        route = plan_route(
            current, stop["goal"],
            expected_terminal_digest=current["terminal_digest"],
            max_steps=max_steps,
        )
        leg_actions = route["actions"]
        current = route["result"]
        interaction = stop["action"]
        if interaction is not None:
            interaction = normalize_action(interaction)
            current = resume_bundle(
                current, [interaction],
                expected_terminal_digest=current["terminal_digest"],
            )
        actions.extend(deepcopy(leg_actions))
        if interaction is not None:
            actions.append(deepcopy(interaction))
        segments.append({
            "index": index,
            "goal": deepcopy(route["goal"]),
            "path": deepcopy(leg_actions),
            "action": deepcopy(interaction),
            "terminal_digest": current["terminal_digest"],
        })
    report = {
        "schema": SCHEMA,
        "root": deepcopy(root),
        "stops": deepcopy(stops),
        "max_steps": max_steps,
        "actions": actions,
        "segments": segments,
        "result": current,
    }
    report["itinerary_digest"] = digest(report)
    if len(canonical(report)) > MAX_ITINERARY_BYTES:
        raise HarborError("itinerary report exceeds byte limit")
    return report


def verify_itinerary(report: Any) -> dict[str, Any]:
    """Independently reconstruct all routes and actions from original source."""
    _keys(report, FIELDS, "itinerary")
    if report["schema"] != SCHEMA or len(canonical(report)) > MAX_ITINERARY_BYTES:
        raise HarborError("unsupported or oversized itinerary")
    if report["itinerary_digest"] != digest({
        key: value for key, value in report.items()
        if key != "itinerary_digest"
    }):
        raise HarborError("itinerary digest mismatch")
    root = report["root"]
    if not isinstance(root, dict):
        raise HarborError("itinerary root missing")
    rebuilt = build_itinerary(
        root, report["stops"],
        expected_terminal_digest=root.get("terminal_digest"),
        max_steps=report["max_steps"],
    )
    if rebuilt != report:
        raise HarborError("itinerary replay mismatch")
    return {
        "source_digest": root["source_digest"],
        "root_terminal_digest": root["terminal_digest"],
        "terminal_digest": rebuilt["result"]["terminal_digest"],
        "stops": len(rebuilt["segments"]),
        "actions": len(rebuilt["actions"]),
        "ending": rebuilt["result"]["state"]["ending"],
    }
