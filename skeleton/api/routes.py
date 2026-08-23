"""
================================================================================
skeleton.api.routes — REST API Surface
================================================================================
Thin FastAPI routers for every subsystem. No domain logic — validation,
call service, serialise.
================================================================================
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from skeleton.api.server import get_state

router = APIRouter()


def _state():
    return get_state()


# =============================================================================
# HEALTH & CAPABILITIES
# =============================================================================

@router.get("/health")
async def health(state=Depends(_state)) -> Dict[str, Any]:
    checks = state.is_healthy()
    return {
        "status": "healthy" if checks["overall"] else "degraded",
        "checks": checks,
    }


@router.get("/capabilities")
async def capabilities(state=Depends(_state)) -> List[Dict[str, Any]]:
    if not state.registry:
        return []
    return [
        {"name": name, "version": info.version, "healthy": info.healthy}
        for name, info in state.registry._capabilities.items()
    ]


# =============================================================================
# JEEVES TUTOR
# =============================================================================

@router.post("/jeeves/session")
async def jeeves_session(request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    if not state.jeeves:
        raise HTTPException(status_code=503, detail="Jeeves not available")
    session_id = state.jeeves.create_session(
        user_id=request.get("user_id"),
        skill_level=request.get("skill_level", "intermediate"),
    )
    return {"session_id": session_id, "status": "created"}


@router.post("/jeeves/interact")
async def jeeves_interact(request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    if not state.jeeves:
        raise HTTPException(status_code=503, detail="Jeeves not available")
    response = state.jeeves.interact(
        session_id=request.get("session_id"),
        user_input=request.get("input", ""),
    )
    return {"response": response, "session_id": request.get("session_id")}


@router.get("/jeeves/matrices/{session_id}")
async def jeeves_matrices(session_id: str, state=Depends(_state)) -> Dict[str, Any]:
    if not state.jeeves:
        raise HTTPException(status_code=503, detail="Jeeves not available")
    return state.jeeves.get_matrices(session_id)


# =============================================================================
# MEMORY TRINITY
# =============================================================================

@router.post("/memory/query")
async def memory_query(request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    if not state.memory_trinity:
        raise HTTPException(status_code=503, detail="Memory not available")
    result = state.memory_trinity.query_unified(
        query_text=request.get("query", ""),
        top_k_per_tier=request.get("top_k", 3),
    )
    return {
        "facts": [r.chunk.text for r in result.facts],
        "persona_frame": [r.chunk.text for r in result.persona_frame],
        "personal_history": [r.chunk.text for r in result.personal_history],
        "combined_score": result.combined_score,
        "token_estimate": result.token_estimate,
    }


# =============================================================================
# SWARM
# =============================================================================

@router.get("/swarm/stats")
async def swarm_stats(state=Depends(_state)) -> Dict[str, Any]:
    if not state.mesh:
        raise HTTPException(status_code=503, detail="Swarm not available")
    return state.mesh.stats()


@router.post("/swarm/agent")
async def swarm_register_agent(request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    if not state.mesh:
        raise HTTPException(status_code=503, detail="Swarm not available")
    from skeleton.agents.mesh import AgentState, AgentRole, CapabilityVector
    agent = AgentState(
        agent_id=request.get("agent_id"),
        role=AgentRole[request.get("role", "WORKER")],
        capabilities=CapabilityVector(**request.get("capabilities", {})),
    )
    state.mesh.register(agent)
    return {"agent_id": str(agent.agent_id), "status": "registered"}


# =============================================================================
# PIPELINES
# =============================================================================

@router.post("/pipeline/npc")
async def pipeline_npc(request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    if not state.npc_pipeline:
        raise HTTPException(status_code=503, detail="NPC pipeline not available")
    result = state.npc_pipeline.generate(
        description=request.get("description", ""),
        include_dialogue=request.get("include_dialogue", True),
    )
    return {"npc": result, "status": "generated"}


@router.post("/pipeline/game-logic")
async def pipeline_game_logic(request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    if not state.game_logic_pipeline:
        raise HTTPException(status_code=503, detail="Game logic pipeline not available")
    result = state.game_logic_pipeline.generate(
        style=request.get("style", "turn_based"),
        include_magic=request.get("include_magic", True),
    )
    return {"game_logic": result, "status": "generated"}


@router.post("/pipeline/animation")
async def pipeline_animation(request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    if not state.animation_pipeline:
        raise HTTPException(status_code=503, detail="Animation pipeline not available")
    result = state.animation_pipeline.generate(
        description=request.get("description", "humanoid"),
        include_fingers=request.get("include_fingers", True),
    )
    return {"animation": result, "status": "generated"}


# =============================================================================
# FORGE
# =============================================================================

@router.post("/forge/blueprint")
async def forge_blueprint(request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    if not state.forge:
        raise HTTPException(status_code=503, detail="Forge not available")
    blueprint = state.forge.create_blueprint(
        kind=request.get("kind", "system"),
        spec=request.get("spec", {}),
    )
    return {"blueprint_id": blueprint.id, "status": "created"}


@router.post("/forge/materialise")
async def forge_materialise(request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    if not state.forge:
        raise HTTPException(status_code=503, detail="Forge not available")
    result = state.forge.materialise(
        blueprint_id=request.get("blueprint_id"),
        seed=request.get("seed"),
    )
    return {"artefact": result, "status": "materialised"}


# =============================================================================
# INTELLIGENCE
# =============================================================================

@router.post("/intelligence/reason")
async def intelligence_reason(request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    if not state.intelligence:
        raise HTTPException(status_code=503, detail="Intelligence not available")
    result = state.intelligence.reason(
        query=request.get("query", ""),
        context=request.get("context"),
    )
    return result


# =============================================================================
# RESILIENCE
# =============================================================================

@router.post("/resilience/sanitise")
async def resilience_sanitise(request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    if not state.resilience:
        raise HTTPException(status_code=503, detail="Resilience not available")
    sanitized, report = state.resilience.process_input(
        raw_input=request.get("input", ""),
        user_id=request.get("user_id", "anonymous"),
    )
    return {
        "sanitized": sanitized,
        "threat_level": report.level.name,
        "confidence": report.confidence,
        "action": report.action_taken,
    }


@router.get("/resilience/stats")
async def resilience_stats(state=Depends(_state)) -> Dict[str, Any]:
    if not state.resilience:
        raise HTTPException(status_code=503, detail="Resilience not available")
    return state.resilience.stats()
