"""Portable replay-verified mission comparisons across alternate saved futures.

This layer never treats a portfolio's digest as proof of game play. Each branch
is independently reconstructed by the canonical save engine before its quest
journal, consequences and score are derived.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import (
    HarborError, MAX_BUNDLE_BYTES, _keys, canonical, digest, verify_bundle,
)
from .harbor_crafting_missions import (
    mission_report, validate_board, verify_mission_report,
)
from .harbor_crafting_sessions import verify_portfolio

SCHEMA = "skeleton.game.harbor.mission-portfolio.v1"
MAX_BYTES = MAX_BUNDLE_BYTES * 8


def mission_branch_report(portfolio: Any, board: Any) -> dict[str, Any]:
    """Produce deterministic scorecards from a verified branching game save."""
    verified_endings = verify_portfolio(portfolio)
    root = portfolio["root"]
    verify_bundle(root)
    authored = validate_board(board, root["source"])
    entries = []
    for entry in portfolio["entries"]:
        name = entry["name"]
        bundle = entry["bundle"]
        report = mission_report(bundle, authored)
        summary = verify_mission_report(report)
        ending = bundle["state"]["ending"]
        if verified_endings[name] != ending:
            raise HarborError("branch ending disagrees with canonical replay")
        entries.append({
            "name": name,
            "ending": ending,
            "terminal_digest": bundle["terminal_digest"],
            "completed": summary["completed"],
            "points": summary["points"],
            "report": report,
        })
    result = {
        "schema": SCHEMA,
        "portfolio": deepcopy(portfolio),
        "portfolio_digest": portfolio["portfolio_digest"],
        "board": authored,
        "board_digest": digest(authored),
        "source_digest": root["source_digest"],
        "entries": entries,
    }
    result["report_digest"] = digest(result)
    if len(canonical(result)) > MAX_BYTES:
        raise HarborError("mission portfolio report exceeds byte limit")
    return result


def verify_mission_branch_report(report: Any) -> list[dict[str, Any]]:
    """Reject fabricated rankings, substituted branches and forged quest points."""
    _keys(report, {
        "schema", "portfolio", "portfolio_digest", "board", "board_digest",
        "source_digest", "entries", "report_digest",
    }, "mission portfolio report")
    if report["schema"] != SCHEMA or len(canonical(report)) > MAX_BYTES:
        raise HarborError("unsupported or oversized mission portfolio report")
    if report["report_digest"] != digest({k: v for k, v in report.items() if k != "report_digest"}):
        raise HarborError("mission portfolio report digest mismatch")
    portfolio = report["portfolio"]
    if not isinstance(portfolio, dict) or report["portfolio_digest"] != portfolio.get("portfolio_digest"):
        raise HarborError("mission portfolio custody mismatch")
    if report["board_digest"] != digest(report["board"]):
        raise HarborError("mission portfolio board mismatch")
    if not isinstance(portfolio.get("root"), dict) or report["source_digest"] != portfolio["root"].get("source_digest"):
        raise HarborError("mission portfolio source mismatch")
    rebuilt = mission_branch_report(portfolio, report["board"])
    if rebuilt != report:
        raise HarborError("mission portfolio replay mismatch")
    return [
        {
            "name": entry["name"],
            "ending": entry["ending"],
            "points": entry["points"],
            "completed": deepcopy(entry["completed"]),
            "terminal_digest": entry["terminal_digest"],
        }
        for entry in rebuilt["entries"]
    ]
