"""
🎨 ASSET GENESIS — real AI-generated, game-ready visual assets (Nano Banana).

Pipeline stage *Asset Genesis* (between Narrative/Mechanics Forge → Implementation):
turns a brief — optionally grounded in a game's WORLD + NARRATIVE + MECHANICS (the
"Central Game Knowledge Base") — into ACTUAL images (sprites, items, tilesets,
backgrounds, key art) with a coherent style guide so a generated game looks
consistent. Unlike routes/asset_pipeline.py (which only emits prompt specs), this
module produces real base64 PNGs and can attach them to a playable so the
Implementation stage can ship them.

Doctrine (see PRD): Nano-Banana image-gen BLOCKS the event loop inside
emergentintegrations, so every generation runs in a DAEMON THREAD (own asyncio
loop). Results are held in-memory and PERSISTED on the first /job poll that observes
completion (the poll handler runs on the main loop, so the motor `_db` is safe).
"""
from __future__ import annotations

import os
import uuid
import base64
import asyncio
import threading
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Query
from fastapi.responses import Response
from pydantic import BaseModel

from routes.playable import _db
from routes.llm_router import EMERGENT_LLM_KEY
from core.databases import client as _MONGO

router = APIRouter(prefix="/api/assets", tags=["Asset Genesis"])

_VAULT = _MONGO.codedock_vault  # bridge to the CodeDock Vault (asset entries)

# Asset kinds that make up a "complete" game skin (the AC completion target).
REQUIRED_KINDS = ["character", "enemy", "item", "background"]


async def recompute_asset_status(game_id: str) -> str:
    """Compute none|partial|complete for a game from its generated assets + applied
    flag, and PERSIST it on the playable (used by generation, apply/artwire and the
    game-status endpoint so the catalogue/leaderboard badge stays fresh)."""
    g = await _db.playables.find_one({"playable_id": game_id}, {"_id": 0, "has_genesis_art": 1})
    if not g:
        return "none"
    rows = await _db.asset_genesis.find({"game_id": game_id}, {"_id": 0, "kind": 1}).to_list(300)
    generated = {r.get("kind") for r in rows}
    missing = [k for k in REQUIRED_KINDS if k not in generated]
    if not missing and bool(g.get("has_genesis_art")):
        status = "complete"
    elif generated:
        status = "partial"
    else:
        status = "none"
    await _db.playables.update_one({"playable_id": game_id}, {"$set": {"asset_status": status}})
    return status

# ── in-memory job table (image bytes live here until persisted) ──────────────
_GEN_JOBS: dict[str, dict] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _vault_save(asset_id: str, kind: str, desc: str, b64: str, mime: str, game_id: str | None):
    """Mirror a generated asset into the CodeDock Vault (codedock_vault.assets) so it
    shows up in /vault and is reusable across games."""
    try:
        size = len(base64.b64decode(b64)) if b64 else 0
    except Exception:
        size = 0
    try:
        await _VAULT.assets.insert_one({
            "id": asset_id, "name": f"{kind}: {desc[:48]}", "description": desc,
            "asset_type": kind, "content_base64": b64, "url": None,
            "tags": ["genesis", kind] + ([game_id] if game_id else []),
            "metadata": {"source": "asset_genesis", "game_id": game_id, "mime": mime},
            "size_bytes": size, "user_id": "default_user",
            "created_at": _now(), "updated_at": _now(),
        })
    except Exception:
        pass


# ── taxonomy ─────────────────────────────────────────────────────────────────
KINDS = {
    "character": "full-body game character sprite, centered, clean readable silhouette, transparent background",
    "enemy":     "menacing enemy/monster game sprite, full body, centered, clean silhouette, transparent background",
    "item":      "single game item / pickup icon, centered, crisp, transparent background",
    "tileset":   "seamless tileable game texture, top-down, evenly lit, repeating pattern, no seams",
    "background":"wide atmospheric game background scene, parallax-ready, no UI, no characters",
    "keyart":    "dramatic cinematic cover key art / splash, dynamic central focal subject, rich depth",
    "icon":      "app/game launcher icon, single bold subject, centered, simple background",
    "prop":      "game environment prop / object, centered, transparent background",
}

STYLES = {
    "pixel":      "16-bit pixel art, limited palette, crisp pixels, retro game aesthetic",
    "flat_vector":"clean flat vector, bold shapes, smooth gradients, modern mobile-game look",
    "hand_drawn": "hand-drawn storybook illustration, soft inked outlines, painterly shading",
    "anime":      "anime / cel-shaded style, vibrant, expressive, clean linework",
    "low_poly":   "stylized low-poly 3D render, faceted geometry, soft studio lighting",
    "realistic":  "semi-realistic painted concept art, dramatic lighting, high detail",
    "neon":       "neon cyberpunk, glowing rim light, dark moody background, saturated accents",
    "claymation": "cute claymation / plasticine look, soft 3D, rounded forms",
}

PALETTES = {
    "vibrant":  "bold saturated vibrant colors",
    "pastel":   "soft pastel colors, gentle contrast",
    "dark":     "dark moody palette with bright accent highlights",
    "earthy":   "warm earthy natural tones",
    "mono":     "near-monochrome with a single accent hue",
    "candy":    "playful candy-bright colors",
}

# kinds that should be produced on a transparent background
_TRANSPARENT = {"character", "enemy", "item", "icon", "prop"}

# default coherent pack
DEFAULT_PACK = ["character", "enemy", "item", "background"]


def _style_guide(style: str, palette: str, world_ctx: str, narrative_ctx: str) -> str:
    """Deterministic style-guide block appended to every prompt so a pack stays
    visually coherent and grounded in the game's world/narrative."""
    parts = [STYLES.get(style, STYLES["flat_vector"]), PALETTES.get(palette, PALETTES["vibrant"])]
    if world_ctx:
        parts.append(f"World setting: {world_ctx[:240]}")
    if narrative_ctx:
        parts.append(f"Narrative tone: {narrative_ctx[:200]}")
    return ". ".join(parts)


def _build_prompt(kind: str, desc: str, guide: str) -> str:
    base = KINDS.get(kind, KINDS["item"])
    bg = ("Isolated on a fully transparent background (alpha), no ground shadow, no scene. "
          if kind in _TRANSPARENT else "")
    return (
        f"{base}. Subject: {desc}. Art direction: {guide}. {bg}"
        "Production-quality game asset, sharp, well-composed, no text, no words, no letters, "
        "no logos, no watermark, no UI elements, no borders."
    )


# ── nano-banana worker (runs in a daemon thread, own loop) ───────────────────
def _gen_one(prompt: str, tag: str) -> tuple[str | None, str]:
    """Blocking single-image generation. Returns (base64|None, mime)."""
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    from core.render_quality import PHOTOREAL_SUFFIX, upscale_b64

    async def _go():
        chat = (LlmChat(api_key=EMERGENT_LLM_KEY, session_id=f"asset-{tag}",
                        system_message="You are a AAA game concept artist producing clean, "
                                       "production-ready game art assets.")
                .with_model("gemini", "gemini-3.1-flash-image-preview")
                .with_params(modalities=["image", "text"]))
        return await chat.send_message_multimodal_response(UserMessage(text=prompt + PHOTOREAL_SUFFIX))

    _txt, images = asyncio.run(_go())
    if images and images[0].get("data"):
        return upscale_b64(images[0]["data"]), images[0].get("mime_type", "image/png")
    return None, "image/png"


def _single_worker(job_id: str, kind: str, desc: str, prompt: str, meta: dict):
    t0 = time.time()
    try:
        b64, mime = _gen_one(prompt, job_id[:8])
        if not b64:
            _GEN_JOBS[job_id] = {"status": "error", "error": "no image returned", "elapsed": round(time.time() - t0, 1)}
            return
        _GEN_JOBS[job_id] = {
            "status": "done", "kind": kind, "desc": desc, "prompt": prompt, "mime": mime,
            "b64": b64, "meta": meta, "elapsed": round(time.time() - t0, 1), "persisted": False,
        }
    except Exception as e:  # pragma: no cover
        _GEN_JOBS[job_id] = {"status": "error", "error": str(e), "elapsed": round(time.time() - t0, 1)}


def _pack_worker(job_id: str, kinds: list[str], desc: str, guide: str, meta: dict):
    t0 = time.time()
    items: list[dict] = []
    try:
        for k in kinds:
            subj = f"{desc} — the {k}" if k in ("character", "enemy") else f"{desc} ({k})"
            prompt = _build_prompt(k, subj, guide)
            b64, mime = _gen_one(prompt, f"{job_id[:6]}{k[:2]}")
            items.append({"kind": k, "b64": b64, "mime": mime, "prompt": prompt, "ok": bool(b64)})
            _GEN_JOBS[job_id] = {"status": "running", "done": len(items), "total": len(kinds),
                                 "items": items, "desc": desc, "meta": meta}
        ok = [i for i in items if i["ok"]]
        _GEN_JOBS[job_id] = {
            "status": "done" if ok else "error", "items": items, "desc": desc, "meta": meta,
            "done": len(items), "total": len(kinds), "elapsed": round(time.time() - t0, 1),
            "persisted": False, "error": None if ok else "all generations failed",
        }
    except Exception as e:  # pragma: no cover
        _GEN_JOBS[job_id] = {"status": "error", "error": str(e), "items": items,
                             "elapsed": round(time.time() - t0, 1)}


def _trim_jobs():
    if len(_GEN_JOBS) > 40:
        for k in list(_GEN_JOBS.keys())[:-40]:
            _GEN_JOBS.pop(k, None)


# ── request models ───────────────────────────────────────────────────────────
class GenBody(BaseModel):
    description: str
    kind: str = "character"
    style: str = "flat_vector"
    palette: str = "vibrant"
    world_context: str = ""
    narrative_context: str = ""
    game_id: str | None = None  # optional playable to ground + (later) attach to


class PackBody(BaseModel):
    description: str
    kinds: list[str] = []
    style: str = "flat_vector"
    palette: str = "vibrant"
    world_context: str = ""
    narrative_context: str = ""
    game_id: str | None = None


class LinkBody(BaseModel):
    game_id: str
    asset_ids: list[str]


# ── routes ───────────────────────────────────────────────────────────────────
@router.get("/genesis/styles")
async def genesis_styles():
    """Taxonomy for the Asset Genesis UI."""
    return {
        "kinds": [{"id": k, "hint": v} for k, v in KINDS.items()],
        "styles": [{"id": k, "hint": v} for k, v in STYLES.items()],
        "palettes": [{"id": k, "hint": v} for k, v in PALETTES.items()],
        "default_pack": DEFAULT_PACK,
    }


async def _ground(game_id: str | None, world_ctx: str, narrative_ctx: str) -> tuple[str, str, str]:
    """Pull a playable's title/genre/brief to ground the prompt (central KB link)."""
    base_desc = ""
    if game_id:
        g = await _db.playables.find_one(
            {"playable_id": game_id}, {"_id": 0, "title": 1, "genre": 1, "brief": 1})
        if g:
            base_desc = f"{g.get('title', '')} — {g.get('brief', '')}".strip(" —")
            if not world_ctx:
                world_ctx = f"{g.get('genre', 'arcade')} game world: {g.get('brief', '')[:200]}"
    return base_desc, world_ctx, narrative_ctx


@router.post("/genesis/async")
async def genesis_async(body: GenBody):
    """★ Kick a single real-image generation (returns job_id; poll /genesis/job/{id})."""
    if not EMERGENT_LLM_KEY:
        return {"error": "image generation unavailable (no key)"}
    desc = (body.description or "").strip()
    base_desc, world_ctx, narr_ctx = await _ground(body.game_id, body.world_context, body.narrative_context)
    if base_desc and base_desc not in desc:
        desc = f"{desc}. {base_desc}" if desc else base_desc
    if not desc:
        return {"error": "description required"}
    kind = body.kind if body.kind in KINDS else "character"
    guide = _style_guide(body.style, body.palette, world_ctx, narr_ctx)
    prompt = _build_prompt(kind, desc, guide)
    job_id = uuid.uuid4().hex
    _GEN_JOBS[job_id] = {"status": "pending"}
    _trim_jobs()
    meta = {"kind": kind, "style": body.style, "palette": body.palette,
            "game_id": body.game_id, "description": desc}
    threading.Thread(target=_single_worker, args=(job_id, kind, desc, prompt, meta), daemon=True).start()
    return {"job_id": job_id, "status": "pending", "kind": kind, "mode": "single"}


@router.post("/genesis/pack/async")
async def genesis_pack_async(body: PackBody):
    """★ Kick a COHERENT asset pack (player/enemy/item/background…) sharing one style guide."""
    if not EMERGENT_LLM_KEY:
        return {"error": "image generation unavailable (no key)"}
    desc = (body.description or "").strip()
    base_desc, world_ctx, narr_ctx = await _ground(body.game_id, body.world_context, body.narrative_context)
    if base_desc and base_desc not in desc:
        desc = f"{desc}. {base_desc}" if desc else base_desc
    if not desc:
        return {"error": "description required"}
    kinds = [k for k in (body.kinds or DEFAULT_PACK) if k in KINDS][:6] or DEFAULT_PACK
    guide = _style_guide(body.style, body.palette, world_ctx, narr_ctx)
    job_id = uuid.uuid4().hex
    _GEN_JOBS[job_id] = {"status": "pending", "total": len(kinds), "done": 0}
    _trim_jobs()
    meta = {"style": body.style, "palette": body.palette, "game_id": body.game_id, "description": desc}
    threading.Thread(target=_pack_worker, args=(job_id, kinds, desc, guide, meta), daemon=True).start()
    return {"job_id": job_id, "status": "pending", "kinds": kinds, "mode": "pack"}


async def _persist_single(job_id: str, j: dict) -> dict:
    aid = uuid.uuid4().hex
    doc = {
        "asset_id": aid, "kind": j["kind"], "description": j["desc"], "prompt": j["prompt"],
        "b64": j["b64"], "mime": j.get("mime", "image/png"), "meta": j.get("meta", {}),
        "game_id": (j.get("meta") or {}).get("game_id"), "created_at": _now(),
    }
    await _db.asset_genesis.insert_one(dict(doc))
    await _vault_save(aid, j["kind"], j["desc"], j["b64"], doc["mime"], doc["game_id"])
    if doc["game_id"]:
        await recompute_asset_status(doc["game_id"])
    j["persisted"] = True
    j["asset_id"] = aid
    return {"asset_id": aid, "kind": j["kind"], "mime": doc["mime"]}


async def _persist_pack(job_id: str, j: dict) -> list[dict]:
    pack_id = uuid.uuid4().hex
    out = []
    for it in j.get("items", []):
        if not it.get("ok"):
            continue
        aid = uuid.uuid4().hex
        doc = {
            "asset_id": aid, "pack_id": pack_id, "kind": it["kind"], "description": j["desc"],
            "prompt": it["prompt"], "b64": it["b64"], "mime": it.get("mime", "image/png"),
            "meta": j.get("meta", {}), "game_id": (j.get("meta") or {}).get("game_id"),
            "created_at": _now(),
        }
        await _db.asset_genesis.insert_one(dict(doc))
        await _vault_save(aid, it["kind"], j["desc"], it["b64"], doc["mime"], doc["game_id"])
        out.append({"asset_id": aid, "kind": it["kind"], "mime": doc["mime"]})
    if (j.get("meta") or {}).get("game_id"):
        await recompute_asset_status((j.get("meta") or {}).get("game_id"))
    j["persisted"] = True
    j["pack_id"] = pack_id
    j["assets"] = out
    return out


@router.get("/genesis/job/{job_id}")
async def genesis_job(job_id: str):
    """Poll a generation job. On completion the asset(s) are persisted (main loop)
    and the response carries asset ids + inline data URIs for immediate preview."""
    j = _GEN_JOBS.get(job_id)
    if not j:
        return {"error": "unknown job"}
    if j.get("status") == "done" and not j.get("persisted"):
        try:
            if "items" in j:
                await _persist_pack(job_id, j)
            else:
                await _persist_single(job_id, j)
        except Exception as e:  # pragma: no cover
            return {"job_id": job_id, "status": "error", "error": f"persist failed: {e}"}

    if "items" in j:  # pack
        assets = j.get("assets", [])
        previews = [{"kind": it["kind"], "ok": it.get("ok", False),
                     "data_uri": (f"data:{it.get('mime','image/png')};base64,{it['b64']}"
                                  if it.get("ok") and it.get("b64") else None),
                     "asset_id": next((a["asset_id"] for a in assets if a["kind"] == it["kind"]), None)}
                    for it in j.get("items", [])]
        return {"job_id": job_id, "status": j.get("status"), "mode": "pack",
                "done": j.get("done", 0), "total": j.get("total", 0),
                "pack_id": j.get("pack_id"), "items": previews,
                "elapsed": j.get("elapsed"), "error": j.get("error")}

    # single
    out = {"job_id": job_id, "status": j.get("status"), "mode": "single",
           "kind": j.get("kind"), "elapsed": j.get("elapsed"), "error": j.get("error"),
           "asset_id": j.get("asset_id")}
    if j.get("status") == "done" and j.get("b64"):
        out["data_uri"] = f"data:{j.get('mime','image/png')};base64,{j['b64']}"
    return out


@router.get("/genesis/list")
async def genesis_list(game_id: str | None = Query(None), kind: str | None = Query(None),
                       limit: int = Query(40, ge=1, le=120)):
    """Recent generated assets (light — no base64). Filter by game_id / kind."""
    q: dict = {}
    if game_id:
        q["game_id"] = game_id
    if kind:
        q["kind"] = kind
    rows = await _db.asset_genesis.find(
        q, {"_id": 0, "b64": 0, "prompt": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    return {"assets": rows, "count": len(rows)}


@router.get("/genesis/game/{game_id}")
async def genesis_game(game_id: str):
    """Load a game's files/context + its asset-generation completion status (AC tag).

    Returns grounding context (title/genre/brief/spec), the REQUIRED asset slots, which
    are already generated, whether art has been applied, and a completion tag. Also
    PERSISTS asset_status on the playable so /api/playable/list can badge it."""
    g = await _db.playables.find_one(
        {"playable_id": game_id},
        {"_id": 0, "title": 1, "genre": 1, "brief": 1, "spec_id": 1, "version": 1,
         "bytes": 1, "has_genesis_art": 1, "playability_score": 1})
    if not g:
        return {"error": "game not found"}
    rows = await _db.asset_genesis.find(
        {"game_id": game_id}, {"_id": 0, "asset_id": 1, "kind": 1, "created_at": 1}
    ).sort("created_at", -1).to_list(60)
    generated = sorted({r["kind"] for r in rows})
    missing = [k for k in REQUIRED_KINDS if k not in generated]
    applied = bool(g.get("has_genesis_art"))
    has_required = len(missing) == 0
    if has_required and applied:
        status, tag = "complete", "🎨 Assets complete"
    elif generated:
        status, tag = "partial", f"⏳ Assets {len(generated)}/{len(REQUIRED_KINDS)}"
    else:
        status, tag = "none", "○ No assets yet"
    # persist the tag on the playable for the catalogue badge
    await _db.playables.update_one({"playable_id": game_id}, {"$set": {"asset_status": status}})
    # "game files" available to ground generation
    files = [{"name": "brief.txt", "kind": "spec", "summary": (g.get("brief") or "")[:200]}]
    if g.get("spec_id"):
        files.append({"name": "design_spec", "kind": "spec", "summary": f"spec_id {g['spec_id']}"})
    files.append({"name": "game.html", "kind": "code",
                  "summary": f"v{g.get('version', 1)} · {round((g.get('bytes') or 0) / 1024, 1)} KB"})
    return {
        "game_id": game_id, "title": g.get("title", ""), "genre": g.get("genre", ""),
        "brief": g.get("brief", ""), "version": g.get("version", 1),
        "required_kinds": REQUIRED_KINDS, "generated_kinds": generated, "missing_kinds": missing,
        "applied": applied, "asset_status": status, "tag": tag,
        "assets": rows, "files": files,
    }


@router.post("/genesis/link")
async def genesis_link(body: LinkBody):
    """Attach generated assets to a playable (so the Implementation stage can ship them)."""
    g = await _db.playables.find_one({"playable_id": body.game_id}, {"_id": 0, "playable_id": 1})
    if not g:
        return {"error": "game not found"}
    res = await _db.asset_genesis.update_many(
        {"asset_id": {"$in": body.asset_ids}}, {"$set": {"game_id": body.game_id}})
    await _db.playables.update_one(
        {"playable_id": body.game_id},
        {"$addToSet": {"genesis_asset_ids": {"$each": body.asset_ids}}})
    return {"ok": True, "linked": res.modified_count, "game_id": body.game_id}


@router.get("/genesis/{asset_id}.png")
async def genesis_png(asset_id: str):
    """Serve a generated asset as raw image/png."""
    doc = await _db.asset_genesis.find_one({"asset_id": asset_id}, {"_id": 0, "b64": 1, "mime": 1})
    if not doc or not doc.get("b64"):
        return Response(status_code=404)
    try:
        raw = base64.b64decode(doc["b64"])
    except Exception:
        return Response(status_code=404)
    return Response(content=raw, media_type=doc.get("mime", "image/png"),
                    headers={"Cache-Control": "public, max-age=86400"})


@router.delete("/genesis/{asset_id}")
async def genesis_delete(asset_id: str):
    r = await _db.asset_genesis.delete_one({"asset_id": asset_id})
    return {"ok": True, "deleted": r.deleted_count}
