"""Scope and cut-line — Pareto control against creep.

Explicit must/should/could and a pre-agreed cut line.
"""

from __future__ import annotations

from typing import Any


def scope_cutline(
    title: str,
    must: list[str],
    should: list[str] | None = None,
    could: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "title": title,
        "must": must,
        "should": should or [],
        "could": could or [],
        "cut_line": "If schedule or quality slips, drop from could, then should. Never drop must without re-scoping the fantasy.",
        "review": "Revisit at vertical-slice approval and again before content lock",
    }


def default_adventure_scope(title: str) -> dict[str, Any]:
    return scope_cutline(
        title,
        must=[
            "critical path completable",
            "core verb taught and reliable",
            "no soft-lock",
            "visible clues on gates",
        ],
        should=[
            "one optional area",
            "hint ladder on all critical puzzles",
            "basic audio feedback",
        ],
        could=[
            "additional endings",
            "cosmetic variants",
            "extended lore logs",
        ],
    )
