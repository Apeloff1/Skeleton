"""
🎨 COVERS & SHARE CARDS — AI concept-art covers (Nano Banana) + branded share PNG.

Extracted from routes/playable.py (Session 12 monolith decomposition). Generates,
caches, serves and lets a creator pick cover art for a playable, plus renders a
1080² branded share card. Shares the Mongo handle with routes.playable; all routes
use deeper paths (/{pid}/cover…, /{pid}/cover.png, /{pid}/card.png) so they never
shadow the GET /{pid} catch-all in routes.playable.
"""
from __future__ import annotations

import os
import uuid
import base64
import asyncio

from fastapi import APIRouter, Query
from fastapi.responses import Response
from pydantic import BaseModel

from routes.playable import _db
from routes.llm_router import EMERGENT_LLM_KEY

router = APIRouter(prefix="/api/playable", tags=["playable"])


# ── VI.3 Creator Marketplace: AI concept-art cover thumbnails (Nano Banana) ──
async def _generate_cover_b64(title: str, genre: str, brief: str) -> str | None:
    """Generate ONE square concept-art cover for a game via Gemini Nano Banana.
    Returns a base64 PNG string (no data: prefix) or None on failure."""
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    from core.render_quality import PHOTOREAL_SUFFIX, upscale_b64
    if not EMERGENT_LLM_KEY:
        return None
    prompt = (
        f"Square key art / cover splash for a browser arcade game titled '{title}'. "
        f"Genre: {genre}. Concept: {brief[:300]}. Bold vibrant colors, dramatic cinematic "
        "lighting, polished game-marketing splash-screen style, dynamic central focal subject, "
        "rich depth. No text, no words, no logos, no watermark, no UI." + PHOTOREAL_SUFFIX
    )
    try:
        chat = (LlmChat(api_key=EMERGENT_LLM_KEY, session_id=f"cover-{uuid.uuid4().hex[:8]}",
                        system_message="You are a AAA game concept artist creating cover key art.")
                .with_model("gemini", "gemini-3.1-flash-image-preview")
                .with_params(modalities=["image", "text"]))
        _text, images = await asyncio.wait_for(
            chat.send_message_multimodal_response(UserMessage(text=prompt)), timeout=60)
        if images and images[0].get("data"):
            return upscale_b64(images[0]["data"])
    except Exception:
        return None
    return None


@router.post("/{pid}/cover")
async def make_cover(pid: str, force: bool = Query(False)):
    """Lazily generate (and cache) a Nano-Banana concept-art cover for a game.
    Idempotent by default; pass ?force=true to REGENERATE fresh art."""
    doc = await _db.playables.find_one(
        {"playable_id": pid}, {"_id": 0, "title": 1, "genre": 1, "brief": 1, "has_cover": 1})
    if not doc:
        return {"error": "not found"}
    if doc.get("has_cover") and not force:
        return {"playable_id": pid, "has_cover": True, "cached": True}
    b64 = await _generate_cover_b64(doc.get("title", ""), doc.get("genre", ""), doc.get("brief", ""))
    if not b64:
        return {"playable_id": pid, "has_cover": bool(doc.get("has_cover")), "error": "cover generation failed"}
    await _db.playables.update_one({"playable_id": pid}, {"$set": {"cover_b64": b64, "has_cover": True}})
    return {"playable_id": pid, "has_cover": True, "cached": False, "regenerated": bool(force)}


@router.post("/{pid}/cover/options")
async def cover_options(pid: str, count: int = Query(3, ge=2, le=3)):
    """🎨 Generate `count` (2-3) alternative cover-art options for a game so the
    creator can pick a favourite. Stored in `cover_options`; serve each via
    GET /{pid}/cover/opt/{idx}.png, then choose one with POST /{pid}/cover/select."""
    doc = await _db.playables.find_one(
        {"playable_id": pid}, {"_id": 0, "title": 1, "genre": 1, "brief": 1})
    if not doc:
        return {"error": "not found"}
    results = await asyncio.gather(*[
        _generate_cover_b64(doc.get("title", ""), doc.get("genre", ""), doc.get("brief", ""))
        for _ in range(count)
    ], return_exceptions=True)
    options = [r for r in results if isinstance(r, str) and r]
    if not options:
        return {"playable_id": pid, "count": 0, "error": "cover generation failed"}
    await _db.playables.update_one({"playable_id": pid}, {"$set": {"cover_options": options}})
    return {"playable_id": pid, "count": len(options),
            "options": list(range(len(options)))}


class CoverSelectBody(BaseModel):
    index: int = 0


@router.post("/{pid}/cover/select")
async def cover_select(pid: str, body: CoverSelectBody):
    """Pick one of the generated cover options as the game's primary cover."""
    doc = await _db.playables.find_one({"playable_id": pid}, {"_id": 0, "cover_options": 1})
    opts = (doc or {}).get("cover_options") or []
    if not doc:
        return {"error": "not found"}
    if body.index < 0 or body.index >= len(opts):
        return {"error": "index out of range", "available": len(opts)}
    await _db.playables.update_one(
        {"playable_id": pid}, {"$set": {"cover_b64": opts[body.index], "has_cover": True}})
    return {"playable_id": pid, "has_cover": True, "selected": body.index}


@router.get("/{pid}/cover/opt/{idx}.png")
async def get_cover_option(pid: str, idx: int):
    """Serve one generated cover OPTION as raw image/png (404 if none)."""
    doc = await _db.playables.find_one({"playable_id": pid}, {"_id": 0, "cover_options": 1})
    opts = (doc or {}).get("cover_options") or []
    if idx < 0 or idx >= len(opts):
        return Response(status_code=404)
    try:
        raw = base64.b64decode(opts[idx])
    except Exception:
        return Response(status_code=404)
    return Response(content=raw, media_type="image/png",
                    headers={"Cache-Control": "public, max-age=3600"})


@router.get("/{pid}/cover.png")
async def get_cover(pid: str):
    """Serve a game's cover as raw image/png (404 if none yet)."""
    doc = await _db.playables.find_one({"playable_id": pid}, {"_id": 0, "cover_b64": 1})
    if not doc or not doc.get("cover_b64"):
        return Response(status_code=404)
    try:
        raw = base64.b64decode(doc["cover_b64"])
    except Exception:
        return Response(status_code=404)
    return Response(content=raw, media_type="image/png",
                    headers={"Cache-Control": "public, max-age=86400"})


_FONT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "fonts")


def _font(bold: bool, size: int):
    from PIL import ImageFont
    try:
        return ImageFont.truetype(os.path.join(_FONT_DIR, "VeraBd.ttf" if bold else "Vera.ttf"), size)
    except Exception:
        return ImageFont.load_default()


def _wrap(draw, text, font, max_w, max_lines=2):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=font) <= max_w:
            cur = t
        else:
            lines.append(cur); cur = w
            if len(lines) == max_lines:
                break
    if cur and len(lines) < max_lines:
        lines.append(cur)
    if len(lines) == max_lines and draw.textlength(lines[-1], font=font) > max_w:
        while lines[-1] and draw.textlength(lines[-1] + "…", font=font) > max_w:
            lines[-1] = lines[-1][:-1]
        lines[-1] += "…"
    return lines


@router.get("/{pid}/card.png")
async def share_card(pid: str):
    """Branded share card: cover art + title + score + Galaxy Studio mark (1080²)."""
    from PIL import Image, ImageDraw
    import io
    doc = await _db.playables.find_one(
        {"playable_id": pid},
        {"_id": 0, "cover_b64": 1, "title": 1, "genre": 1, "playability_score": 1, "evaluation.overall": 1})
    if not doc:
        return Response(status_code=404)
    SZ = 1080
    # base: cover art, or a deep gradient if none yet
    base = None
    if doc.get("cover_b64"):
        try:
            base = Image.open(io.BytesIO(base64.b64decode(doc["cover_b64"]))).convert("RGB").resize((SZ, SZ))
        except Exception:
            base = None
    if base is None:
        base = Image.new("RGB", (SZ, SZ), (12, 12, 28))
        gd = ImageDraw.Draw(base)
        for y in range(SZ):
            t = y / SZ
            gd.line([(0, y), (SZ, y)], fill=(int(20 + 30 * t), int(16 + 20 * t), int(40 + 50 * t)))
    # bottom scrim for legibility
    scrim = Image.new("RGBA", (SZ, SZ), (0, 0, 0, 0))
    sd = ImageDraw.Draw(scrim)
    for y in range(int(SZ * 0.5), SZ):
        a = int(235 * ((y - SZ * 0.5) / (SZ * 0.5)) ** 1.3)
        sd.line([(0, y), (SZ, y)], fill=(5, 6, 14, min(a, 235)))
    img = Image.alpha_composite(base.convert("RGBA"), scrim)
    d = ImageDraw.Draw(img)
    # title (bottom-left, up to 2 lines)
    tfont = _font(True, 70)
    lines = _wrap(d, doc.get("title", "Untitled Game"), tfont, SZ - 120, 2)
    y = SZ - 110 - len(lines) * 84
    for ln in lines:
        d.text((60, y), ln, font=tfont, fill=(253, 230, 138)); y += 84
    # genre + brand
    d.text((62, y + 4), (doc.get("genre", "") or "arcade").upper(), font=_font(False, 30), fill=(148, 163, 184))
    d.text((62, SZ - 52), "▲ GALAXY STUDIO", font=_font(True, 30), fill=(251, 191, 36))
    # score badge (top-right)
    score = (doc.get("evaluation") or {}).get("overall") or doc.get("playability_score") or 0
    bf = _font(True, 64)
    label = f"{score}"
    tw = d.textlength(label, font=bf)
    bw, bx, by = tw + 110, SZ - (tw + 110) - 48, 48
    d.rounded_rectangle([bx, by, bx + bw, by + 96], radius=24, fill=(251, 191, 36))
    d.text((bx + 28, by + 14), "★", font=bf, fill=(58, 46, 16))
    d.text((bx + 28 + d.textlength("★ ", font=bf), by + 14), label, font=bf, fill=(58, 46, 16))
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png",
                    headers={"Cache-Control": "public, max-age=3600"})
