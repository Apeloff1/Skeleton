"""
routes/nexus.py — Knowledge Nexus integration + Curiosity epistemic service.

The vendored Nexus remains isolation-guarded. Curiosity, empirical verification,
truth-state, calibration, provenance-gated watch feeds, and transparency proofs
share /api/nexus.
"""
from __future__ import annotations

from dataclasses import asdict
import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from core.curiosity_service import curiosity_service
from core.truth_verifier import EvidenceItem, EvidenceKind
from core.truth_watch import TruthEventKind

router = APIRouter(prefix="/api/nexus", tags=["knowledge-nexus"])
_NX = str(Path(__file__).resolve().parent.parent / "knowledge_nexus")


def _isolated(fn):
    saved_path = list(sys.path); saved_mods = set(sys.modules); sys.path.insert(0, _NX)
    try: return fn()
    finally:
        sys.path[:] = saved_path
        for name in list(sys.modules):
            if name in saved_mods: continue
            mod = sys.modules.get(name); f = getattr(mod, "__file__", "") or ""
            if f.startswith(_NX): del sys.modules[name]


def _capabilities() -> dict:
    root = Path(_NX); caps: dict[str, list[str]] = {}
    if root.exists():
        for d in sorted(p for p in root.iterdir() if p.is_dir() and p.name != "__pycache__"):
            caps[d.name] = sorted(f.stem for f in d.glob("*.py"))
    return caps


@router.on_event("startup")
async def _start_curiosity() -> None: curiosity_service().start()


@router.on_event("shutdown")
async def _stop_curiosity() -> None: curiosity_service().stop()


@router.get("/status")
async def nexus_status():
    caps = _capabilities(); curiosity = curiosity_service().status()
    return {"vendored": bool(caps), "domains": list(caps), "module_count": sum(len(v) for v in caps.values()),
            "capabilities": caps, "curiosity": curiosity}


@router.get("/orchestrator")
async def nexus_orchestrator():
    def _load():
        from orchestration.nexus_orchestration_layer import NexusOrchestrator
        o = NexusOrchestrator()
        return {"ok": True, "orchestrator": "NexusOrchestrator",
                "methods": [m for m in dir(o) if not m.startswith("_") and callable(getattr(o, m))]}
    try: return _isolated(_load)
    except Exception as e: return JSONResponse({"ok": False, "error": f"{type(e).__name__}: {e}"[:200]}, status_code=207)


class NexusEvent(BaseModel):
    event: str
    source: str = "gameforge"


@router.post("/event")
async def nexus_event(body: NexusEvent):
    def _run():
        from orchestration.nexus_orchestration_layer import NexusOrchestrator
        return NexusOrchestrator().process_important_event(body.event, body.source)
    try: return {"ok": True, "result": _isolated(_run)}
    except Exception as e: return JSONResponse({"ok": False, "error": f"{type(e).__name__}: {e}"[:200]}, status_code=207)


class CuriosityPrompt(BaseModel):
    prompt: str = Field(min_length=1, max_length=20000)
    user_scope: str = Field(default="default", max_length=120)
    signal_key: str | None = Field(default=None, max_length=300)


class CuriosityBoost(BaseModel):
    subject: str = Field(min_length=1, max_length=240)
    delta: float = Field(default=0.15, ge=-0.5, le=0.75)


class SourceRetractionBody(BaseModel):
    source_id: str = Field(min_length=1, max_length=1000)
    reason: str = Field(min_length=3, max_length=2000)
    cascade: bool = True


class ReverifyClaimBody(BaseModel):
    claim: str = Field(min_length=1, max_length=10000)


class ClaimCompareBody(BaseModel):
    left: str = Field(min_length=1, max_length=10000)
    right: str = Field(min_length=1, max_length=10000)


class CalibrationForecastBody(BaseModel):
    claim: str = Field(min_length=1, max_length=10000)
    probability: float = Field(ge=0.0, le=1.0)
    forecaster: str = Field(min_length=1, max_length=300)
    context_sha256: str = Field(default="", max_length=64)
    forecast_id: str | None = Field(default=None, max_length=128)


class TruthWatchEventBody(BaseModel):
    kind: str
    target: str = Field(min_length=1, max_length=10000)
    reason: str = Field(default="", max_length=2000)
    provider: str = Field(min_length=1, max_length=300)
    provider_cursor: str = Field(default="", max_length=1000)
    provenance_verified: bool = False
    event_id: str | None = Field(default=None, max_length=128)
    payload: dict[str, Any] = Field(default_factory=dict)


class TransparencyHeadBody(BaseModel):
    log_id: str = Field(min_length=1, max_length=300)
    tree_size: int = Field(ge=0)
    root_sha256: str = Field(min_length=64, max_length=64)
    source: str = Field(min_length=1, max_length=300)


class TruthEvidenceBody(BaseModel):
    source_id: str = Field(min_length=1, max_length=1000)
    locator: str = Field(default="", max_length=2000)
    kind: str
    supports: bool = True
    independence_group: str = Field(min_length=1, max_length=500)
    quality: float = Field(ge=0.0, le=1.0)
    observed_at: str = Field(default="", max_length=100)
    reproducible: bool = False
    peer_reviewed: bool = False
    primary: bool = False
    provenance_verified: bool = False
    preregistered: bool = False
    data_available: bool = False
    code_available: bool = False
    sample_size: int | None = Field(default=None, ge=1)
    uncertainty_reported: bool = False
    notes: str = Field(default="", max_length=4000)


class VerifyClaimBody(BaseModel):
    claim: str = Field(min_length=1, max_length=10000)
    evidence: list[TruthEvidenceBody] = Field(default_factory=list, max_length=128)
    falsifiable: bool | None = None


@router.post("/curiosity/observe")
async def curiosity_observe(body: CuriosityPrompt):
    return curiosity_service().observe(body.prompt, user_scope=body.user_scope, signal_key=body.signal_key)


@router.get("/curiosity/status")
async def curiosity_status(): return curiosity_service().status()


@router.get("/curiosity/frontier")
async def curiosity_frontier(limit: int = Query(default=20, ge=1, le=100)):
    rows = curiosity_service().frontier(limit=limit); return {"count": len(rows), "topics": rows}


@router.get("/curiosity/knowledge")
async def curiosity_knowledge(q: str = Query(min_length=1, max_length=1000), limit: int = Query(default=8, ge=1, le=50)):
    return curiosity_service().search(q, limit=limit)


@router.get("/curiosity/verification")
async def curiosity_verification_status(): return curiosity_service().engine.verification_status()


@router.get("/curiosity/epistemic-root")
async def curiosity_epistemic_root(): return curiosity_service().epistemic_root()


@router.get("/curiosity/proof")
async def curiosity_claim_proof(claim: str = Query(min_length=1, max_length=10000)):
    return curiosity_service().claim_proof(claim)


@router.get("/curiosity/transparency")
async def curiosity_transparency_status(): return curiosity_service().transparency_status()


@router.post("/curiosity/transparency/checkpoint")
async def curiosity_transparency_checkpoint(): return curiosity_service().checkpoint_truth()


@router.get("/curiosity/transparency/inclusion")
async def curiosity_transparency_inclusion(checkpoint_sha256: str = Query(min_length=64, max_length=64)):
    try: return curiosity_service().transparency_inclusion(checkpoint_sha256)
    except KeyError as exc: raise HTTPException(status_code=404, detail="checkpoint not found in transparency log") from exc


@router.get("/curiosity/transparency/consistency")
async def curiosity_transparency_consistency(old_size: int = Query(ge=0)):
    try: return curiosity_service().transparency_consistency(old_size)
    except ValueError as exc: raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/curiosity/transparency/gossip")
async def curiosity_transparency_gossip(body: TransparencyHeadBody):
    try:
        return curiosity_service().observe_transparency_head(
            log_id=body.log_id, tree_size=body.tree_size, root_sha256=body.root_sha256, source=body.source,
        )
    except ValueError as exc: raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/curiosity/truth")
async def curiosity_truth_state(claim: str = Query(min_length=1, max_length=10000)):
    engine = curiosity_service().engine; state = engine.truth_ledger.get(claim)
    return {"claim": claim, "state": asdict(state) if state is not None else None,
            "authoritative": engine.truth_ledger.authoritative(claim), "contradiction": engine.contradiction_status(claim),
            "dependencies": list(engine.claim_dependencies.dependencies(claim)),
            "dependents": list(engine.claim_dependencies.dependents(claim, recursive=True))}


@router.post("/curiosity/claim-identity")
async def curiosity_claim_identity(body: ClaimCompareBody): return curiosity_service().compare_claims(body.left, body.right)


@router.post("/curiosity/calibration/forecast")
async def curiosity_calibration_forecast(body: CalibrationForecastBody):
    return curiosity_service().record_forecast(
        claim=body.claim, probability=body.probability, forecaster=body.forecaster,
        context_sha256=body.context_sha256, forecast_id=body.forecast_id,
    )


@router.get("/curiosity/calibration")
async def curiosity_calibration_metrics(bins: int = Query(default=10, ge=2, le=100), forecaster: str | None = Query(default=None, max_length=300)):
    return curiosity_service().calibration_metrics(bins=bins, forecaster=forecaster)


@router.post("/curiosity/reverify")
async def curiosity_reverify_claim(body: ReverifyClaimBody): return curiosity_service().engine.reverify_claim(body.claim)


@router.post("/curiosity/retract-source")
async def curiosity_retract_source(body: SourceRetractionBody):
    engine = curiosity_service().engine
    if engine.source_lineage.get(body.source_id) is None: raise HTTPException(status_code=404, detail="source not found in lineage registry")
    return engine.retract_source(body.source_id, body.reason, cascade=body.cascade)


@router.get("/curiosity/watch")
async def curiosity_watch_status(limit: int = Query(default=100, ge=1, le=1000)):
    service = curiosity_service()
    return {"status": service.watch.stats(),
            "pending": [{**asdict(event), "kind": event.kind.value} for event in service.watch.pending(limit=limit)]}


@router.post("/curiosity/watch")
async def curiosity_watch_ingest(body: TruthWatchEventBody):
    try: TruthEventKind(body.kind)
    except ValueError as exc: raise HTTPException(status_code=422, detail=f"unsupported truth watch event kind: {body.kind}") from exc
    return curiosity_service().ingest_watch(
        kind=body.kind, target=body.target, reason=body.reason,
        provider=body.provider, provider_cursor=body.provider_cursor,
        provenance_verified=body.provenance_verified, event_id=body.event_id,
        payload=body.payload,
    )


@router.post("/curiosity/watch/apply")
async def curiosity_watch_apply(limit: int = Query(default=100, ge=1, le=1000)):
    return curiosity_service().apply_watch_now(limit=limit)


@router.post("/curiosity/verify")
async def curiosity_verify_claim(body: VerifyClaimBody):
    evidence: list[EvidenceItem] = []
    for row in body.evidence:
        try: kind = EvidenceKind(row.kind)
        except ValueError as exc: raise HTTPException(status_code=422, detail=f"unsupported evidence kind: {row.kind}") from exc
        evidence.append(EvidenceItem(source_id=row.source_id, locator=row.locator, kind=kind, supports=row.supports,
            independence_group=row.independence_group, quality=row.quality, observed_at=row.observed_at,
            reproducible=row.reproducible, peer_reviewed=row.peer_reviewed, primary=row.primary, notes=row.notes,
            provenance_verified=row.provenance_verified, preregistered=row.preregistered,
            data_available=row.data_available, code_available=row.code_available, sample_size=row.sample_size,
            uncertainty_reported=row.uncertainty_reported))
    result = curiosity_service().engine.verifier.verify_claim(body.claim, evidence, falsifiable=body.falsifiable)
    payload = asdict(result); payload["state"] = result.state.value
    payload["accepted_evidence"] = [{**asdict(item), "kind": item.kind.value} for item in result.accepted_evidence]
    payload["rejected_evidence"] = [{**asdict(item), "kind": item.kind.value} for item in result.rejected_evidence]
    payload["authoritative"] = result.state.value == "verified"
    return payload


@router.post("/curiosity/research")
async def curiosity_research_now():
    try: return await curiosity_service().run_now()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"curiosity research unavailable: {type(exc).__name__}: {exc}"[:1000]) from exc


@router.post("/curiosity/boost")
async def curiosity_boost(body: CuriosityBoost):
    changed = curiosity_service().engine.boost(body.subject, body.delta)
    if not changed: raise HTTPException(status_code=404, detail="subject not found in curiosity frontier")
    return {"subject": body.subject, "boosted": True, "delta": body.delta}
