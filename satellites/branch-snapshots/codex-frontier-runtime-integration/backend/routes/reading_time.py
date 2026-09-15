"""
═══════════════════════════════════════════════════════════════════════════
 READING TIME TRACKER — persists total time spent reading, per user/book.
═══════════════════════════════════════════════════════════════════════════
 Routes:
   POST /api/reading-time/heartbeat   — record a session tick (seconds)
   POST /api/reading-time/start       — open a session (returns session_id)
   POST /api/reading-time/stop        — close a session, returns totals
   GET  /api/reading-time/total/{user_id}
   GET  /api/reading-time/leaderboard

 Frontend sends a heartbeat every 15-30 s while the reading view is mounted
 (with elapsed seconds delta). Backend stores immutable session rows and
 maintains a rolled-up totals doc per user for O(1) "total time" reads.
═══════════════════════════════════════════════════════════════════════════
"""
from datetime import datetime, timezone
from typing import Optional, Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator
import uuid

from services.database import db

router = APIRouter(prefix="/api/reading-time", tags=["Reading Time"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class HeartbeatRequest(BaseModel):
    user_id: str
    seconds: int
    book_id: Optional[str] = None
    chapter_id: Optional[str] = None
    session_id: Optional[str] = None

    @field_validator("seconds")
    @classmethod
    def _clip_seconds(cls, v):
        # Cap one heartbeat to 5 min so a tab left open forever can't inflate.
        try: v = int(v)
        except Exception: v = 0
        return max(0, min(300, v))


class StartRequest(BaseModel):
    user_id: str
    book_id: Optional[str] = None
    chapter_id: Optional[str] = None


class StopRequest(BaseModel):
    user_id: str
    session_id: str
    final_seconds: int = 0

    @field_validator("final_seconds")
    @classmethod
    def _clip(cls, v):
        try: v = int(v)
        except Exception: v = 0
        return max(0, min(7200, v))  # max 2h finishing burst


async def _bump_totals(user_id: str, seconds: int, book_id: Optional[str]):
    if seconds <= 0:
        return
    inc: dict = {"total_seconds": seconds, "sessions": 0}
    set_: dict = {"last_active_at": _now_iso(), "user_id": user_id}
    if book_id:
        inc[f"per_book.{book_id}.seconds"] = seconds
        set_[f"per_book.{book_id}.last_at"] = _now_iso()
    await db.reading_time_totals.update_one(
        {"user_id": user_id},
        {"$inc": inc, "$set": set_, "$setOnInsert": {"created_at": _now_iso()}},
        upsert=True,
    )


@router.post("/start")
async def start_session(req: StartRequest):
    sid = uuid.uuid4().hex[:12]
    await db.reading_time_sessions.insert_one({
        "session_id": sid,
        "user_id": req.user_id,
        "book_id": req.book_id,
        "chapter_id": req.chapter_id,
        "started_at": _now_iso(),
        "ended_at": None,
        "total_seconds": 0,
        "heartbeats": 0,
    })
    await db.reading_time_totals.update_one(
        {"user_id": req.user_id}, {"$inc": {"sessions": 1}, "$setOnInsert": {"created_at": _now_iso()}},
        upsert=True,
    )
    return {"session_id": sid, "started_at": _now_iso()}


@router.post("/heartbeat")
async def heartbeat(req: HeartbeatRequest):
    """Record `seconds` more reading time. Creates session if missing."""
    sid = req.session_id or uuid.uuid4().hex[:12]
    await db.reading_time_sessions.update_one(
        {"session_id": sid},
        {
            "$inc": {"total_seconds": req.seconds, "heartbeats": 1},
            "$set": {"last_heartbeat_at": _now_iso()},
            "$setOnInsert": {
                "user_id": req.user_id, "book_id": req.book_id, "chapter_id": req.chapter_id,
                "started_at": _now_iso(), "ended_at": None,
            },
        },
        upsert=True,
    )
    await _bump_totals(req.user_id, req.seconds, req.book_id)
    totals = await db.reading_time_totals.find_one({"user_id": req.user_id}) or {}
    return {
        "session_id": sid,
        "seconds_added": req.seconds,
        "user_total_seconds": int(totals.get("total_seconds", 0)),
        "user_total_minutes": round(int(totals.get("total_seconds", 0)) / 60, 1),
    }


@router.post("/stop")
async def stop_session(req: StopRequest):
    await db.reading_time_sessions.update_one(
        {"session_id": req.session_id},
        {"$inc": {"total_seconds": req.final_seconds}, "$set": {"ended_at": _now_iso()}},
        upsert=False,
    )
    if req.final_seconds > 0:
        session = await db.reading_time_sessions.find_one({"session_id": req.session_id}) or {}
        await _bump_totals(req.user_id, req.final_seconds, session.get("book_id"))
    session = await db.reading_time_sessions.find_one({"session_id": req.session_id}) or {}
    session.pop("_id", None)
    return session or {"ok": False, "error": "session not found"}


@router.get("/total/{user_id}")
async def total_for_user(user_id: str):
    totals = await db.reading_time_totals.find_one({"user_id": user_id}) or {}
    totals.pop("_id", None)
    seconds = int(totals.get("total_seconds", 0))
    return {
        "user_id": user_id,
        "total_seconds": seconds,
        "total_minutes": round(seconds / 60, 1),
        "total_hours": round(seconds / 3600, 2),
        "sessions": int(totals.get("sessions", 0)),
        "last_active_at": totals.get("last_active_at"),
        "per_book": totals.get("per_book", {}),
    }


@router.get("/leaderboard")
async def leaderboard(limit: int = 10):
    limit = max(1, min(limit, 100))
    cursor = db.reading_time_totals.find(
        {}, {"_id": 0, "user_id": 1, "total_seconds": 1, "sessions": 1, "last_active_at": 1},
    ).sort("total_seconds", -1).limit(limit)
    docs = await cursor.to_list(length=limit)
    for i, d in enumerate(docs):
        d["rank"] = i + 1
        d["total_minutes"] = round(int(d.get("total_seconds", 0)) / 60, 1)
        d["total_hours"] = round(int(d.get("total_seconds", 0)) / 3600, 2)
    return {"leaderboard": docs, "count": len(docs)}
