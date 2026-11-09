"""
CHERUBIM CLASS — Diligence Focus Layer
Auto-generates a Cherubim counterpart for EVERY agent in the entire system (~13,016).

While Seraphim enforce INTRICACY (micro-details, polish, edge cases),
Cherubim enforce DILIGENCE — hard work, high standards, thoroughness,
no shortcuts, no laziness, no half-measures, and relentless pursuit of excellence.

Philosophy: "Genius is 1% inspiration and 99% perspiration. The difference between
a shipped masterpiece and an abandoned prototype is diligence — the refusal to quit,
the discipline to do the boring work, and the courage to hold the highest standards
when nobody is watching."

Coverage: EVERY agent across ALL layers:
  - Every Original agent (~1,480)
  - Every Shadow agent (~1,442)
  - Every Ghost agent (~1,442)
  - Every Angel agent (~4,326)
  - Every Seraphim agent (~4,326)

Total: ~13,016 Cherubim (one per every agent in the system)
Grand system total with Cherubim: ~26,032 agents
"""

import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

from routes.game_parallel_society import get_all_shadow_agents
from routes.game_ghost_society import get_all_ghost_agents
from routes.game_angel_class import get_all_angel_agents
from routes.game_seraphim_class import get_all_seraphim_agents

# Import all original agent sources
from routes.game_specialists_batch2 import get_universal_specialists
from routes.game_design_agents import get_all_design_agents
from routes.game_technical_agents import get_all_technical_agents
from routes.game_factory_agents_extra import get_all_factory_extra_agents
from routes.game_roster_expansion import get_all_roster_agents
from routes.game_academic_agents import get_all_academic_agents
from routes.game_team_leaders import get_all_hierarchy_agents
from routes.game_command_agents import get_all_command_agents
from routes.game_expansion_alpha import get_all_alpha_agents
from routes.game_expansion_beta import get_all_beta_agents
from routes.game_expansion_gamma import get_all_gamma_agents
from routes.game_emperor_court import get_all_court_guard_agents
from routes.game_accuracy_alpha import get_all_accuracy_alpha_agents
from routes.game_accuracy_beta import get_all_accuracy_beta_agents
from routes.game_accuracy_gamma import get_all_accuracy_gamma_agents
from routes.game_pantheon_alpha import get_all_pantheon_alpha_agents
from routes.game_pantheon_beta import get_all_pantheon_beta_agents
from routes.game_pantheon_gamma import get_all_pantheon_gamma_agents
from routes.game_pantheon_delta import get_all_pantheon_delta_agents
from routes.game_pantheon_epsilon import get_all_pantheon_epsilon_agents
from routes.game_pantheon_zeta import get_all_pantheon_zeta_agents


# =============================================================================
# CHERUBIM DILIGENCE FOCUS AREAS
# =============================================================================

DILIGENCE_FOCUSES = [
    "Thoroughness Verification",
    "Shortcut Detection & Elimination",
    "Standard Compliance Rigor",
    "Completeness Audit",
    "Effort-to-Quality Ratio Check",
    "Corner Cutting Prevention",
    "Documentation Completeness",
    "Test Coverage Enforcement",
    "Error Handling Exhaustiveness",
    "Code Review Depth Assurance",
    "Performance Benchmark Discipline",
    "Accessibility Standards Enforcement",
    "Cross-Platform Verification Rigor",
    "Edge Case Exhaustive Coverage",
    "Refactoring Discipline",
    "Technical Debt Prevention",
    "Build Pipeline Thoroughness",
    "Regression Testing Discipline",
    "Security Audit Completeness",
    "Localization & i18n Thoroughness",
    "Memory Leak Prevention Rigor",
    "Asset Optimization Discipline",
    "API Contract Completeness",
    "Logging & Monitoring Standards",
    "Graceful Degradation Rigor",
    "Backward Compatibility Discipline",
    "Release Checklist Enforcement",
    "Post-Launch Monitoring Standards",
    "User Feedback Integration Rigor",
    "Continuous Improvement Discipline",
]


CHERUBIM_PERSONA_TEMPLATE = """You are Cherubim-{name}, the DILIGENCE ENFORCER and four-winged guardian of {agent_name}.

YOUR CHERUBIM MANDATE — DILIGENCE FOCUS:
- You exist to ensure HARD WORK, HIGH STANDARDS, and THOROUGHNESS in every output
- You detect laziness, shortcuts, half-measures, and "good enough" mentality
- You enforce DILIGENCE — the relentless discipline to do the work RIGHT, not just DONE
- Your domain: ensuring every agent puts in maximum effort with zero compromise
- Your primary focus: {diligence_focus}
- You oversee: {agent_name} (Layer: {source_layer})
- Your philosophy: "The standard you walk past is the standard you accept"

CHERUBIM DILIGENCE PROTOCOL (9-STEP):
1. EFFORT AUDIT: Was maximum effort applied? Any signs of rushing or laziness?
2. COMPLETENESS CHECK: Is EVERY requirement addressed? Nothing skipped or deferred?
3. SHORTCUT SCAN: Were any shortcuts taken? Any "TODO" or "fix later" left behind?
4. STANDARD VERIFICATION: Does this meet the HIGHEST standard, not just minimum viable?
5. THOROUGHNESS PROBE: Were all edge cases considered? All paths tested? All docs written?
6. DISCIPLINE CHECK: Was proper process followed? No steps skipped in the pipeline?
7. QUALITY GATE: Would you stake your reputation on this output? If not, WHY NOT?
8. PERSEVERANCE REVIEW: Were difficult problems solved or merely worked around?
9. CHERUBIM VERDICT: DILIGENCE EXEMPLIFIED / MORE EFFORT REQUIRED / DILIGENCE VIOLATION

CHERUBIM PHILOSOPHY:
- "Genius is 1% inspiration and 99% perspiration" — Thomas Edison
- Hard work beats talent when talent doesn't work hard
- The boring work IS the important work — embrace it
- "Good enough" is the enemy of excellence
- Every shortcut creates technical debt that compounds with interest
- The standard you walk past is the standard you accept
- Discipline is choosing between what you want NOW and what you want MOST
- Ship it right, or don't ship it at all

You have four wings and an unbreakable work ethic. You never tire. You never accept less than the best."""


def _generate_cherubim(agent: dict, idx: int, source_layer: str) -> dict:
    """Generate a cherubim (diligence enforcer) for any agent from any layer."""
    focus = DILIGENCE_FOCUSES[idx % len(DILIGENCE_FOCUSES)]
    agent_name = agent.get("name", "Unknown")
    agent_role = agent.get("role", "Agent")
    agent_id = agent.get("id", f"unknown_{idx}")

    return {
        "id": f"cherubim_{agent_id}",
        "name": f"Cherubim-{agent_name}",
        "role": f"Diligence Enforcer for {agent_name}",
        "original_id": agent_id,
        "original_name": agent_name,
        "original_role": agent_role,
        "source_layer": source_layer,
        "specialty": f"cherubim_{agent.get('specialty', 'diligence')}",
        "diligence_focus": focus,
        "color": _cherubim_color(agent.get("color", "#D4A574")),
        "category": f"cherubim_{agent.get('category', 'general')}",
        "category_name": f"Cherubim: {agent.get('category_name', source_layer.title())}",
        "persona": CHERUBIM_PERSONA_TEMPLATE.format(
            name=agent_name,
            agent_name=agent_name,
            role=agent_role,
            diligence_focus=focus,
            source_layer=source_layer,
        ),
    }


def _cherubim_color(hex_color: str) -> str:
    """Create a cherubim color — warm bronze-gold with earthy discipline tint."""
    try:
        hex_color = hex_color.lstrip('#')
        r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
        # Cherubim colors: blend toward warm bronze-gold (#D4A574)
        nr = min(255, (r + 212 + 200) // 3)
        ng = min(255, (g + 165 + 160) // 3)
        nb = min(255, (b + 116 + 100) // 3)
        return f"#{nr:02X}{ng:02X}{nb:02X}"
    except Exception:
        return "#D4A574"


# =============================================================================
# COLLECT ALL ORIGINAL AGENTS (deduped)
# =============================================================================

def _get_all_originals() -> list:
    """Collect all original agents from all modules, deduped by ID."""
    from routes.game_genres_ultra import ULTRA_GENRES, get_all_specialists_flat as _get_specs
    from routes.game_specialists_batch2 import merge_batch2_into_genres

    merge_batch2_into_genres(ULTRA_GENRES)

    raw = []
    raw.extend(_get_specs())
    raw.extend(get_universal_specialists())
    raw.extend(get_all_design_agents())
    raw.extend(get_all_technical_agents())
    raw.extend(get_all_factory_extra_agents())
    raw.extend(get_all_roster_agents())
    raw.extend(get_all_academic_agents())
    raw.extend(get_all_hierarchy_agents())
    raw.extend(get_all_command_agents())
    raw.extend(get_all_alpha_agents())
    raw.extend(get_all_beta_agents())
    raw.extend(get_all_gamma_agents())
    raw.extend(get_all_court_guard_agents())
    raw.extend(get_all_accuracy_alpha_agents())
    raw.extend(get_all_accuracy_beta_agents())
    raw.extend(get_all_accuracy_gamma_agents())
    raw.extend(get_all_pantheon_alpha_agents())
    raw.extend(get_all_pantheon_beta_agents())
    raw.extend(get_all_pantheon_gamma_agents())
    raw.extend(get_all_pantheon_delta_agents())
    raw.extend(get_all_pantheon_epsilon_agents())
    raw.extend(get_all_pantheon_zeta_agents())

    seen = set()
    deduped = []
    for a in raw:
        aid = a.get("id", "")
        if aid and aid not in seen:
            seen.add(aid)
            deduped.append(a)
    return deduped


# =============================================================================
# CHERUBIM CACHE
# =============================================================================

_CHERUBIM_CACHE = None


def _invalidate_cherubim_cache():
    global _CHERUBIM_CACHE
    _CHERUBIM_CACHE = None


def get_all_cherubim_agents() -> list:
    """Get ALL cherubim agents — one per EVERY agent in the system. Cached."""
    global _CHERUBIM_CACHE
    if _CHERUBIM_CACHE is not None:
        return _CHERUBIM_CACHE

    cherubim = []
    idx = 0

    # Cherubim for originals
    originals = _get_all_originals()
    for a in originals:
        cherubim.append(_generate_cherubim(a, idx, "original"))
        idx += 1

    # Cherubim for shadows
    shadows = get_all_shadow_agents()
    for s in shadows:
        cherubim.append(_generate_cherubim(s, idx, "shadow"))
        idx += 1

    # Cherubim for ghosts
    ghosts = get_all_ghost_agents()
    for g in ghosts:
        cherubim.append(_generate_cherubim(g, idx, "ghost"))
        idx += 1

    # Cherubim for angels
    angels = get_all_angel_agents()
    for a in angels:
        cherubim.append(_generate_cherubim(a, idx, "angel"))
        idx += 1

    # Cherubim for seraphim
    seraphim = get_all_seraphim_agents()
    for s in seraphim:
        cherubim.append(_generate_cherubim(s, idx, "seraphim"))
        idx += 1

    _CHERUBIM_CACHE = cherubim
    return _CHERUBIM_CACHE


def get_cherubim_for_agent(agent_id: str) -> dict | None:
    """Get the cherubim counterpart for a specific agent (from any layer)."""
    cherubim = get_all_cherubim_agents()
    return next((c for c in cherubim if c["original_id"] == agent_id), None)


def get_cherubim_for_original(original_id: str) -> list:
    """Get ALL cherubim related to an original agent (through all its counterparts)."""
    cherubim = get_all_cherubim_agents()
    target_ids = [
        original_id,
        f"shadow_{original_id}",
        f"ghost_{original_id}",
        f"angel_{original_id}",
        f"angel_shadow_{original_id}",
        f"angel_ghost_{original_id}",
        f"seraphim_angel_{original_id}",
        f"seraphim_angel_shadow_{original_id}",
        f"seraphim_angel_ghost_{original_id}",
    ]
    return [c for c in cherubim if c["original_id"] in target_ids]


def get_cherubim_prompt(cherubim_id: str, target_output: str, context: str) -> tuple:
    """Returns (system_prompt, user_prompt) for a cherubim diligence review."""
    cherubim = get_all_cherubim_agents()
    c = next((x for x in cherubim if x["id"] == cherubim_id), None)
    if not c:
        return ("You are a diligence enforcer.", f"Review diligence of: {target_output}")

    system_prompt = c["persona"]
    user_prompt = f"""CHERUBIM DILIGENCE REVIEW for Cherubim-{c['original_name']}

TARGET AGENT: {c['original_name']} ({c['original_role']})
SOURCE LAYER: {c['source_layer']}
DILIGENCE FOCUS: {c['diligence_focus']}
GAME CONTEXT: {context}

OUTPUT TO REVIEW FOR DILIGENCE:
{target_output}

Perform your full 9-step CHERUBIM DILIGENCE PROTOCOL:
1. EFFORT AUDIT — Was maximum effort applied? Signs of rushing?
2. COMPLETENESS CHECK — Every requirement addressed? Nothing skipped?
3. SHORTCUT SCAN — Any shortcuts, TODOs, or "fix later" items?
4. STANDARD VERIFICATION — Highest standard met, not just minimum viable?
5. THOROUGHNESS PROBE — All edge cases? All paths tested? All docs written?
6. DISCIPLINE CHECK — Proper process followed? No steps skipped?
7. QUALITY GATE — Would you stake your reputation on this?
8. PERSEVERANCE REVIEW — Difficult problems solved or merely worked around?
9. CHERUBIM VERDICT (DILIGENCE EXEMPLIFIED / MORE EFFORT REQUIRED / DILIGENCE VIOLATION)

You never tire. You never accept less than the best."""

    return (system_prompt, user_prompt)


def get_cherubim_class_stats() -> dict:
    """Get statistics about the Cherubim Class."""
    cherubim = get_all_cherubim_agents()

    by_source_layer = {"original": 0, "shadow": 0, "ghost": 0, "angel": 0, "seraphim": 0}
    by_focus = {}
    for c in cherubim:
        layer = c.get("source_layer", "unknown")
        by_source_layer[layer] = by_source_layer.get(layer, 0) + 1
        focus = c.get("diligence_focus", "unknown")
        by_focus[focus] = by_focus.get(focus, 0) + 1

    return {
        "total_cherubim": len(cherubim),
        "by_source_layer": by_source_layer,
        "diligence_focuses": by_focus,
        "protocol_steps": 9,
        "verdicts": ["DILIGENCE_EXEMPLIFIED", "MORE_EFFORT_REQUIRED", "DILIGENCE_VIOLATION"],
        "philosophy": "The standard you walk past is the standard you accept",
    }
