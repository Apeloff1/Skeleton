"""routes/churn.py — CHURN 2.0 API (Segment 1, P0).

Detect deficits → generate exhaustive alternatives (pros/cons/recommended) →
apply a chosen alternative. Triggerable from the Command Center, Advanced
Options, or the proactive background daemon.

All generation runs as an async job (kick + poll) so the 30s ingress proxy is
never blocked, even when LLM enrichment is requested.
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from core import churn_2_service as churn

router = APIRouter(prefix="/api/churn", tags=["churn"])


# ── model catalog (full list — premium + free, all providers) ────────────────
@router.get("/models")
def models():
    from routes.llm_router import MODEL_CATALOG
    by_provider: dict[str, list] = {}
    for name, meta in MODEL_CATALOG.items():
        prov = meta.get("provider", "other")
        cost = meta.get("cost_in", 0) + meta.get("cost_out", 0)
        # "free" tier = nano/bulk/fast cheapest models; everything else "premium"
        band = "free" if meta.get("tier") in ("nano", "bulk", "fast") else "premium"
        by_provider.setdefault(prov, []).append(
            {"id": name, "provider": prov, "tier": meta.get("tier"),
             "band": band, "cost_per_1k": round(cost, 5)})
    for prov in by_provider:
        by_provider[prov].sort(key=lambda m: m["cost_per_1k"])
    all_models = [m for ms in by_provider.values() for m in ms]
    return {"count": len(all_models), "providers": list(by_provider.keys()),
            "by_provider": by_provider, "models": all_models,
            "default": "claude-sonnet-4-6", "qc_bar": churn.QC_BAR}


# ── analysis ─────────────────────────────────────────────────────────────────
@router.get("/{build_id}/analyze")
def analyze(build_id: str):
    return churn.analyze_build(build_id)


@router.get("/{build_id}/{gid}/analyze")
def analyze_one(build_id: str, gid: str):
    return churn.analyze_gamefile(build_id, gid)


# ── run (async) ──────────────────────────────────────────────────────────────
class RunReq(BaseModel):
    gid: str | None = None            # None → churn the whole build (weakest top_n)
    deficit: str | None = None        # None → auto-detect worst deficit
    n: int = churn.DEFAULT_ALTERNATIVES
    model: str | None = None          # None → deterministic (no LLM cost)
    top_n: int = 3                    # whole-build mode: how many targets to churn


@router.post("/{build_id}/run/async")
def run_async(build_id: str, req: RunReq | None = None):
    r = req or RunReq()
    jid = churn.start_churn_job(build_id, gid=r.gid, deficit=r.deficit,
                                n=r.n, model=r.model, top_n=r.top_n)
    return {"job_id": jid, "status": "running"}


@router.get("/job/{job_id}")
def job(job_id: str):
    return churn.get_job(job_id)


# ── runs history ─────────────────────────────────────────────────────────────
@router.get("/{build_id}/runs")
def runs(build_id: str, limit: int = 30):
    return churn.list_runs(build_id, limit=limit)


# ── apply a chosen alternative ───────────────────────────────────────────────
class ApplyReq(BaseModel):
    run_id: str
    variant_id: str


@router.post("/{build_id}/{gid}/apply")
def apply(build_id: str, gid: str, req: ApplyReq):
    return churn.apply_alternative(build_id, gid, req.run_id, req.variant_id)


# ── proactive daemon ─────────────────────────────────────────────────────────
class DaemonReq(BaseModel):
    enabled: bool
    interval_s: int | None = None


@router.post("/daemon/toggle")
def daemon_toggle(req: DaemonReq):
    return churn.toggle_daemon(req.enabled, req.interval_s)


@router.get("/daemon/status")
def daemon_status():
    return churn.daemon_status()
