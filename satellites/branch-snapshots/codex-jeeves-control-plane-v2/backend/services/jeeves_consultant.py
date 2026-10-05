"""
jeeves_consultant.py — Helper for agents and build pipelines to "consult Jeeves"
without going through HTTP. Pulls persona DB rows directly from Mongo and
returns context-appropriate guidance.
"""
from __future__ import annotations
import random, os
from motor.motor_asyncio import AsyncIOMotorClient
# ★ Consolidated 2026-02 — shared MongoDB client (lazy connect, fast timeouts)
from core.databases import client as _SHARED_MONGO_CLIENT
from typing import Any

_MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
_DB_NAME = os.environ.get("DB_NAME", "test_database")
_client: AsyncIOMotorClient | None = None


def _db():
    global _client
    if _client is None:
        _client = _SHARED_MONGO_CLIENT  # consolidated → core.databases.client
    return _client[_DB_NAME]


async def consult(context: str, topic: str = "", limit: int = 1) -> dict:
    """
    Pull a context-appropriate catchphrase + relevant knowledge entry for the
    given build/agent step. Returns:
      { catchphrase: str, knowledge: str, mannerism: dict, citation: str }

    `context` examples: 'celebration', 'debug', 'lesson', 'gentle_correction'.
    `topic`   examples: 'physics', 'compiler', 'pathfinding'.
    """
    db = _db()
    out: dict[str, Any] = {"catchphrase": "", "knowledge": "", "mannerism": {}, "citation": ""}

    # The Jeeves persona DB packs everything into a single collection keyed by
    # `_key` — each doc has a `data` field that holds the array/dict of items.

    # 1) Catchphrase — context-filtered random pick (with smart fallback)
    try:
        cp_doc = await db.jeeves_persona.find_one({"_key": "catchphrases"})
        if cp_doc and isinstance(cp_doc.get("data"), (list, dict)):
            phrases = cp_doc["data"]
            if isinstance(phrases, dict):
                # Shape: { context: [phrases...] } OR { phrases: [...] }
                bucket = phrases.get(context) or phrases.get("phrases") or []
                # Fallback: if requested context is unknown, sample from a
                # safe default bucket (greeting/lesson_intro/encouragement)
                if not bucket:
                    for alt in ("lesson_intro", "encouragement", "greeting", "thinking"):
                        bucket = phrases.get(alt) or []
                        if bucket:
                            break
                    # Last resort — flatten everything
                    if not bucket:
                        bucket = sum(
                            (v for v in phrases.values() if isinstance(v, list)),
                            []
                        )
            else:
                bucket = phrases
            # Filter for those tagged with this context if items are dicts
            candidates = []
            for p in bucket:
                if isinstance(p, dict):
                    if not context or p.get("context") == context or context in (p.get("contexts") or []):
                        candidates.append(p.get("text") or p.get("phrase") or "")
                elif isinstance(p, str):
                    candidates.append(p)
            candidates = [c for c in candidates if c]
            # Fallback: if context filter produced nothing, take ANY catchphrase from the bucket
            if not candidates:
                for p in bucket:
                    if isinstance(p, dict):
                        t = p.get("text") or p.get("phrase") or ""
                        if t: candidates.append(t)
                    elif isinstance(p, str):
                        candidates.append(p)
            if candidates:
                out["catchphrase"] = random.choice(candidates)
    except Exception as e:
        out["catchphrase"] = ""
        out["_cp_err"] = str(e)

    # 2) Knowledge — fuzzy topic match from knowledge_database / knowledge_domains
    if topic:
        try:
            for key in ("knowledge_database", "knowledge_domains"):
                kdoc = await db.jeeves_persona.find_one({"_key": key})
                if not kdoc:
                    continue
                items = kdoc.get("data", [])
                if isinstance(items, dict):
                    # Could be { topic: details }
                    for k, v in items.items():
                        if topic.lower() in k.lower():
                            out["knowledge"] = str(v)[:400]
                            out["citation"] = key
                            break
                elif isinstance(items, list):
                    for entry in items:
                        if not isinstance(entry, dict):
                            continue
                        blob = (entry.get("topic", "") + " " + str(entry.get("tags", "")) + " " + entry.get("summary", "")).lower()
                        if topic.lower() in blob:
                            out["knowledge"] = entry.get("summary") or entry.get("text") or ""
                            out["citation"] = entry.get("citation") or key
                            break
                if out["knowledge"]:
                    break
        except Exception:
            pass

    # 3) Mannerism — vocal cues for the step
    try:
        m = await db.jeeves_persona.find_one({"_key": "vocal_mannerisms"})
        if m:
            data = m.get("data", {})
            if isinstance(data, dict) and context in data:
                out["mannerism"] = data[context]
    except Exception:
        pass

    return out


async def famous_quote(theme: str = "") -> dict:
    """Pick one of the 27+ famous quotes from the Jeeves DB."""
    db = _db()
    try:
        q = await db.jeeves_persona.find_one({"_key": "famous_quotes"})
        if not q:
            return {}
        quotes = q.get("data", [])
        if isinstance(quotes, dict):
            quotes = sum(quotes.values(), []) if all(isinstance(v, list) for v in quotes.values()) else list(quotes.values())
        if theme:
            quotes = [x for x in quotes if isinstance(x, dict) and theme.lower() in (str(x.get("theme","")) + " " + str(x.get("tags",""))).lower()]
        return random.choice(quotes) if quotes else {}
    except Exception:
        return {}
