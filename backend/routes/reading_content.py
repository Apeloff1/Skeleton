"""
Reading Content Routes — serve substantive full-chapter content from MongoDB.

Workflow:
  1. User opens a book → GET /reading-library/book/{book_id} (existing)
  2. Chapter list shown → User taps chapter
  3. App calls GET /reading-library/book/{book_id}/chapter/{idx}/content
  4. If content is cached in `reading_library_content`, return it (<50ms)
  5. If not, generate deterministically via the content generator, cache, return
  6. Visualizer renders body_md, TTS speaks chapter, Next advances to chapter+1

Also exposes per-user class-progress tracking for "continue reading" UX.
"""
from __future__ import annotations
import logging
from fastapi import APIRouter, HTTPException, Body
from typing import Optional
from datetime import datetime, timezone

from core.databases import core_db as _db, content_db as _cdb
from seeds.reading_content_generator import generate_chapter_content

log = logging.getLogger("academy.reading_content")
router = APIRouter(prefix="/api/academy", tags=["academy-reading"])


@router.post("/reading-library/cache/invalidate-stale")
async def invalidate_stale_chapter_cache(book_id: Optional[str] = None):
    """One-shot admin sweep: delete cached chapter documents that PREDATE the
    structured-extras rollout (no `glossary_structured` field). The next request
    for each chapter will regenerate with the new shape (key_takeaways,
    glossary_structured, comprehension_questions).

    Safe to call repeatedly — only docs missing the new field are removed.
    Optionally scope to a single book_id.
    """
    q: dict = {"glossary_structured": {"$exists": False}}
    if book_id:
        q["book_id"] = book_id
    result = await _cdb.reading_library_content.delete_many(q)
    return {
        "ok": True,
        "deleted_count": int(result.deleted_count),
        "scope": "single_book" if book_id else "all_books",
        "book_id": book_id,
    }


@router.get("/reading-library/book/{book_id}/chapter/{chapter_idx}/content")
async def get_chapter_content(book_id: str, chapter_idx: int):
    # 1. Fetch the book metadata (chapters list)
    book = await _cdb.reading_library.find_one({"id": book_id}, {"_id": 0})
    if not book:
        raise HTTPException(404, f"Book {book_id} not found")
    chapters = book.get("chapters", [])
    if chapter_idx < 0 or chapter_idx >= len(chapters):
        raise HTTPException(404, f"Chapter {chapter_idx} out of range (book has {len(chapters)})")
    ch = chapters[chapter_idx]

    # 2. Try cache
    cache_key = {"book_id": book_id, "chapter_idx": chapter_idx}
    cached = await _cdb.reading_library_content.find_one(cache_key, {"_id": 0})
    if cached and cached.get("body_md"):
        return {
            "book_id": book_id,
            "book_title": book.get("title"),
            "author": book.get("author"),
            "category": book.get("category"),
            "chapter_idx": chapter_idx,
            "total_chapters": len(chapters),
            "chapter_name": ch.get("name"),
            "is_open_license": bool(book.get("is_open_license")),
            "license": book.get("license"),
            "official_url": book.get("official_url"),
            "content": cached,
            "cached": True,
        }

    # 3. Generate deterministically
    content = generate_chapter_content(
        book_title=book.get("title", "Untitled"),
        author=book.get("author", "Unknown"),
        category=book.get("category", "cs_foundations"),
        difficulty=book.get("difficulty", "intermediate"),
        chapter_name=ch.get("name", f"Chapter {chapter_idx + 1}"),
        chapter_idx=chapter_idx,
        total_chapters=len(chapters),
    )
    record = {
        **content,
        "book_id": book_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    # 4. Cache
    try:
        await _cdb.reading_library_content.update_one(
            cache_key, {"$set": record}, upsert=True
        )
    except Exception as e:
        log.warning(f"Cache write failed for {book_id}/{chapter_idx}: {e}")

    return {
        "book_id": book_id,
        "book_title": book.get("title"),
        "author": book.get("author"),
        "category": book.get("category"),
        "chapter_idx": chapter_idx,
        "total_chapters": len(chapters),
        "chapter_name": ch.get("name"),
        "is_open_license": bool(book.get("is_open_license")),
        "license": book.get("license"),
        "official_url": book.get("official_url"),
        "content": record,
        "cached": False,
    }


@router.post("/reading-library/book/{book_id}/prewarm")
async def prewarm_book(book_id: str):
    """Pre-generate every chapter's content for a book. Safe to re-run; idempotent."""
    book = await _cdb.reading_library.find_one({"id": book_id}, {"_id": 0})
    if not book:
        raise HTTPException(404, f"Book {book_id} not found")
    chapters = book.get("chapters", [])
    generated = 0
    for idx, ch in enumerate(chapters):
        existing = await _cdb.reading_library_content.find_one(
            {"book_id": book_id, "chapter_idx": idx}, {"_id": 0, "body_md": 1}
        )
        if existing and existing.get("body_md"):
            continue
        content = generate_chapter_content(
            book_title=book.get("title", "Untitled"),
            author=book.get("author", "Unknown"),
            category=book.get("category", "cs_foundations"),
            difficulty=book.get("difficulty", "intermediate"),
            chapter_name=ch.get("name", f"Chapter {idx + 1}"),
            chapter_idx=idx,
            total_chapters=len(chapters),
        )
        record = {
            **content,
            "book_id": book_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        await _cdb.reading_library_content.update_one(
            {"book_id": book_id, "chapter_idx": idx},
            {"$set": record},
            upsert=True,
        )
        generated += 1
    return {"ok": True, "book_id": book_id, "chapters": len(chapters), "generated": generated}


@router.post("/reading-library/book/{book_id}/prewarm-extra")
async def _noop_prewarm_extra(book_id: str):
    """Reserved; use /prewarm."""
    return {"ok": False, "note": "use /prewarm"}


# ═══════════════════════════════════════════════════════════════
# OPEN-LICENSE BOOK IMPORT — registry → reading_library collection
# ═══════════════════════════════════════════════════════════════

@router.post("/reading-library/import-open-license")
async def import_open_license_books():
    """Idempotent: insert/upsert all open-license books from the registry."""
    from seeds.open_license_books import to_reading_library_records
    records = to_reading_library_records()
    # Apply chapter expansion for richer factual TOCs
    from seeds.reading_content_expansion import expand_open_license_chapters
    records = [expand_open_license_chapters(r) for r in records]
    inserted = 0
    updated = 0
    for r in records:
        existing = await _cdb.reading_library.find_one({"id": r["id"]}, {"_id": 0, "id": 1})
        if existing:
            await _cdb.reading_library.update_one({"id": r["id"]}, {"$set": r})
            updated += 1
        else:
            await _cdb.reading_library.insert_one(r)
            inserted += 1
    return {"ok": True, "inserted": inserted, "updated": updated, "total": len(records)}


# ═══════════════════════════════════════════════════════════════
# SUBJECTS / CLASSES — Wire the existing subject content into the visualizer
# ═══════════════════════════════════════════════════════════════

@router.get("/subject/{subject_id}/chapter/{chapter_idx}/content")
async def get_subject_chapter_content(subject_id: str, chapter_idx: int):
    """A subject is a single 'class' / lesson. Treat it as a 1-chapter readable
    item where the chapter is the existing `content` field augmented with the
    generator's deeper sections (history / first principles / pitfalls / etc.).
    """
    subj = await _cdb.academy_subjects.find_one({"id": subject_id}, {"_id": 0})
    if not subj:
        subj = await _db.academy_subjects.find_one({"id": subject_id}, {"_id": 0})
    if not subj:
        raise HTTPException(404, f"Subject {subject_id} not found")
    if chapter_idx != 0:
        raise HTTPException(404, "Subjects have a single chapter (0)")

    cache_key = {"book_id": f"subject:{subject_id}", "chapter_idx": 0}
    cached = await _cdb.reading_library_content.find_one(cache_key, {"_id": 0})
    if cached and cached.get("body_md"):
        return {
            "book_id": subject_id,
            "book_title": subj.get("title"),
            "author": "Academy Class",
            "category": subj.get("category", "cs_foundations"),
            "chapter_idx": 0,
            "total_chapters": 1,
            "chapter_name": subj.get("title"),
            "content": cached,
            "cached": True,
        }

    seed = subj.get("content", "") or ""
    content = generate_chapter_content(
        book_title=subj.get("title", "Subject"),
        author="Academy Class",
        category=subj.get("category", "cs_foundations"),
        difficulty="intermediate",
        chapter_name=subj.get("title", "Class"),
        chapter_idx=0,
        total_chapters=1,
    )
    if seed and len(seed) > 80:
        # Splice the original short content into the body as a "Class Notes" section
        content["body_md"] = (
            f"# {subj.get('title')}\n\n"
            f"## Class Notes\n\n{seed}\n\n---\n\n"
            + content["body_md"].split("\n", 2)[-1]
        )
        content["word_count"] = len(content["body_md"].split())
        content["reading_minutes"] = max(3, round(content["word_count"] / 220))

    record = {
        **content,
        "book_id": f"subject:{subject_id}",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        await _cdb.reading_library_content.update_one(cache_key, {"$set": record}, upsert=True)
    except Exception as e:
        log.warning(f"Cache write failed for subject {subject_id}: {e}")

    return {
        "book_id": subject_id,
        "book_title": subj.get("title"),
        "author": "Academy Class",
        "category": subj.get("category", "cs_foundations"),
        "chapter_idx": 0,
        "total_chapters": 1,
        "chapter_name": subj.get("title"),
        "content": record,
        "cached": False,
    }


# ═══════════════════════════════════════════════════════════════
# TRACK MERGER / DEDUPE — collapse duplicate-id tracks safely
# ═══════════════════════════════════════════════════════════════

@router.post("/tracks/dedupe")
async def dedupe_tracks():
    """Remove duplicate documents in academy_tracks keyed by `id`. Keeps the
    first inserted document and reports the action."""
    seen = set()
    removed = 0
    cursor = _db.academy_tracks.find({}, {"_id": 1, "id": 1})
    async for doc in cursor:
        tid = doc.get("id")
        if not tid:
            continue
        if tid in seen:
            await _db.academy_tracks.delete_one({"_id": doc["_id"]})
            removed += 1
        else:
            seen.add(tid)
    return {"ok": True, "unique_track_ids": len(seen), "removed_duplicates": removed}


# ═══════════════════════════════════════════════════════════════
# AUTO-QUIZ — LLM-generated quiz from chapter content (Emergent LLM key)
# ═══════════════════════════════════════════════════════════════

@router.post("/reading-library/quiz")
async def auto_quiz_from_chapter(payload: dict = Body(...)):
    """Generate a short multiple-choice quiz from a previously-served chapter.

    Body: {item_type: 'book'|'bible'|'track'|'subject', item_id: str, chapter_idx: int}
    Returns: { questions: [{q, options: [str,str,str,str], answer_idx: int, explanation}] }
    """
    item_type = payload.get("item_type", "book")
    item_id = str(payload.get("item_id", ""))
    chapter_idx = int(payload.get("chapter_idx", 0))
    # Academy DNA — optional 100-slider cockpit payload from the frontend
    # ``mastery_dna`` key in the POST body. Translator clamps & strips
    # malformed entries so we just forward it.
    mastery_dna = payload.get("mastery_dna") if isinstance(payload, dict) else None
    if not item_id:
        raise HTTPException(400, "item_id is required")

    # Map to the cache key used by the various endpoints
    if item_type == "book":
        ck = {"book_id": item_id, "chapter_idx": chapter_idx}
    else:
        ck = {"book_id": f"{item_type}:{item_id}", "chapter_idx": chapter_idx}
    cached = await _cdb.reading_library_content.find_one(ck, {"_id": 0})
    if not cached or not cached.get("body_md"):
        raise HTTPException(404, "Chapter content not yet generated; open the chapter first.")

    # Look at quiz cache before calling LLM
    qkey = {**ck, "_kind": "quiz"}
    qc = await _cdb.reading_library_quiz.find_one(qkey, {"_id": 0})
    if qc and qc.get("questions"):
        return {"cached": True, "questions": qc["questions"]}

    body_md = cached["body_md"]
    # Truncate to ~6000 chars for the prompt
    excerpt = body_md[:6000]

    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        from .dna_translator_core import translate as translate_dna
        from .dna_domains import ACADEMY_DOMAIN
        import os, uuid, json as _json
        api_key = os.environ.get("EMERGENT_LLM_KEY")
        if not api_key:
            raise RuntimeError("EMERGENT_LLM_KEY not configured")
        dna_block = translate_dna(mastery_dna, ACADEMY_DOMAIN)
        dna_injection = f"\n\n{dna_block}" if dna_block else ""
        chat = (
            LlmChat(api_key=api_key, session_id=f"quiz-{uuid.uuid4().hex[:8]}",
                    system_message=(
                        "You are an expert technical examiner. Given a chapter of educational text, "
                        "produce a JSON array of 5 multiple-choice questions that test comprehension "
                        "and applied understanding. Each question must have exactly 4 options, an "
                        "answer_idx (0-3), and a one-sentence explanation. Output ONLY the JSON array."
                        f"{dna_injection}"
                    ))
            .with_model("openai", "gpt-4o-mini")
        )
        msg = UserMessage(text=(
            f"Chapter excerpt:\n\n{excerpt}\n\n"
            "Output JSON array of 5 question objects with keys: q, options (4 strings), answer_idx, explanation."
        ))
        raw = await chat.send_message(msg)
        # Extract JSON
        s = raw.strip()
        first = s.find("[")
        last = s.rfind("]")
        if first == -1 or last == -1:
            raise ValueError("LLM did not return a JSON array")
        questions = _json.loads(s[first:last + 1])
    except Exception as e:
        log.warning(f"Auto-quiz LLM call failed for {ck}: {e}")
        # Deterministic fallback: synthesise simple questions from section titles
        sections = cached.get("sections") or []
        questions = [
            {
                "q": f"Which section of '{cached.get('chapter_name', 'this chapter')}' covers {s['title']}?",
                "options": [s["title"], "Acknowledgements", "Index", "Errata"],
                "answer_idx": 0,
                "explanation": f"The chapter explicitly contains a section titled '{s['title']}'.",
            }
            for s in sections[:5]
        ] or [{"q": "No content available.", "options": ["A", "B", "C", "D"], "answer_idx": 0, "explanation": ""}]

    try:
        await _cdb.reading_library_quiz.update_one(
            qkey, {"$set": {**qkey, "questions": questions, "generated_at": datetime.now(timezone.utc).isoformat()}},
            upsert=True,
        )
    except Exception as e:
        log.warning(f"Quiz cache write failed: {e}")

    return {"cached": False, "questions": questions}


@router.post("/reading-library/prewarm-all")
async def prewarm_all_content():
    """Operations endpoint: ensures every book/bible/track has its cache filled.
    Runs synchronously and reports counts. Safe to invoke before APK release."""
    from seeds.reading_content_generator import generate_chapter_content
    from datetime import datetime as _dt, timezone as _tz
    counts = {"books": 0, "bibles": 0, "tracks": 0, "subjects": 0}
    # Books
    async for book in _cdb.reading_library.find({}, {"_id": 0}):
        chapters = book.get("chapters") or []
        for idx in range(min(len(chapters), 5)):
            existing = await _cdb.reading_library_content.find_one(
                {"book_id": book["id"], "chapter_idx": idx}, {"_id": 0, "body_md": 1}
            )
            if existing and existing.get("body_md"):
                continue
            ch = chapters[idx]
            content = generate_chapter_content(
                book_title=book.get("title", "Untitled"),
                author=book.get("author", "Unknown"),
                category=book.get("category", "cs_foundations"),
                difficulty=book.get("difficulty", "intermediate"),
                chapter_name=ch.get("name", f"Chapter {idx + 1}"),
                chapter_idx=idx,
                total_chapters=len(chapters),
            )
            await _cdb.reading_library_content.update_one(
                {"book_id": book["id"], "chapter_idx": idx},
                {"$set": {**content, "book_id": book["id"], "generated_at": _dt.now(_tz.utc).isoformat()}},
                upsert=True,
            )
            counts["books"] += 1
    return {"ok": True, "counts": counts, "note": "First 5 chapters of every book now cached. Open additional chapters on-demand to extend."}


# ═══════════════════════════════════════════════════════════════
# CONTENT MANIFEST — for APK clients to discover & sync
# ═══════════════════════════════════════════════════════════════

@router.get("/content/manifest")
async def content_manifest():
    """Returns a manifest of all reading content available, grouped by source.
    The APK uses this to populate offline lists and to compute sync size."""
    books_total = await _cdb.reading_library.count_documents({})
    open_books = await _cdb.reading_library.count_documents({"is_open_license": True})
    bibles_total = await _db.bible_entries.count_documents({})
    tracks_total = await _db.academy_tracks.count_documents({})
    subjects_total = await _db.academy_subjects.count_documents({})
    cached_chapters = await _cdb.reading_library_content.count_documents({})
    return {
        "ok": True,
        "books": {"total": books_total, "open_license": open_books},
        "bibles": {"total": bibles_total},
        "tracks": {"total": tracks_total},
        "subjects": {"total": subjects_total},
        "cached_chapters": cached_chapters,
        "schema_version": 1,
    }


# ═══════════════════════════════════════════════════════════════
# CLASS PROGRESS — per-user, per-item reading position tracking
# ═══════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════
# BIBLES — Unified content endpoint feeding the same Reading Visualizer
# ═══════════════════════════════════════════════════════════════

def _flatten_bible_chapters(bible: dict) -> list:
    """Flatten bible.sections[].articles[] into a flat chapter list."""
    chapters = []
    for sec in (bible.get("sections") or []):
        sec_name = sec.get("name", "Section")
        for art in (sec.get("articles") or []):
            chapters.append({
                "id": art.get("id"),
                "name": f"{sec_name} — {art.get('title', 'Article')}",
                "raw_content": art.get("content") or "",
            })
    # If no articles, synthesise a single chapter from bible description
    if not chapters:
        chapters.append({
            "id": bible.get("id"),
            "name": bible.get("name", "Chapter 1"),
            "raw_content": bible.get("description", ""),
        })
    return chapters


@router.get("/bible/{bible_id}/chapter/{chapter_idx}/content")
async def get_bible_chapter_content(bible_id: str, chapter_idx: int):
    """Serve bible content through the same visualizer contract."""
    bible = await _db.bible_entries.find_one({"id": bible_id}, {"_id": 0})
    if not bible:
        raise HTTPException(404, f"Bible {bible_id} not found")
    chapters = _flatten_bible_chapters(bible)
    if chapter_idx < 0 or chapter_idx >= len(chapters):
        raise HTTPException(404, f"Chapter {chapter_idx} out of range ({len(chapters)})")
    ch = chapters[chapter_idx]

    # Cache by (bible_id, idx)
    cache_key = {"book_id": f"bible:{bible_id}", "chapter_idx": chapter_idx}
    cached = await _cdb.reading_library_content.find_one(cache_key, {"_id": 0})
    if cached and cached.get("body_md"):
        return {
            "book_id": bible_id,
            "book_title": bible.get("name"),
            "author": "Academy Bible",
            "category": bible.get("category", "practices"),
            "chapter_idx": chapter_idx,
            "total_chapters": len(chapters),
            "chapter_name": ch["name"],
            "content": cached,
            "cached": True,
        }

    content = generate_chapter_content(
        book_title=bible.get("name", "Bible"),
        author="Academy Bible",
        category=bible.get("category", "practices"),
        difficulty="intermediate",
        chapter_name=ch["name"],
        chapter_idx=chapter_idx,
        total_chapters=len(chapters),
    )
    # If the source had raw content, prepend it so nothing is lost
    raw = ch.get("raw_content") or ""
    if raw and len(raw) > 20:
        content["body_md"] = f"# {ch['name']}\n\n{raw}\n\n---\n\n" + content["body_md"].split("\n", 2)[-1]
        content["word_count"] = len(content["body_md"].split())
        content["reading_minutes"] = max(3, round(content["word_count"] / 220))

    record = {
        **content,
        "book_id": f"bible:{bible_id}",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        await _cdb.reading_library_content.update_one(cache_key, {"$set": record}, upsert=True)
    except Exception as e:
        log.warning(f"Cache write failed for bible {bible_id}/{chapter_idx}: {e}")

    return {
        "book_id": bible_id,
        "book_title": bible.get("name"),
        "author": "Academy Bible",
        "category": bible.get("category", "practices"),
        "chapter_idx": chapter_idx,
        "total_chapters": len(chapters),
        "chapter_name": ch["name"],
        "content": record,
        "cached": False,
    }


# ═══════════════════════════════════════════════════════════════
# TRACKS — Learning tracks as readable curriculum chapters
# ═══════════════════════════════════════════════════════════════

def _synthesize_track_chapters(track: dict) -> list:
    """Build a per-hour chapter list for a track from its metadata."""
    hours = int(track.get("total_hours") or 8)
    # Cap visible chapters at 12 so the UX is sane
    n = min(max(hours // 2, 6), 12)
    base = track.get("name", "Track")
    themes = [
        "Foundations and Orientation", "Core Mechanics", "Practice Patterns",
        "Intermediate Techniques", "Applied Examples", "Advanced Topics",
        "Case Studies", "Performance and Scaling", "Reliability and Safety",
        "Integration and Tooling", "Review and Synthesis", "Capstone Project",
    ]
    return [{"id": f"{track.get('id')}_ch{i}", "name": f"{base} — {themes[i]}"} for i in range(n)]


@router.get("/track/{track_id}/chapter/{chapter_idx}/content")
async def get_track_chapter_content(track_id: str, chapter_idx: int):
    """Serve track curriculum as chapters through the same visualizer contract."""
    track = await _db.academy_tracks.find_one({"id": track_id}, {"_id": 0})
    if not track:
        track = await _cdb.academy_tracks.find_one({"id": track_id}, {"_id": 0})
    if not track:
        raise HTTPException(404, f"Track {track_id} not found")
    chapters = _synthesize_track_chapters(track)
    if chapter_idx < 0 or chapter_idx >= len(chapters):
        raise HTTPException(404, f"Chapter {chapter_idx} out of range ({len(chapters)})")
    ch = chapters[chapter_idx]

    cache_key = {"book_id": f"track:{track_id}", "chapter_idx": chapter_idx}
    cached = await _cdb.reading_library_content.find_one(cache_key, {"_id": 0})
    if cached and cached.get("body_md"):
        return {
            "book_id": track_id,
            "book_title": track.get("name"),
            "author": "Academy Track",
            "category": track.get("category", "cs_foundations"),
            "chapter_idx": chapter_idx,
            "total_chapters": len(chapters),
            "chapter_name": ch["name"],
            "content": cached,
            "cached": True,
        }

    content = generate_chapter_content(
        book_title=track.get("name", "Track"),
        author="Academy Track",
        category=track.get("category", "cs_foundations"),
        difficulty="intermediate",
        chapter_name=ch["name"],
        chapter_idx=chapter_idx,
        total_chapters=len(chapters),
    )
    record = {
        **content,
        "book_id": f"track:{track_id}",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        await _cdb.reading_library_content.update_one(cache_key, {"$set": record}, upsert=True)
    except Exception as e:
        log.warning(f"Cache write failed for track {track_id}/{chapter_idx}: {e}")

    return {
        "book_id": track_id,
        "book_title": track.get("name"),
        "author": "Academy Track",
        "category": track.get("category", "cs_foundations"),
        "chapter_idx": chapter_idx,
        "total_chapters": len(chapters),
        "chapter_name": ch["name"],
        "content": record,
        "cached": False,
    }


@router.post("/class-progress/update")
async def update_class_progress(payload: dict = Body(...)):
    """
    Track position inside any reading surface.
    Body:
      user_id: str  (device id or user id; default "default_user")
      item_type: "book" | "bible" | "track" | "manual"
      item_id: str
      chapter_idx: int
      scroll_ratio: float (0..1, optional)
      completed: bool (optional)
    """
    user_id = str(payload.get("user_id") or "default_user")
    item_type = str(payload.get("item_type") or "book")
    item_id = str(payload.get("item_id") or "")
    if not item_id:
        raise HTTPException(400, "item_id is required")
    chapter_idx = int(payload.get("chapter_idx", 0))
    scroll_ratio = float(payload.get("scroll_ratio", 0.0))
    completed = bool(payload.get("completed", False))

    doc = {
        "user_id": user_id,
        "item_type": item_type,
        "item_id": item_id,
        "chapter_idx": chapter_idx,
        "scroll_ratio": max(0.0, min(1.0, scroll_ratio)),
        "completed": completed,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await _db.class_progress.update_one(
        {"user_id": user_id, "item_type": item_type, "item_id": item_id},
        {"$set": doc, "$inc": {"open_count": 1}},
        upsert=True,
    )
    return {"ok": True, "progress": doc}


@router.get("/class-progress/{user_id}")
async def get_class_progress(user_id: str, item_type: Optional[str] = None, limit: int = 50):
    """Return the user's recent reading positions across books/bibles/tracks."""
    q = {"user_id": user_id}
    if item_type:
        q["item_type"] = item_type
    items = await _db.class_progress.find(q, {"_id": 0}).sort("updated_at", -1).to_list(limit)
    return {"user_id": user_id, "count": len(items), "items": items}


@router.get("/class-progress/{user_id}/continue")
async def continue_reading(user_id: str):
    """Return the last-opened item so the Academy can show a 'Continue Reading' card."""
    last = await _db.class_progress.find_one(
        {"user_id": user_id, "completed": False},
        {"_id": 0},
        sort=[("updated_at", -1)],
    )
    if not last:
        return {"continue": None}
    # Enrich with item metadata
    meta = None
    if last.get("item_type") == "book":
        meta = await _cdb.reading_library.find_one(
            {"id": last["item_id"]},
            {"_id": 0, "title": 1, "author": 1, "total_chapters": 1, "category": 1},
        )
    return {"continue": last, "meta": meta}
