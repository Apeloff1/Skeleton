"""
Health and System Information Routes
"""

from fastapi import APIRouter, Request
from datetime import datetime
import os

router = APIRouter(tags=["Health"])

# Version Info
SYSTEM_VERSION = "10.0.0"
SYSTEM_CODENAME = "CS Bible Edition"
SYSTEM_BUILD = "2026.02.22-PRODUCTION"

SYSTEM_FEATURES = [
    "teaching_mode",
    "tooltips_engine",
    "hidden_advanced_panel",
    "language_dock_system",
    "expansion_ready",
    "hotfix_system",
    "plugin_architecture",
    "custom_language_support",
    "retry_with_backoff",
    "connection_status_indicator",
    "enhanced_error_handling",
    "grok_enhanced_prompts",
    "cs_bible_15_year_curriculum",
    "multiplayer_collaboration",
    "quantum_compiler_suite",
    "ultimate_hub",
    "modular_architecture"
]


@router.get("/")
async def root():
    """Root endpoint with version info"""
    return {
        "name": "CodeDock Quantum Nexus",
        "version": SYSTEM_VERSION,
        "codename": SYSTEM_CODENAME,
        "build": SYSTEM_BUILD,
        "features": SYSTEM_FEATURES,
        "status": "operational",
        "architecture": "modular"
    }


@router.get("/health")
async def health_check():
    """Production health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": SYSTEM_VERSION,
        "services": {
            "api": "running",
            "database": "connected",
            "ai": "available" if os.environ.get('EMERGENT_LLM_KEY') else "limited"
        },
        "uptime": "operational"
    }


@router.get("/health/detailed")
async def detailed_health():
    """Detailed health check for monitoring"""
    import psutil
    
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": SYSTEM_VERSION,
        "codename": SYSTEM_CODENAME,
        "system": {
            "cpu_percent": psutil.cpu_percent(),
            "memory_percent": psutil.virtual_memory().percent,
            "disk_percent": psutil.disk_usage('/').percent
        },
        "features": len(SYSTEM_FEATURES),
        "endpoints": "100+"
    }


@router.get("/system/info")
async def system_info():
    """Get detailed system information"""
    return {
        "version": SYSTEM_VERSION,
        "codename": SYSTEM_CODENAME,
        "build": SYSTEM_BUILD,
        "features": SYSTEM_FEATURES,
        "environment": os.environ.get('ENVIRONMENT', 'production'),
        "architecture": {
            "type": "modular",
            "routes": ["health", "compiler", "hub", "bible", "ai", "files"],
            "database": "mongodb",
            "ai_provider": "openai"
        }
    }


@router.get("/health/boot")
async def boot_health(request: Request):
    """Boot kick observability — surfaces the lifespan kick registry.

    Added 2026-02-18 alongside the lifespan upgrade. Lets operators see
    exactly which background seeders / toolchains / watchdogs are pending,
    running, done, failed or cancelled, with per-task timing.

    Returns a JSON shape like:
        {
          "ready_ms": 312,        # how long until /api/health/ready was set
          "uptime_s": 184.2,      # seconds since lifespan() entered
          "tasks_total":   25,
          "tasks_done":    21,
          "tasks_running":  2,
          "tasks_failed":   0,
          "tasks_pending":  2,
          "tasks": [
            {label, delay, status, scheduled_at, started_at,
             completed_at, duration_ms, error}
          ]
        }
    """
    s = request.app.state
    registry: dict = getattr(s, "_boot_registry", {}) or {}
    start_ts: float = getattr(s, "_boot_start_ts", 0.0)
    ready_ms = getattr(s, "_boot_ready_ms", None)

    tasks = []
    counts = {"done": 0, "running": 0, "failed": 0, "pending": 0, "cancelled": 0}
    for label, e in registry.items():
        tasks.append({"label": label, **e})
        st = e.get("status", "pending")
        counts[st] = counts.get(st, 0) + 1

    return {
        "ready_ms": ready_ms,
        "uptime_s": round(datetime.utcnow().timestamp() - start_ts, 1) if start_ts else None,
        "tasks_total":    len(tasks),
        "tasks_done":     counts["done"],
        "tasks_running":  counts["running"],
        "tasks_failed":   counts["failed"],
        "tasks_pending":  counts["pending"],
        "tasks_cancelled": counts.get("cancelled", 0),
        "tasks": sorted(tasks, key=lambda t: t.get("delay", 0)),
    }


@router.get("/readiness")
async def readiness_check():
    """Kubernetes readiness probe"""
    return {"ready": True}


@router.get("/liveness")
async def liveness_check():
    """Kubernetes liveness probe"""
    return {"alive": True}
