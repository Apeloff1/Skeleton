"""Design decision log — Pareto memory for why choices were made.

Prevents re-litigating settled constraints.
"""

from __future__ import annotations

from typing import Any


def decision(
    title: str,
    choice: str,
    rationale: str,
    alternatives: list[str] | None = None,
    era: str | None = None,
) -> dict[str, Any]:
    return {
        "title": title,
        "choice": choice,
        "rationale": rationale,
        "alternatives_considered": alternatives or [],
        "era": era,
        "status": "accepted",
        "revisit_if": "New evidence from playtest or operator direction",
    }


def log_template(project: str) -> dict[str, Any]:
    return {
        "project": project,
        "entries": [],
        "rule": "Append-only. Supersede by new entry, do not silently edit history.",
    }
