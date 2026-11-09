"""Cutscene readiness checklist — Pareto gate before a scene ships.

Covers skip, length, readability, pacing, camera, audio, and handoff.
"""

from __future__ import annotations


def cutscene_checklist() -> list[str]:
    return [
        "Skippable without losing required info",
        "Required beats also exist in world or log",
        "Length justified (short unless climax)",
        "Speaker and action readable",
        "Pacing has establish/turn/button",
        "Camera keeps subject clear",
        "Audio does not fight text",
        "Handoff restores sensible control",
        "No soft-lock",
        "Era constraints respected",
    ]
