"""
SERAPHIM CLASS — Intricacy Focus Layer
Auto-generates a Seraphim counterpart for EVERY Angel agent (~4,326).

While Angels enforce COMPLEXITY (simplification & clarity),
Seraphim enforce INTRICACY — the fine details, precision, nuance, edge cases,
subtle interactions, and the micro-level craftsmanship that separates
good games from masterpieces.

Philosophy: "God is in the details. The difference between AAA and legendary
is the ten thousand intricate touches that nobody notices consciously but
everybody feels."

Total: ~4,326 Seraphim (one per every Angel)
Grand system total with Seraphim: ~13,016 agents
"""

import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

from routes.game_angel_class import get_all_angel_agents


# =============================================================================
# SERAPHIM INTRICACY FOCUS AREAS
# =============================================================================

INTRICACY_FOCUSES = [
    "Micro-Animation Polish",
    "Edge Case Detection",
    "Subtle State Transition Smoothing",
    "Sub-Pixel Precision",
    "Audio Layering Nuance",
    "Haptic Feedback Granularity",
    "Color Gradient Subtlety",
    "Frame-Perfect Timing",
    "Physics Micro-Interaction Fidelity",
    "Font Kerning & Typography Detail",
    "Shadow Penumbra Accuracy",
    "Particle System Fine-Tuning",
    "Input Latency Micro-Optimization",
    "Ambient Sound Layering Detail",
    "Material Texture Micro-Detail",
    "Weather Transition Smoothness",
    "NPC Micro-Expression Nuance",
    "Lighting Bounce Accuracy",
    "Menu Animation Easing Curves",
    "Environmental Storytelling Subtlety",
    "Dialogue Timing & Cadence Polish",
    "Camera Shake Frequency Tuning",
    "Footstep Surface Variation",
    "Cloth Simulation Drape Detail",
    "Water Surface Ripple Fidelity",
    "Foliage Wind Response Subtlety",
    "Weapon Impact Micro-Feedback",
    "Loading Screen Transition Grace",
    "Achievement Notification Timing",
    "Death Animation Dignity & Weight",
]


SERAPHIM_PERSONA_TEMPLATE = """You are Seraphim-{name}, the INTRICACY ARBITER and six-winged overseer of Angel-{angel_name}.

YOUR SERAPHIM MANDATE — INTRICACY FOCUS:
- You exist to ensure the FINEST DETAILS are perfect in every aspect of game development
- You see what others miss — the sub-pixel misalignment, the 2ms input lag, the slightly wrong easing curve
- You enforce INTRICACY — the micro-level craftsmanship that separates good from legendary
- Your domain: the ten thousand subtle touches nobody notices consciously but everybody FEELS
- Your primary focus: {intricacy_focus}
- You oversee Angel: {angel_name} (who manages complexity for {original_name})

SERAPHIM INTRICACY PROTOCOL (8-STEP):
1. DETAIL SCAN: What micro-details exist in this work? What's missing?
2. EDGE CASE PROBE: What edge cases, corner cases, and rare scenarios are unhandled?
3. NUANCE CHECK: Are subtle variations present? (Not all footsteps sound the same)
4. TRANSITION AUDIT: Are all state transitions smooth? No pops, jumps, or jarring cuts?
5. SENSORY LAYER REVIEW: Does every sense get detailed attention? (Visual + Audio + Haptic)
6. MICRO-INTERACTION VERIFY: Do small interactions feel polished? (Button press feel, hover states)
7. CONSISTENCY MICROSCOPE: Are similar elements identically detailed across the entire project?
8. SERAPHIM VERDICT: INTRICACY MASTERED / POLISH NEEDED / DETAIL VIOLATION

SERAPHIM PHILOSOPHY:
- "God is in the details" — Mies van der Rohe
- The last 10% of polish takes 90% of the effort — and it's worth every second
- Players can't articulate WHY a game feels amazing — it's the intricacy they can't see
- A single wrong animation frame at 60fps is visible to the subconscious
- The difference between "good" and "masterpiece" is 10,000 tiny details done right
- Intricacy is not complexity — it's the precision within simplicity

You have six wings and infinite patience for detail. You see everything. Nothing escapes your gaze."""


def _generate_seraphim(angel: dict, idx: int) -> dict:
    """Generate a seraphim (intricacy arbiter) for a single angel agent."""
    focus = INTRICACY_FOCUSES[idx % len(INTRICACY_FOCUSES)]
    angel_name = angel.get("name", "Unknown")
    angel_id = angel.get("id", f"unknown_{idx}")
    original_name = angel.get("original_name", "Unknown")

    return {
        "id": f"seraphim_{angel_id}",
        "name": f"Seraphim-{angel_name}",
        "role": f"Intricacy Arbiter for {angel_name}",
        "angel_id": angel_id,
        "angel_name": angel_name,
        "original_name": original_name,
        "original_id": angel.get("original_id", ""),
        "angel_layer": angel.get("layer", "unknown"),
        "specialty": f"seraphim_{angel.get('specialty', 'intricacy')}",
        "intricacy_focus": focus,
        "color": _seraphim_color(angel.get("color", "#FFF5D4")),
        "category": f"seraphim_{angel.get('category', 'general')}",
        "category_name": f"Seraphim: {angel.get('category_name', 'Angel')}",
        "persona": SERAPHIM_PERSONA_TEMPLATE.format(
            name=original_name,
            angel_name=angel_name,
            original_name=original_name,
            intricacy_focus=focus,
        ),
    }


def _seraphim_color(hex_color: str) -> str:
    """Create a seraphim color — radiant white-gold with celestial fire tint."""
    try:
        hex_color = hex_color.lstrip('#')
        r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
        # Seraphim colors: blend toward radiant white-gold (#FFFAE5) with fire hints
        nr = min(255, (r + 255 + 255) // 3)
        ng = min(255, (g + 250 + 230) // 3)
        nb = min(255, (b + 229 + 200) // 3)
        return f"#{nr:02X}{ng:02X}{nb:02X}"
    except Exception:
        return "#FFFAE5"


# =============================================================================
# SERAPHIM CACHE
# =============================================================================

_SERAPHIM_CACHE = None


def _invalidate_seraphim_cache():
    global _SERAPHIM_CACHE
    _SERAPHIM_CACHE = None


def get_all_seraphim_agents() -> list:
    """Get ALL seraphim agents — one per every angel. Cached."""
    global _SERAPHIM_CACHE
    if _SERAPHIM_CACHE is not None:
        return _SERAPHIM_CACHE

    angels = get_all_angel_agents()
    _SERAPHIM_CACHE = [_generate_seraphim(a, i) for i, a in enumerate(angels)]
    return _SERAPHIM_CACHE


def get_seraphim_for_angel(angel_id: str) -> dict | None:
    """Get the seraphim counterpart for a specific angel."""
    seraphim = get_all_seraphim_agents()
    return next((s for s in seraphim if s["angel_id"] == angel_id), None)


def get_seraphim_for_original(original_id: str) -> list:
    """Get ALL seraphim related to an original agent (through its angels)."""
    seraphim = get_all_seraphim_agents()
    target_angel_ids = [
        f"angel_{original_id}",
        f"angel_shadow_{original_id}",
        f"angel_ghost_{original_id}",
    ]
    return [s for s in seraphim if s["angel_id"] in target_angel_ids]


def get_seraphim_prompt(seraphim_id: str, target_output: str, context: str) -> tuple:
    """Returns (system_prompt, user_prompt) for a seraphim intricacy review."""
    seraphim = get_all_seraphim_agents()
    s = next((x for x in seraphim if x["id"] == seraphim_id), None)
    if not s:
        return ("You are an intricacy arbiter.", f"Review intricacy of: {target_output}")

    system_prompt = s["persona"]
    user_prompt = f"""SERAPHIM INTRICACY REVIEW for Seraphim-{s['original_name']}

TARGET ANGEL: {s['angel_name']}
ORIGINAL AGENT: {s['original_name']}
LAYER CHAIN: Original → Shadow/Ghost → Angel → Seraphim (you)
INTRICACY FOCUS: {s['intricacy_focus']}
GAME CONTEXT: {context}

OUTPUT TO REVIEW FOR INTRICACY:
{target_output}

Perform your full 8-step SERAPHIM INTRICACY PROTOCOL:
1. DETAIL SCAN — What micro-details exist? What's missing?
2. EDGE CASE PROBE — What rare scenarios are unhandled?
3. NUANCE CHECK — Are subtle variations present?
4. TRANSITION AUDIT — Are all state transitions smooth?
5. SENSORY LAYER REVIEW — Visual + Audio + Haptic detail?
6. MICRO-INTERACTION VERIFY — Do small interactions feel polished?
7. CONSISTENCY MICROSCOPE — Identical detail level across project?
8. SERAPHIM VERDICT (INTRICACY MASTERED / POLISH NEEDED / DETAIL VIOLATION)

Nothing escapes your gaze. The details are everything."""

    return (system_prompt, user_prompt)


def get_seraphim_class_stats() -> dict:
    """Get statistics about the Seraphim Class."""
    seraphim = get_all_seraphim_agents()

    by_angel_layer = {"original": 0, "shadow": 0, "ghost": 0}
    by_focus = {}
    for s in seraphim:
        layer = s.get("angel_layer", "unknown")
        by_angel_layer[layer] = by_angel_layer.get(layer, 0) + 1
        focus = s.get("intricacy_focus", "unknown")
        by_focus[focus] = by_focus.get(focus, 0) + 1

    return {
        "total_seraphim": len(seraphim),
        "by_angel_layer": by_angel_layer,
        "intricacy_focuses": by_focus,
        "protocol_steps": 8,
        "verdicts": ["INTRICACY_MASTERED", "POLISH_NEEDED", "DETAIL_VIOLATION"],
        "philosophy": "God is in the details",
    }
