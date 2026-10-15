"""Production planning extensions: risk matrices, resource outlines, milestone templates.
Companion to full_game_creation_capability. Data-only.
"""

from __future__ import annotations

from typing import Any


def risk_matrix(title: str) -> dict[str, Any]:
    return {
        "title": title,
        "risks": [
            {"id": "scope", "likelihood": "medium", "impact": "high", "mitigation": "vertical-slice gate + backlog cut line"},
            {"id": "asset_bottleneck", "likelihood": "high", "impact": "medium", "mitigation": "style lock early + modular kit"},
            {"id": "era_violation", "likelihood": "low", "impact": "high", "mitigation": "core constraint checklist per asset"},
            {"id": "soft_lock", "likelihood": "medium", "impact": "high", "mitigation": "fairness audit + critical path test"},
            {"id": "provenance_gap", "likelihood": "medium", "impact": "medium", "mitigation": "catalog gate before content lock"},
        ],
    }


def resource_outline(weeks: int = 40) -> dict[str, Any]:
    return {
        "duration_weeks": weeks,
        "roles": ["designer", "narrative", "artist", "audio", "producer"],
        "note": "Relative allocation only; operator sets real capacity",
        "critical_path": ["design bible", "vertical slice", "content lock", "RC"],
    }


def milestone_template() -> list[dict[str, Any]]:
    return [
        {"name": "Concept lock", "gate": "pillars + high concept signed"},
        {"name": "Vertical slice", "gate": "one complete critical-path segment playable"},
        {"name": "Alpha", "gate": "all systems present, content incomplete ok"},
        {"name": "Content lock", "gate": "no new rooms/puzzles/flags"},
        {"name": "RC", "gate": "target core build + provenance audit"},
    ]
