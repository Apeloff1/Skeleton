"""
╔══════════════════════════════════════════════════════════════════════════╗
║  AI READER — Text-to-Speech Reading Mode for All Books                 ║
║  Pleasant female voice using OpenAI TTS via Emergent                   ║
║  Converts book content to audio for an immersive reading experience    ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
import logging

from dotenv import load_dotenv
from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import Response
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv()

log = logging.getLogger("ai.reader")
router = APIRouter(prefix="/api/reader", tags=["ai-reader"])

# reading_library now lives in content_db (regenerable). Use centralized handles.
from core.databases import core_db as _db, content_db as _cdb
from core.expressive_tts import generate_expressive_tts
PROJ = {"_id": 0}

# Voice options for the reader
VOICE_OPTIONS = {
    "nova": {"name": "Nova", "description": "Warm, engaging female voice — recommended for reading", "gender": "female"},
    "shimmer": {"name": "Shimmer", "description": "Bright, cheerful female voice", "gender": "female"},
    "coral": {"name": "Coral", "description": "Warm, friendly female voice", "gender": "female"},
    "alloy": {"name": "Alloy", "description": "Neutral, balanced voice", "gender": "neutral"},
    "sage": {"name": "Sage", "description": "Wise, measured voice — great for technical content", "gender": "neutral"},
    "fable": {"name": "Fable", "description": "Expressive, storytelling voice", "gender": "neutral"},
    "echo": {"name": "Echo", "description": "Smooth, calm voice", "gender": "male"},
    "onyx": {"name": "Onyx", "description": "Deep, authoritative voice", "gender": "male"},
}


@router.get("/voices")
async def get_available_voices():
    """Get all available reading voices."""
    return {"voices": VOICE_OPTIONS, "default": "nova", "recommended": "nova"}


@router.post("/speak")
async def speak_text(
    text: str = Query(..., max_length=4096),
    voice: str = Query("nova"),
    speed: float = Query(1.0, ge=0.5, le=2.0),
    quality: str = Query("standard"),
    tone: str = Query("", description="Optional expressive tone (storyteller, warm, dramatic, …) — adds immersive cadence"),
):
    """Convert text to speech. Returns audio as base64 for mobile playback.
    When `tone` is provided, applies the expressive cadence engine for immersion."""
    if tone:
        from core.expressive_tts import generate_expressive_tts
        try:
            out = await generate_expressive_tts(
                text=text, tone=tone,
                voice_override=(voice if voice in VOICE_OPTIONS else None),
                speed_override=speed,
            )
            out["status"] = "success"
            return out
        except Exception as exc:
            log.warning("Expressive TTS failed: %s", type(exc).__name__)
            raise HTTPException(status_code=500, detail="Expressive TTS failed") from None
    if voice not in VOICE_OPTIONS:
        raise HTTPException(400, f"Voice '{voice}' not available. Choose from: {list(VOICE_OPTIONS.keys())}")

    try:
        out = await generate_expressive_tts(
            text=text,
            voice_override=voice,
            speed_override=speed,
            shape=False,
        )
        out["status"] = "success"
        return out
    except Exception as exc:
        log.warning("TTS generation failed: %s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="TTS generation failed") from None


@router.post("/read-chapter")
async def read_book_chapter(
    book_id: str = Query(...),
    chapter_idx: int = Query(...),
    lesson_idx: int = Query(0),
    voice: str = Query("nova"),
    speed: float = Query(0.95, ge=0.5, le=2.0),
):
    """Read a specific book chapter/lesson aloud. Returns audio base64."""
    book = await _cdb.reading_library.find_one({"id": book_id}, PROJ)
    if not book:
        raise HTTPException(404, f"Book '{book_id}' not found")

    chapters = book.get("chapters", [])
    if chapter_idx < 0 or chapter_idx >= len(chapters):
        raise HTTPException(404, f"Chapter {chapter_idx} not found")

    chapter = chapters[chapter_idx]
    lessons = chapter.get("lessons", [])

    if lesson_idx < 0 or lesson_idx >= len(lessons):
        raise HTTPException(404, f"Lesson {lesson_idx} not found")

    lesson = lessons[lesson_idx]
    content = lesson.get("content", "")
    title = lesson.get("title", "")

    # Build reading text
    reading_text = f"{title}. {content}"
    # Truncate to TTS limit
    if len(reading_text) > 4000:
        reading_text = reading_text[:4000] + "..."

    try:
        out = await generate_expressive_tts(
            text=reading_text,
            voice_override=voice,
            speed_override=speed,
            shape=False,
        )
        return {
            **out,
            "book_title": book.get("title", ""),
            "chapter_name": chapter.get("name", ""),
            "lesson_title": title,
            "text_length": len(reading_text),
        }
    except Exception as exc:
        log.warning("TTS generation failed: %s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="TTS generation failed") from None


@router.post("/read-knowledge")
async def read_knowledge_entry(
    domain: str = Query(...),
    field_id: str = Query(...),
    voice: str = Query("nova"),
    speed: float = Query(0.95, ge=0.5, le=2.0),
):
    """Read a knowledge database entry aloud."""
    entry = await _db.knowledge_databases.find_one({"_domain": domain, "id": field_id}, PROJ)
    if not entry:
        raise HTTPException(404, f"Entry '{field_id}' in '{domain}' not found")

    name = entry.get("name", field_id)
    topics = entry.get("topics", [])
    hours = entry.get("hours", 0)
    level = entry.get("level", "")

    reading_text = f"{name}. This is a {level} level topic requiring approximately {hours} hours of study. "
    reading_text += f"Key topics include: {', '.join(topics[:15])}."

    if len(reading_text) > 4000:
        reading_text = reading_text[:4000] + "..."

    try:
        out = await generate_expressive_tts(
            text=reading_text,
            voice_override=voice,
            speed_override=speed,
            shape=False,
        )
        return {
            **out,
            "entry_name": name,
            "text_length": len(reading_text),
        }
    except Exception as exc:
        log.warning("TTS generation failed: %s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="TTS generation failed") from None
