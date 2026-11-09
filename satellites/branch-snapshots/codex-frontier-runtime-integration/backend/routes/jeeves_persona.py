"""
Jeeves Persona + Personality-aware TTS
=======================================
Exposes the persona DB + a context-aware TTS endpoint that prepends/postpends
catchphrases and selects voice/speed based on the requested context.

Endpoints:
  GET  /api/jeeves/persona            → full persona profile (cached)
  GET  /api/jeeves/persona/{key}      → single section (biography|catchphrases|…)
  GET  /api/jeeves/catchphrase?context=greeting → random phrase for context
  POST /api/jeeves/speak              → TTS with Jeeves flair wrapper
"""
import random
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
import logging

from core.databases import core_db as _db

logger = logging.getLogger("api.jeeves_persona")

router = APIRouter(prefix="/api/jeeves", tags=["Jeeves Persona + Personality TTS"])


# ─── In-memory cache so we don't hit Mongo on every catchphrase ─────────
_PERSONA_CACHE: dict = {}


async def _load_persona() -> dict:
    if _PERSONA_CACHE:
        return _PERSONA_CACHE
    try:
        async for doc in _db.jeeves_persona.find({}, {"_id": 0}):
            _PERSONA_CACHE[doc["_key"]] = doc
    except Exception as e:
        logger.warning(f"persona load failed: {e}")
    return _PERSONA_CACHE


@router.get("/persona")
async def get_persona():
    """Full Jeeves persona — biography, catchphrases, mannerisms, quirks, domains, rules."""
    p = await _load_persona()
    if not p:
        return {"error": "persona_not_seeded"}
    return {
        "biography":         p.get("biography"),
        "catchphrases":      (p.get("catchphrases") or {}).get("data"),
        "vocal_mannerisms":  (p.get("vocal_mannerisms") or {}).get("data"),
        "quirks":            (p.get("quirks") or {}).get("data"),
        "knowledge_domains": (p.get("knowledge_domains") or {}).get("data"),
        "behavioural_rules": (p.get("behavioural_rules") or {}).get("data"),
        "knowledge_database": (p.get("knowledge_database") or {}).get("data"),
        "famous_quotes":     (p.get("famous_quotes") or {}).get("data"),
        "stats": {
            "total_catchphrases":      (p.get("catchphrases") or {}).get("total_phrases", 0),
            "total_mannerisms":        (p.get("vocal_mannerisms") or {}).get("total_contexts", 0),
            "total_quirks":            (p.get("quirks") or {}).get("total_quirks", 0),
            "total_knowledge_tags":    (p.get("knowledge_domains") or {}).get("total_tags", 0),
            "total_rules":             (p.get("behavioural_rules") or {}).get("total_rules", 0),
            "total_knowledge_entries": (p.get("knowledge_database") or {}).get("total_entries", 0),
            "total_famous_quotes":     (p.get("famous_quotes") or {}).get("total_quotes", 0),
        },
    }


@router.get("/quote/random")
async def get_random_quote():
    """A random famous quote Jeeves adores."""
    p = await _load_persona()
    quotes = ((p.get("famous_quotes") or {}).get("data") or [])
    if not quotes:
        return {"error": "no_quotes_seeded"}
    return {"quote": random.choice(quotes)}


@router.get("/knowledge/search")
async def search_knowledge(q: str = Query("", description="search term — title/domain/summary")):
    """Search the knowledge database by free-text query (case-insensitive)."""
    p = await _load_persona()
    entries = ((p.get("knowledge_database") or {}).get("data") or [])
    qq = (q or "").lower().strip()
    if not qq:
        return {"count": len(entries), "entries": entries[:5]}
    matches = [
        e for e in entries
        if qq in (e.get("title", "") + " " + e.get("domain", "") + " " + e.get("summary", "")).lower()
    ]
    return {"query": q, "count": len(matches), "entries": matches[:20]}


@router.get("/persona/{key}")
async def get_persona_section(key: str):
    """One section of the persona — biography, catchphrases, vocal_mannerisms, …"""
    p = await _load_persona()
    if not p:
        return {"error": "persona_not_seeded"}
    if key == "biography":
        return p.get("biography") or {}
    if key in p:
        doc = p[key]
        return doc.get("data") if "data" in doc else doc
    return {"error": "unknown_key", "available": list(p.keys())}


@router.get("/catchphrase")
async def get_catchphrase(context: str = Query("greeting")):
    """Random catchphrase for the requested context."""
    p = await _load_persona()
    bank = ((p.get("catchphrases") or {}).get("data") or {}).get(context)
    if not bank:
        return {"context": context, "phrase": "", "available_contexts": list(((p.get("catchphrases") or {}).get("data") or {}).keys())}
    return {"context": context, "phrase": random.choice(bank)}


# ─── TTS with Jeeves flair ──────────────────────────────────────────────
class SpeakRequest(BaseModel):
    text: str
    context: Optional[str] = "lesson"     # greeting/lesson/joke/encouragement/...
    prepend_catchphrase: bool = True
    append_signoff: bool = False
    user_speed_override: Optional[float] = None
    quality: str = "standard"


@router.post("/speak")
async def jeeves_speak(req: SpeakRequest):
    """TTS endpoint that:
       1. Optionally pre-pends a context-appropriate catchphrase
       2. Looks up vocal mannerism → voice & speed
       3. Delegates to the ai_reader /api/reader/speak handler for actual audio
       4. Returns audio base64 + the assembled `spoken_text` so clients can show captions"""
    p = await _load_persona()
    if not p:
        raise HTTPException(503, "Jeeves persona not seeded yet")

    catchphrases  = ((p.get("catchphrases") or {}).get("data") or {})
    mannerisms    = ((p.get("vocal_mannerisms") or {}).get("data") or {})
    ctx = req.context if req.context in mannerisms else "lesson"
    mannerism = mannerisms.get(ctx, {})
    voice  = mannerism.get("voice", "fable")
    speed  = float(req.user_speed_override if req.user_speed_override else mannerism.get("speed", 1.0))
    emoji  = mannerism.get("emoji", "")

    # Assemble spoken text
    parts = []
    if req.prepend_catchphrase and catchphrases.get(ctx):
        parts.append(random.choice(catchphrases[ctx]))
    parts.append(req.text)
    if req.append_signoff and catchphrases.get("sign_off"):
        parts.append(random.choice(catchphrases["sign_off"]))
    spoken_text = " ".join(p for p in parts if p).strip()

    # Hand off to the real HD TTS pipeline (tts-1-hd via Emergent key).
    try:
        import os
        from emergentintegrations.llm.openai import OpenAITextToSpeech
        api_key = os.environ.get("EMERGENT_LLM_KEY")
        if not api_key:
            raise HTTPException(500, "EMERGENT_LLM_KEY not configured")
        model = "tts-1-hd"  # top-scale TTS — always HD
        tts = OpenAITextToSpeech(api_key=api_key)
        audio_b64 = await tts.generate_speech_base64(
            text=spoken_text, model=model, voice=voice, speed=speed,
        )
        return {
            "status":       "success",
            "voice":        voice,
            "speed":        speed,
            "context":      ctx,
            "emoji":        emoji,
            "spoken_text":  spoken_text,
            "audio_base64": audio_b64,
            "format":       "mp3",
            "model":        model,
        }
    except HTTPException:
        raise
    except Exception as e:
        return {
            "status":      "fallback_text_only",
            "context":     ctx,
            "voice":       voice,
            "speed":       speed,
            "spoken_text": spoken_text,
            "error":       str(e)[:200],
        }
