"""
routes/omega_conductor.py — Ω-ULTRA CONDUCTOR API (/api/omega).

Upgrades the context system, Jeeves, the Jeeves orchestrator, agents,
agent↔agent hand-offs, the agent map and the mastermap with a single
battle-ready fail-safe progress engine. Session-based, in-process.

Roles: context · agent · agent2agent · orchestrator · mastermap · agentmap · jeeves
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from gameforge.omega import (
    conductor_registry, omega_fabric,
    AgentToAgentConductor, OrchestratorConductor, UserToJeevesConductor,
    RepetitionError, MarathonStateError, ConsensusError,
)

router = APIRouter(prefix="/api/omega", tags=["omega-conductor"])


# ── models ──────────────────────────────────────────────────────────
class CreateReq(BaseModel):
    role: str = "context"
    node_id: Optional[str] = None
    mode: str = "pages"
    total: float = 12.0
    autobegin: bool = True


class DeliverReq(BaseModel):
    content: str = Field(..., min_length=1)
    progress: Optional[float] = None
    depth: float = 0.0
    branch: float = 0.0
    page_id: Optional[str] = None


class InterpretReq(BaseModel):
    text: str = Field(..., min_length=1)


class AttachReq(BaseModel):
    name: str
    role: str = "agentmap"


def _sess_or_404(sid: str):
    s = conductor_registry.get(sid)
    if not s:
        raise HTTPException(status_code=404, detail="session_not_found")
    return s


# ── lifecycle ───────────────────────────────────────────────────────
@router.get("/roles")
async def roles():
    return {"ok": True, "roles": conductor_registry.roles()}


@router.get("/sessions")
async def sessions():
    return {"ok": True, "sessions": conductor_registry.list()}


@router.post("/session")
async def create_session(req: CreateReq):
    try:
        sess = conductor_registry.create(req.role, req.node_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    snap = None
    if req.autobegin:
        snap = await sess.conductor.begin(req.mode, req.total, fresh=True)
    return {"ok": True, "session_id": sess.session_id, "role": sess.role,
            "node_id": sess.conductor.node_id, "snapshot": snap}


@router.post("/session/{sid}/begin")
async def begin(sid: str, req: CreateReq):
    sess = _sess_or_404(sid)
    return {"ok": True, "snapshot": await sess.conductor.begin(req.mode, req.total, fresh=True)}


@router.get("/session/{sid}/status")
async def status(sid: str):
    sess = _sess_or_404(sid)
    return {"ok": True, "role": sess.role, "snapshot": sess.conductor.snapshot("STATUS")}


@router.get("/session/{sid}/bar")
async def bar(sid: str, side: str = "context", width: int = 50):
    sess = _sess_or_404(sid)
    return {"ok": True, "bar": sess.conductor.get_progress_bar(side, width)}


@router.post("/session/{sid}/wipe")
async def wipe(sid: str):
    sess = _sess_or_404(sid)
    return {"ok": True, "snapshot": await sess.conductor.wipe_and_restart()}


@router.post("/session/{sid}/end")
async def end(sid: str):
    sess = _sess_or_404(sid)
    snap = await sess.conductor.end()
    conductor_registry.drop(sid)
    return {"ok": True, "snapshot": snap}


# ── delivery (context / response / handoff / jeeves) ─────────────────
def _map_err(e: Exception) -> HTTPException:
    if isinstance(e, RepetitionError):
        return HTTPException(status_code=409, detail=f"repetition_blocked: {e}")
    if isinstance(e, MarathonStateError):
        return HTTPException(status_code=409, detail=f"not_begun: {e}")
    if isinstance(e, ConsensusError):
        return HTTPException(status_code=503, detail=f"consensus_failed: {e}")
    return HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.post("/session/{sid}/context")
async def deliver_context(sid: str, req: DeliverReq):
    sess = _sess_or_404(sid)
    try:
        snap = await sess.conductor.deliver_context(req.content, req.progress, req.depth, req.branch, req.page_id)
    except (RepetitionError, MarathonStateError, ConsensusError) as e:
        raise _map_err(e)
    return {"ok": True, "snapshot": snap}


@router.post("/session/{sid}/response")
async def deliver_response(sid: str, req: DeliverReq):
    sess = _sess_or_404(sid)
    try:
        snap = await sess.conductor.deliver_response(req.content, req.progress, req.depth, req.branch, req.page_id)
    except (RepetitionError, MarathonStateError, ConsensusError) as e:
        raise _map_err(e)
    return {"ok": True, "snapshot": snap}


@router.post("/session/{sid}/handoff")
async def handoff(sid: str, req: DeliverReq):
    """Agent ↔ agent hand-off (role must be agent2agent)."""
    sess = _sess_or_404(sid)
    if not isinstance(sess.conductor, AgentToAgentConductor):
        raise HTTPException(status_code=400, detail="session_role_must_be_agent2agent")
    try:
        snap = await sess.conductor.handoff(req.content, progress=req.progress, depth=req.depth,
                                            branch=req.branch, page_id=req.page_id)
    except (RepetitionError, MarathonStateError, ConsensusError) as e:
        raise _map_err(e)
    return {"ok": True, "snapshot": snap}


@router.post("/session/{sid}/jeeves/interpret")
async def jeeves_interpret(sid: str, req: InterpretReq):
    """Jeeves parses natural language → begins the right mode/total."""
    sess = _sess_or_404(sid)
    if not isinstance(sess.conductor, UserToJeevesConductor):
        raise HTTPException(status_code=400, detail="session_role_must_be_jeeves")
    return {"ok": True, "snapshot": await sess.conductor.interpret_and_begin(req.text)}


# ── orchestrator / mastermap / agent-map ─────────────────────────────
@router.post("/session/{sid}/attach")
async def attach(sid: str, req: AttachReq):
    """Attach a sub-conductor to an orchestrator/mastermap session."""
    sess = _sess_or_404(sid)
    if not isinstance(sess.conductor, OrchestratorConductor):
        raise HTTPException(status_code=400, detail="session_role_must_be_orchestrator_or_mastermap")
    sub = conductor_registry.create(req.role, node_id=req.name)
    await sub.conductor.begin(sess.conductor.mode, sess.conductor.total, fresh=True)
    sess.conductor.attach(req.name, sub.conductor)
    return {"ok": True, "attached": req.name, "sub_session_id": sub.session_id,
            "subs": list(sess.conductor.subs.keys())}


@router.get("/session/{sid}/subs")
async def subs(sid: str):
    sess = _sess_or_404(sid)
    if not isinstance(sess.conductor, OrchestratorConductor):
        raise HTTPException(status_code=400, detail="session_role_must_be_orchestrator_or_mastermap")
    return {"ok": True, "subs": sess.conductor.sub_summary()}


# ══════════════════════════════════════════════════════════════
# OmegaFabric — Ω conductor wired INTO Jeeves + ALL agents
# (jeeves ≙ mastermap, each agent ≙ map). Rising System-IQ.
# ══════════════════════════════════════════════════════════════
class EmitReq(BaseModel):
    content: str = Field(..., min_length=1)
    topic: str = "general"


@router.get("/fabric")
async def fabric_overview():
    await omega_fabric.ensure_started()
    return {"ok": True, **omega_fabric.overview()}


@router.get("/fabric/agents")
async def fabric_agents():
    return {"ok": True, "agents": omega_fabric.list_agents()}


@router.get("/fabric/agent/{agent_id}")
async def fabric_agent_status(agent_id: str):
    snap = omega_fabric.agent_status(agent_id)
    if snap is None:
        raise HTTPException(status_code=404, detail="agent_not_registered")
    return {"ok": True, "snapshot": snap}


@router.post("/fabric/agent/{agent_id}/emit")
async def fabric_agent_emit(agent_id: str, req: EmitReq):
    """Route an agent's output through its conductor (never-repeat + progress)."""
    return {"ok": True, "result": await omega_fabric.agent_emit(agent_id, req.content, req.topic)}


@router.post("/fabric/jeeves/emit")
async def fabric_jeeves_emit(req: EmitReq):
    """Route Jeeves output through the mastermap conductor."""
    return {"ok": True, "result": await omega_fabric.jeeves_emit(req.content, req.topic)}


# ══════════════════════════════════════════════════════════════
# DELTA MEMORY (KDA) — fixed-size multimodal associative memory.
# "Attention is a lookup, folded into ONE matrix." Corrects, never appends.
# ══════════════════════════════════════════════════════════════
class DeltaWriteReq(BaseModel):
    key: str = Field(..., min_length=1)
    value: str = Field(..., min_length=1)
    modality: str = "text"        # text | image | audio | video | vector
    key_modality: str = "text"


class DeltaReadReq(BaseModel):
    key: str = Field(..., min_length=1)
    key_modality: str = "text"


@router.get("/delta/stats")
async def delta_stats():
    from gameforge.omega import delta_memory
    return {"ok": True, **delta_memory.stats()}


@router.get("/delta/heatmap")
async def delta_heatmap(cells: int = 8):
    from gameforge.omega import delta_memory
    return {"ok": True, "cells": cells, "heatmap": delta_memory.snapshot_heatmap(max(2, min(cells, 16)))}


@router.post("/delta/write")
async def delta_write(req: DeltaWriteReq):
    """Fold a (key → value) association of ANY modality into the fixed matrix.
    image/audio/video values may be raw base64 or data-URIs — the memory is
    content-addressed so binaries never grow the footprint."""
    from gameforge.omega import delta_memory
    res = delta_memory.write(req.key, req.value, modality=req.modality,
                             key_modality=req.key_modality)
    try:
        import asyncio
        asyncio.get_running_loop().create_task(omega_fabric._persist_state())
    except Exception:  # noqa: BLE001
        pass
    return {"ok": True, **res}


@router.post("/delta/read")
async def delta_read(req: DeltaReadReq):
    """Associative recall — read the current value vector for a key + nearest
    stored concept (works cross-modally)."""
    from gameforge.omega import delta_memory
    return {"ok": True, **delta_memory.read(req.key, key_modality=req.key_modality)}
