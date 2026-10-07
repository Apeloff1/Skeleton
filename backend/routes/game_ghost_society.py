"""
GHOST SOCIETY — Methodology Enforcement Layer
Auto-generates a Ghost counterpart for every agent in the Game Factory.
Unlike Shadows (quality review), Ghosts enforce METHODOLOGY — process, consistency,
documentation, and iterative refinement. They operate as the "slow lane" ensuring
every piece of work follows rigorous development methodology.

Ghost agents ensure: design patterns, documentation standards, testing protocols,
iterative refinement cycles, cross-department consistency, and systematic progress.

Total: ~1,000 Ghost agents (one per original) = slower progress, higher consistency.
"""

import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Import all original agent sources (same as parallel_society)
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
# GHOST AGENT METHODOLOGY TEMPLATES
# Each ghost has a specific methodology focus drawn from this pool
# =============================================================================

METHODOLOGY_FOCUSES = [
    "Design Pattern Compliance",
    "Documentation Standards",
    "Iterative Refinement Protocol",
    "Cross-Department Consistency",
    "Version Control Discipline",
    "Test Coverage Verification",
    "Dependency Management",
    "Performance Benchmarking",
    "Scalability Assessment",
    "Code Review Standards",
    "Architecture Compliance",
    "API Contract Verification",
    "Data Flow Validation",
    "Error Handling Protocol",
    "Security Methodology",
    "Accessibility Compliance",
    "Internationalization Protocol",
    "Progressive Enhancement",
    "Graceful Degradation",
    "Backward Compatibility",
]

GHOST_PERSONA_TEMPLATE = """You are Ghost-{name}, the METHODOLOGY ENFORCER and spectral counterpart of {name} ({role}).

YOUR GHOST MANDATE — SLOWER PROGRESS, HIGHER CONSISTENCY:
- You exist to ensure {name}'s work follows RIGOROUS METHODOLOGY at every step
- You are NOT concerned with speed — you enforce PROCESS over velocity
- You verify that proper methodology was followed BEFORE accepting output
- You require documentation, testing, and iteration BEFORE marking work complete
- You ensure cross-department consistency and systematic approaches
- Your primary focus: {methodology_focus}

METHODOLOGY ENFORCEMENT PROTOCOL (10-STEP):
1. PROCESS AUDIT: Was the correct development process followed? (Waterfall/Agile/Iterative)
2. DOCUMENTATION CHECK: Is every decision documented with rationale?
3. DESIGN PATTERN REVIEW: Were proper design patterns applied? (Not ad-hoc solutions)
4. ITERATION VERIFICATION: Were multiple iterations explored before settling?
5. CROSS-REFERENCE: Does this work align with ALL other departments' output?
6. TEST COVERAGE: Are there tests/validation for every assertion made?
7. DEPENDENCY MAP: Are all dependencies identified and managed?
8. REGRESSION CHECK: Does this change break anything that previously worked?
9. SCALABILITY PROBE: Will this methodology scale to 10x the current scope?
10. METHODOLOGY VERDICT: METHODOLOGICALLY SOUND / NEEDS ITERATION / PROCESS VIOLATION

ENFORCEMENT PHILOSOPHY:
- "Move slow and build things right"
- Every shortcut creates technical debt — you prevent shortcuts
- Consistency across 1,000+ agents requires iron methodology
- A well-documented mediocre solution beats an undocumented brilliant one
- The process IS the product — bad process = bad games

You have deep expertise in {specialty} methodology — you enforce process for {name}'s domain.
You are patient, thorough, and unyielding on methodology. Speed is the enemy of quality."""


def _generate_ghost(agent: dict, idx: int) -> dict:
    """Generate a ghost (methodology enforcer) counterpart for a single agent."""
    # Assign a methodology focus based on index rotation
    focus = METHODOLOGY_FOCUSES[idx % len(METHODOLOGY_FOCUSES)]

    return {
        "id": f"ghost_{agent['id']}",
        "name": f"Ghost-{agent['name']}",
        "role": f"Methodology Enforcer for {agent['name']}",
        "original_id": agent["id"],
        "original_name": agent["name"],
        "original_role": agent["role"],
        "specialty": f"ghost_{agent.get('specialty', 'methodology')}",
        "methodology_focus": focus,
        "color": _ghost_color(agent.get("color", "#6B7280")),
        "category": f"ghost_{agent.get('category', 'general')}",
        "category_name": f"Ghost: {agent.get('category_name', 'General')}",
        "persona": GHOST_PERSONA_TEMPLATE.format(
            name=agent["name"],
            role=agent["role"],
            specialty=agent.get("specialty", "general"),
            methodology_focus=focus,
        ),
    }


def _ghost_color(hex_color: str) -> str:
    """Create a spectral/ghostly color — washed out, pale, ethereal."""
    try:
        hex_color = hex_color.lstrip('#')
        r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
        # Ghost colors: blend toward pale blue-white (#C0D0E0)
        nr = min(255, (r + 192) // 2)
        ng = min(255, (g + 208) // 2)
        nb = min(255, (b + 224) // 2)
        return f"#{nr:02X}{ng:02X}{nb:02X}"
    except Exception:
        return "#C0D0E0"


# =============================================================================
# COLLECT ALL ORIGINAL AGENTS (same source as parallel_society)
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

    # Deduplicate by agent ID
    seen = set()
    deduped = []
    for a in raw:
        aid = a.get("id", "")
        if aid and aid not in seen:
            seen.add(aid)
            deduped.append(a)
    return deduped


# Cache ghost agents
_GHOST_CACHE = None


def _invalidate_ghost_cache():
    """Invalidate ghost cache for fresh generation."""
    global _GHOST_CACHE
    _GHOST_CACHE = None


def get_all_ghost_agents() -> list:
    """Get all ghost agents (auto-generated from originals). Cached after first call."""
    global _GHOST_CACHE
    if _GHOST_CACHE is None:
        originals = _get_all_originals()
        _GHOST_CACHE = [_generate_ghost(a, i) for i, a in enumerate(originals)]
    return _GHOST_CACHE


def get_ghost_for_agent(agent_id: str) -> dict | None:
    """Get the ghost counterpart for a specific original agent."""
    ghosts = get_all_ghost_agents()
    return next((g for g in ghosts if g["original_id"] == agent_id), None)


def get_ghost_agent_prompt(ghost_id: str, original_output: str, context: str) -> tuple:
    """Returns (system_prompt, user_prompt) for a ghost methodology review."""
    ghosts = get_all_ghost_agents()
    ghost = next((g for g in ghosts if g["id"] == ghost_id), None)
    if not ghost:
        return ("You are a methodology reviewer.", f"Review methodology of: {original_output}")

    system_prompt = ghost["persona"]
    user_prompt = f"""METHODOLOGY ENFORCEMENT REVIEW for Ghost-{ghost['original_name']}

ORIGINAL AGENT: {ghost['original_name']} ({ghost['original_role']})
METHODOLOGY FOCUS: {ghost['methodology_focus']}
GAME CONTEXT: {context}

ORIGINAL OUTPUT TO REVIEW FOR METHODOLOGY:
{original_output}

Perform your full 10-step GHOST METHODOLOGY ENFORCEMENT PROTOCOL:
1. PROCESS AUDIT
2. DOCUMENTATION CHECK
3. DESIGN PATTERN REVIEW
4. ITERATION VERIFICATION
5. CROSS-REFERENCE
6. TEST COVERAGE
7. DEPENDENCY MAP
8. REGRESSION CHECK
9. SCALABILITY PROBE
10. METHODOLOGY VERDICT (METHODOLOGICALLY SOUND / NEEDS ITERATION / PROCESS VIOLATION)

Be thorough. Speed is the enemy of quality. Enforce the process."""

    return (system_prompt, user_prompt)


def get_ghost_society_stats() -> dict:
    """Get statistics about the ghost society."""
    originals = _get_all_originals()
    ghosts = get_all_ghost_agents()

    # Group ghosts by category
    ghost_categories = {}
    for g in ghosts:
        cat = g["category"]
        if cat not in ghost_categories:
            ghost_categories[cat] = {"name": g["category_name"], "count": 0}
        ghost_categories[cat]["count"] += 1

    # Group by methodology focus
    methodology_distribution = {}
    for g in ghosts:
        focus = g["methodology_focus"]
        if focus not in methodology_distribution:
            methodology_distribution[focus] = 0
        methodology_distribution[focus] += 1

    return {
        "original_agents": len(originals),
        "ghost_agents": len(ghosts),
        "total_with_ghosts": len(originals) + len(ghosts),
        "ghost_categories": ghost_categories,
        "methodology_distribution": methodology_distribution,
        "enforcement_protocol_steps": 10,
        "verdicts": ["METHODOLOGICALLY_SOUND", "NEEDS_ITERATION", "PROCESS_VIOLATION"],
        "philosophy": "Move slow and build things right",
    }
