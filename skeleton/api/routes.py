"""
================================================================================
skeleton.api.routes — REST API Surface (v16.2 wiring)
================================================================================
Thin FastAPI routers for every subsystem. No domain logic — validate, call
the service, serialise. Written against the actual v16.2 package APIs:

  - Jeeves:    open_session / ask / set_mode / review_code / close_session
  - Memory:    MemoryTrinity.query_unified
  - Agents:    AgentMesh.join / route / stats, SwarmScheduler.submit / stats
  - Pipelines: NpcPipeline.run / GameLogicPipeline.run / AnimationPipeline.run
  - Forge:     Forge.new_blueprint / instantiate / materialise
  - Registry:  CapabilityRegistry.list
================================================================================
"""
from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException

from skeleton.api.server import get_state
from skeleton.kernel.errors import SkeletonError

router = APIRouter()

# Blueprints are in-flight domain objects; keep them addressable by id
# between the create and materialise calls.
_blueprints: Dict[str, Any] = {}


def _state():
    return get_state()


def _require(obj: Any, name: str) -> Any:
    if obj is None:
        raise HTTPException(status_code=503, detail=f"{name} not available")
    return obj


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
    registry = _require(state.registry, "Registry")
    return [cap.to_dict() for cap in registry.list()]


# =============================================================================
# JEEVES TUTOR
# =============================================================================

@router.post("/jeeves/session")
async def jeeves_session(request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    jeeves = _require(state.jeeves, "Jeeves")
    from skeleton.jeeves.core import SessionMode
    mode = SessionMode.CO_CODING if request.get("mode") == "co_coding" else SessionMode.TUTORING
    session = jeeves.open_session(request.get("user_id", "anonymous"), mode=mode)
    return {"session_id": session.session_id, "mode": session.mode.value, "status": "created"}


@router.post("/jeeves/interact")
async def jeeves_interact(request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    jeeves = _require(state.jeeves, "Jeeves")
    reply = jeeves.ask(
        request.get("session_id", ""),
        request.get("input", ""),
        context=request.get("context"),
    )
    return {"response": reply, "session_id": request.get("session_id")}


@router.post("/jeeves/review")
async def jeeves_review(request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    jeeves = _require(state.jeeves, "Jeeves")
    return jeeves.review_code(request.get("session_id", ""), request.get("code", ""))


@router.post("/jeeves/session/{session_id}/close")
async def jeeves_close(session_id: str, state=Depends(_state)) -> Dict[str, Any]:
    jeeves = _require(state.jeeves, "Jeeves")
    session = jeeves.close_session(session_id)
    return {"session_id": session.session_id, "turns": len(session.turns), "status": "closed"}


@router.get("/jeeves/matrices")
async def jeeves_matrices(state=Depends(_state)) -> Dict[str, Any]:
    """Snapshots of the three self-learning matrices (SAM / CLOM / KREM)."""
    return {
        "sam": state.sam.snapshot() if state.sam else {},
        "clom": state.clom.snapshot() if state.clom else {},
        "krem": state.krem.snapshot() if state.krem else {},
    }


# =============================================================================
# MEMORY TRINITY
# =============================================================================

@router.post("/memory/query")
async def memory_query(request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    trinity = _require(state.memory_trinity, "Memory")
    result = trinity.query_unified(
        request.get("query", ""),
        top_k_per_tier=request.get("top_k", 3),
        metadata_filter=request.get("metadata_filter"),
    )
    return {
        "facts": [r.chunk.text for r in result.facts],
        "persona_frame": [r.chunk.text for r in result.persona_frame],
        "personal_history": [r.chunk.text for r in result.personal_history],
        "combined_score": result.combined_score,
        "token_estimate": result.token_estimate,
        "provenance": result.provenance_chain,
    }


@router.get("/memory/health")
async def memory_health(state=Depends(_state)) -> Dict[str, Any]:
    trinity = _require(state.memory_trinity, "Memory")
    return trinity.health()


# =============================================================================
# SWARM
# =============================================================================

@router.get("/swarm/stats")
async def swarm_stats(state=Depends(_state)) -> Dict[str, Any]:
    mesh = _require(state.mesh, "Swarm")
    return mesh.stats()


@router.post("/swarm/agent")
async def swarm_join_agent(request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    mesh = _require(state.mesh, "Swarm")
    agent = mesh.join(
        set(request.get("specialisations", [])),
        weight=float(request.get("weight", 1.0)),
        metadata=request.get("metadata"),
    )
    return {"agent_id": str(agent.agent_id), "status": "joined"}


@router.post("/swarm/route/{capability}")
async def swarm_route(capability: str, state=Depends(_state)) -> Dict[str, Any]:
    mesh = _require(state.mesh, "Swarm")
    agent = mesh.route(capability)
    return {"agent_id": str(agent.agent_id), "load": agent.load}


@router.get("/scheduler/stats")
async def scheduler_stats(state=Depends(_state)) -> Dict[str, Any]:
    scheduler = _require(state.scheduler, "Scheduler")
    return scheduler.stats()


# =============================================================================
# PIPELINES
# =============================================================================

@router.post("/pipeline/npc")
async def pipeline_npc(request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    pipeline = _require(state.npc_pipeline, "NPC pipeline")
    spec = pipeline.run(
        request.get("description", ""),
        name=request.get("name"),
        dialogue_beats=int(request.get("dialogue_beats", 3)),
        params=request.get("params"),
    )
    return {"npc": spec.to_dict(), "status": "generated"}


@router.post("/pipeline/game-logic")
async def pipeline_game_logic(request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    pipeline = _require(state.game_logic_pipeline, "Game logic pipeline")
    spec = pipeline.run(
        request.get("description", ""),
        title=request.get("title", "untitled"),
        max_level=int(request.get("max_level", 50)),
        curve=request.get("curve", "quadratic"),
        currency=request.get("currency", "gold"),
    )
    return {"game_logic": spec.to_dict(), "status": "generated"}


@router.post("/pipeline/animation")
async def pipeline_animation(request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    pipeline = _require(state.animation_pipeline, "Animation pipeline")
    actions = request.get("actions")
    spec = pipeline.run(
        request.get("description", ""),
        actions=tuple(actions) if actions else ("idle", "walk", "run", "attack"),
    )
    return {"animation": spec.to_dict(), "status": "generated"}


# =============================================================================
# FORGE
# =============================================================================

@router.post("/forge/blueprint")
async def forge_blueprint(request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    forge = _require(state.forge, "Forge")
    blueprint = forge.new_blueprint(request.get("name", "untitled"))
    for comp in request.get("components", []):
        forge.instantiate(
            blueprint,
            comp["kind"],
            comp["instance_id"],
            config=comp.get("config"),
        )
    for wire in request.get("wires", []):
        blueprint.connect(tuple(wire["src"]), tuple(wire["dst"]))
    _blueprints[blueprint.blueprint_id] = blueprint
    return {
        "blueprint_id": blueprint.blueprint_id,
        "components": len(blueprint.components),
        "wires": len(blueprint.wires),
        "status": "created",
    }


@router.get("/forge/kinds")
async def forge_kinds(state=Depends(_state)) -> Dict[str, Any]:
    forge = _require(state.forge, "Forge")
    return {"kinds": forge.available_kinds()}


@router.post("/forge/materialise")
async def forge_materialise(request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    forge = _require(state.forge, "Forge")
    blueprint_id = request.get("blueprint_id", "")
    blueprint = _blueprints.get(blueprint_id)
    if blueprint is None:
        raise HTTPException(status_code=404, detail=f"unknown blueprint {blueprint_id!r}")
    result = forge.materialise(blueprint)
    return {"artefact": result, "status": "materialised"}


# =============================================================================
# INTELLIGENCE
# =============================================================================

@router.post("/intelligence/reason")
async def intelligence_reason(request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    intelligence = _require(state.intelligence, "Intelligence")
    return intelligence.reason(
        query=request.get("query", ""),
        context=request.get("context"),
    )


# =============================================================================
# RESILIENCE
# =============================================================================

@router.post("/resilience/sanitise")
async def resilience_sanitise(request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    fortress = _require(state.resilience, "Resilience")
    sanitized, report = fortress.process_input(
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
    fortress = _require(state.resilience, "Resilience")
    return fortress.stats()
