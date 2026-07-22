"""
🎮 ARTWIRE — inject Asset-Genesis art into a playable so the game RENDERS it.

The final link of the pipeline: Asset Genesis produces real sprites/backgrounds; this
module retrofits them into a generated game's HTML so the running game actually draws
them (player/enemy/item sprites + scene background) instead of primitive shapes.

How it stays reliable + cheap on tokens:
  1. The LLM only sees the ORIGINAL (small) game HTML + the list of available asset
     KEYS — never the multi-MB base64 (so the prompt stays tiny). It rewires the
     render code to draw from the preloaded `window.GENESIS_IMAGES[key]` Image objects,
     with `.complete` fallbacks so the game never breaks while art loads.
  2. We then DETERMINISTICALLY inject the real data-URI registry
     (`window.GENESIS_ASSETS` / `window.GENESIS_IMAGES`) into <head>.
  3. Persist only if the result stays runnable (version++, edit_trail kind='artwire').

Shares the codegen helpers + Mongo handle with routes.playable.
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
from routes.asset_genesis import recompute_asset_status
from routes.playable_htmlutils import inject_into_head

router = APIRouter(prefix="/api/playable", tags=["playable"])

# render-relevant kinds + the JS key we expose them under (character → player alias)
_KEY_ALIAS = {"character": "player"}
_RENDER_KINDS = ("character", "enemy", "item", "prop", "background", "tileset")

_ARTWIRE_SYS = _GAME_SYS + (
    "\n\nYou are in ART-WIRE MODE on an existing, working HTML5 game. Real sprite/background "
    "images are preloaded globally as HTMLImageElement objects on `window.GENESIS_IMAGES` "
    "(keys given below). Rewire the game's RENDER code so it DRAWS these images with "
    "ctx.drawImage(...) in place of the primitive shapes for the matching entities (e.g. the "
    "player ship/character, enemies, collectible items), scaled to each entity's existing size "
    "and centered on its position. If a 'background' key exists, draw it as the full-canvas "
    "backdrop each frame (before entities). ALWAYS guard each draw with "
    "`var im=window.GENESIS_IMAGES&&window.GENESIS_IMAGES[KEY]; if(im&&im.complete&&im.naturalWidth) "
    "{ctx.drawImage(...)} else {/* keep the original shape as fallback */}` so the game still "
    "works while art loads or if a key is missing. Do NOT inline any image data — only reference "
    "window.GENESIS_IMAGES. Preserve ALL gameplay, controls, collision, scoring and balance. "
    "Keep it a single self-contained runnable HTML file. Return the FULL updated HTML document.")


def _asset_registry_script(assets: dict[str, str]) -> str:
    """Build the deterministic <script> that defines the real data-URI registry +
    preloads Image objects under window.GENESIS_IMAGES."""
    import json
    payload = json.dumps(assets)
    return (
        "<script id=\"__genesis_assets\">"
        f"window.GENESIS_ASSETS={payload};"
        "window.GENESIS_IMAGES={};(function(){var A=window.GENESIS_ASSETS,I=window.GENESIS_IMAGES;"
        "for(var k in A){try{var im=new Image();im.src=A[k];I[k]=im;}catch(e){}}})();"
        "</script>"
    )


def _inject_registry(html: str, script: str) -> str:
    return inject_into_head(html, script)


async def _collect_assets(pid: str, selected: dict | None = None) -> tuple[dict[str, str], list[dict]]:
    """Latest asset per render-kind for this game → {js_key: data_uri}, + descriptions.
    `selected` optionally pins a specific asset_id per kind when multiple exist."""
    rows = await _db.asset_genesis.find(
        {"game_id": pid},
        {"_id": 0, "asset_id": 1, "kind": 1, "b64": 1, "mime": 1, "description": 1, "created_at": 1},
    ).sort("created_at", -1).to_list(60)
    selected = selected or {}
    latest: dict[str, dict] = {}
    for r in rows:
        k = r.get("kind")
        if k not in _RENDER_KINDS:
            continue
        # honour an explicit per-kind selection; otherwise keep the most recent
        if selected.get(k):
            if r.get("asset_id") == selected[k]:
                latest[k] = r
        elif k not in latest:
            latest[k] = r
    # if a selection id wasn't found, fall back to most-recent for that kind
    for k in _RENDER_KINDS:
        if selected.get(k) and k not in latest:
            for r in rows:
                if r.get("kind") == k:
                    latest[k] = r
                    break
    assets: dict[str, str] = {}
    descs: list[dict] = []
    for k, r in latest.items():
        js_key = _KEY_ALIAS.get(k, k)
        assets[js_key] = f"data:{r.get('mime', 'image/png')};base64,{r['b64']}"
        descs.append({"key": js_key, "kind": k, "description": (r.get("description") or "")[:80]})
    return assets, descs


async def _do_artwire(pid: str, selected: dict | None = None) -> dict:
    doc = await _db.playables.find_one({"playable_id": pid}, {"_id": 0})
    if not doc or not doc.get("html"):
        return {"error": "not found", "applied": False}
    assets, descs = await _collect_assets(pid, selected)
    if not assets:
        return {"playable_id": pid, "applied": False,
                "error": "no generated assets linked to this game yet"}
    prev_score = int(doc.get("playability_score") or 0)
    base_html = doc["html"]
    key_lines = "\n".join(f"  - window.GENESIS_IMAGES['{d['key']}']  ({d['kind']}: {d['description']})"
                          for d in descs)
    prompt = (
        f"ORIGINAL BRIEF:\n{doc.get('brief', '')}\n\n"
        f"AVAILABLE PRELOADED ART (HTMLImageElement objects):\n{key_lines}\n\n"
        "Rewire the render code to draw these images for the matching entities (and the "
        "background if present), with .complete guards + shape fallbacks as instructed. "
        f"Return the FULL updated single-file HTML:\n{base_html[:16000]}"
    )
    try:
        routed = await asyncio.to_thread(_llm_in_thread, prompt, _ARTWIRE_SYS, _GAME_ENSEMBLE)
    except Exception:
        return {"playable_id": pid, "applied": False, "error": "artwire model unavailable"}
    new_html, removed = _sanitize(_extract_html(routed.get("content", "")))
    val = _validate(new_html)
    floor = max(PLAYABILITY_THRESHOLD, prev_score - 15)
    if not new_html or val["score"] < floor:
        return {"playable_id": pid, "applied": False, "score": val["score"],
                "missing": val.get("missing", []), "prev_score": prev_score}
    # deterministically inject the real data-URI registry
    final_html = inject_into_head(new_html, _asset_registry_script(assets))
    trail = doc.get("edit_trail") or []
    trail.append({"n": len(trail) + 1, "kind": "artwire",
                  "instruction": f"wired {len(assets)} asset(s): {', '.join(assets.keys())}",
                  "score": val["score"], "model": routed.get("model"),
                  "at": datetime.now(timezone.utc).isoformat()})
    version = int(doc.get("version") or 1) + 1
    await _db.playables.update_one({"playable_id": pid}, {"$set": {
        "html": final_html, "bytes": len(final_html), "status": "ready",
        "playability_score": val["score"], "intricacy": val.get("intricacy"),
        "edit_trail": trail, "version": version, "sanitized": removed,
        "has_genesis_art": True, "edited_at": datetime.now(timezone.utc).isoformat(),
    }})
    await recompute_asset_status(pid)
    return {"playable_id": pid, "applied": True, "kind": "artwire", "version": version,
            "applied_keys": list(assets.keys()), "score": val["score"],
            "raw_path": f"/api/playable/{pid}/raw"}


class ArtwireBody(BaseModel):
    selected: dict[str, str] | None = None  # optional {kind: asset_id} per-slot pin


@router.post("/{pid}/apply-assets/async")
async def apply_assets_async(pid: str, body: ArtwireBody | None = None):
    """🎮 Retrofit this game with its linked Asset-Genesis art so it RENDERS the
    sprites/background. Optional body {selected:{kind:asset_id}} pins a specific asset
    per slot. Async; poll /job/{job_id} (result carries applied, applied_keys, version)."""
    from core.anti_farm import allow
    if not allow(f"artwire:{pid}", rate_per_sec=0.2, burst=4):
        return {"error": "rate_limited", "detail": "Too many art-apply runs on this game — slow down."}
    base = await _db.playables.find_one(
        {"playable_id": pid}, {"_id": 0, "playable_id": 1, "html": 1})
    if not base or not base.get("html"):
        return {"error": "not found"}
    selected = (body.selected if body else None) or None
    assets, _ = await _collect_assets(pid, selected)
    if not assets:
        return {"error": "no generated assets linked to this game yet"}
    job_id = uuid.uuid4().hex
    await _db.playable_jobs.insert_one({
        "job_id": job_id, "job_status": "running", "kind": "artwire", "parent_id": pid,
        "created_at": datetime.now(timezone.utc).isoformat()})
    asyncio.create_task(_run_job(job_id, _do_artwire(pid, selected)))
    return {"job_id": job_id, "job_status": "running", "asset_count": len(assets)}
