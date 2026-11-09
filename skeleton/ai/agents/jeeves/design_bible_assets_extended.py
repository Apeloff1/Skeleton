"""Design bible section templates and asset quality checklists.
Companion material for full creation and adventure capabilities.
"""

from __future__ import annotations

from typing import Any


def bible_section_template(section: str) -> dict[str, Any]:
    return {
        "section": section,
        "required": ["purpose", "rules", "examples", "acceptance_criteria", "open_questions"],
        "acceptance_criteria_example": f"{section} has at least one measurable gate",
    }


def asset_quality_checklist(tier: str = "polished") -> list[str]:
    base = [
        "Palette matches target era/core",
        "Silhouettes readable at native resolution",
        "Interactive vs scenic elements distinguishable",
        "Examine text present and informative",
        "Provenance and license recorded",
    ]
    if tier in ("polished", "premium"):
        base += [
            "Consistent light direction",
            "Purposeful animation timing",
            "Audio feedback on every interaction",
            "UI does not obscure critical scene info",
        ]
    return base


def era_style_notes(era: str) -> dict[str, str]:
    notes = {
        "8bit": "Bold silhouettes, minimal frames, high contrast, sparse text",
        "16bit": "Richer palettes, layered backgrounds where supported, short paragraphs",
        "handheld": "Small-screen readability, short loops, high-contrast UI",
        "32bit": "Pre-rendered or low-poly clarity, CD audio possible",
    }
    return {"era": era, "notes": notes.get(era, "Respect declared core limits")}
