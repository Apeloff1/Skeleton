"""
✏️ FINETUNE & 🐛 BUGSQUASH — precise, IN-PLACE edits to a single playable.

Extracted from routes/playable.py (Session 11 refactor). Unlike the derive modes
(which spawn a NEW child and deliberately grow scope), these EDIT the loaded game
in place: finetune = a surgical tweak that changes ONLY what's asked; bugsquash =
fix a user-described bug at its root. Both bump `version`, append to `edit_trail`,
and persist ONLY if the result stays runnable and doesn't regress >10 pts below the
prior playability score.

Shares the codegen helpers + Mongo handle with routes.playable (single source of truth).
"""
from __future__ import annotations

import uuid
import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel

from routes.playable import (
    _db, _GAME_SYS, _GAME_ENSEMBLE, PLAYABILITY_THRESHOLD,
    _sanitize, _extract_html, _validate, _llm_in_thread, _run_job,
)

router = APIRouter(prefix="/api/playable", tags=["playable"])

_FINETUNE_SYS = _GAME_SYS + (
    "\n\nYou are FINE-TUNING an existing, working game. Apply EXACTLY the requested change and "
    "NOTHING ELSE — this is surgical editing. Preserve the game's identity, art, mechanics, "
    "controls, balance, and every feature that already works; change only what the instruction "
    "asks for. Do NOT add unrelated features, do NOT rewrite from scratch, do NOT increase scope. "
    "Keep it a single, fully self-contained, runnable HTML file. Return the FULL updated HTML document.")

_BUGSQUASH_SYS = _GAME_SYS + (
    "\n\nYou are in BUGSQUASH MODE on a working game. The player reports a specific bug. Reproduce "
    "it mentally, find the ROOT CAUSE, and fix it precisely with the smallest correct change. Do NOT "
    "change unrelated gameplay, art or balance, and do NOT add features. Ensure no NEW errors are "
    "introduced and the game stays fully runnable and self-contained. Return the FULL corrected HTML document.")


class EditBody(BaseModel):
    instruction: str = ""


async def _do_edit(pid: str, mode: str, instruction: str) -> dict:
    """Precise IN-PLACE edit of one playable (mode='finetune' surgical tweak |
    'bugsquash' fix a described bug). Persists only if it stays runnable and does
    not regress >10 pts below the prior playability score."""
    doc = await _db.playables.find_one({"playable_id": pid}, {"_id": 0})
    if not doc or not doc.get("html"):
        return {"error": "not found", "edited": False}
    instr = (instruction or "").strip()
    if len(instr) < 3:
        return {"error": "instruction too short (min 3 chars)", "edited": False}
    prev_score = int(doc.get("playability_score") or 0)
    base_html = doc["html"]
    if mode == "bugsquash":
        sys_prompt = _BUGSQUASH_SYS
        prompt = (f"ORIGINAL BRIEF:\n{doc.get('brief', '')}\n\n"
                  f"BUG REPORT (fix this precisely, at the root):\n  {instr}\n\n"
                  f"Keep everything else identical. Return the FULL corrected single-file HTML:\n{base_html[:16000]}")
    else:  # finetune
        sys_prompt = _FINETUNE_SYS
        prompt = (f"ORIGINAL BRIEF:\n{doc.get('brief', '')}\n\n"
                  f"REQUESTED CHANGE (apply EXACTLY this and nothing else):\n  {instr}\n\n"
                  f"Preserve everything else. Return the FULL updated single-file HTML:\n{base_html[:16000]}")
    try:
        routed = await asyncio.to_thread(_llm_in_thread, prompt, sys_prompt, _GAME_ENSEMBLE)
    except Exception:
        return {"playable_id": pid, "edited": False, "error": "edit model unavailable"}
    new_html, removed = _sanitize(_extract_html(routed.get("content", "")))
    val = _validate(new_html)
    # guard: must stay runnable AND not regress more than 10 pts below the prior score
    floor = max(PLAYABILITY_THRESHOLD, prev_score - 10)
    if not new_html or val["score"] < floor:
        return {"playable_id": pid, "edited": False, "kind": mode, "score": val["score"],
                "missing": val.get("missing", []), "prev_score": prev_score}
    trail = doc.get("edit_trail") or []
    trail.append({"n": len(trail) + 1, "kind": mode, "instruction": instr[:300],
                  "score": val["score"], "model": routed.get("model"),
                  "at": datetime.now(timezone.utc).isoformat()})
    version = int(doc.get("version") or 1) + 1
    await _db.playables.update_one({"playable_id": pid}, {"$set": {
        "html": new_html, "bytes": len(new_html), "status": "ready",
        "playability_score": val["score"], "intricacy": val.get("intricacy"),
        "edit_trail": trail, "version": version, "sanitized": removed,
        "edited_at": datetime.now(timezone.utc).isoformat(),
    }})
    out = await _db.playables.find_one({"playable_id": pid}, {"_id": 0, "html": 0})
    out["raw_path"] = f"/api/playable/{pid}/raw"
    out["edited"] = True
    out["kind"] = mode
    return out


async def _kick_edit(pid: str, mode: str, instruction: str) -> dict:
    from core.anti_farm import allow
    if not allow(f"edit:{pid}", rate_per_sec=0.2, burst=4):
        return {"error": "rate_limited", "detail": "Too many edits on this game — slow down."}
    instr = (instruction or "").strip()
    if len(instr) < 3:
        return {"error": "instruction too short (min 3 chars)"}
    base = await _db.playables.find_one({"playable_id": pid}, {"_id": 0, "playable_id": 1, "html": 1})
    if not base or not base.get("html"):
        return {"error": "not found"}
    job_id = uuid.uuid4().hex
    await _db.playable_jobs.insert_one({
        "job_id": job_id, "job_status": "running", "kind": mode, "parent_id": pid,
        "tweak": instr[:300], "created_at": datetime.now(timezone.utc).isoformat()})
    asyncio.create_task(_run_job(job_id, _do_edit(pid, mode, instr)))
    return {"job_id": job_id, "job_status": "running"}


@router.post("/{pid}/finetune/async")
async def finetune_async(pid: str, body: EditBody):
    """✏️ FINETUNE — apply a surgical, in-place tweak to this exact game (no scope
    growth). Async; poll /job/{job_id} (result carries kind='finetune', edited:bool)."""
    return await _kick_edit(pid, "finetune", body.instruction)


@router.post("/{pid}/bugsquash/async")
async def bugsquash_async(pid: str, body: EditBody):
    """🐛 BUGSQUASH — fix a user-described bug in this exact game at the root, in
    place. Async; poll /job/{job_id} (result carries kind='bugsquash', edited:bool)."""
    return await _kick_edit(pid, "bugsquash", body.instruction)
