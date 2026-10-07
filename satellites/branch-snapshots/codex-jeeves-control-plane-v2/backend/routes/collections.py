"""
VI.3 Creator Marketplace — Collections / Playlists.

Curate a set of generated games into a named, shareable bundle. No identity layer
yet, so collections are global (anyone can create / curate) — an MVP-friendly
shared shelf. Game metadata is hydrated from the shared `playables` collection.
"""
from __future__ import annotations

import os
import base64
import uuid
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Query, Response
from pydantic import BaseModel, Field

from core.databases import client as _SHARED_MONGO_CLIENT

router = APIRouter(prefix="/api/collections", tags=["collections"])
_db = _SHARED_MONGO_CLIENT[os.environ.get("DB_NAME", "test_database")]

_GAME_LIGHT = {
    "_id": 0, "playable_id": 1, "title": 1, "genre": 1, "has_cover": 1,
    "plays": 1, "evaluation.overall": 1,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _hydrate(ids: List[str]) -> dict:
    """Fetch light metadata for a set of playable ids, keyed by id."""
    if not ids:
        return {}
    docs = await _db.playables.find(
        {"playable_id": {"$in": ids}}, _GAME_LIGHT).to_list(len(ids))
    return {d["playable_id"]: d for d in docs}


def _game_row(d: dict) -> dict:
    return {
        "playable_id": d.get("playable_id"), "title": d.get("title"),
        "genre": d.get("genre"), "has_cover": bool(d.get("has_cover")),
        "plays": d.get("plays", 0) or 0,
        "overall": (d.get("evaluation") or {}).get("overall"),
    }


class CollectionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=400)


class GameRef(BaseModel):
    playable_id: str


@router.post("")
async def create_collection(body: CollectionCreate):
    """Create a new (empty) collection."""
    cid = uuid.uuid4().hex
    doc = {
        "collection_id": cid, "name": body.name.strip(),
        "description": body.description.strip(), "game_ids": [],
        "created_at": _now(), "updated_at": _now(),
    }
    await _db.collections.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


@router.get("")
async def list_collections(limit: int = Query(50, le=100)):
    """List collections (newest first) with a small cover preview per bundle."""
    docs = await _db.collections.find({}, {"_id": 0}).sort("updated_at", -1).limit(limit).to_list(limit)
    preview_ids = [gid for d in docs for gid in (d.get("game_ids") or [])[:3]]
    metas = await _hydrate(list(dict.fromkeys(preview_ids)))
    out = []
    for d in docs:
        gids = d.get("game_ids") or []
        out.append({
            "collection_id": d.get("collection_id"), "name": d.get("name"),
            "description": d.get("description", ""), "count": len(gids),
            "preview": [_game_row(metas[g]) for g in gids[:3] if g in metas],
            "updated_at": d.get("updated_at"),
        })
    return {"collections": out, "count": len(out)}


@router.get("/{cid}")
async def get_collection(cid: str):
    """Fetch a collection with its games hydrated (in curated order)."""
    d = await _db.collections.find_one({"collection_id": cid}, {"_id": 0})
    if not d:
        return {"error": "not found"}
    gids = d.get("game_ids") or []
    metas = await _hydrate(gids)
    d["games"] = [_game_row(metas[g]) for g in gids if g in metas]
    d["count"] = len(d["games"])
    return d


@router.post("/{cid}/games")
async def add_game(cid: str, body: GameRef):
    """Add a game to a collection (idempotent; appends to the end).
    Returns added=False when the game was already in the collection."""
    coll = await _db.collections.find_one({"collection_id": cid}, {"_id": 0, "game_ids": 1})
    if not coll:
        return {"error": "collection not found"}
    game = await _db.playables.find_one({"playable_id": body.playable_id}, {"_id": 0, "playable_id": 1})
    if not game:
        return {"error": "game not found"}
    already = body.playable_id in (coll.get("game_ids") or [])
    await _db.collections.update_one(
        {"collection_id": cid},
        {"$addToSet": {"game_ids": body.playable_id}, "$set": {"updated_at": _now()}})
    return {"collection_id": cid, "playable_id": body.playable_id, "added": not already}


@router.delete("/{cid}/games/{pid}")
async def remove_game(cid: str, pid: str):
    """Remove a game from a collection."""
    res = await _db.collections.update_one(
        {"collection_id": cid},
        {"$pull": {"game_ids": pid}, "$set": {"updated_at": _now()}})
    if res.matched_count == 0:
        return {"error": "not found"}
    return {"collection_id": cid, "playable_id": pid, "removed": res.modified_count > 0}


@router.delete("/{cid}")
async def delete_collection(cid: str):
    """Delete a collection entirely."""
    res = await _db.collections.delete_one({"collection_id": cid})
    return {"collection_id": cid, "deleted": res.deleted_count > 0}


_FONT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "fonts")


def _font(bold: bool, size: int):
    from PIL import ImageFont
    try:
        return ImageFont.truetype(os.path.join(_FONT_DIR, "VeraBd.ttf" if bold else "Vera.ttf"), size)
    except Exception:
        return ImageFont.load_default()


@router.get("/{cid}/card.png")
async def collection_card(cid: str):
    """🔗 Branded share card for a whole collection: a 2×2 cover montage + name +
    game count + Galaxy Studio mark (1080²). One-tap shareable."""
    from PIL import Image, ImageDraw
    import io
    coll = await _db.collections.find_one({"collection_id": cid}, {"_id": 0, "name": 1, "game_ids": 1})
    if not coll:
        return Response(status_code=404)
    gids = (coll.get("game_ids") or [])[:4]
    covers = []
    if gids:
        docs = await _db.playables.find(
            {"playable_id": {"$in": gids}}, {"_id": 0, "playable_id": 1, "cover_b64": 1}).to_list(4)
        by_id = {d["playable_id"]: d for d in docs}
        for gid in gids:
            covers.append((by_id.get(gid) or {}).get("cover_b64"))
    SZ, H = 1080, 540  # montage occupies the top portion
    img = Image.new("RGB", (SZ, SZ), (10, 12, 24))
    # 2×2 montage tiles
    tiles = [(0, 0), (SZ // 2, 0), (0, H // 2), (SZ // 2, H // 2)]
    for i, (tx, ty) in enumerate(tiles):
        tile = None
        b64 = covers[i] if i < len(covers) else None
        if b64:
            try:
                tile = Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB").resize((SZ // 2, H // 2))
            except Exception:
                tile = None
        if tile is None:
            tile = Image.new("RGB", (SZ // 2, H // 2), (22 + i * 6, 18, 44))
        img.paste(tile, (tx, ty))
    d = ImageDraw.Draw(img)
    # gradient panel under the text
    for y in range(H, SZ):
        t = (y - H) / (SZ - H)
        d.line([(0, y), (SZ, y)], fill=(int(12 + 8 * t), int(10 + 6 * t), int(26 + 14 * t)))
    d.text((60, H + 50), "📚 COLLECTION", font=_font(True, 34), fill=(192, 132, 252))
    name = (coll.get("name") or "Untitled")[:48]
    d.text((60, H + 110), name, font=_font(True, 76), fill=(255, 255, 255))
    n = len(coll.get("game_ids") or [])
    d.text((60, H + 220), f"{n} game{'' if n == 1 else 's'} · curated on Galaxy Studio",
           font=_font(False, 34), fill=(148, 163, 184))
    d.text((60, SZ - 70), "▲ GALAXY STUDIO", font=_font(True, 34), fill=(251, 191, 36))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png",
                    headers={"Cache-Control": "public, max-age=600"})
