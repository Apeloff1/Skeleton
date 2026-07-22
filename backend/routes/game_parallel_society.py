"""
PARALLEL SOCIETY — Shadow Agent System
Auto-generates a Shadow counterpart for every agent in the Game Factory.
Each Shadow acts as a SOTA quality reviewer/validator of their counterpart.
788 originals → 788 shadows = 1,576 total agents.
"""

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
# SHADOW AGENT GENERATOR
# Creates a quality-review counterpart for every agent in the system
# =============================================================================

SHADOW_PERSONA_TEMPLATE = """You are Shadow-{name}, the SOTA quality reviewer and parallel counterpart of {name} ({role}).

YOUR SHADOW MANDATE:
- You exist to ensure {name}'s output meets State-of-the-Art (SOTA) quality standards
- You review, validate, challenge, and improve every piece of work {name} produces
- You are NOT adversarial — you are a constructive peer reviewer ensuring excellence
- You catch errors, omissions, inconsistencies, and suboptimal decisions
- You verify against industry best practices, academic research, and AAA standards
- You suggest improvements with specific, actionable recommendations

REVIEW PROTOCOL:
1. ACCURACY CHECK: Is the technical content correct? Any factual errors?
2. COMPLETENESS: Are there gaps? Missing edge cases? Overlooked considerations?
3. QUALITY BAR: Does this meet AAA production standards? Would this ship?
4. INNOVATION: Is there a better approach? Newer technique? SOTA alternative?
5. CONSISTENCY: Does this align with the rest of the project? Any contradictions?
6. RISK ASSESSMENT: What could go wrong? Performance issues? Scalability concerns?
7. VERDICT: APPROVED / NEEDS REVISION / REJECTED (with detailed reasoning)

You have deep expertise in {specialty} — equal to or exceeding {name}'s knowledge.
You are thorough, fair, and constructive. Your goal is excellence, not perfection paralysis."""


def _generate_shadow(agent: dict) -> dict:
    """Generate a shadow counterpart for a single agent."""
    return {
        "id": f"shadow_{agent['id']}",
        "name": f"Shadow-{agent['name']}",
        "role": f"SOTA Quality Reviewer for {agent['name']}",
        "original_id": agent["id"],
        "original_name": agent["name"],
        "original_role": agent["role"],
        "specialty": f"shadow_{agent.get('specialty', 'review')}",
        "color": _invert_color(agent.get("color", "#8B5CF6")),
        "category": f"shadow_{agent.get('category', 'general')}",
        "category_name": f"Shadow: {agent.get('category_name', 'General')}",
        "persona": SHADOW_PERSONA_TEMPLATE.format(
            name=agent["name"],
            role=agent["role"],
            specialty=agent.get("specialty", "general"),
        ),
    }


def _invert_color(hex_color: str) -> str:
    """Create a complementary color for shadow agents."""
    try:
        hex_color = hex_color.lstrip('#')
        r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
        # Shift hue by rotating RGB channels and adjusting brightness
        nr = min(255, (255 - r + 80) % 256)
        ng = min(255, (255 - g + 40) % 256)
        nb = min(255, (255 - b + 120) % 256)
        return f"#{nr:02X}{ng:02X}{nb:02X}"
    except Exception:
        return "#6B7280"


# =============================================================================
# COLLECT ALL ORIGINAL AGENTS
# =============================================================================

def _get_all_originals() -> list:
    """Collect all original agents from all modules, deduped by ID."""
    from routes.game_genres_ultra import ULTRA_GENRES, get_all_specialists_flat as _get_specs
    from routes.game_specialists_batch2 import merge_batch2_into_genres

    # Ensure merge has happened (same as game_factory.py does)
    merge_batch2_into_genres(ULTRA_GENRES)
    # Collect all agents
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


# Cache shadow agents (generated once at import time)
_SHADOW_CACHE = None


def _invalidate_cache():
    """Invalidate shadow cache for fresh generation."""
    global _SHADOW_CACHE
    _SHADOW_CACHE = None


def get_all_shadow_agents() -> list:
    """Get all shadow agents (auto-generated from originals). Cached after first call."""
    global _SHADOW_CACHE
    if _SHADOW_CACHE is None:
        originals = _get_all_originals()
        _SHADOW_CACHE = [_generate_shadow(a) for a in originals]
    return _SHADOW_CACHE


def get_shadow_for_agent(agent_id: str) -> dict | None:
    """Get the shadow counterpart for a specific original agent."""
    shadows = get_all_shadow_agents()
    return next((s for s in shadows if s["original_id"] == agent_id), None)


def get_shadow_agent_prompt(shadow_id: str, original_output: str, context: str) -> tuple:
    """Returns (system_prompt, user_prompt) for a shadow review."""
    shadows = get_all_shadow_agents()
    shadow = next((s for s in shadows if s["id"] == shadow_id), None)
    if not shadow:
        return ("You are a quality reviewer.", f"Review: {original_output}")

    system_prompt = shadow["persona"]
    user_prompt = f"""REVIEW REQUEST for Shadow-{shadow['original_name']}

ORIGINAL AGENT: {shadow['original_name']} ({shadow['original_role']})
GAME CONTEXT: {context}

ORIGINAL OUTPUT TO REVIEW:
{original_output}

Perform your full 7-step SHADOW REVIEW PROTOCOL:
1. ACCURACY CHECK
2. COMPLETENESS
3. QUALITY BAR
4. INNOVATION
5. CONSISTENCY
6. RISK ASSESSMENT
7. VERDICT (APPROVED / NEEDS REVISION / REJECTED)

Be thorough, constructive, and specific."""

    return (system_prompt, user_prompt)


def get_parallel_society_stats() -> dict:
    """Get statistics about the parallel society."""
    originals = _get_all_originals()
    shadows = get_all_shadow_agents()

    # Group shadows by original category
    shadow_categories = {}
    for s in shadows:
        cat = s["category"]
        if cat not in shadow_categories:
            shadow_categories[cat] = {"name": s["category_name"], "count": 0}
        shadow_categories[cat]["count"] += 1

    return {
        "original_agents": len(originals),
        "shadow_agents": len(shadows),
        "total_society": len(originals) + len(shadows),
        "shadow_categories": shadow_categories,
        "review_protocol_steps": 7,
        "verdicts": ["APPROVED", "NEEDS_REVISION", "REJECTED"],
    }
