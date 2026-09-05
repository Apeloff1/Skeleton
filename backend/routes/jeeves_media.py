"""
routes/jeeves_media.py — Jeeves in-game media studio (/api/jeeves/media).

Real captured frames from the game's world:
  * POST /api/jeeves/media/images         → full image set (base64 PNGs)
  * POST /api/jeeves/media/video          → start a background render job
  * GET  /api/jeeves/media/video/{job_id} → job status + download url
  * GET  /api/jeeves/media/download/{job} → stream the finished mp4
  * GET  /api/jeeves/media/types          → available video products
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Dict, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from gameforge.media.studio import (
    GameWorld, render_image_set, produce_video, media_path, VIDEO_TYPES,
    produce_presskit, presskit_path,
)

router = APIRouter(prefix="/api/jeeves/media", tags=["jeeves-media"])

_JOBS: Dict[str, Dict] = {}

def _safe_job_id(job_id: str) -> str:
    s = str(job_id or "").strip()
    if (
        not s
        or s in {".", ".."}
        or ".." in s
        or "/" in s
        or "\\" in s
        or s.startswith(("~", "/", "\\"))
    ):
        raise HTTPException(status_code=400, detail="invalid job_id")
    return s


def _world(game_name: str) -> GameWorld:
    files = []
    try:
        from routes.gameforge_build import _gamefiles
        files = _gamefiles(game_name)
    except Exception:  # noqa: BLE001
        pass
    return GameWorld(game_name, files)


class MediaReq(BaseModel):
    game_name: str = Field(..., min_length=1)


@router.get("/types")
async def types():
    return {"ok": True, "video_types": [
        {"id": k, "duration_s": v[0], "fps": v[1], "label": v[3]} for k, v in VIDEO_TYPES.items()]}


@router.post("/images")
async def images(req: MediaReq):
    """Generate the full in-game image set: main character, cast, promos 1-10,
    landscapes 10-20 — each a REAL rendered frame of THIS game's world."""
    world = _world(req.game_name)
    imgs = await asyncio.to_thread(render_image_set, world)
    return {"ok": True, "game_name": req.game_name, "count": len(imgs), "images": imgs}


class VideoReq(BaseModel):
    game_name: str = Field(..., min_length=1)
    type: str = "clip30"


async def _run_job(job_id: str, game_name: str, vtype: str):
    prog = _JOBS[job_id]
    try:
        world = _world(game_name)
        result = await asyncio.to_thread(produce_video, world, vtype, job_id, prog)
        prog.update(result)
        prog["status"] = "done"
    except Exception as e:  # noqa: BLE001
        prog["status"] = "error"
        prog["error"] = str(e)[:300]


@router.post("/video")
async def video(req: VideoReq):
    """Start a background render of an ACTUAL-gameplay video (30s/120s/trailer/
    showcase/letsplay). Poll /video/{job_id} for progress + download."""
    if req.type not in VIDEO_TYPES:
        raise HTTPException(status_code=400, detail=f"unknown type; choose {list(VIDEO_TYPES)}")
    job_id = f"{req.game_name}-{req.type}-{uuid.uuid4().hex[:8]}".replace(" ", "_")
    _JOBS[job_id] = {"status": "rendering", "type": req.type, "game_name": req.game_name,
                     "percent": 0.0, "rendered": 0}
    asyncio.create_task(_run_job(job_id, req.game_name, req.type))
    return {"ok": True, "job_id": job_id, "status": "rendering",
            "poll": f"/api/jeeves/media/video/{job_id}"}


@router.get("/video/{job_id}")
async def video_status(job_id: str):
    job = _JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="unknown job")
    return {"ok": True, "job_id": job_id, **job}


@router.get("/download/{job_id}")
async def download(job_id: str):
    job_id = _safe_job_id(job_id)
    path = media_path(job_id)
    if not path:
        raise HTTPException(status_code=404, detail="media not ready")
    return FileResponse(path, media_type="video/mp4", filename=f"{job_id}.mp4")


# ── Press Kit — store-ready ZIP (images + trailer + showcase + fact-sheet) ──
async def _run_presskit(job_id: str, game_name: str):
    prog = _JOBS[job_id]
    try:
        world = _world(game_name)
        result = await asyncio.to_thread(produce_presskit, world, job_id, prog)
        prog.update(result); prog["status"] = "done"
    except Exception as e:  # noqa: BLE001
        prog["status"] = "error"; prog["error"] = str(e)[:300]


@router.post("/presskit")
async def presskit(req: MediaReq):
    """Assemble a store-ready press kit ZIP in the background."""
    job_id = f"{req.game_name}-presskit-{uuid.uuid4().hex[:8]}".replace(" ", "_")
    _JOBS[job_id] = {"status": "rendering", "kind": "presskit",
                     "game_name": req.game_name, "percent": 0.0, "stage": "queued"}
    asyncio.create_task(_run_presskit(job_id, req.game_name))
    return {"ok": True, "job_id": job_id, "status": "rendering",
            "poll": f"/api/jeeves/media/video/{job_id}"}


@router.get("/presskit/download/{job_id}")
async def presskit_download(job_id: str):
    job_id = _safe_job_id(job_id)
    path = presskit_path(job_id)
    if not path:
        raise HTTPException(status_code=404, detail="press kit not ready")
    return FileResponse(path, media_type="application/zip", filename=f"{job_id}_presskit.zip")
