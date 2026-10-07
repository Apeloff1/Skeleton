"""
╔══════════════════════════════════════════════════════════════════════════╗
║  AI READER — Text-to-Speech Reading Mode for All Books                 ║
║  Pleasant female voice using OpenAI TTS via Emergent                   ║
║  Converts book content to audio for an immersive reading experience    ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import Response
import os
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv()

router = APIRouter(prefix="/api/reader", tags=["ai-reader"])

# reading_library now lives in content_db (regenerable). Use centralized handles.
from core.databases import core_db as _db, content_db as _cdb
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
        except Exception as e:
            raise HTTPException(500, f"Expressive TTS failed: {str(e)}")
    if voice not in VOICE_OPTIONS:
        raise HTTPException(400, f"Voice '{voice}' not available. Choose from: {list(VOICE_OPTIONS.keys())}")

    try:
        from emergentintegrations.llm.openai import OpenAITextToSpeech
        api_key = os.environ.get("EMERGENT_LLM_KEY")
        if not api_key:
            raise HTTPException(500, "TTS API key not configured")

        model = "tts-1-hd"  # top-scale TTS — always HD
        tts = OpenAITextToSpeech(api_key=api_key)
        audio_base64 = await tts.generate_speech_base64(
            text=text,
            model=model,
            voice=voice,
            speed=speed,
        )
        return {
            "audio_base64": audio_base64,
            "format": "mp3",
            "voice": voice,
            "model": model,
            "text_length": len(text),
        }
    except ImportError:
        raise HTTPException(500, "TTS library not installed")
    except Exception as e:
        raise HTTPException(500, f"TTS generation failed: {str(e)}")


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
        from emergentintegrations.llm.openai import OpenAITextToSpeech
        api_key = os.environ.get("EMERGENT_LLM_KEY")
        if not api_key:
            raise HTTPException(500, "TTS API key not configured")

        tts = OpenAITextToSpeech(api_key=api_key)
        audio_base64 = await tts.generate_speech_base64(
            text=reading_text,
            model="tts-1-hd",
            voice=voice,
            speed=speed,
        )
        return {
            "audio_base64": audio_base64,
            "format": "mp3",
            "book_title": book.get("title", ""),
            "chapter_name": chapter.get("name", ""),
            "lesson_title": title,
            "text_length": len(reading_text),
            "voice": voice,
        }
    except ImportError:
        raise HTTPException(500, "TTS library not installed")
    except Exception as e:
        raise HTTPException(500, f"TTS generation failed: {str(e)}")


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
        from emergentintegrations.llm.openai import OpenAITextToSpeech
        api_key = os.environ.get("EMERGENT_LLM_KEY")
        if not api_key:
            raise HTTPException(500, "TTS API key not configured")

        tts = OpenAITextToSpeech(api_key=api_key)
        audio_base64 = await tts.generate_speech_base64(
            text=reading_text,
            model="tts-1-hd",
            voice=voice,
            speed=speed,
        )
        return {
            "audio_base64": audio_base64,
            "format": "mp3",
            "entry_name": name,
            "text_length": len(reading_text),
            "voice": voice,
        }
    except ImportError:
        raise HTTPException(500, "TTS library not installed")
    except Exception as e:
        raise HTTPException(500, f"TTS generation failed: {str(e)}")
