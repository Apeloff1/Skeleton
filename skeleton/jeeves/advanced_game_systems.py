"""Advanced game systems — Pareto patterns for production-grade design.

Covers progression, economy-of-actions, narrative delivery, and systemic interactions.
Data-only. Composes with adventure and creation capabilities.
"""

from __future__ import annotations

from typing import Any


def progression_curve(stages: int = 5) -> dict[str, Any]:
    return {
        "stages": stages,
        "curve": "early mastery reward → mid complication → late expression",
        "gates": ["teach verb", "combine verbs", "constrain resources", "offer mastery expression"],
        "anti_patterns": ["sudden difficulty spike with no teach", "grind without new verb"],
    }


def action_economy(verbs: list[str]) -> dict[str, Any]:
    return {
        "verbs": verbs,
        "rule": "Every verb has cost, feedback, fail state, and at least one interesting combination",
        "density": "Prefer fewer deep verbs over many shallow ones",
        "teaching": "First use is safe and rewarded; later uses have risk/reward",
    }


def systemic_interaction_matrix(systems: list[str]) -> dict[str, Any]:
    pairs = []
    for i, a in enumerate(systems):
        for b in systems[i+1:]:
            pairs.append({"a": a, "b": b, "interaction": f"{a} can modify or gate {b}"})
    return {
        "systems": systems,
        "interactions": pairs[:12],  # cap for readability
        "note": "Document only interactions that create player-facing decisions",
    }


def narrative_delivery_plan() -> dict[str, Any]:
    return {
        "priority": ["environmental", "examine", "item text", "optional dialogue", "critical dialogue"],
        "rule": "Critical path understandable with minimal text; extra text rewards curiosity",
        "flags": "Narrative state is flag-driven and serializable",
        "pacing": "Setup, complication, midpoint reversal, climax, resolution",
    }


def advanced_package(title: str, verbs: list[str] | None = None) -> dict[str, Any]:
    verbs = verbs or ["examine", "use", "combine", "talk"]
    return {
        "title": title,
        "progression": progression_curve(),
        "action_economy": action_economy(verbs),
        "systems": systemic_interaction_matrix(["inventory", "dialogue", "environment", "flags"]),
        "narrative": narrative_delivery_plan(),
        "quality_bar": "Each system creates at least one interesting decision on the critical path",
    }
