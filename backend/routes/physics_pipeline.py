"""
physics_pipeline.py — 🧲 Physics System pipeline.

Surfaces the physics_system artifact forged in the Snowball pipeline (the
`physics` stage, which parses the game's files + mechanics) and exports it as
engine-ready config. Includes a unified Engine Config Bundle that merges
physics + camera + mechanics into one drop-in file.

Endpoints (prefix /api/physics):
  GET  /presets           — reference catalog of physics material/body presets
  POST /compose/{pid}      — forge/refresh the physics system (async job)
  GET  /system/{pid}       — read the stored physics system
  GET  /export/{pid}       — engine-ready physics config (JSON)
  GET  /bundle/{pid}       — ⭐ unified engine bundle (physics + camera + mechanics)
"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
import os

from core.databases import client as _MONGO

router = APIRouter(prefix="/api/physics", tags=["physics-pipeline"])
_db = _MONGO[os.environ.get("DB_NAME", "test_database")]


# Reference presets the physics engineer composes from — for the UI.
_PRESETS = {
    "materials": [
        {"id": "default",  "friction": 0.5,  "restitution": 0.2, "density": 1.0,  "use": "General-purpose bodies."},
        {"id": "ice",      "friction": 0.02, "restitution": 0.1, "density": 0.9,  "use": "Slippery surfaces."},
        {"id": "rubber",   "friction": 0.9,  "restitution": 0.8, "density": 1.1,  "use": "Bouncy balls / pads."},
        {"id": "metal",    "friction": 0.4,  "restitution": 0.05,"density": 7.8,  "use": "Heavy, low-bounce objects."},
        {"id": "wood",     "friction": 0.6,  "restitution": 0.3, "density": 0.6,  "use": "Crates / platforms."},
    ],
    "body_types": [
        {"id": "static",    "use": "Immovable geometry — ground, walls."},
        {"id": "dynamic",   "use": "Fully simulated — player, projectiles, debris."},
        {"id": "kinematic", "use": "Script-driven movement, unaffected by forces — moving platforms."},
    ],
    "tuning_profiles": [
        {"id": "arcade",   "gravity_scale": 1.4, "bounce": 0.3, "use": "Snappy, responsive, slightly exaggerated."},
        {"id": "realistic","gravity_scale": 1.0, "bounce": 0.2, "use": "Grounded, physically plausible."},
        {"id": "floaty",   "gravity_scale": 0.5, "bounce": 0.5, "use": "Low-gravity, drifty (space / dreamlike)."},
        {"id": "heavy",    "gravity_scale": 1.8, "bounce": 0.05,"use": "Weighty, deliberate, momentum-driven."},
    ],
}


class ComposeBody(BaseModel):
    instruction: Optional[str] = None


async def _get_artifact(pid: str, key: str) -> dict:
    kb = await _db.game_kb.find_one(
        {"game_id": pid}, {"_id": 0, f"artifacts.{key}": 1})
    return ((kb or {}).get("artifacts") or {}).get(key) or {}


@router.get("/presets")
async def list_presets():
    """Reference physics presets (materials, body types, tuning profiles)."""
    return {"presets": _PRESETS}


@router.post("/compose/{pid}")
async def compose(pid: str, body: ComposeBody = ComposeBody()):
    """🧲 Forge (or refresh) the physics system by parsing the game's files +
    mechanics. Runs ASYNC (quality-gated) — returns a job_id; poll
    /api/playable/job/{job_id}."""
    import uuid, asyncio
    from routes.game_kb import _forge_physics, _stamped, _run_job, _db as _kbdb, _now
    g = await _kbdb.playables.find_one({"playable_id": pid}, {"_id": 0, "playable_id": 1})
    if not g:
        return {"ok": False, "error": "game not found"}
    note = (body.instruction or "").strip()
    job_id = uuid.uuid4().hex
    await _kbdb.playable_jobs.insert_one({
        "job_id": job_id, "job_status": "running", "kind": "forge:physics",
        "parent_id": pid, "created_at": _now()})
    asyncio.create_task(_run_job(job_id, _stamped(pid, "physics", _forge_physics(pid, note))))
    return {"ok": True, "job_id": job_id, "job_status": "running", "stage": "physics",
            "poll": f"/api/playable/job/{job_id}"}


@router.get("/system/{pid}")
async def get_system(pid: str):
    """Read the stored physics system for a game."""
    phys = await _get_artifact(pid, "physics_system")
    if not phys:
        return {"present": False, "system": None,
                "hint": "Run the Physics System stage in Snowball (or POST /api/physics/compose/{pid})."}
    return {
        "present": True,
        "system": phys,
        "stats": {
            "bodies": len(phys.get("bodies") or []),
            "materials": len(phys.get("materials") or []),
            "forces": len(phys.get("forces") or []),
            "constraints": len(phys.get("constraints") or []),
        },
    }


@router.get("/export/{pid}")
async def export_config(pid: str):
    """Engine-ready physics config (drop into the build's engine config)."""
    phys = await _get_artifact(pid, "physics_system")
    if not phys:
        return {"ok": False, "error": "no physics system — compose it first"}
    eng = phys.get("engine_export") or {}
    config = {
        "schema": "galaxy.physics_system/v1",
        "engine": eng.get("engine", "generic-2d3d"),
        "fps": eng.get("fps", 60),
        "units": eng.get("units", "meters"),
        "world": phys.get("world") or {},
        "materials": phys.get("materials") or [],
        "body_types": phys.get("body_types") or [],
        "bodies": phys.get("bodies") or [],
        "collisions": phys.get("collisions") or [],
        "forces": phys.get("forces") or [],
        "constraints": phys.get("constraints") or [],
        "tuning": phys.get("tuning") or {},
    }
    return {"ok": True, "filename": f"physics_system_{pid}.json", "config": config}


@router.get("/bundle/{pid}")
async def engine_bundle(pid: str):
    """⭐ Unified Engine Config Bundle — merges the physics system, camera
    director, and core mechanics into a single drop-in engine config so a build
    ships its whole runtime setup in one file."""
    phys = await _get_artifact(pid, "physics_system")
    cam = await _get_artifact(pid, "camera_director")
    mech = await _get_artifact(pid, "mechanics_config")
    present = {"physics": bool(phys), "camera": bool(cam), "mechanics": bool(mech)}
    if not any(present.values()):
        return {"ok": False, "error": "nothing to bundle — forge physics/camera/mechanics first"}
    bundle = {
        "schema": "galaxy.engine_bundle/v1",
        "game_id": pid,
        "includes": present,
        "physics": {
            "world": phys.get("world") or {},
            "materials": phys.get("materials") or [],
            "bodies": phys.get("bodies") or [],
            "forces": phys.get("forces") or [],
            "tuning": phys.get("tuning") or {},
        } if phys else None,
        "camera": {
            "global": cam.get("global") or {},
            "rigs": cam.get("rigs") or [],
            "scenes": cam.get("scenes") or [],
        } if cam else None,
        "mechanics": {
            "core_mechanics": mech.get("core_mechanics") or [],
            "balance_params": mech.get("balance_params") or {},
        } if mech else None,
    }
    return {"ok": True, "filename": f"engine_bundle_{pid}.json", "bundle": bundle}
