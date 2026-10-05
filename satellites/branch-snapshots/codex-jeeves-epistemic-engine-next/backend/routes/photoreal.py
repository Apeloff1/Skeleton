"""
🖼️ PHOTOREAL — app-wide photorealistic image generation (Gemini Nano-Banana).

Reuses the proven WorldForge Nano-Banana integration (emergentintegrations + EMERGENT_LLM_KEY)
to render cinematic, photorealistic key art for ANY canon entity — character, faction, region,
creature, or the game's cover. Generated images are cached per (game_id, kind, name) so they're
reusable across the app.
"""
from __future__ import annotations

import os
import uuid
import time
import asyncio
import logging
import threading

from fastapi import APIRouter
from pydantic import BaseModel

from core.databases import client as _MONGO

router = APIRouter(prefix="/api/photoreal", tags=["photoreal"])
_db = _MONGO[os.environ.get("DB_NAME", "test_database")]
_log = logging.getLogger("photoreal")
_JOBS: dict = {}

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


def _worker(job_id: str, pid: str, kind: str, name: str, prompt: str):
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    t0 = time.time()
    try:
        key = os.environ.get("EMERGENT_LLM_KEY")

        async def _gen():
            chat = LlmChat(api_key=key, session_id=f"pr-{job_id[:8]}",
                           system_message="You generate photorealistic, cinematic, production-grade game art.")
            chat.with_model("gemini", "gemini-3.1-flash-image-preview").with_params(modalities=["image", "text"])
            return await chat.send_message_multimodal_response(UserMessage(text=prompt))

        _txt, images = asyncio.run(_gen())
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
        _log.warning("photoreal job %s failed: %s", job_id, e)
        _JOBS[job_id] = {"status": "error", "error": str(e)[:200], "elapsed": round(time.time() - t0, 1)}


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
    if len(_JOBS) > 40:
        for k in list(_JOBS.keys())[:-40]:
            _JOBS.pop(k, None)
    threading.Thread(target=_worker, args=(job_id, pid, kind, name, prompt), daemon=True).start()
    return {"job_id": job_id, "status": "pending", "kind": kind, "name": name}


@router.get("/job/{job_id}")
async def job(job_id: str):
    j = _JOBS.get(job_id)
    if not j:
        return {"error": "unknown job"}
    if j.get("status") == "done" and not j.get("saved"):
        await _db.photoreal_images.update_one(
            {"game_id": j.get("pid", ""), "kind": j["kind"], "name": j["name"]},
            {"$set": {"game_id": j.get("pid", ""), "kind": j["kind"], "name": j["name"],
                      "image": j["image"], "prompt": j.get("prompt"), "created_at": time.time()}},
            upsert=True)
        j["saved"] = True
    return {"job_id": job_id, **{k: v for k, v in j.items() if k != "prompt"}}


@router.get("/{pid}")
async def list_images(pid: str):
    """All cached photoreal images for a game (reusable across the app)."""
    docs = await _db.photoreal_images.find(
        {"game_id": pid}, {"_id": 0, "kind": 1, "name": 1, "image": 1}).to_list(length=200)
    return {"game_id": pid, "count": len(docs), "images": docs}
