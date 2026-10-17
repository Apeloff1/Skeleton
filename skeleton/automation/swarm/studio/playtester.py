"""QA playtester.

Loads the assembled playable, runs it headless, and files blocker issues the
planner can schedule back onto the systems role.
"""

from __future__ import annotations

import json
from typing import Any, Mapping

from skeleton.automation.swarm.studio.loop import coverage, simulate
from skeleton.automation.swarm.studio.tools import StudioTools, ToolError


def playtest_project(tools: StudioTools, brief: Mapping[str, Any]) -> dict[str, Any]:
    try:
        raw = tools.read_text("playable.json")
        playable = json.loads(raw)
    except (ToolError, json.JSONDecodeError, OSError):
        return _report(
            {
                "booted": False,
                "ticks": 0,
                "verbs": [],
                "phases": [],
                "won": False,
                "crashed": False,
                "loop_works": False,
            },
            brief,
            issues=[
                {
                    "issue_id": "issue-boot",
                    "severity": "blocker",
                    "owner_role": "systems",
                    "summary": "playable did not boot",
                    "evidence": {"file": "playable.json"},
                }
            ],
            coverage_score=0.0,
        )
    if not isinstance(playable, dict):
        playable = {}
    signals = simulate(playable)
    covered = coverage(playable, brief) if signals["booted"] else 0.0
    issues = _issues(playable, signals, covered)
    return _report(signals, brief, issues=issues, coverage_score=covered)


def _issues(playable: Mapping[str, Any], signals: Mapping[str, Any], covered: float) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    if not signals.get("booted"):
        issues.append(_issue("issue-boot", "systems", "playable did not boot"))
        return issues
    if signals.get("crashed"):
        issues.append(_issue("issue-crash", "systems", "playable crashed during the loop"))
    if not signals.get("won"):
        summary = "unreachable win condition"
        win = playable.get("win") if isinstance(playable.get("win"), Mapping) else {}
        item = win.get("has_item")
        placed = False
        rooms = playable.get("rooms") if isinstance(playable.get("rooms"), Mapping) else {}
        for room in rooms.values():
            if isinstance(room, Mapping) and item in (room.get("items") or []):
                placed = True
        if item and not placed:
            summary = "unreachable win item is not placed"
        issues.append(_issue("issue-win", "systems", summary, {"ticks": signals.get("ticks", 0)}))
    if not signals.get("loop_works"):
        issues.append(_issue("issue-loop", "qa", "core loop did not advance", severity="major"))
    if covered < 0.6:
        issues.append(_issue("issue-spec", "designer", "spec coverage is below the bar", severity="major"))
    return issues


def _issue(issue_id: str, owner: str, summary: str, evidence: dict[str, Any] | None = None, *, severity: str = "blocker") -> dict[str, Any]:
    return {
        "issue_id": issue_id,
        "severity": severity,
        "owner_role": owner,
        "summary": summary,
        "evidence": evidence or {},
    }


def _report(
    signals: Mapping[str, Any],
    brief: Mapping[str, Any],
    *,
    issues: list[dict[str, Any]],
    coverage_score: float,
) -> dict[str, Any]:
    return {
        "booted": bool(signals.get("booted")),
        "ticks": int(signals.get("ticks") or 0),
        "verbs": list(signals.get("verbs") or []),
        "loop_works": bool(signals.get("loop_works")),
        "won": bool(signals.get("won")),
        "spec_coverage": coverage_score,
        "issues": issues,
        "signals": {
            "phases": list(signals.get("phases") or []),
            "crashed": bool(signals.get("crashed")),
            "genre": brief.get("genre"),
        },
    }
