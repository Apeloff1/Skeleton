"""
Per-creator Studio Preferences ("creative constitution").

Lets a creator persist durable preferences that bias every future game they
generate — preferred genres, art style, difficulty, tone, and a free-form
constitution paragraph plus hard "avoid" rules. The generation pipeline
(routes.playable) imports `preference_bias()` and appends the resulting guidance
block to the build prompt.

  GET /api/creator/preferences/{creator_id}
  PUT /api/creator/preferences/{creator_id}
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel

from core.databases import client as _SHARED_MONGO_CLIENT

router = APIRouter(prefix="/api/creator", tags=["creator-preferences"])
_db = _SHARED_MONGO_CLIENT[os.environ.get("DB_NAME", "test_database")]

ART_STYLES = ["any", "neon", "pixel", "minimal", "flat", "retro", "hand-drawn", "vaporwave", "monochrome"]
DIFFICULTIES = ["any", "chill", "balanced", "hardcore"]
TONES = ["any", "playful", "epic", "cozy", "competitive", "zen", "spooky"]

_DEFAULTS = {
    "genres": [], "art_style": "any", "difficulty": "balanced",
    "tone": "any", "constitution": "", "avoid": "",
}


class PrefsBody(BaseModel):
    genres: list[str] = []
    art_style: str = "any"
    difficulty: str = "balanced"
    tone: str = "any"
    constitution: str = ""
    avoid: str = ""


def _clean(p: dict) -> dict:
    out = {**_DEFAULTS, **{k: v for k, v in (p or {}).items() if k in _DEFAULTS}}
    out["genres"] = [str(g).strip()[:24] for g in (out.get("genres") or [])][:6]
    out["art_style"] = out["art_style"] if out["art_style"] in ART_STYLES else "any"
    out["difficulty"] = out["difficulty"] if out["difficulty"] in DIFFICULTIES else "balanced"
    out["tone"] = out["tone"] if out["tone"] in TONES else "any"
    out["constitution"] = (out.get("constitution") or "")[:600]
    out["avoid"] = (out.get("avoid") or "")[:300]
    return out


@router.get("/preferences/{creator_id}")
async def get_prefs(creator_id: str):
    doc = await _db.creator_preferences.find_one({"creator_id": creator_id}, {"_id": 0})
    prefs = _clean(doc or {})
    return {"creator_id": creator_id, "preferences": prefs,
            "options": {"art_styles": ART_STYLES, "difficulties": DIFFICULTIES, "tones": TONES},
            "has_saved": bool(doc)}


@router.put("/preferences/{creator_id}")
async def put_prefs(creator_id: str, body: PrefsBody):
    prefs = _clean(body.model_dump())
    await _db.creator_preferences.update_one(
        {"creator_id": creator_id},
        {"$set": {**prefs, "creator_id": creator_id,
                  "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True)
    return {"creator_id": creator_id, "preferences": prefs, "saved": True}


# ── Generation-bias helper (imported by routes.playable) ────────────────────
async def preference_bias(creator_id: str) -> str:
    """Return a prompt-appendable guidance block from a creator's saved prefs,
    or '' when the creator has none. Pure-additive; never overrides the brief."""
    if not creator_id:
        return ""
    doc = await _db.creator_preferences.find_one({"creator_id": creator_id}, {"_id": 0})
    if not doc:
        return ""
    p = _clean(doc)
    lines = []
    if p["genres"]:
        lines.append(f"- Favoured genres/themes: {', '.join(p['genres'])}.")
    if p["art_style"] != "any":
        lines.append(f"- Visual style: lean into a '{p['art_style']}' aesthetic.")
    if p["difficulty"] != "any":
        lines.append(f"- Difficulty feel: tune the challenge to '{p['difficulty']}'.")
    if p["tone"] != "any":
        lines.append(f"- Overall tone/mood: '{p['tone']}'.")
    if p["constitution"]:
        lines.append(f"- Creator's standing guidance: {p['constitution']}")
    if p["avoid"]:
        lines.append(f"- HARD AVOID (never include): {p['avoid']}")
    if not lines:
        return ""
    return ("\n\nCREATOR STUDIO PREFERENCES (apply unless the brief explicitly "
            "contradicts them; the brief always wins):\n" + "\n".join(lines))
