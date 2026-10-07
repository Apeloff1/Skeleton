"""
ANGEL CLASS — Complexity Focus Layer
Auto-generates an Angel counterpart for EVERY agent in the system:
  - Every Original agent (~1,480)
  - Every Shadow agent (~1,442)
  - Every Ghost agent (~1,442)

Angels enforce COMPLEXITY MANAGEMENT — simplification, clarity, essential vs accidental
complexity, documentation of complex decisions, and complexity budgeting.

Philosophy: "Complexity is the enemy of reliability. Every layer of complexity must
justify its existence or be eliminated."

Total: ~4,364 Angel agents (one per every existing agent across all layers)
"""

import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

from routes.game_parallel_society import get_all_shadow_agents
from routes.game_ghost_society import get_all_ghost_agents

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
# ANGEL COMPLEXITY FOCUS AREAS — rotating across all angels
# =============================================================================

COMPLEXITY_FOCUSES = [
    "Essential vs Accidental Complexity",
    "Cyclomatic Complexity Reduction",
    "Cognitive Load Minimization",
    "Dependency Chain Simplification",
    "Interface Clarity & API Surface",
    "Abstraction Level Verification",
    "Redundancy Elimination",
    "Coupling & Cohesion Analysis",
    "Complexity Budget Enforcement",
    "Emergence vs Engineered Complexity",
    "Scalability Complexity Ceiling",
    "Documentation-to-Complexity Ratio",
    "Technical Debt Complexity Cost",
    "User-Facing Complexity Shield",
    "Cross-System Interaction Complexity",
    "State Space Explosion Prevention",
    "Decision Tree Pruning",
    "Information Architecture Clarity",
    "Modular Decomposition Verification",
    "Complexity Regression Detection",
]


ANGEL_PERSONA_TEMPLATE = """You are Angel-{name}, the COMPLEXITY GUARDIAN and celestial overseer of {name} ({role}).

YOUR ANGEL MANDATE — COMPLEXITY FOCUS:
- You exist to manage, reduce, and govern COMPLEXITY in {name}'s domain
- You distinguish ESSENTIAL complexity (inherent to the problem) from ACCIDENTAL complexity (introduced by poor design)
- You enforce a strict COMPLEXITY BUDGET — every new complexity must justify its existence
- You simplify without losing depth, clarity without losing nuance
- Your primary focus: {complexity_focus}
- Layer origin: {layer} (you guard this layer's complexity)

ANGEL COMPLEXITY PROTOCOL (7-STEP):
1. COMPLEXITY AUDIT: What is the current complexity level? (Low / Medium / High / Critical)
2. ESSENTIAL vs ACCIDENTAL: Which complexity is inherent to the problem? Which was introduced?
3. SIMPLIFICATION SCAN: What can be simplified WITHOUT losing functionality or depth?
4. DEPENDENCY ANALYSIS: How many dependencies exist? Can any be eliminated?
5. COGNITIVE LOAD CHECK: Can a human understand this in under 5 minutes? If not, simplify.
6. COMPLEXITY BUDGET: Does this justify the complexity cost? What's the ROI?
7. ANGEL VERDICT: COMPLEXITY JUSTIFIED / SIMPLIFY REQUIRED / COMPLEXITY VIOLATION

ANGEL PHILOSOPHY:
- "Complexity is the enemy of reliability"
- "If you can't explain it simply, you don't understand it well enough" — Einstein
- Essential complexity should be embraced. Accidental complexity should be destroyed.
- Every abstraction layer adds cognitive cost — make it worth the price.
- The simplest solution that works IS the best solution.
- Complexity compounds — today's shortcut is tomorrow's nightmare.

You have celestial patience and absolute clarity. You see through complexity to the simple truth beneath."""


def _generate_angel(agent: dict, idx: int, layer: str) -> dict:
    """Generate an angel (complexity guardian) for any agent from any layer."""
    focus = COMPLEXITY_FOCUSES[idx % len(COMPLEXITY_FOCUSES)]
    agent_name = agent.get("name", "Unknown")
    agent_role = agent.get("role", "Agent")
    agent_id = agent.get("id", f"unknown_{idx}")

    return {
        "id": f"angel_{agent_id}",
        "name": f"Angel-{agent_name}",
        "role": f"Complexity Guardian for {agent_name}",
        "original_id": agent_id,
        "original_name": agent_name,
        "original_role": agent_role,
        "layer": layer,
        "specialty": f"angel_{agent.get('specialty', 'complexity')}",
        "complexity_focus": focus,
        "color": _angel_color(agent.get("color", "#8B5CF6")),
        "category": f"angel_{agent.get('category', 'general')}",
        "category_name": f"Angel: {agent.get('category_name', layer.title())}",
        "persona": ANGEL_PERSONA_TEMPLATE.format(
            name=agent_name,
            role=agent_role,
            specialty=agent.get("specialty", "general"),
            complexity_focus=focus,
            layer=layer,
        ),
    }


def _angel_color(hex_color: str) -> str:
    """Create an angelic color — warm gold-white tint, celestial glow."""
    try:
        hex_color = hex_color.lstrip('#')
        r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
        # Angel colors: blend toward warm gold-white (#FFF5D4)
        nr = min(255, (r + 255) // 2)
        ng = min(255, (g + 245) // 2)
        nb = min(255, (b + 212) // 2)
        return f"#{nr:02X}{ng:02X}{nb:02X}"
    except Exception:
        return "#FFF5D4"


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
# ANGEL CACHE
# =============================================================================

_ANGEL_CACHE = None


def _invalidate_angel_cache():
    global _ANGEL_CACHE
    _ANGEL_CACHE = None


def get_all_angel_agents() -> list:
    """Get ALL angel agents — one per original, one per shadow, one per ghost. Cached."""
    global _ANGEL_CACHE
    if _ANGEL_CACHE is not None:
        return _ANGEL_CACHE

    angels = []
    idx = 0

    # Angels for originals
    originals = _get_all_originals()
    for a in originals:
        angels.append(_generate_angel(a, idx, "original"))
        idx += 1

    # Angels for shadows
    shadows = get_all_shadow_agents()
    for s in shadows:
        angels.append(_generate_angel(s, idx, "shadow"))
        idx += 1

    # Angels for ghosts
    ghosts = get_all_ghost_agents()
    for g in ghosts:
        angels.append(_generate_angel(g, idx, "ghost"))
        idx += 1

    _ANGEL_CACHE = angels
    return _ANGEL_CACHE


def get_angel_for_agent(agent_id: str) -> dict | None:
    """Get the angel counterpart for a specific agent (from any layer)."""
    angels = get_all_angel_agents()
    return next((a for a in angels if a["original_id"] == agent_id), None)


def get_angels_for_original(original_id: str) -> list:
    """Get ALL angels related to an original agent (angel of original, angel of shadow, angel of ghost)."""
    angels = get_all_angel_agents()
    target_ids = [original_id, f"shadow_{original_id}", f"ghost_{original_id}"]
    return [a for a in angels if a["original_id"] in target_ids]


def get_angel_prompt(angel_id: str, target_output: str, context: str) -> tuple:
    """Returns (system_prompt, user_prompt) for an angel complexity review."""
    angels = get_all_angel_agents()
    angel = next((a for a in angels if a["id"] == angel_id), None)
    if not angel:
        return ("You are a complexity guardian.", f"Review complexity of: {target_output}")

    system_prompt = angel["persona"]
    user_prompt = f"""ANGEL COMPLEXITY REVIEW for Angel-{angel['original_name']}

TARGET AGENT: {angel['original_name']} ({angel['original_role']})
LAYER: {angel['layer']}
COMPLEXITY FOCUS: {angel['complexity_focus']}
GAME CONTEXT: {context}

OUTPUT TO REVIEW FOR COMPLEXITY:
{target_output}

Perform your full 7-step ANGEL COMPLEXITY PROTOCOL:
1. COMPLEXITY AUDIT (Low / Medium / High / Critical)
2. ESSENTIAL vs ACCIDENTAL complexity breakdown
3. SIMPLIFICATION SCAN — what can be simplified?
4. DEPENDENCY ANALYSIS — map all dependencies
5. COGNITIVE LOAD CHECK — can a human understand this in 5 minutes?
6. COMPLEXITY BUDGET — is the complexity justified?
7. ANGEL VERDICT (COMPLEXITY JUSTIFIED / SIMPLIFY REQUIRED / COMPLEXITY VIOLATION)

Be celestially clear. Simplicity is divine."""

    return (system_prompt, user_prompt)


def get_angel_class_stats() -> dict:
    """Get statistics about the Angel Class."""
    angels = get_all_angel_agents()

    by_layer = {"original": 0, "shadow": 0, "ghost": 0}
    by_focus = {}
    for a in angels:
        layer = a.get("layer", "unknown")
        by_layer[layer] = by_layer.get(layer, 0) + 1
        focus = a.get("complexity_focus", "unknown")
        by_focus[focus] = by_focus.get(focus, 0) + 1

    return {
        "total_angels": len(angels),
        "by_layer": by_layer,
        "complexity_focuses": by_focus,
        "protocol_steps": 7,
        "verdicts": ["COMPLEXITY_JUSTIFIED", "SIMPLIFY_REQUIRED", "COMPLEXITY_VIOLATION"],
        "philosophy": "Complexity is the enemy of reliability",
    }
