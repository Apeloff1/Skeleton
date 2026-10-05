"""
camera_director.py — 🎥 Cinematic Camera Director system.

Surfaces the camera_director artifact forged in the Snowball pipeline (the
`cinematics` stage, which parses the game's files + design artifacts) and turns
it into engine-ready exports plus a narrated walkthrough.

Endpoints (prefix /api/camera):
  GET  /rigs              — catalog of cinematic camera rig presets
  POST /compose/{pid}     — synchronously forge/refresh the camera director
  GET  /director/{pid}    — read the stored camera director
  GET  /export/{pid}      — engine-ready camera config (JSON)
  POST /narrate/{pid}     — voiced walkthrough of the camera plan (real HD TTS)
"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
import os

from core.databases import client as _MONGO

router = APIRouter(prefix="/api/camera", tags=["camera-director"])
_db = _MONGO[os.environ.get("DB_NAME", "test_database")]


# Cinematic rig presets the director draws from — reference catalog for the UI.
_RIGS = [
    {"id": "follow",     "type": "follow",     "label": "Follow Cam",      "fov": 60,
     "use": "Default gameplay — smoothly trails the player with lerp + deadzone."},
    {"id": "orbit",      "type": "orbit",      "label": "Orbit",           "fov": 55,
     "use": "Boss reveals & hubs — circles a target to show scale."},
    {"id": "dolly",      "type": "dolly",      "label": "Dolly Track",     "fov": 50,
     "use": "Cutscene push-ins / reveals along a fixed rail."},
    {"id": "crane",      "type": "crane",      "label": "Crane",           "fov": 45,
     "use": "Establishing shots — sweeps from high to low."},
    {"id": "pan",        "type": "pan",        "label": "Pan",             "fov": 60,
     "use": "Level intros — lateral sweep across the playfield."},
    {"id": "handheld",   "type": "handheld",   "label": "Handheld",        "fov": 65,
     "use": "Tense moments — subtle noise/shake for energy."},
    {"id": "fps",        "type": "fps",        "label": "First Person",    "fov": 90,
     "use": "Immersive first-person perspective."},
    {"id": "thirdperson","type": "thirdperson","label": "Third Person",    "fov": 65,
     "use": "Over-the-shoulder action framing."},
    {"id": "topdown",    "type": "topdown",    "label": "Top-Down",        "fov": 70,
     "use": "Strategy / twin-stick — locked overhead view."},
    {"id": "isometric",  "type": "isometric",  "label": "Isometric",       "fov": 40,
     "use": "Builders / RPGs — angled orthographic-style view."},
    {"id": "fixed",      "type": "fixed",      "label": "Fixed",           "fov": 60,
     "use": "Arcade / puzzle screens — a static, composed frame."},
]


class ComposeBody(BaseModel):
    instruction: Optional[str] = None


async def _get_director(pid: str) -> dict:
    kb = await _db.game_kb.find_one(
        {"game_id": pid}, {"_id": 0, "artifacts.camera_director": 1})
    return ((kb or {}).get("artifacts") or {}).get("camera_director") or {}


@router.get("/rigs")
async def list_rigs():
    """Catalog of cinematic camera rig presets the director composes from."""
    return {"rigs": _RIGS, "count": len(_RIGS)}


@router.post("/compose/{pid}")
async def compose(pid: str, body: ComposeBody = ComposeBody()):
    """🎬 Forge (or refresh) the cinematic camera director by parsing the game's
    files + design artifacts. Runs ASYNC (quality-gated) — returns a job_id; poll
    /api/playable/job/{job_id} (result carries ok, summary, artifact)."""
    import uuid, asyncio
    from routes.game_kb import _forge_cinematics, _stamped, _run_job, _db as _kbdb, _now
    g = await _kbdb.playables.find_one({"playable_id": pid}, {"_id": 0, "playable_id": 1})
    if not g:
        return {"ok": False, "error": "game not found"}
    note = (body.instruction or "").strip()
    job_id = uuid.uuid4().hex
    await _kbdb.playable_jobs.insert_one({
        "job_id": job_id, "job_status": "running", "kind": "forge:cinematics",
        "parent_id": pid, "created_at": _now()})
    asyncio.create_task(_run_job(job_id, _stamped(pid, "cinematics", _forge_cinematics(pid, note))))
    return {"ok": True, "job_id": job_id, "job_status": "running", "stage": "cinematics",
            "poll": f"/api/playable/job/{job_id}"}


@router.get("/director/{pid}")
async def get_director(pid: str):
    """Read the stored camera director for a game."""
    director = await _get_director(pid)
    if not director:
        return {"present": False, "director": None,
                "hint": "Run the Cinematic Camera stage in Snowball (or POST /api/camera/compose/{pid})."}
    scenes = director.get("scenes") or []
    return {
        "present": True,
        "director": director,
        "stats": {
            "rigs": len(director.get("rigs") or []),
            "scenes": len(scenes),
            "shots": sum(len(s.get("shots") or []) for s in scenes),
            "cutscenes": len(director.get("cutscenes") or []),
        },
    }


@router.get("/export/{pid}")
async def export_config(pid: str):
    """Engine-ready camera config (drop into the build's engine/netcode config)."""
    director = await _get_director(pid)
    if not director:
        return {"ok": False, "error": "no camera director — compose it first"}
    eng = director.get("engine_export") or {}
    config = {
        "schema": "galaxy.camera_director/v1",
        "fps": eng.get("fps", 60),
        "coordinate_system": eng.get("coordinate_system", "right-handed"),
        "up_axis": eng.get("up_axis", "y"),
        "global": director.get("global") or {},
        "rigs": director.get("rigs") or [],
        "scenes": director.get("scenes") or [],
        "cutscenes": director.get("cutscenes") or [],
        "transitions": director.get("transitions") or [],
    }
    return {"ok": True, "filename": f"camera_director_{pid}.json", "config": config}


@router.post("/narrate/{pid}")
async def narrate(pid: str):
    """🎙️ Voiced walkthrough of the camera plan (real HD TTS) — the director,
    read aloud like a cinematographer pitching the shot list."""
    director = await _get_director(pid)
    if not director:
        return {"ok": False, "error": "no camera director — compose it first"}
    rigs = director.get("rigs") or []
    scenes = director.get("scenes") or []
    gl = director.get("global") or {}
    lines = [f"Here is the cinematic camera plan. "
             f"The default rig is {gl.get('default_rig', 'a follow camera')}, "
             f"at a {gl.get('fov', 60) } degree field of view."]
    if rigs:
        lines.append("We use " + ", ".join(
            f"{r.get('id')} as a {r.get('type')} rig" for r in rigs[:4]) + ".")
    for s in scenes[:4]:
        shots = s.get("shots") or []
        lines.append(f"In {s.get('scene', 'the scene')}, "
                     f"{len(shots)} shots: " +
                     "; ".join(f"a {sh.get('movement', 'move')} on {sh.get('rig', 'camera')}"
                               for sh in shots[:3]) + ".")
    script = " ".join(lines)[:1200]
    try:
        from core.expressive_tts import generate_expressive_tts
        out = await generate_expressive_tts(script, tone="cinematic")
        return {"ok": True, "script": script,
                "audio_base64": out.get("audio_base64"), "format": "mp3",
                "voice": out.get("voice")}
    except Exception as e:
        return {"ok": True, "script": script, "audio_base64": None, "error": str(e)}
