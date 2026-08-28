"""REST API surface — thin FastAPI routers for every subsystem."""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Request

from skeleton.api.idempotency import IdempotencyGuard
from skeleton.api.server import get_state
from skeleton.jeeves.core import SessionMode

router = APIRouter()

# Idempotency for retry-sensitive POSTs (forge materialise, gameforge runs):
# a client retry replays the first recorded response instead of re-executing.
_idempotency = IdempotencyGuard()


def _state():
    return get_state()


def _require(obj: Any, name: str) -> Any:
    if obj is None:
        raise HTTPException(status_code=503, detail=f"{name} not available")
    return obj


@router.get("/health")
async def health(state=Depends(_state)) -> Dict[str, Any]:
    checks = state.is_healthy()
    return {"status": "healthy" if checks["overall"] else "degraded", "checks": checks}


@router.get("/health/live")
async def live(state=Depends(_state)) -> Dict[str, Any]:
    return _require(state.health, "Health").liveness()


@router.get("/health/ready")
async def ready(state=Depends(_state)) -> Dict[str, Any]:
    return _require(state.health, "Health").readiness()


@router.get("/metrics")
async def metrics(state=Depends(_state)) -> Dict[str, Any]:
    return _require(state.metrics, "Metrics").snapshot()


@router.get("/genesis")
async def genesis_report(state=Depends(_state)) -> Dict[str, Any]:
    genesis = _require(state.genesis, "Genesis")
    return {"report": genesis.report.to_dict(), "health": genesis.health()}


@router.get("/genesis/handles")
async def genesis_handles(state=Depends(_state)) -> Dict[str, Any]:
    """Names of every subsystem handle wired by the Genesis boot, per phase."""
    genesis = _require(state.genesis, "Genesis")
    return {
        "phases": genesis.report.phases,
        "wired": genesis.report.wired,
        "handle_names": sorted(genesis.handles.keys()),
    }


@router.get("/interface/reranker/stats")
async def reranker_stats(state=Depends(_state)) -> Dict[str, Any]:
    """FeatureReranker counters (queries reranked, active weights)."""
    genesis = _require(state.genesis, "Genesis")
    reranker = genesis.handles.get("reranker")
    if reranker is None:
        raise HTTPException(status_code=503, detail="reranker not wired")
    stats = reranker.stats() if hasattr(reranker, "stats") else {}
    return {"reranker": stats}


@router.post("/retrieval/query")
async def retrieval_query(request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    """Fan a query over the four-plane quad retriever (RAG+CAG+MAG+KAG, RRF)."""
    genesis = _require(state.genesis, "Genesis")
    quad = genesis.handles.get("quad")
    if quad is None:
        raise HTTPException(status_code=503, detail="quad retriever not wired")
    query = str(request.get("query", ""))
    if not query.strip():
        raise HTTPException(status_code=422, detail="query is required")
    k = int(request.get("k", 8))
    results = quad.retrieve(query, k=k, use_cache=bool(request.get("use_cache", True)))
    return {
        "query": query,
        "results": [
            {
                "id": f.fragment_id,
                "plane": f.plane,
                "content": f.content,
                "score": round(f.score, 6),
                "provenance": f.provenance,
            }
            for f in results
        ],
        "stats": quad.stats(),
    }


@router.post("/retrieval/ingest")
async def retrieval_ingest(request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    """Ingest a document into the quad retriever's RAG+MAG planes."""
    genesis = _require(state.genesis, "Genesis")
    quad = genesis.handles.get("quad")
    if quad is None:
        raise HTTPException(status_code=503, detail="quad retriever not wired")
    doc_id = str(request.get("doc_id", "")).strip()
    text = str(request.get("text", "")).strip()
    if not doc_id or not text:
        raise HTTPException(status_code=422, detail="doc_id and text are required")
    chunks = quad.ingest_document(
        doc_id, text,
        metadata=request.get("metadata"),
        salience=float(request.get("salience", 0.5)),
    )
    return {"doc_id": doc_id, "chunks": chunks, "status": "ingested"}


@router.get("/capabilities")
async def capabilities(state=Depends(_state)) -> List[Dict[str, Any]]:
    return [cap.to_dict() for cap in _require(state.registry, "Registry").list()]


@router.post("/jeeves/session")
async def jeeves_session(request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    jeeves = _require(state.jeeves, "Jeeves")
    raw_mode = request.get("mode", "tutoring")
    mode = SessionMode.TUTORING
    for m in SessionMode:
        if m.value == raw_mode:
            mode = m
            break
    session = jeeves.open_session(request.get("user_id", "anonymous"), mode=mode)
    return {"session_id": session.session_id, "mode": session.mode.value, "status": "created"}


@router.post("/jeeves/interact")
async def jeeves_interact(request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    jeeves = _require(state.jeeves, "Jeeves")
    reply = jeeves.ask(request.get("session_id", ""), request.get("input", ""), context=request.get("context"))
    return {"response": reply, "session_id": request.get("session_id")}


@router.post("/jeeves/review")
async def jeeves_review(request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    return _require(state.jeeves, "Jeeves").review_code(request.get("session_id", ""), request.get("code", ""))


@router.post("/jeeves/bind-era")
async def jeeves_bind_era(request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    pack = _require(state.jeeves, "Jeeves").bind_era(request.get("era", "extraction_now"))
    return {"era": pack["era"], "primary_dps": pack["primary_dps"], "status": "bound"}


@router.post("/jeeves/advise")
async def jeeves_advise(request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    return _require(state.jeeves, "Jeeves").advise(
        request.get("session_id", ""), request.get("telemetry") or {},
    )


@router.get("/jeeves/matrices/{session_id}")
async def jeeves_matrices(session_id: str, state=Depends(_state)) -> Dict[str, Any]:
    _require(state.jeeves, "Jeeves")
    return {
        "sam": state.jeeves_sam.snapshot() if state.jeeves_sam else {},
        "clom": state.jeeves_clom.snapshot() if state.jeeves_clom else {},
        "krem": state.jeeves_krem.snapshot() if state.jeeves_krem else {},
        "memory_items": len(state.jeeves_memory) if state.jeeves_memory else 0,
    }


@router.post("/memory/query")
async def memory_query(request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    result = _require(state.memory_trinity, "Memory").query_unified(
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


@router.get("/swarm/stats")
async def swarm_stats(state=Depends(_state)) -> Dict[str, Any]:
    return _require(state.mesh, "Swarm").stats()


@router.post("/swarm/agent")
async def swarm_register_agent(request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    agent = _require(state.mesh, "Swarm").join(
        set(request.get("specialisations", [])),
        weight=request.get("weight", 1.0),
        metadata=request.get("metadata"),
    )
    return {"agent_id": str(agent.agent_id), "status": "registered"}


@router.post("/swarm/route")
async def swarm_route(request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    agent = _require(state.mesh, "Swarm").route(request.get("capability", ""))
    return {"agent_id": str(agent.agent_id), "load": agent.load}


@router.get("/ledger/stats")
async def ledger_stats(state=Depends(_state)) -> Dict[str, Any]:
    return _require(state.ledger, "Ledger").stats()


@router.get("/ledger/tail")
async def ledger_tail(n: int = 50, state=Depends(_state)) -> List[Dict[str, Any]]:
    return [e.to_dict() for e in _require(state.ledger, "Ledger").tail(n)]


@router.get("/scheduler/stats")
async def scheduler_stats(state=Depends(_state)) -> Dict[str, Any]:
    return _require(state.scheduler, "Scheduler").stats()


@router.post("/pipeline/npc")
async def pipeline_npc(request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    spec = _require(state.npc_pipeline, "NPC pipeline").run(
        request.get("description", ""),
        name=request.get("name"),
        dialogue_beats=request.get("dialogue_beats", 3),
        params=request.get("params"),
    )
    return {"npc": spec.to_dict(), "status": "generated"}


@router.post("/pipeline/game-logic")
async def pipeline_game_logic(request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    spec = _require(state.game_logic_pipeline, "Game logic pipeline").run(
        request.get("description", ""),
        title=request.get("title", "untitled"),
        max_level=request.get("max_level", 50),
        curve=request.get("curve", "quadratic"),
        currency=request.get("currency", "gold"),
    )
    return {"game_logic": spec.to_dict(), "status": "generated"}


@router.post("/pipeline/animation")
async def pipeline_animation(request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    actions = request.get("actions")
    spec = _require(state.animation_pipeline, "Animation pipeline").run(
        request.get("description", "humanoid"),
        actions=tuple(actions) if actions else ("idle", "walk", "run", "attack"),
    )
    return {"animation": spec.to_dict(), "status": "generated"}


@router.post("/forge/blueprint")
async def forge_blueprint(request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    forge = _require(state.forge, "Forge")
    bp = forge.new_blueprint(request.get("name", "unnamed"))
    for comp in request.get("components", []):
        forge.instantiate(bp, comp["kind"], comp["instance_id"], config=comp.get("config"))
    for wire in request.get("wires", []):
        bp.connect(tuple(wire["from"]), tuple(wire["to"]))
    problems = bp.validate()
    return {"blueprint_id": bp.blueprint_id, "valid": not problems, "problems": problems, "status": "created"}


@router.post("/forge/materialise")
async def forge_materialise(http_request: Request, request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    replay = _idempotency.replay(dict(http_request.headers))
    if replay is not None:
        return replay  # type: ignore[return-value]
    forge = _require(state.forge, "Forge")
    bp = forge.new_blueprint(request.get("name", "unnamed"))
    for comp in request.get("components", []):
        forge.instantiate(bp, comp["kind"], comp["instance_id"], config=comp.get("config"))
    for wire in request.get("wires", []):
        bp.connect(tuple(wire["from"]), tuple(wire["to"]))
    response = {"artefact": forge.materialise(bp, era=request.get("era", "extraction_now"), target=request.get("target", "json")), "status": "materialised"}
    _idempotency.remember(dict(http_request.headers), response)
    return response


@router.get("/forge/kinds")
async def forge_kinds(state=Depends(_state)) -> List[str]:
    return _require(state.forge, "Forge").available_kinds()


@router.get("/forge/eras")
async def forge_eras() -> Dict[str, Any]:
    from skeleton.forge.eras import list_eras, compile_era
    return {"eras": list_eras(), "default": "extraction_now", "sample": compile_era("extraction_now")["primary_dps"]}


@router.post("/forge/archetype")
async def forge_archetype(http_request: Request, request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    replay = _idempotency.replay(dict(http_request.headers))
    if replay is not None:
        return replay  # type: ignore[return-value]
    from skeleton.forge.archetypes import default_library
    forge = _require(state.forge, "Forge")
    name = request.get("name", "extraction")
    era = request.get("era", "extraction_now")
    target = request.get("target", "godot")
    bp = default_library().build(forge, name)
    artefact = forge.materialise(bp, era=era, target=target)
    response = {"blueprint_id": bp.blueprint_id, "artefact": artefact, "status": "materialised"}
    _idempotency.remember(dict(http_request.headers), response)
    return response


@router.post("/intelligence/reason")
async def intelligence_reason(request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    return _require(state.intelligence, "Intelligence").reason(
        query=request.get("query", ""), context=request.get("context")
    )


@router.post("/resilience/sanitise")
async def resilience_sanitise(request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    fortress = _require(state.resilience, "Resilience")
    sanitized, report = fortress.process_input(
        raw_input=request.get("input", ""),
        user_id=request.get("user_id", "anonymous"),
    )
    level = getattr(report.level, "name", None) or getattr(report.level, "value", str(report.level))
    return {
        "sanitized": sanitized,
        "threat_level": level,
        "confidence": getattr(report, "confidence", None),
        "action": getattr(report, "action_taken", None),
    }


@router.get("/resilience/stats")
async def resilience_stats(state=Depends(_state)) -> Dict[str, Any]:
    return _require(state.resilience, "Resilience").stats()


@router.get("/context/snapshot")
async def context_snapshot(state=Depends(_state)) -> Dict[str, Any]:
    return _require(state.cockpit, "Cockpit").snapshot()


@router.post("/context/command")
async def context_command(request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    return _require(state.cockpit, "Cockpit").apply(request.get("command", ""))


@router.post("/gameforge/run")
async def gameforge_run(http_request: Request, request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    replay = _idempotency.replay(dict(http_request.headers))
    if replay is not None:
        return replay  # type: ignore[return-value]
    runner = _require(state.gameforge, "GameForge")
    out = runner.execute(
        request.get("vision", ""),
        era=request.get("era"),
        archetype=request.get("archetype", "extraction"),
        target=request.get("target", "godot"),
    )
    # files can be large; keep names in the HTTP body
    files = out.get("files") or {}
    out = dict(out)
    out["file_names"] = sorted(files)
    if not request.get("include_files"):
        out.pop("files", None)
    _idempotency.remember(dict(http_request.headers), out)
    return out


@router.post("/gameforge/intake")
async def gameforge_intake(http_request: Request, request: Dict[str, Any], state=Depends(_state)) -> Dict[str, Any]:
    replay = _idempotency.replay(dict(http_request.headers))
    if replay is not None:
        return replay  # type: ignore[return-value]
    from skeleton.context.questionnaire import intake
    taken = intake(request.get("answers") or {})
    runner = _require(state.gameforge, "GameForge")
    out = runner.execute(
        taken.vision,
        era=taken.era,
        answers=request.get("answers") or {},
        project_root=request.get("project_root"),
        overwrite=bool(request.get("overwrite")),
        target=request.get("target", "godot"),
        archetype=request.get("archetype", "extraction"),
    )
    files = out.get("files") or {}
    out = dict(out)
    out["intake"] = taken.to_dict()
    out["file_names"] = sorted(files)
    if not request.get("include_files"):
        out.pop("files", None)
    _idempotency.remember(dict(http_request.headers), out)
    return out


@router.get("/auth/github")
async def github_oauth_card() -> Dict[str, Any]:
    """The exact strings to paste into GitHub → New OAuth App."""
    from skeleton.api.oauth import oauth_card
    return oauth_card()


@router.get("/auth/github/start")
async def github_oauth_start() -> Dict[str, Any]:
    from skeleton.api.oauth import authorize_url, client_id
    if not client_id():
        raise HTTPException(status_code=503, detail="SKELETON_GITHUB_CLIENT_ID unset")
    return authorize_url()


@router.get("/auth/github/callback")
async def github_oauth_callback(code: str = "", state: str = "") -> Dict[str, Any]:
    from skeleton.api.oauth import exchange_code
    if not code:
        raise HTTPException(status_code=400, detail="missing code")
    out = exchange_code(code)
    safe = {k: v for k, v in out.items() if k != "access_token"}
    safe["state"] = state
    return safe
