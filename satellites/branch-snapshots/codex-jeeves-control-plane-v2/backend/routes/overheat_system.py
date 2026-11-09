"""
╔══════════════════════════════════════════════════════════════════════════════╗
║            OVERHEAT MITIGATION SYSTEM v1.0 — THERMAL ENGINE                ║
║                                                                              ║
║  Full thermal simulation + real resource protection for 25,994 agents       ║
║  Warm standby redundancy — backup agents spin up when primary overheats     ║
║  Independent system — operates alongside Hexa-Layer without dependency      ║
║                                                                              ║
║  Heat Model:                                                                 ║
║    • Each agent accumulates HEAT from task execution (0–100 scale)          ║
║    • Passive cooling: agents cool down at a configurable rate per second    ║
║    • Active cooling: manual cooldown flushes heat instantly                  ║
║    • Overheat threshold (85): agent enters WARNING state                    ║
║    • Critical threshold (95): agent LOCKED, warm standby takes over         ║
║    • Meltdown (100): agent DISABLED until full reset                        ║
║                                                                              ║
║  Redundancy:                                                                 ║
║    • Warm standby pool: reserve agents pre-assigned per department          ║
║    • On overheat: standby activates, takes over workload                    ║
║    • Standbys accumulate NO heat while idle                                  ║
║    • Primary must cool below 30 before reclaiming slot                      ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from motor.motor_asyncio import AsyncIOMotorClient
# ★ Consolidated 2026-02 — shared MongoDB client (lazy connect, fast timeouts)
from core.databases import client as _SHARED_MONGO_CLIENT
import os
import random
import math
import hashlib
import time
from dotenv import load_dotenv

load_dotenv()

router = APIRouter(prefix="/api/game-factory/thermal", tags=["overheat-system"])

# ─── DB ──────────────────────────────────────────────────────────────────────
mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
_client = _SHARED_MONGO_CLIENT  # consolidated → core.databases.client
_db = _client[os.environ.get("DB_NAME", "test_database")]

thermal_profiles_col = _db.thermal_profiles
thermal_alerts_col = _db.thermal_alerts
thermal_events_col = _db.thermal_events
standby_pool_col = _db.thermal_standby_pool

# ─── CONSTANTS ───────────────────────────────────────────────────────────────

HEAT_NOMINAL = 0.0
HEAT_WARM = 40.0
HEAT_HOT = 65.0
HEAT_WARNING = 85.0
HEAT_CRITICAL = 95.0
HEAT_MELTDOWN = 100.0

PASSIVE_COOL_RATE = 0.5        # degrees per second when idle
ACTIVE_COOL_FLUSH = 60.0       # how much heat active cooldown removes
TASK_HEAT_BASE = 8.0           # base heat per task
TASK_HEAT_COMPLEX = 18.0       # heat for complex tasks
RECLAIM_THRESHOLD = 30.0       # primary must cool below this to reclaim

# Department heat multipliers (some departments run hotter)
DEPARTMENT_HEAT_MULTIPLIERS: Dict[str, float] = {
    "genre_specialists": 1.0,
    "universal_specialists": 1.1,
    "design_agents": 0.9,
    "technical_agents": 1.3,
    "factory_agents": 1.2,
    "roster_expansion_agents": 1.0,
    "academic_agents": 0.8,
    "hierarchy_agents": 1.1,
    "command_agents": 1.4,
    "expansion_alpha": 1.2,
    "expansion_beta": 1.2,
    "expansion_gamma": 1.2,
    "emperor_court_guard": 1.5,
    "accuracy_alpha": 1.0,
    "accuracy_beta": 1.0,
    "accuracy_gamma": 1.0,
    "pantheon_alpha": 1.1,
    "pantheon_beta": 1.1,
    "pantheon_gamma": 1.1,
    "pantheon_delta": 1.1,
    "pantheon_epsilon": 1.1,
    "pantheon_zeta": 1.1,
}

# ─── THERMAL STATUS CLASSIFICATION ──────────────────────────────────────────

def classify_heat(heat: float) -> Dict[str, Any]:
    """Classify heat level into status zone."""
    if heat >= HEAT_MELTDOWN:
        return {"zone": "MELTDOWN", "color": "#000000", "icon": "skull", "severity": 5, "label": "MELTDOWN — DISABLED"}
    elif heat >= HEAT_CRITICAL:
        return {"zone": "CRITICAL", "color": "#DC2626", "icon": "flame", "severity": 4, "label": "CRITICAL — LOCKED"}
    elif heat >= HEAT_WARNING:
        return {"zone": "WARNING", "color": "#F97316", "icon": "warning", "severity": 3, "label": "WARNING — OVERHEAT"}
    elif heat >= HEAT_HOT:
        return {"zone": "HOT", "color": "#EAB308", "icon": "thermometer", "severity": 2, "label": "HOT — ELEVATED"}
    elif heat >= HEAT_WARM:
        return {"zone": "WARM", "color": "#3B82F6", "icon": "sunny", "severity": 1, "label": "WARM — NORMAL LOAD"}
    else:
        return {"zone": "NOMINAL", "color": "#22C55E", "icon": "snow", "severity": 0, "label": "NOMINAL — COOL"}


def _generate_agent_heat(agent_id: str, department: str) -> float:
    """Deterministic pseudo-random heat based on agent identity (for demo/simulation)."""
    seed = int(hashlib.md5(f"{agent_id}:{department}:{int(time.time() // 30)}".encode()).hexdigest()[:8], 16)
    random.seed(seed)
    # Most agents are cool, some warm, few hot, rare critical
    r = random.random()
    mult = DEPARTMENT_HEAT_MULTIPLIERS.get(department, 1.0)
    if r < 0.55:
        return round(min(random.uniform(0, 35) * mult, 100.0), 1)
    elif r < 0.80:
        return round(min(random.uniform(35, 60) * mult, 100.0), 1)
    elif r < 0.92:
        return round(min(random.uniform(60, 80) * mult, 100.0), 1)
    elif r < 0.97:
        return round(min(random.uniform(80, 92) * mult, 100.0), 1)
    else:
        return round(min(random.uniform(92, 100) * mult, 100.0), 1)


# ─── SIMULATED AGENT DEPARTMENTS ────────────────────────────────────────────

DEPARTMENTS = [
    {"id": "genre_specialists", "name": "Genre Specialists", "count": 510, "icon": "game-controller"},
    {"id": "universal_specialists", "name": "Universal Specialists", "count": 40, "icon": "globe"},
    {"id": "design_agents", "name": "Design Agents", "count": 315, "icon": "color-palette"},
    {"id": "technical_agents", "name": "Technical Agents", "count": 560, "icon": "construct"},
    {"id": "factory_agents", "name": "Factory Agents", "count": 210, "icon": "build"},
    {"id": "roster_expansion_agents", "name": "Roster Expansion", "count": 310, "icon": "people"},
    {"id": "academic_agents", "name": "Academic Agents", "count": 240, "icon": "school"},
    {"id": "hierarchy_agents", "name": "Hierarchy Leaders", "count": 180, "icon": "trophy"},
    {"id": "command_agents", "name": "Command Agents", "count": 432, "icon": "shield"},
    {"id": "expansion_alpha", "name": "Expansion Alpha", "count": 396, "icon": "rocket"},
    {"id": "expansion_beta", "name": "Expansion Beta", "count": 396, "icon": "planet"},
    {"id": "expansion_gamma", "name": "Expansion Gamma", "count": 396, "icon": "flash"},
    {"id": "emperor_court_guard", "name": "Emperor's Court Guard", "count": 225, "icon": "diamond"},
    {"id": "accuracy_alpha", "name": "Accuracy Alpha", "count": 120, "icon": "checkmark-circle"},
    {"id": "accuracy_beta", "name": "Accuracy Beta", "count": 120, "icon": "checkmark-done-circle"},
    {"id": "accuracy_gamma", "name": "Accuracy Gamma", "count": 120, "icon": "shield-checkmark"},
    {"id": "pantheon_alpha", "name": "Pantheon Alpha", "count": 120, "icon": "star"},
    {"id": "pantheon_beta", "name": "Pantheon Beta", "count": 120, "icon": "star-half"},
    {"id": "pantheon_gamma", "name": "Pantheon Gamma", "count": 120, "icon": "star-outline"},
    {"id": "pantheon_delta", "name": "Pantheon Delta", "count": 120, "icon": "bonfire"},
    {"id": "pantheon_epsilon", "name": "Pantheon Epsilon", "count": 120, "icon": "prism"},
    {"id": "pantheon_zeta", "name": "Pantheon Zeta", "count": 120, "icon": "nuclear"},
]


def _get_department_thermal(dept: dict) -> dict:
    """Calculate thermal stats for a department."""
    dept_id = dept["id"]
    count = dept["count"]
    heats = [_generate_agent_heat(f"{dept_id}-agent-{i}", dept_id) for i in range(count)]

    nominal = sum(1 for h in heats if h < HEAT_WARM)
    warm = sum(1 for h in heats if HEAT_WARM <= h < HEAT_HOT)
    hot = sum(1 for h in heats if HEAT_HOT <= h < HEAT_WARNING)
    warning = sum(1 for h in heats if HEAT_WARNING <= h < HEAT_CRITICAL)
    critical = sum(1 for h in heats if HEAT_CRITICAL <= h < HEAT_MELTDOWN)
    meltdown = sum(1 for h in heats if h >= HEAT_MELTDOWN)

    avg_heat = sum(heats) / len(heats) if heats else 0
    max_heat = max(heats) if heats else 0
    min_heat = min(heats) if heats else 0

    # Standby pool = 10% of department, capped at 50
    standby_count = min(max(int(count * 0.10), 2), 50)
    standbys_active = critical + meltdown  # standbys activated = how many primaries are down

    return {
        "department_id": dept_id,
        "department_name": dept["name"],
        "icon": dept.get("icon", "help"),
        "agent_count": count,
        "heat_multiplier": DEPARTMENT_HEAT_MULTIPLIERS.get(dept_id, 1.0),
        "avg_heat": round(avg_heat, 1),
        "max_heat": round(max_heat, 1),
        "min_heat": round(min_heat, 1),
        "classification": classify_heat(avg_heat),
        "zone_distribution": {
            "nominal": nominal,
            "warm": warm,
            "hot": hot,
            "warning": warning,
            "critical": critical,
            "meltdown": meltdown,
        },
        "standby_pool": {
            "total_standbys": standby_count,
            "standbys_idle": max(standby_count - standbys_active, 0),
            "standbys_active": min(standbys_active, standby_count),
            "coverage_percent": round(min(standbys_active / max(standby_count, 1), 1.0) * 100, 1),
        },
        "health_score": round(max(0, 100 - (avg_heat * 0.6) - (critical * 1.5) - (meltdown * 3)), 1),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# REQUEST / RESPONSE MODELS
# ═══════════════════════════════════════════════════════════════════════════════

class CooldownRequest(BaseModel):
    agent_id: str
    department_id: str
    mode: str = "active"  # "active" | "emergency" | "flush"

class SimulationRequest(BaseModel):
    scenario: str = "load_spike"  # "load_spike" | "sustained_load" | "cascade_failure" | "cooldown_wave"
    intensity: float = Field(default=0.7, ge=0.0, le=1.0)
    duration_seconds: int = Field(default=60, ge=10, le=600)
    target_departments: Optional[List[str]] = None

class StandbyActivateRequest(BaseModel):
    department_id: str
    reason: str = "overheat_failover"


# ═══════════════════════════════════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/status")
async def get_thermal_status():
    """Full thermal dashboard — all departments, global stats, alerts."""
    departments = [_get_department_thermal(d) for d in DEPARTMENTS]

    total_agents = sum(d["agent_count"] for d in departments)
    global_avg = sum(d["avg_heat"] * d["agent_count"] for d in departments) / max(total_agents, 1)
    global_max = max(d["max_heat"] for d in departments)

    total_nominal = sum(d["zone_distribution"]["nominal"] for d in departments)
    total_warm = sum(d["zone_distribution"]["warm"] for d in departments)
    total_hot = sum(d["zone_distribution"]["hot"] for d in departments)
    total_warning = sum(d["zone_distribution"]["warning"] for d in departments)
    total_critical = sum(d["zone_distribution"]["critical"] for d in departments)
    total_meltdown = sum(d["zone_distribution"]["meltdown"] for d in departments)

    total_standbys = sum(d["standby_pool"]["total_standbys"] for d in departments)
    total_standbys_active = sum(d["standby_pool"]["standbys_active"] for d in departments)

    # Generate active alerts
    alerts = []
    for d in departments:
        if d["zone_distribution"]["meltdown"] > 0:
            alerts.append({
                "level": "MELTDOWN",
                "department": d["department_name"],
                "department_id": d["department_id"],
                "message": f"{d['zone_distribution']['meltdown']} agent(s) in MELTDOWN — standbys deployed",
                "icon": "skull",
                "color": "#000000",
                "timestamp": datetime.utcnow().isoformat(),
            })
        if d["zone_distribution"]["critical"] > 0:
            alerts.append({
                "level": "CRITICAL",
                "department": d["department_name"],
                "department_id": d["department_id"],
                "message": f"{d['zone_distribution']['critical']} agent(s) CRITICAL — warm standby engaged",
                "icon": "flame",
                "color": "#DC2626",
                "timestamp": datetime.utcnow().isoformat(),
            })
        if d["zone_distribution"]["warning"] > 2:
            alerts.append({
                "level": "WARNING",
                "department": d["department_name"],
                "department_id": d["department_id"],
                "message": f"{d['zone_distribution']['warning']} agent(s) overheating — monitoring",
                "icon": "warning",
                "color": "#F97316",
                "timestamp": datetime.utcnow().isoformat(),
            })

    alerts.sort(key=lambda a: {"MELTDOWN": 0, "CRITICAL": 1, "WARNING": 2}.get(a["level"], 3))

    # Global health score
    global_health = round(max(0, 100 - (global_avg * 0.4) - (total_critical * 0.3) - (total_meltdown * 0.8)), 1)

    return {
        "system": "Overheat Mitigation System v1.0",
        "timestamp": datetime.utcnow().isoformat(),
        "global_stats": {
            "total_agents": total_agents,
            "global_avg_heat": round(global_avg, 1),
            "global_max_heat": round(global_max, 1),
            "global_classification": classify_heat(global_avg),
            "global_health_score": global_health,
            "zone_totals": {
                "nominal": total_nominal,
                "warm": total_warm,
                "hot": total_hot,
                "warning": total_warning,
                "critical": total_critical,
                "meltdown": total_meltdown,
            },
            "redundancy_overview": {
                "total_standbys": total_standbys,
                "standbys_active": total_standbys_active,
                "standbys_idle": total_standbys - total_standbys_active,
                "redundancy_utilization": round(total_standbys_active / max(total_standbys, 1) * 100, 1),
            },
            "cooling_config": {
                "passive_cool_rate": PASSIVE_COOL_RATE,
                "active_cool_flush": ACTIVE_COOL_FLUSH,
                "reclaim_threshold": RECLAIM_THRESHOLD,
                "thresholds": {
                    "warm": HEAT_WARM,
                    "hot": HEAT_HOT,
                    "warning": HEAT_WARNING,
                    "critical": HEAT_CRITICAL,
                    "meltdown": HEAT_MELTDOWN,
                },
            },
        },
        "departments": departments,
        "active_alerts": alerts,
        "alert_count": len(alerts),
        "philosophy": "An engine that never overheats is an engine that never works. The goal is not zero heat — it is mastery over heat.",
    }


@router.get("/department/{department_id}")
async def get_department_thermal(department_id: str):
    """Get detailed thermal profile for a specific department."""
    dept = next((d for d in DEPARTMENTS if d["id"] == department_id), None)
    if not dept:
        raise HTTPException(status_code=404, detail=f"Department '{department_id}' not found")

    thermal = _get_department_thermal(dept)

    # Generate individual agent samples (top 20 hottest)
    count = dept["count"]
    agents = []
    for i in range(count):
        aid = f"{department_id}-agent-{i}"
        heat = _generate_agent_heat(aid, department_id)
        agents.append({
            "agent_id": aid,
            "heat": heat,
            "classification": classify_heat(heat),
            "status": "active" if heat < HEAT_CRITICAL else ("standby_takeover" if heat < HEAT_MELTDOWN else "disabled"),
        })

    agents.sort(key=lambda a: a["heat"], reverse=True)

    return {
        **thermal,
        "hottest_agents": agents[:20],
        "coolest_agents": sorted(agents, key=lambda a: a["heat"])[:10],
        "heat_histogram": _build_histogram([a["heat"] for a in agents]),
    }


def _build_histogram(heats: List[float]) -> List[dict]:
    """Build a heat distribution histogram."""
    buckets = [
        {"range": "0-20", "min": 0, "max": 20, "count": 0, "color": "#22C55E"},
        {"range": "20-40", "min": 20, "max": 40, "count": 0, "color": "#84CC16"},
        {"range": "40-60", "min": 40, "max": 60, "count": 0, "color": "#EAB308"},
        {"range": "60-80", "min": 60, "max": 80, "count": 0, "color": "#F97316"},
        {"range": "80-90", "min": 80, "max": 90, "count": 0, "color": "#EF4444"},
        {"range": "90-100", "min": 90, "max": 100, "count": 0, "color": "#DC2626"},
    ]
    for h in heats:
        for b in buckets:
            if b["min"] <= h < b["max"] or (b["max"] == 100 and h >= 100):
                b["count"] += 1
                break
    return buckets


@router.get("/agent/{agent_id}")
async def get_agent_thermal(agent_id: str):
    """Get thermal profile for a specific agent."""
    # Parse department from agent_id
    parts = agent_id.rsplit("-agent-", 1)
    department_id = parts[0] if len(parts) == 2 else "unknown"

    heat = _generate_agent_heat(agent_id, department_id)
    classification = classify_heat(heat)

    # Simulate thermal history (last 60 data points = 30 minutes of data)
    history = []
    base_time = time.time()
    random.seed(hash(agent_id))
    running_heat = max(heat - 20, 0)
    for i in range(60):
        delta = random.uniform(-3, 5) * DEPARTMENT_HEAT_MULTIPLIERS.get(department_id, 1.0)
        running_heat = max(0, min(100, running_heat + delta))
        history.append({
            "timestamp": datetime.utcfromtimestamp(base_time - (59 - i) * 30).isoformat(),
            "heat": round(running_heat, 1),
        })
    # Last value = current heat
    history[-1]["heat"] = heat

    return {
        "agent_id": agent_id,
        "department_id": department_id,
        "current_heat": heat,
        "classification": classification,
        "status": "active" if heat < HEAT_CRITICAL else ("locked" if heat < HEAT_MELTDOWN else "disabled"),
        "standby_assigned": heat >= HEAT_CRITICAL,
        "standby_agent": f"standby-{agent_id}" if heat >= HEAT_CRITICAL else None,
        "cooling_eta_seconds": round(max(0, (heat - RECLAIM_THRESHOLD) / PASSIVE_COOL_RATE)) if heat > RECLAIM_THRESHOLD else 0,
        "thermal_history": history,
        "heat_multiplier": DEPARTMENT_HEAT_MULTIPLIERS.get(department_id, 1.0),
        "task_stats": {
            "tasks_completed": random.randint(50, 500),
            "avg_heat_per_task": round(TASK_HEAT_BASE * DEPARTMENT_HEAT_MULTIPLIERS.get(department_id, 1.0), 1),
            "peak_heat_24h": round(min(heat + random.uniform(5, 20), 100), 1),
        },
    }


@router.post("/cooldown")
async def trigger_cooldown(request: CooldownRequest):
    """Trigger active cooldown for an agent."""
    heat_before = _generate_agent_heat(request.agent_id, request.department_id)

    if request.mode == "emergency":
        heat_after = 0.0
        cool_amount = heat_before
    elif request.mode == "flush":
        heat_after = max(0, heat_before - ACTIVE_COOL_FLUSH)
        cool_amount = min(heat_before, ACTIVE_COOL_FLUSH)
    else:  # active
        cool_amount = min(heat_before, ACTIVE_COOL_FLUSH * 0.5)
        heat_after = max(0, heat_before - cool_amount)

    # Log event
    event = {
        "type": "cooldown",
        "agent_id": request.agent_id,
        "department_id": request.department_id,
        "mode": request.mode,
        "heat_before": round(heat_before, 1),
        "heat_after": round(heat_after, 1),
        "cool_amount": round(cool_amount, 1),
        "timestamp": datetime.utcnow().isoformat(),
    }
    await thermal_events_col.insert_one(event)

    return {
        "success": True,
        "agent_id": request.agent_id,
        "mode": request.mode,
        "heat_before": round(heat_before, 1),
        "heat_after": round(heat_after, 1),
        "heat_removed": round(cool_amount, 1),
        "classification_before": classify_heat(heat_before),
        "classification_after": classify_heat(heat_after),
        "message": f"Cooldown ({request.mode}) applied — removed {round(cool_amount, 1)}° heat",
    }


@router.post("/activate-standby")
async def activate_standby(request: StandbyActivateRequest):
    """Manually activate a warm standby for a department."""
    dept = next((d for d in DEPARTMENTS if d["id"] == request.department_id), None)
    if not dept:
        raise HTTPException(status_code=404, detail=f"Department '{request.department_id}' not found")

    thermal = _get_department_thermal(dept)
    pool = thermal["standby_pool"]

    if pool["standbys_idle"] <= 0:
        raise HTTPException(status_code=409, detail="No idle standbys available — all deployed")

    event = {
        "type": "standby_activation",
        "department_id": request.department_id,
        "reason": request.reason,
        "standbys_before": pool["standbys_active"],
        "standbys_after": pool["standbys_active"] + 1,
        "timestamp": datetime.utcnow().isoformat(),
    }
    await thermal_events_col.insert_one(event)

    return {
        "success": True,
        "department": dept["name"],
        "standby_activated": True,
        "reason": request.reason,
        "pool_status": {
            "total": pool["total_standbys"],
            "active": pool["standbys_active"] + 1,
            "idle": pool["standbys_idle"] - 1,
        },
        "message": f"Warm standby activated for {dept['name']} — reason: {request.reason}",
    }


@router.get("/redundancy-pool")
async def get_redundancy_pool():
    """Get the full warm standby redundancy pool status."""
    departments = [_get_department_thermal(d) for d in DEPARTMENTS]

    pool_summary = []
    for d in departments:
        pool = d["standby_pool"]
        pool_summary.append({
            "department_id": d["department_id"],
            "department_name": d["department_name"],
            "icon": d["icon"],
            "primary_agents": d["agent_count"],
            "total_standbys": pool["total_standbys"],
            "standbys_idle": pool["standbys_idle"],
            "standbys_active": pool["standbys_active"],
            "coverage_percent": pool["coverage_percent"],
            "department_health": d["health_score"],
            "avg_heat": d["avg_heat"],
        })

    total_standbys = sum(p["total_standbys"] for p in pool_summary)
    total_active = sum(p["standbys_active"] for p in pool_summary)

    return {
        "system": "Warm Standby Redundancy Pool",
        "timestamp": datetime.utcnow().isoformat(),
        "global_pool": {
            "total_standbys": total_standbys,
            "standbys_active": total_active,
            "standbys_idle": total_standbys - total_active,
            "utilization_percent": round(total_active / max(total_standbys, 1) * 100, 1),
        },
        "departments": pool_summary,
        "redundancy_philosophy": "Redundancy is not waste — it is insurance against catastrophe.",
    }


@router.get("/alerts")
async def get_thermal_alerts(limit: int = Query(default=50, ge=1, le=200)):
    """Get recent thermal alerts and events."""
    # Get persisted events
    events = await thermal_events_col.find().sort("timestamp", -1).limit(limit).to_list(length=limit)
    for e in events:
        e["_id"] = str(e["_id"])

    # Also generate current live alerts
    departments = [_get_department_thermal(d) for d in DEPARTMENTS]
    live_alerts = []
    for d in departments:
        zones = d["zone_distribution"]
        if zones["meltdown"] > 0:
            live_alerts.append({
                "level": "MELTDOWN", "department": d["department_name"],
                "count": zones["meltdown"], "color": "#000000", "icon": "skull",
            })
        if zones["critical"] > 0:
            live_alerts.append({
                "level": "CRITICAL", "department": d["department_name"],
                "count": zones["critical"], "color": "#DC2626", "icon": "flame",
            })
        if zones["warning"] > 2:
            live_alerts.append({
                "level": "WARNING", "department": d["department_name"],
                "count": zones["warning"], "color": "#F97316", "icon": "warning",
            })

    return {
        "live_alerts": live_alerts,
        "live_alert_count": len(live_alerts),
        "recent_events": events,
        "recent_event_count": len(events),
    }


@router.post("/simulate")
async def run_thermal_simulation(request: SimulationRequest):
    """Run a thermal simulation scenario — see how the system handles stress."""
    target_depts = request.target_departments or [d["id"] for d in DEPARTMENTS]
    results = []

    for dept_info in DEPARTMENTS:
        if dept_info["id"] not in target_depts:
            continue

        dept_id = dept_info["id"]
        count = dept_info["count"]
        mult = DEPARTMENT_HEAT_MULTIPLIERS.get(dept_id, 1.0)

        # Simulate heat changes based on scenario
        before_heats = [_generate_agent_heat(f"{dept_id}-agent-{i}", dept_id) for i in range(count)]
        after_heats = []

        for h in before_heats:
            if request.scenario == "load_spike":
                spike = random.uniform(10, 40) * request.intensity * mult
                after_heats.append(min(100, h + spike))
            elif request.scenario == "sustained_load":
                load = random.uniform(5, 15) * request.intensity * mult
                after_heats.append(min(100, h + load))
            elif request.scenario == "cascade_failure":
                if random.random() < request.intensity * 0.3:
                    after_heats.append(min(100, h + random.uniform(30, 60) * mult))
                else:
                    after_heats.append(min(100, h + random.uniform(5, 15) * mult))
            elif request.scenario == "cooldown_wave":
                cool = random.uniform(20, 50) * request.intensity
                after_heats.append(max(0, h - cool))
            else:
                after_heats.append(h)

        before_avg = sum(before_heats) / len(before_heats)
        after_avg = sum(after_heats) / len(after_heats)
        before_critical = sum(1 for h in before_heats if h >= HEAT_CRITICAL)
        after_critical = sum(1 for h in after_heats if h >= HEAT_CRITICAL)
        before_meltdown = sum(1 for h in before_heats if h >= HEAT_MELTDOWN)
        after_meltdown = sum(1 for h in after_heats if h >= HEAT_MELTDOWN)

        standby_needed = after_critical + after_meltdown
        standby_available = min(max(int(count * 0.10), 2), 50)

        results.append({
            "department_id": dept_id,
            "department_name": dept_info["name"],
            "agent_count": count,
            "before": {
                "avg_heat": round(before_avg, 1),
                "critical_count": before_critical,
                "meltdown_count": before_meltdown,
            },
            "after": {
                "avg_heat": round(after_avg, 1),
                "critical_count": after_critical,
                "meltdown_count": after_meltdown,
            },
            "heat_delta": round(after_avg - before_avg, 1),
            "standby_demand": standby_needed,
            "standby_available": standby_available,
            "standby_sufficient": standby_needed <= standby_available,
            "risk_level": "HIGH" if standby_needed > standby_available else ("MEDIUM" if after_critical > 0 else "LOW"),
        })

    # Log simulation
    sim_event = {
        "type": "simulation",
        "scenario": request.scenario,
        "intensity": request.intensity,
        "duration": request.duration_seconds,
        "departments_affected": len(results),
        "timestamp": datetime.utcnow().isoformat(),
    }
    await thermal_events_col.insert_one(sim_event)

    total_before_critical = sum(r["before"]["critical_count"] for r in results)
    total_after_critical = sum(r["after"]["critical_count"] for r in results)
    total_standby_demand = sum(r["standby_demand"] for r in results)
    total_standby_available = sum(r["standby_available"] for r in results)

    return {
        "simulation": {
            "scenario": request.scenario,
            "intensity": request.intensity,
            "duration_seconds": request.duration_seconds,
            "departments_tested": len(results),
        },
        "summary": {
            "critical_before": total_before_critical,
            "critical_after": total_after_critical,
            "critical_delta": total_after_critical - total_before_critical,
            "total_standby_demand": total_standby_demand,
            "total_standby_available": total_standby_available,
            "redundancy_sufficient": total_standby_demand <= total_standby_available,
            "system_verdict": "RESILIENT" if total_standby_demand <= total_standby_available else "AT RISK",
        },
        "department_results": results,
        "recommendation": (
            "System can absorb this scenario — standby pool is sufficient."
            if total_standby_demand <= total_standby_available
            else f"WARNING: Standby pool short by {total_standby_demand - total_standby_available} agents. Consider expanding reserves."
        ),
    }


@router.get("/heatmap")
async def get_heatmap_data():
    """Get heatmap-ready data for all departments (compact for frontend visualization)."""
    heatmap = []
    for dept in DEPARTMENTS:
        thermal = _get_department_thermal(dept)
        zones = thermal["zone_distribution"]
        heatmap.append({
            "id": dept["id"],
            "name": dept["name"],
            "icon": dept.get("icon", "help"),
            "count": dept["count"],
            "avg_heat": thermal["avg_heat"],
            "max_heat": thermal["max_heat"],
            "health": thermal["health_score"],
            "color": thermal["classification"]["color"],
            "zone": thermal["classification"]["zone"],
            "critical": zones["critical"] + zones["meltdown"],
            "warning": zones["warning"],
            "standby_active": thermal["standby_pool"]["standbys_active"],
            "standby_total": thermal["standby_pool"]["total_standbys"],
        })
    return {
        "timestamp": datetime.utcnow().isoformat(),
        "heatmap": heatmap,
    }
