"""
🖼️ PHOTOREAL — app-wide photorealistic image generation (Gemini Nano-Banana).

Uses the canonical engine facade for cinematic key art for canon entities.
Generated images are stored per owner, tenant, game, kind and name. Unsupported
image execution remains an explicit failed job.
"""
from __future__ import annotations
from skeleton.context.instruction_policy import InstructionPolicy

import os
import uuid
import time
import asyncio
import logging

from fastapi import HTTPException
from pydantic import BaseModel

from core.databases import client as _MONGO
from routes.playable_access import (
    assert_project_access, project_identity, project_router,
    reauthorize_project_context, scoped_database,
)

router = project_router(prefix="/api/photoreal", tags=["photoreal"], local_jobs=True)
_db = scoped_database(_MONGO[os.environ.get("DB_NAME", "test_database")])
_log = logging.getLogger("photoreal")
_JOBS: dict = {}
_JOB_AUTHORITY: dict[str, dict] = {}


async def _owned_job(job_id: str) -> dict:
    identity = await reauthorize_project_context()
    authority = _JOB_AUTHORITY.get(job_id)
    row = _JOBS.get(job_id)
    if not row or not authority or authority["identity"] != identity:
        raise HTTPException(404, "Job not found")
    if authority["pid"]:
        await assert_project_access(authority["pid"])
    return row


async def _run_worker(*args):
    loop = asyncio.get_running_loop()

    def authorize():
        return asyncio.run_coroutine_threadsafe(
            reauthorize_project_context(mutate=True), loop
        ).result(timeout=30)

    await reauthorize_project_context(mutate=True)
    await asyncio.to_thread(_worker, *args, authorize=authorize)

_STYLE = {
    "character": "Photorealistic cinematic character portrait, dramatic rim lighting, shallow depth of "
                 "field, hyper-detailed skin and costume, AAA game key art, volumetric atmosphere, 8k.",
    "faction":   "Photorealistic epic banner scene for a faction — iconic emblem, soldiers/architecture, "
                 "moody cinematic lighting, blockbuster concept art, ultra-detailed, 8k.",
    "region":    "Photorealistic establishing landscape, cinematic wide shot, volumetric god-rays, rich "
                 "atmosphere, film-grade colour, ultra-detailed environment concept art, 8k.",
    "creature":  "Photorealistic menacing creature concept, anatomically detailed, dramatic lighting, wet "
                 "textures, AAA monster design, cinematic, 8k.",
    "cover":     "Photorealistic blockbuster video-game cover key art, dynamic hero composition, dramatic "
                 "lighting, premium poster, ultra-detailed, 8k, no text.",
}


def _prompt(kind: str, name: str, desc: str) -> str:
    base = _STYLE.get(kind, _STYLE["cover"])
    subj = f"Subject: {name}." + (f" Details: {desc[:400]}." if desc else "")
    return f"{subj} {base} No text, no watermark, no logo."


def _worker(job_id: str, pid: str, kind: str, name: str, prompt: str, *, authorize):
    from core.engine_chat import EngineChat, UserMessage
    t0 = time.time()
    try:
        authorize()

        async def _gen():
            identity = project_identity()
            chat = EngineChat(
                session_id=f"pr-{job_id[:8]}",
                tenant_id=identity["tenant_id"],
                actor_id=identity["owner_id"],
                data_class="confidential",
                instruction_policy=InstructionPolicy(
                    policy_id="backend.photoreal.image-generation",
                    version="1",
                    instructions=(
                        "You generate photorealistic, cinematic, "
                        "production-grade game art."
                    ),
                ),
            )
            chat.with_model("gemini", "gemini-3.1-flash-image-preview").with_params(modalities=["image", "text"])
            return await chat.send_message_multimodal_response(UserMessage(text=prompt))

        _txt, images = asyncio.run(_gen())
        authorize()
        if images:
            mime = images[0].get("mime_type", "image/png")
            data_url = f"data:{mime};base64,{images[0].get('data')}"
            _JOBS[job_id] = {"status": "done", "image": data_url, "kind": kind, "name": name,
                             "pid": pid, "prompt": prompt, "saved": False,
                             "elapsed": round(time.time() - t0, 1)}
        else:
            _JOBS[job_id] = {"status": "error", "error": "no image returned",
                             "elapsed": round(time.time() - t0, 1)}
    except Exception as e:  # noqa
        _log.warning("photoreal job %s failed: %s", job_id, type(e).__name__)
        _JOBS[job_id] = {"status": "error", "error": "photoreal_generation_failed", "elapsed": round(time.time() - t0, 1)}


class GenBody(BaseModel):
    pid: str = ""
    kind: str = "cover"
    name: str = ""
    desc: str = ""


@router.post("/generate/async")
async def generate(body: GenBody):
    """★ Kick a photoreal image job. Builds a cinematic prompt from the entity + canon; if name/desc
    are blank it falls back to the game's title/brief. Poll /api/photoreal/job/{id}."""
    pid, kind, name, desc = body.pid, body.kind, body.name.strip(), body.desc.strip()
    if not name or not desc:
        g = await _db.playables.find_one({"playable_id": pid}, {"_id": 0, "title": 1, "brief": 1})
        if g:
            name = name or g.get("title", "Untitled")
            desc = desc or (g.get("brief", "") if kind == "cover" else desc)
    prompt = _prompt(kind, name or "Untitled", desc)
    job_id = uuid.uuid4().hex
    _JOBS[job_id] = {"status": "pending"}
    _JOB_AUTHORITY[job_id] = {"identity": project_identity(), "pid": pid}
    if len(_JOBS) > 40:
        for k in list(_JOBS.keys())[:-40]:
            _JOBS.pop(k, None)
            _JOB_AUTHORITY.pop(k, None)
    asyncio.create_task(_run_worker(job_id, pid, kind, name, prompt))
    return {"job_id": job_id, "status": "pending", "kind": kind, "name": name}


@router.get("/job/{job_id}")
async def job(job_id: str):
    j = await _owned_job(job_id)
    if j.get("status") == "done" and not j.get("saved"):
        await reauthorize_project_context(mutate=True)
        await _db.photoreal_images.update_one(
            {"game_id": j.get("pid", ""), "kind": j["kind"], "name": j["name"]},
            {"$set": {"game_id": j.get("pid", ""), "kind": j["kind"], "name": j["name"],
                      "image": j["image"], "prompt": j.get("prompt"), "created_at": time.time()}},
            upsert=True)
        j["saved"] = True
    await reauthorize_project_context()
    return {"job_id": job_id, **{k: v for k, v in j.items() if k != "prompt"}}


@router.get("/{pid}")
async def list_images(pid: str):
    """All cached photoreal images for a game (reusable across the app)."""
    docs = await _db.photoreal_images.find(
        {"game_id": pid}, {"_id": 0, "kind": 1, "name": 1, "image": 1}).to_list(length=200)
    return {"game_id": pid, "count": len(docs), "images": docs}
