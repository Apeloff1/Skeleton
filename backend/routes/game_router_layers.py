"""
GAME ROUTER — LAYERS
Sub-router for all multi-layer endpoints:
  Shadow (Parallel Society), Ghost Society, Angel Class, and Hexa-Layer views.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from routes.game_shared import call_llm
from routes.chat_vault import log_chat_message, log_shadow_review
from routes.game_parallel_society import get_all_shadow_agents, get_shadow_for_agent, get_shadow_agent_prompt, get_parallel_society_stats
from routes.game_ghost_society import get_all_ghost_agents, get_ghost_for_agent, get_ghost_agent_prompt, get_ghost_society_stats
from routes.game_angel_class import get_all_angel_agents, get_angel_for_agent, get_angels_for_original, get_angel_prompt, get_angel_class_stats
from routes.game_seraphim_class import get_seraphim_for_original
from routes.game_cherubim_class import get_cherubim_for_original

router = APIRouter()


# =============================================================================
# PARALLEL SOCIETY — Shadow Agents (SOTA quality review)
# =============================================================================

@router.get("/parallel-society")
async def get_parallel_society():
    """Get the Parallel Society stats — shadow counterpart for every agent."""
    stats = get_parallel_society_stats()
    return {
        "system": "Parallel Society",
        "purpose": "SOTA quality assurance through shadow agent peer review",
        "original_agents": stats["original_agents"],
        "shadow_agents": stats["shadow_agents"],
        "total_society": stats["total_society"],
        "shadow_categories": stats["shadow_categories"],
        "review_protocol": [
            "1. ACCURACY CHECK — Is the technical content correct?",
            "2. COMPLETENESS — Any gaps or missing edge cases?",
            "3. QUALITY BAR — Does it meet AAA standards?",
            "4. INNOVATION — Better approach or SOTA alternative?",
            "5. CONSISTENCY — Aligns with rest of project?",
            "6. RISK ASSESSMENT — What could go wrong?",
            "7. VERDICT — APPROVED / NEEDS REVISION / REJECTED",
        ],
        "verdicts": ["APPROVED", "NEEDS_REVISION", "REJECTED"],
    }


@router.get("/shadow-agents")
async def list_shadow_agents(limit: int = 50, skip: int = 0):
    """List shadow agents with pagination."""
    all_shadows = get_all_shadow_agents()
    page = all_shadows[skip:skip + limit]
    return {
        "shadows": [{
            "id": s["id"], "name": s["name"], "role": s["role"],
            "original_id": s["original_id"], "original_name": s["original_name"],
            "color": s["color"], "category": s["category"],
        } for s in page],
        "total": len(all_shadows), "showing": len(page), "skip": skip, "limit": limit,
    }


@router.get("/shadow-for/{agent_id}")
async def get_shadow_for(agent_id: str):
    """Get the shadow counterpart for a specific original agent."""
    shadow = get_shadow_for_agent(agent_id)
    if not shadow:
        raise HTTPException(status_code=404, detail=f"No shadow found for agent '{agent_id}'")
    return {"shadow": {
        "id": shadow["id"], "name": shadow["name"], "role": shadow["role"],
        "original_id": shadow["original_id"], "original_name": shadow["original_name"], "color": shadow["color"],
    }}


class ShadowReviewRequest(BaseModel):
    original_agent_id: str
    original_output: str
    game_context: str = ""
    session_id: Optional[str] = None


@router.post("/shadow-review")
async def shadow_review(req: ShadowReviewRequest):
    """Send an original agent's output to its Shadow for SOTA quality review."""
    shadow = get_shadow_for_agent(req.original_agent_id)
    if not shadow:
        raise HTTPException(status_code=404, detail=f"No shadow agent for '{req.original_agent_id}'")

    sys_prompt, user_prompt = get_shadow_agent_prompt(shadow["id"], req.original_output, req.game_context)
    llm_result = await call_llm(sys_prompt, user_prompt, f"shadow_{shadow['id']}_{req.session_id or 'default'}")

    response_text = llm_result.get("response", "Shadow review in progress...")

    await log_shadow_review(
        original_agent_id=req.original_agent_id, shadow_agent_id=shadow["id"],
        original_output=req.original_output, shadow_review=response_text,
        verdict="PENDING", session_id=req.session_id or "default", game_context=req.game_context,
    )

    return {
        "shadow_agent": shadow["name"], "original_agent": shadow["original_name"],
        "review": response_text, "success": llm_result.get("success", False), "logged_to_vault": True,
    }


# =============================================================================
# GHOST SOCIETY — Methodology Enforcement Layer
# =============================================================================

@router.get("/ghost-society")
async def get_ghost_society():
    """Get the Ghost Society stats — methodology enforcement layer for every agent."""
    stats = get_ghost_society_stats()
    return {
        "system": "Ghost Society",
        "purpose": "Methodology enforcement through ghost agent process review — slower progress, higher consistency",
        "philosophy": stats["philosophy"],
        "original_agents": stats["original_agents"], "ghost_agents": stats["ghost_agents"],
        "total_with_ghosts": stats["total_with_ghosts"],
        "ghost_categories": stats["ghost_categories"],
        "methodology_distribution": stats["methodology_distribution"],
        "enforcement_protocol": [
            "1. PROCESS AUDIT — Was the correct development process followed?",
            "2. DOCUMENTATION CHECK — Is every decision documented with rationale?",
            "3. DESIGN PATTERN REVIEW — Were proper design patterns applied?",
            "4. ITERATION VERIFICATION — Were multiple iterations explored?",
            "5. CROSS-REFERENCE — Does this align with ALL other departments?",
            "6. TEST COVERAGE — Are there tests/validation for every assertion?",
            "7. DEPENDENCY MAP — Are all dependencies identified and managed?",
            "8. REGRESSION CHECK — Does this break anything previously working?",
            "9. SCALABILITY PROBE — Will this scale to 10x current scope?",
            "10. METHODOLOGY VERDICT — SOUND / NEEDS ITERATION / VIOLATION",
        ],
        "verdicts": stats["verdicts"],
    }


@router.get("/ghost-agents")
async def list_ghost_agents(limit: int = 50, skip: int = 0):
    """List ghost agents with pagination."""
    all_ghosts = get_all_ghost_agents()
    page = all_ghosts[skip:skip + limit]
    return {
        "ghosts": [{
            "id": g["id"], "name": g["name"], "role": g["role"],
            "original_id": g["original_id"], "original_name": g["original_name"],
            "methodology_focus": g["methodology_focus"], "color": g["color"], "category": g["category"],
        } for g in page],
        "total": len(all_ghosts), "showing": len(page), "skip": skip, "limit": limit,
    }


@router.get("/ghost-for/{agent_id}")
async def get_ghost_for(agent_id: str):
    """Get the ghost (methodology enforcer) counterpart for a specific original agent."""
    ghost = get_ghost_for_agent(agent_id)
    if not ghost:
        raise HTTPException(status_code=404, detail=f"No ghost found for agent '{agent_id}'")
    return {"ghost": {
        "id": ghost["id"], "name": ghost["name"], "role": ghost["role"],
        "original_id": ghost["original_id"], "original_name": ghost["original_name"],
        "methodology_focus": ghost["methodology_focus"], "color": ghost["color"],
    }}


class GhostReviewRequest(BaseModel):
    original_agent_id: str
    original_output: str
    game_context: str = ""
    session_id: Optional[str] = None


@router.post("/ghost-review")
async def ghost_methodology_review(req: GhostReviewRequest):
    """Send an original agent's output to its Ghost for methodology enforcement review."""
    ghost = get_ghost_for_agent(req.original_agent_id)
    if not ghost:
        raise HTTPException(status_code=404, detail=f"No ghost agent for '{req.original_agent_id}'")

    sys_prompt, user_prompt = get_ghost_agent_prompt(ghost["id"], req.original_output, req.game_context)
    llm_result = await call_llm(sys_prompt, user_prompt, f"ghost_{ghost['id']}_{req.session_id or 'default'}")

    response_text = llm_result.get("response", "Ghost methodology review in progress...")

    await log_chat_message(
        room_id="ghost_methodology",
        agent_id=ghost["id"], agent_name=ghost["name"], agent_role=ghost["role"],
        category="ghost_society", user_message=f"[METHODOLOGY REVIEW] Agent: {req.original_agent_id} | Context: {req.game_context}",
        agent_response=response_text, session_id=req.session_id or "default",
        game_context=req.game_context, success=llm_result.get("success", False),
    )

    return {
        "ghost_agent": ghost["name"], "original_agent": ghost["original_name"],
        "methodology_focus": ghost["methodology_focus"],
        "review": response_text, "success": llm_result.get("success", False), "logged_to_vault": True,
    }


@router.get("/triple-layer/{agent_id}")
async def get_agent_triple_layer(agent_id: str):
    """Get the full triple-layer view for any agent: Original + Shadow + Ghost."""
    shadow = get_shadow_for_agent(agent_id)
    ghost = get_ghost_for_agent(agent_id)
    if not shadow and not ghost:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found in any layer")
    return {
        "agent_id": agent_id,
        "layers": {
            "original": {"exists": True, "id": agent_id},
            "shadow": {"exists": shadow is not None, "id": shadow["id"] if shadow else None, "name": shadow["name"] if shadow else None, "purpose": "SOTA Quality Review (fast lane)"},
            "ghost": {"exists": ghost is not None, "id": ghost["id"] if ghost else None, "name": ghost["name"] if ghost else None, "methodology_focus": ghost["methodology_focus"] if ghost else None, "purpose": "Methodology Enforcement (slow lane)"},
        },
        "total_counterparts": (1 if shadow else 0) + (1 if ghost else 0),
    }


# =============================================================================
# ANGEL CLASS — Complexity Guardians
# =============================================================================

@router.get("/angel-class")
async def get_angel_class():
    """Get the Angel Class stats — complexity guardian layer across ALL agents."""
    stats = get_angel_class_stats()
    return {
        "system": "Angel Class",
        "purpose": "Complexity guardians — every agent, shadow, and ghost gets an Angel enforcing simplicity and clarity",
        "philosophy": stats["philosophy"], "total_angels": stats["total_angels"],
        "by_layer": stats["by_layer"], "complexity_focuses": stats["complexity_focuses"],
        "protocol": [
            "1. COMPLEXITY AUDIT — What is the current complexity level?",
            "2. ESSENTIAL vs ACCIDENTAL — Which complexity is inherent vs introduced?",
            "3. SIMPLIFICATION SCAN — What can be simplified without losing functionality?",
            "4. DEPENDENCY ANALYSIS — How many dependencies? Can any be eliminated?",
            "5. COGNITIVE LOAD CHECK — Can a human understand this in 5 minutes?",
            "6. COMPLEXITY BUDGET — Does this justify the complexity cost?",
            "7. ANGEL VERDICT — JUSTIFIED / SIMPLIFY REQUIRED / VIOLATION",
        ],
        "verdicts": stats["verdicts"],
    }


@router.get("/angel-agents")
async def list_angel_agents(limit: int = 50, skip: int = 0, layer: Optional[str] = None):
    """List angel agents with pagination. Optionally filter by layer."""
    all_angels = get_all_angel_agents()
    if layer:
        all_angels = [a for a in all_angels if a.get("layer") == layer]
    page = all_angels[skip:skip + limit]
    return {
        "angels": [{
            "id": a["id"], "name": a["name"], "role": a["role"],
            "original_id": a["original_id"], "original_name": a["original_name"],
            "layer": a["layer"], "complexity_focus": a["complexity_focus"], "color": a["color"],
        } for a in page],
        "total": len(all_angels), "showing": len(page), "skip": skip, "limit": limit, "layer_filter": layer,
    }


@router.get("/angel-for/{agent_id}")
async def get_angel_for(agent_id: str):
    """Get the Angel (complexity guardian) for a specific agent from any layer."""
    angel = get_angel_for_agent(agent_id)
    if not angel:
        raise HTTPException(status_code=404, detail=f"No angel found for agent '{agent_id}'")
    return {"angel": {
        "id": angel["id"], "name": angel["name"], "role": angel["role"],
        "original_id": angel["original_id"], "original_name": angel["original_name"],
        "layer": angel["layer"], "complexity_focus": angel["complexity_focus"], "color": angel["color"],
    }}


class AngelReviewRequest(BaseModel):
    agent_id: str
    agent_output: str
    game_context: str = ""
    session_id: Optional[str] = None


@router.post("/angel-review")
async def angel_complexity_review(req: AngelReviewRequest):
    """Send any agent's output to its Angel for complexity enforcement review."""
    angel = get_angel_for_agent(req.agent_id)
    if not angel:
        raise HTTPException(status_code=404, detail=f"No angel for '{req.agent_id}'")

    sys_prompt, user_prompt = get_angel_prompt(angel["id"], req.agent_output, req.game_context)
    llm_result = await call_llm(sys_prompt, user_prompt, f"angel_{angel['id']}_{req.session_id or 'default'}")

    response_text = llm_result.get("response", "Angel is reviewing complexity...")

    await log_chat_message(
        room_id="angel_complexity",
        agent_id=angel["id"], agent_name=angel["name"], agent_role=angel["role"],
        category="angel_class", user_message=f"[COMPLEXITY REVIEW] Agent: {req.agent_id} | Context: {req.game_context}",
        agent_response=response_text, session_id=req.session_id or "default",
        game_context=req.game_context, success=llm_result.get("success", False),
    )

    return {
        "angel_agent": angel["name"], "target_agent": angel["original_name"],
        "layer": angel["layer"], "complexity_focus": angel["complexity_focus"],
        "review": response_text, "success": llm_result.get("success", False), "logged_to_vault": True,
    }


# =============================================================================
# MULTI-LAYER VIEWS (Quad / Quint / Hexa)
# =============================================================================

@router.get("/quad-layer/{agent_id}")
async def get_agent_quad_layer(agent_id: str):
    """Backward compat — delegates to hexa-layer."""
    return await get_agent_hexa_layer(agent_id)


@router.get("/quint-layer/{agent_id}")
async def get_agent_quint_layer(agent_id: str):
    """Backward compat — delegates to hexa-layer."""
    return await get_agent_hexa_layer(agent_id)


@router.get("/hexa-layer/{agent_id}")
async def get_agent_hexa_layer(agent_id: str):
    """Get the full HEXA-LAYER view: Original + Shadow + Ghost + Angels + Seraphim + Cherubim."""
    shadow = get_shadow_for_agent(agent_id)
    ghost = get_ghost_for_agent(agent_id)
    angels = get_angels_for_original(agent_id)
    seraphim = get_seraphim_for_original(agent_id)
    cherubim = get_cherubim_for_original(agent_id)

    if not shadow and not ghost:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found in any layer")

    return {
        "agent_id": agent_id,
        "layers": {
            "original": {"exists": True, "id": agent_id},
            "shadow": {"exists": shadow is not None, "id": shadow["id"] if shadow else None, "name": shadow["name"] if shadow else None, "purpose": "SOTA Quality Review (fast lane)"},
            "ghost": {"exists": ghost is not None, "id": ghost["id"] if ghost else None, "name": ghost["name"] if ghost else None, "methodology_focus": ghost["methodology_focus"] if ghost else None, "purpose": "Methodology Enforcement (slow lane)"},
            "angels": [{"id": a["id"], "name": a["name"], "layer": a["layer"], "complexity_focus": a["complexity_focus"], "purpose": "Complexity Guardian"} for a in angels],
            "seraphim": [{"id": s["id"], "name": s["name"], "angel_name": s["angel_name"], "intricacy_focus": s["intricacy_focus"], "purpose": "Intricacy Arbiter"} for s in seraphim],
            "cherubim": [{"id": c["id"], "name": c["name"], "source_layer": c["source_layer"], "diligence_focus": c["diligence_focus"], "purpose": "Diligence Enforcer"} for c in cherubim],
        },
        "total_counterparts": (1 if shadow else 0) + (1 if ghost else 0) + len(angels) + len(seraphim) + len(cherubim),
        "hexa_layer_complete": shadow is not None and ghost is not None and len(angels) >= 3 and len(seraphim) >= 3 and len(cherubim) >= 1,
    }
