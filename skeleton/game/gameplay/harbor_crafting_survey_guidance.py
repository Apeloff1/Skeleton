"""Replay-verified deterministic navigation to the next unvisited survey site."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import HarborError, _keys, canonical, digest
from .harbor_crafting_route import plan_route
from .harbor_crafting_survey import MAX_REPORT_BYTES, verify_survey

SCHEMA = "skeleton.game.harbor.survey-guidance.v1"
MAX_GUIDANCE_BYTES = MAX_REPORT_BYTES * 2
FIELDS = {"schema", "survey", "site_id", "route", "guidance_digest"}


def survey_hint(report: Any, *, max_steps: int = 64) -> dict[str, Any]:
    status = verify_survey(report)
    if report["bundle"]["state"]["ending"] is not None:
        raise HarborError("cannot navigate completed survey")
    visited = set(status["visited"])
    candidates = []
    for site in report["board"]["sites"]:
        if site["id"] in visited:
            continue
        try:
            route = plan_route(
                report["bundle"], site["at"],
                expected_terminal_digest=report["bundle"]["terminal_digest"],
                max_steps=max_steps,
            )
        except HarborError as exc:
            if "route unavailable within bounded search" not in str(exc):
                raise
            continue
        candidates.append((len(route["actions"]), site["id"], route))
    if not candidates:
        raise HarborError("no reachable unvisited survey site")
    candidates.sort(key=lambda entry: (entry[0], entry[1]))
    _, name, route = candidates[0]
    guidance = {
        "schema": SCHEMA, "survey": deepcopy(report),
        "site_id": name, "route": route,
    }
    guidance["guidance_digest"] = digest(guidance)
    if len(canonical(guidance)) > MAX_GUIDANCE_BYTES:
        raise HarborError("survey guidance exceeds byte limit")
    return guidance


def verify_survey_hint(guidance: Any) -> dict[str, Any]:
    _keys(guidance, FIELDS, "survey guidance")
    if guidance["schema"] != SCHEMA or len(canonical(guidance)) > MAX_GUIDANCE_BYTES:
        raise HarborError("invalid survey guidance size or schema")
    if guidance["guidance_digest"] != digest({
        key: value for key, value in guidance.items() if key != "guidance_digest"
    }):
        raise HarborError("survey guidance digest mismatch")
    route = guidance["route"]
    if not isinstance(route, dict):
        raise HarborError("survey guidance route missing")
    rebuilt = survey_hint(guidance["survey"], max_steps=route.get("max_steps"))
    if rebuilt != guidance:
        raise HarborError("survey guidance replay mismatch")
    return {
        "site_id": rebuilt["site_id"],
        "steps": len(rebuilt["route"]["actions"]),
        "terminal_digest": rebuilt["route"]["result"]["terminal_digest"],
    }
