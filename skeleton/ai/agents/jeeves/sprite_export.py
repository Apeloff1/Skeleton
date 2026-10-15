"""Sprite export and catalog — Pareto handoff to the asset pipeline.

Every sprite sheet leaves with identity and constraints.
"""

from __future__ import annotations

from typing import Any


def export_spec(sprite_id: str, era: str) -> dict[str, Any]:
    return {
        "id": sprite_id,
        "era": era,
        "required_meta": ["source", "license", "palette_count", "frame_size", "animations"],
        "naming": "consistent, no spaces, era prefix optional",
        "rule": "Catalog insert fails if meta is incomplete",
        "link": "Provenance gate applies",
    }
