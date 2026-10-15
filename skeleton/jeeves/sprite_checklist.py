"""Sprite readiness checklist — Pareto gate before a sprite set ships.

Covers silhouette, palette, animation, budget, states, export, and reuse.
"""

from __future__ import annotations


def sprite_checklist() -> list[str]:
    return [
        "Silhouette readable at native scale",
        "Black-only version still identifiable",
        "Palette inside era budget",
        "Bright values reserved for focus",
        "Required states (idle/move/act/hurt) distinct",
        "Act/contact frame is clearest",
        "Frame count and size inside budget",
        "Export meta complete (source, license, size, anims)",
        "Reuse considered before new unique art",
        "Provenance gate passed",
    ]
