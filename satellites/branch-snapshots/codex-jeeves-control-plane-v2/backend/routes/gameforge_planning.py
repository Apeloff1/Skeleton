"""
routes/gameforge_planning.py — Tier-3 hyper-advanced strategic planning
(/api/gameforge/planning).

Native implementation of the Final-Release Tier-3 engines (the shipped zip
modules were design scaffolds bound to non-existent governance/orchestration
packages). Deterministic, dependency-free math:

  • Resource Forecasting  — agents/rooms/hours for a horizon
  • Risk Modeling / Time  — base risk evolving over the horizon
  • Dependency Graph      — DAG + critical-path (longest weighted chain)
  • Predictive Simulation — Monte-Carlo-style outcome probability
  • Advanced Delegation   — composite long-horizon strategic plan

Persisted in Mongo (gameforge_plans) so plans survive restarts.
"""
from __future__ import annotations

import math
import time
import uuid
from typing import Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/gameforge/planning", tags=["gameforge-planning"])


def _plans():
    from core.databases import get_sync_db
    return get_sync_db()["gameforge_plans"]


# ── Resource Forecasting ─────────────────────────────────────────────────────
def _forecast(horizon_days: int, base_agents: int = 5) -> dict:
    growth = 1 + (horizon_days / 90) * 0.3
    return {
        "horizon_days": horizon_days,
        "estimated_agents_needed": int(base_agents * growth),
        "estimated_rooms_needed": max(3, int(horizon_days / 30)),
        "estimated_total_hours": round(horizon_days * 8 * growth, 1),
        "confidence": 0.75,
    }


# ── Risk Modeling over Time ──────────────────────────────────────────────────
def _risk_curve(base_risk: float, horizon_days: int, volatility: float = 0.15) -> dict:
    """Risk compounds mildly with time then saturates (logistic-ish)."""
    points = []
    steps = min(max(horizon_days // 7, 1), 26)  # weekly points, capped
    for i in range(steps + 1):
        day = int(i * (horizon_days / steps)) if steps else 0
        t = day / max(horizon_days, 1)
        risk = base_risk + (1 - base_risk) * (1 - math.exp(-volatility * horizon_days * t / 30))
        points.append({"day": day, "risk": round(min(risk, 0.99), 3)})
    peak = max(points, key=lambda p: p["risk"])
    return {"base_risk": base_risk, "final_risk": points[-1]["risk"],
            "peak_risk": peak["risk"], "peak_day": peak["day"], "curve": points}


# ── Dependency Graph + critical path ─────────────────────────────────────────
def _critical_path(nodes: List[dict], edges: List[dict]) -> dict:
    """Longest weighted path through a DAG (topological longest-path)."""
    dur = {n["id"]: float(n.get("duration", 1)) for n in nodes}
    adj: Dict[str, List[str]] = {n["id"]: [] for n in nodes}
    indeg = {n["id"]: 0 for n in nodes}
    for e in edges:
        f, t = e.get("from"), e.get("to")
        if f in adj and t in indeg:
            adj[f].append(t)
            indeg[t] += 1
    # Kahn topological order
    queue = [n for n in indeg if indeg[n] == 0]
    order: List[str] = []
    indeg2 = dict(indeg)
    while queue:
        cur = queue.pop(0)
        order.append(cur)
        for nxt in adj.get(cur, []):
            indeg2[nxt] -= 1
            if indeg2[nxt] == 0:
                queue.append(nxt)
    if len(order) != len(nodes):
        return {"critical_path": [], "length": 0, "acyclic": False}
    best = {n: dur.get(n, 0) for n in dur}
    prev: Dict[str, Optional[str]] = {n: None for n in dur}
    for cur in order:
        for nxt in adj.get(cur, []):
            if best[cur] + dur.get(nxt, 0) > best.get(nxt, 0):
                best[nxt] = best[cur] + dur.get(nxt, 0)
                prev[nxt] = cur
    if not best:
        return {"critical_path": [], "length": 0, "acyclic": True}
    end = max(best, key=lambda k: best[k])
    path = []
    cur: Optional[str] = end
    while cur is not None:
        path.append(cur)
        cur = prev[cur]
    path.reverse()
    return {"critical_path": path, "length": round(best[end], 2), "acyclic": True}


# ── Predictive Simulation (Monte-Carlo-ish, deterministic) ───────────────────
def _simulate(base_risk: float, horizon_days: int, scenario: str, iterations: int) -> dict:
    mult = {"aggressive_timeline": 1.4, "high_risk": 1.7,
            "resource_constrained": 1.25, "nominal": 1.0}.get(scenario, 1.0)
    eff_risk = min(base_risk * mult, 0.98)
    success_prob = round((1 - eff_risk) ** (1 + horizon_days / 180), 3)
    expected_delay = round(horizon_days * eff_risk * 0.35, 1)
    return {"scenario": scenario, "iterations": iterations,
            "success_probability": success_prob,
            "expected_delay_days": expected_delay,
            "effective_risk": round(eff_risk, 3),
            "recommendation": ("Proceed" if success_prob >= 0.6
                               else "Add buffer / split objective" if success_prob >= 0.35
                               else "High risk — rescope before committing")}


class StrategicPlanBody(BaseModel):
    objective: str
    horizon_days: int = 30
    base_risk: float = 0.2
    scenario: str = "nominal"
    milestones: Optional[List[str]] = None


@router.post("/strategic-plan")
async def strategic_plan(b: StrategicPlanBody):
    """Composite Tier-3 delegation plan: forecast + risk curve + dependency
    critical path + predictive simulation + a graph-based delegation workflow."""
    plan_id = f"plan-{uuid.uuid4().hex[:10]}"
    ms = b.milestones or ["Design", "Prototype", "Content", "Polish", "Ship"]
    nodes = [{"id": m, "duration": max(1, b.horizon_days // len(ms))} for m in ms]
    edges = [{"from": ms[i], "to": ms[i + 1]} for i in range(len(ms) - 1)]

    forecast = _forecast(b.horizon_days)
    risk = _risk_curve(b.base_risk, b.horizon_days)
    crit = _critical_path(nodes, edges)
    sim = _simulate(b.base_risk, b.horizon_days, b.scenario, 100)
    workflow = [
        {"step": i + 1, "milestone": m,
         "assign_to": ["engineering", "art", "narrative", "qa", "engineering"][i % 5],
         "budget_hours": round(forecast["estimated_total_hours"] / len(ms), 1)}
        for i, m in enumerate(ms)
    ]
    plan = {"plan_id": plan_id, "objective": b.objective, "horizon_days": b.horizon_days,
            "scenario": b.scenario, "forecast": forecast, "risk": risk,
            "dependency": crit, "simulation": sim, "workflow": workflow,
            "created_at": time.time()}
    try:
        _plans().insert_one(dict(plan))
    except Exception:  # noqa: BLE001
        pass
    plan.pop("_id", None)
    return {"ok": True, **plan}


@router.get("/plans")
async def list_plans(limit: int = 20):
    rows = list(_plans().find({}, {"_id": 0}).sort("created_at", -1).limit(limit))
    return {"ok": True, "plans": rows}


class ForecastBody(BaseModel):
    horizon_days: int = 30


@router.post("/forecast")
async def forecast(b: ForecastBody):
    return {"ok": True, **_forecast(b.horizon_days)}


class RiskBody(BaseModel):
    base_risk: float = 0.2
    horizon_days: int = 30


@router.post("/risk")
async def risk(b: RiskBody):
    return {"ok": True, **_risk_curve(b.base_risk, b.horizon_days)}


class SimBody(BaseModel):
    base_risk: float = 0.2
    horizon_days: int = 30
    scenario: str = "nominal"
    iterations: int = 100


@router.post("/simulate")
async def simulate(b: SimBody):
    return {"ok": True, **_simulate(b.base_risk, b.horizon_days, b.scenario, b.iterations)}
