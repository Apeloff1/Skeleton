"""
routes/prood.py — PROOD Final-Implementation Readiness Audit
(/api/prood).

The PROOD master document describes a production-grade, AI-first game-dev
platform (Churn Pipeline, Resilience/165+ gates, Saga orchestration, CQRS +
Event Bus, Observability, Billing, Multi-agent, SOTA engines). Nearly all of
it is already implemented across this backend.

Rather than fabricate a completion figure, this endpoint computes a REAL,
weighted completion percentage by live-probing each capability's backing
endpoints (same technique as gameforge/coverage/selftest) and, for engine
coverage, folding in the coverage report's own overall_percent.
"""
from __future__ import annotations

import time
from typing import Dict, List, Optional

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

from gameforge.prood import event_bus, saga_orchestrator
from gameforge.prood.saga_orchestrator import SagaStep
from gameforge.workflow.internal_build_system import create_internal_build_system
from gameforge.workflow.jeeves_vault import jeeves_vault

router = APIRouter(prefix="/api/prood", tags=["prood"])

_BASE = "http://127.0.0.1:8001"

# capability → (weight, [probe paths]). Derived directly from the PROOD PDF.
CAPABILITIES: List[Dict] = [
    {"key": "churn_pipeline", "name": "Churn Pipeline (quality iteration)", "weight": 12,
     "probes": ["/api/churn/models", "/api/churn/daemon/status"],
     "section": "2.2 Key Systems"},
    {"key": "resilience", "name": "Resilience & Self-Healing (165+ gates)", "weight": 12,
     "probes": ["/api/resilience-forge/status", "/api/sentinel-array/status"],
     "section": "2.2 Key Systems"},
    {"key": "quality_control", "name": "Quality Control / Gates", "weight": 8,
     "probes": ["/api/quality-control/standards"],
     "section": "2.1 Core Patterns"},
    {"key": "observability", "name": "Observability (metrics · alerting · health)", "weight": 10,
     "probes": ["/api/health/runtime", "/api/telemetry/trail"],
     "section": "2.2 Key Systems"},
    {"key": "saga_orchestration", "name": "Saga & Workflow Orchestration", "weight": 10,
     "probes": ["/api/gameforge/runtime/status", "/api/gameforge/workflow/status"],
     "section": "2.1 Core Patterns"},
    {"key": "autonomous_workflow", "name": "Autonomous Workflow → Deploy", "weight": 12,
     "probes": ["/api/gameforge/workflow/status", "/api/gameforge/build/toolchains"],
     "section": "3. Frontend / Ship"},
    {"key": "multi_agent", "name": "Multi-Agent Orchestration", "weight": 10,
     "probes": ["/api/gameforge/runtime/status"],
     "section": "4. SOTA Capabilities"},
    {"key": "billing", "name": "Billing & Usage (Stripe · quotas)", "weight": 8,
     "probes": ["/api/monetization/overview", "/api/premium/plans", "/api/marketplace/listings"],
     "section": "2.2 Key Systems"},
    {"key": "governance", "name": "Governance & Audit", "weight": 8,
     "probes": ["/api/governance/reports", "/api/governance/audit"],
     "section": "2.1 Core Patterns"},
    {"key": "cqrs_events", "name": "CQRS · Event Sourcing · Event Bus", "weight": 6,
     "probes": ["/api/prood/events"],
     "section": "2.1 Core Patterns"},
    {"key": "collaboration", "name": "Real-time Collaboration", "weight": 6,
     "probes": ["/api/collaboration/sessions"],
     "section": "3. Frontend"},
    {"key": "marketplace", "name": "Marketplace & Community", "weight": 6,
     "probes": ["/api/marketplace/listings", "/api/creators"],
     "section": "2.2 Key Systems"},
    {"key": "testing_qa", "name": "Testing & QA Pipeline", "weight": 6,
     "probes": ["/api/testing-qa/overview"],
     "section": "5. Quality"},
    {"key": "omega_conductor", "name": "Ω-Ultra Conductor (context · agents · jeeves)", "weight": 8,
     "probes": ["/api/omega/roles", "/api/omega/sessions"],
     "section": "2.1 Core Patterns"},
]

# Special capability scored from the coverage report's own overall_percent.
_ENGINE_COVERAGE = {"key": "engine_coverage", "name": "SOTA Engine Coverage",
                    "weight": 10, "section": "4. SOTA Capabilities"}


async def _probe(client: httpx.AsyncClient, path: str) -> Dict:
    t0 = time.time()
    ok = False
    status = 0
    try:
        r = await client.get(_BASE + path)
        status = r.status_code
        ok = 200 <= r.status_code < 300
    except Exception:  # noqa: BLE001
        ok = False
    return {"path": path, "ok": ok, "status": status,
            "latency_ms": round((time.time() - t0) * 1000, 1)}


@router.get("/capabilities")
async def capabilities():
    """Static map of PROOD capabilities → backing endpoints (no probing)."""
    return {"ok": True,
            "capabilities": CAPABILITIES + [{**_ENGINE_COVERAGE, "probes": ["/api/gameforge/coverage"]}]}


@router.get("/readiness")
async def readiness():
    """Live-probe every PROOD capability and compute a weighted completion %."""
    results: List[Dict] = []
    weighted_sum = 0.0
    weight_total = 0.0

    async with httpx.AsyncClient(timeout=10) as client:
        for cap in CAPABILITIES:
            probes = [await _probe(client, p) for p in cap["probes"]]
            passed = sum(1 for p in probes if p["ok"])
            score = passed / max(len(probes), 1)
            weighted_sum += score * cap["weight"]
            weight_total += cap["weight"]
            results.append({
                "key": cap["key"], "name": cap["name"], "section": cap["section"],
                "weight": cap["weight"], "score": round(score, 3),
                "passed": passed, "total": len(probes), "probes": probes,
                "status": "live" if score == 1 else ("partial" if score > 0 else "down"),
            })

        # engine coverage — fold in the coverage report's own overall_percent
        cov_score = 0.0
        cov_detail = {}
        try:
            cr = await client.get(_BASE + "/api/gameforge/coverage")
            if cr.status_code == 200:
                data = cr.json()
                cov_score = float(data.get("overall_percent", 0)) / 100.0
                cov_detail = {"overall_percent": data.get("overall_percent"),
                              "engines": data.get("engines"),
                              "subsystem_count": data.get("subsystem_count")}
        except Exception:  # noqa: BLE001
            cov_score = 0.0
    weighted_sum += cov_score * _ENGINE_COVERAGE["weight"]
    weight_total += _ENGINE_COVERAGE["weight"]
    results.append({
        "key": _ENGINE_COVERAGE["key"], "name": _ENGINE_COVERAGE["name"],
        "section": _ENGINE_COVERAGE["section"], "weight": _ENGINE_COVERAGE["weight"],
        "score": round(cov_score, 3), "passed": 1 if cov_score > 0 else 0, "total": 1,
        "detail": cov_detail,
        "status": "live" if cov_score >= 0.95 else ("partial" if cov_score > 0 else "down"),
    })

    overall = round((weighted_sum / max(weight_total, 1)) * 100, 1)
    live = sum(1 for r in results if r["status"] == "live")
    return {
        "ok": True,
        "product": "PROOD",
        "overall_percent": overall,
        "capabilities_live": live,
        "capabilities_total": len(results),
        "capabilities": results,
        "generated_at": time.time(),
    }


# ─────────────────────────────────────────────────────────────────────
# Saga orchestration (real build → register → deliver, with compensation)
# ─────────────────────────────────────────────────────────────────────
class SagaDemoRequest(BaseModel):
    project_name: str = "ProodSagaDemo"
    fail_at: Optional[str] = None   # None | "build" | "register" | "deliver"


@router.post("/saga/deploy")
async def saga_deploy(req: SagaDemoRequest):
    """Run the PROOD deployment saga: build → register → deliver. Pass
    `fail_at` to inject a failure and prove automatic compensation (rollback
    in reverse) — a registered package is deleted on rollback."""
    builder = create_internal_build_system(req.project_name)

    async def _build(ctx):
        if req.fail_at == "build":
            raise RuntimeError("injected build failure")
        b = builder.build_game({"project": req.project_name, "systems": {"demo": {}}}, phase="saga")
        await event_bus.publish("saga.build.ok", {"project": req.project_name})
        return {"_bundle": b["bundle_bytes"], "package_name": b["package_name"],
                "signature": b["signature"], "architectures": b["architectures"]}

    async def _register(ctx):
        if req.fail_at == "register":
            raise RuntimeError("injected register failure")
        pkg = jeeves_vault.register(
            project_name=req.project_name, package_name=ctx["package_name"],
            package_bytes=ctx["_bundle"], quality=0.9,
            architectures=ctx["architectures"], signature=ctx["signature"],
            metadata={"kind": "saga_demo"},
        )
        await event_bus.publish("saga.register.ok", {"package_id": pkg["package_id"]})
        return {"package_id": pkg["package_id"], "download_path": pkg["download_path"]}

    async def _unregister(ctx):
        # compensation for register: remove the package
        if ctx.get("package_id"):
            jeeves_vault.delete(ctx["package_id"])
            await event_bus.publish("saga.register.compensated", {"package_id": ctx["package_id"]})
        return {"package_id": None, "rolled_back": True}

    async def _deliver(ctx):
        if req.fail_at == "deliver":
            raise RuntimeError("injected deliver failure")
        return {"delivered": True, "download_path": ctx.get("download_path")}

    saga_orchestrator.register_saga("prood_deploy", [
        SagaStep("build", _build),
        SagaStep("register", _register, compensate=_unregister),
        SagaStep("deliver", _deliver),
    ])
    result = await saga_orchestrator.execute_saga("prood_deploy")
    data = result.to_dict()
    # strip raw bytes from context before returning
    data["context"].pop("_bundle", None)
    data["context"].pop("signature", None)
    return {"ok": result.status in ("completed", "compensated"), **data}


@router.get("/events")
async def events():
    """PROOD EventBus stats + recent event history (observability)."""
    return {"ok": True, **event_bus.stats()}
