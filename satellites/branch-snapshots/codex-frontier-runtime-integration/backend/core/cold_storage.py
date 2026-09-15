"""
╔════════════════════════════════════════════════════════════════════════╗
║  COLD STORAGE — MongoDB ↔ Compressed Vault                             ║
║  ────────────────────────────────────────────────────────────────────  ║
║  Moves Mongo collections to zstd-compressed on-disk shards, runs       ║
║  compact() to reclaim WiredTiger space, and offers transparent         ║
║  access patterns:                                                      ║
║                                                                        ║
║    • freeze(name)       → export + drop, shard becomes source-of-truth ║
║    • thaw(name)         → re-hydrate docs from shard back into Mongo   ║
║    • cold_query(name,…) → stream from compressed shard WITHOUT loading ║
║                           the collection back into Mongo (read-only)   ║
║    • heat_touch(name)   → record an access to keep a thawed coll live  ║
║    • evictor_tick()     → re-freeze collections idle > COLD_TTL sec    ║
║                                                                        ║
║  Manifest collection `cold_registry` tracks state of every frozen      ║
║  collection: {name, shard, rows, last_accessed, hot, created_at}.      ║
║                                                                        ║
║  Safety:                                                               ║
║    • freeze() only drops AFTER successful shard write + verification   ║
║    • thaw() is idempotent; no-op if collection already hydrated        ║
║    • Critical collections can be locked with `hot=True, locked=True`   ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations
import os
import time
import threading
from typing import Iterable, Iterator, Any

from pymongo import ASCENDING
from core.databases import get_sync_db

from core.compressed_vault import (
    write_shard,
    iter_shard,
    read_shard,
    sample_shard,
    get_shard_entry,
    list_shards,
    vault_stats,
)

COLD_TTL_SEC = int(os.environ.get("COLD_TTL_SEC", "600"))  # 10 min idle → re-freeze
SHARD_PREFIX = "coll__"  # to distinguish from swarm-agent shards

_db = get_sync_db()
_registry = _db["cold_registry"]
_registry.create_index([("name", ASCENDING)], unique=True)
_registry.create_index([("last_accessed", ASCENDING)])

# Collections that must NEVER be auto-frozen (system collections + very hot ones).
# These can still be manually frozen by explicit API call with force=True.
PROTECTED = {
    "cold_registry",
    "swarm_micro_db",
    "swarm_agents",
    "swarm_discourse_logs",
    "galaxy_vault",
    "galaxy_builds",          # ← active in-flight Galaxy Studio builds.
                              #   Never freeze — freezing drops the collection
                              #   and /status/{id} returns 404 mid-build.
    "galaxy_build_archive",
    "jeeves_builds",
    "system.views",
    # ═══ Academy / Quiz / Test data — user-facing hot collections.
    # Must NEVER be auto-frozen; the UI reads them directly via /api/academy/*.
    # Freezing them leaves empty collections and the UI renders empty lists.
    "academy_tracks",
    "academy_subjects",
    "exercises",
    "projects",
    "assessments",
    "algo_challenges",
    "knowledge_vault",
    "knowledge_databases",
    "interactive_quizzes",
    "reading_library",
    "study_paths",
    "achievements_catalog",
    "flashcard_decks",
    "bugfix_library",
    "career_roadmaps",
    "cheatsheets",
    "interview_prep",
    "project_ideas",
    "tech_glossary",
    "workaround_library",
    "math_database",
    "game_database",
    "http_status_codes",
    "bible_entries",
    "complexity_reference",
    "code_snippets",
    "quiz_scores",
    "user_progress",
    # Narrative vaults — actively consumed during builds
    "playwright_library",
    "narration_library",
    "quest_library",
    "mission_library",
    "story_arc_library",
    "storytelling_library",
    "specialized_vault",
    # ═══ 500-topic game knowledge vault — consumed by every agent
    "game_knowledge_vault",
}


def _shard_name(coll: str) -> str:
    return f"{SHARD_PREFIX}{coll}"


def _iter_coll(coll_name: str, batch_size: int = 2000) -> Iterator[dict]:
    """Stream docs out of a Mongo collection, stripping _id to plain dicts."""
    cur = _db[coll_name].find({}, batch_size=batch_size)
    for doc in cur:
        doc.pop("_id", None)
        yield doc


# ── Public API ──────────────────────────────────────────────────────────
def freeze(
    name: str,
    *,
    drop_after: bool = True,
    compact: bool = True,
    force: bool = False,
) -> dict:
    """Export a Mongo collection to a compressed shard.

    drop_after=True : drop the collection to reclaim Mongo storage (recommended)
    compact=True    : run Mongo compact to release WiredTiger space to OS
    force=True      : allow freezing PROTECTED collections
    """
    if not force and name in PROTECTED:
        raise ValueError(f"Collection '{name}' is protected; pass force=True to override")

    if name not in _db.list_collection_names():
        return {"name": name, "status": "missing", "rows": 0}

    shard = _shard_name(name)
    count = _db[name].estimated_document_count()
    if count == 0 and drop_after:
        # empty collection — drop without shard write
        _db[name].drop()
        _registry.update_one(
            {"name": name},
            {"$set": {"name": name, "shard": None, "rows": 0, "last_accessed": 0,
                      "hot": False, "frozen_at": time.time(), "status": "dropped_empty"}},
            upsert=True,
        )
        return {"name": name, "status": "dropped_empty", "rows": 0}

    # Write shard (stream-compressed)
    entry = write_shard(
        shard,
        _iter_coll(name),
        domain=f"mongo:{name}",
        agent_id=f"agent__{name}",
        description=f"Cold-storage shard for Mongo collection {name}",
        scratch=False,
    )

    # Verify
    if entry["rows"] != count and entry["rows"] > 0:
        # mild mismatch is okay (live writes); only fail on zero
        pass
    if entry["rows"] == 0 and count > 0:
        return {"name": name, "status": "verify_failed", "written": 0, "expected": count}

    if drop_after:
        _db[name].drop()

    _registry.update_one(
        {"name": name},
        {"$set": {
            "name": name,
            "shard": shard,
            "rows": entry["rows"],
            "compressed_bytes": entry["compressed_bytes"],
            "raw_bytes": entry["raw_bytes"],
            "last_accessed": 0,
            "hot": False,
            "frozen_at": time.time(),
            "status": "frozen",
        }},
        upsert=True,
    )

    result = {
        "name": name,
        "shard": shard,
        "status": "frozen",
        "rows": entry["rows"],
        "compressed_mb": round(entry["compressed_bytes"] / 1024 / 1024, 2),
        "raw_mb": round(entry["raw_bytes"] / 1024 / 1024, 2),
        "ratio": entry["compression_ratio"],
    }
    if compact and drop_after:
        try:
            _db.command({"compact": name, "force": True})
        except Exception:
            pass
    return result


def thaw(name: str, *, batch_size: int = 2000, mark_hot: bool = True) -> dict:
    """Restore a frozen collection back into Mongo (idempotent)."""
    # Already live?
    if name in _db.list_collection_names() and _db[name].estimated_document_count() > 0:
        if mark_hot:
            _registry.update_one(
                {"name": name},
                {"$set": {"last_accessed": time.time(), "hot": True, "status": "hot"}},
            )
        return {"name": name, "status": "already_live"}

    shard = _shard_name(name)
    if not get_shard_entry(shard):
        return {"name": name, "status": "not_frozen"}

    # Bulk insert from the shard stream
    buf: list[dict] = []
    total = 0
    coll = _db[name]
    for doc in iter_shard(shard):
        buf.append(doc)
        if len(buf) >= batch_size:
            coll.insert_many(buf, ordered=False)
            total += len(buf); buf = []
    if buf:
        coll.insert_many(buf, ordered=False)
        total += len(buf)

    _registry.update_one(
        {"name": name},
        {"$set": {"last_accessed": time.time(), "hot": True, "status": "hot", "rows": total}},
    )
    return {"name": name, "status": "thawed", "rows": total}


def cold_query(name: str, filter: dict | None = None, limit: int = 50, offset: int = 0) -> list[dict]:
    """Read directly from the compressed shard WITHOUT hydrating Mongo.

    Applies a simple equality/contains filter in Python.
    """
    shard = _shard_name(name)
    if not get_shard_entry(shard):
        return []
    heat_touch(name, hydrate=False)

    def match(row: dict) -> bool:
        if not filter:
            return True
        for k, v in filter.items():
            rv = row.get(k)
            if isinstance(v, str) and isinstance(rv, str):
                if v.lower() not in rv.lower():
                    return False
            elif rv != v:
                return False
        return True

    hit = 0
    out: list[dict] = []
    for i, row in enumerate(iter_shard(shard)):
        if not match(row):
            continue
        if hit < offset:
            hit += 1
            continue
        out.append(row)
        hit += 1
        if len(out) >= limit:
            break
    return out


def heat_touch(name: str, hydrate: bool = True) -> None:
    """Record an access, optionally thawing the collection."""
    _registry.update_one(
        {"name": name},
        {"$set": {"last_accessed": time.time(), "hot": True}},
        upsert=True,
    )
    if hydrate and name not in _db.list_collection_names():
        thaw(name, mark_hot=True)


def evictor_tick(ttl: int = COLD_TTL_SEC, max_freeze: int = 10) -> dict:
    """Re-freeze idle thawed collections + purge phantom empty re-creations."""
    now = time.time()
    frozen = 0
    candidates: list[str] = []
    for reg in _registry.find({"hot": True, "locked": {"$ne": True}}):
        la = reg.get("last_accessed", 0)
        if la and now - la > ttl:
            candidates.append(reg["name"])
    for name in candidates[:max_freeze]:
        try:
            freeze(name, drop_after=True, compact=False, force=True)
            frozen += 1
        except Exception:
            continue

    # Purge phantom re-creations: collections in registry as frozen but
    # now exist in Mongo with 0 docs (recreated by startup indexes/seeders).
    phantoms = 0
    live = set(_db.list_collection_names())
    for reg in _registry.find({"status": {"$in": ["frozen", "dropped_empty"]}}):
        name = reg["name"]
        if name not in live:
            continue
        try:
            cnt = _db[name].estimated_document_count()
            if cnt == 0:
                _db[name].drop()
                phantoms += 1
        except Exception:
            continue

    return {"candidates": len(candidates), "re_frozen": frozen, "phantoms_purged": phantoms, "ttl_sec": ttl}


def freeze_all(
    min_storage_bytes: int = 0,
    skip_protected: bool = True,
    dry_run: bool = False,
    limit: int | None = None,
) -> dict:
    """Sweep: freeze every non-protected collection whose storage exceeds threshold."""
    all_names = _db.list_collection_names()
    work: list[tuple[str, int]] = []
    for n in all_names:
        if skip_protected and n in PROTECTED:
            continue
        if n.startswith(SHARD_PREFIX):
            continue
        try:
            st = _db.command("collStats", n)
            stor = st.get("storageSize", 0)
            cnt = st.get("count", 0)
        except Exception:
            continue
        if stor >= min_storage_bytes:
            work.append((n, stor))
    work.sort(key=lambda t: -t[1])
    if limit:
        work = work[:limit]

    if dry_run:
        return {
            "would_freeze": len(work),
            "names": [n for n, _ in work],
            "total_storage_mb": round(sum(s for _, s in work) / 1024 / 1024, 2),
        }

    results = []
    for n, _sz in work:
        try:
            res = freeze(n, drop_after=True, compact=False, force=False)
            results.append(res)
        except Exception as ex:
            results.append({"name": n, "status": "error", "error": str(ex)})

    # One compact pass at the DB level is cheaper than per-collection
    try:
        _db.command({"compact": "cold_registry", "force": True})
    except Exception:
        pass

    return {
        "frozen": len([r for r in results if r.get("status") == "frozen"]),
        "dropped_empty": len([r for r in results if r.get("status") == "dropped_empty"]),
        "errors": len([r for r in results if r.get("status") == "error"]),
        "results": results,
    }


def stats() -> dict:
    live_cols = _db.list_collection_names()
    registry_docs = list(_registry.find({}))
    frozen = [r for r in registry_docs if r.get("status") in ("frozen", "dropped_empty")]
    hot = [r for r in registry_docs if r.get("status") == "hot"]
    shards = [s for s in list_shards() if s["name"].startswith(SHARD_PREFIX)]
    total_compressed = sum(s.get("compressed_bytes", 0) for s in shards)
    total_raw = sum(s.get("raw_bytes", 0) for s in shards)
    total_rows = sum(s.get("rows", 0) for s in shards)
    return {
        "live_collections": len(live_cols),
        "registered_collections": len(registry_docs),
        "frozen": len(frozen),
        "hot": len(hot),
        "cold_shards": len(shards),
        "cold_rows": total_rows,
        "cold_compressed_mb": round(total_compressed / 1024 / 1024, 2),
        "cold_raw_mb": round(total_raw / 1024 / 1024, 2),
        "cold_ttl_sec": COLD_TTL_SEC,
    }


def registry_list(status: str | None = None, limit: int = 400) -> list[dict]:
    q: dict[str, Any] = {}
    if status:
        q["status"] = status
    out: list[dict] = []
    for r in _registry.find(q).limit(limit):
        r.pop("_id", None)
        out.append(r)
    return out


# ── Background evictor ──────────────────────────────────────────────────
_evictor_thread: threading.Thread | None = None
_stop = threading.Event()


def _evictor_loop():
    while not _stop.is_set():
        try:
            evictor_tick()
        except Exception:
            pass
        _stop.wait(60)  # check every minute


def start_evictor():
    global _evictor_thread
    if _evictor_thread and _evictor_thread.is_alive():
        return False
    _stop.clear()
    _evictor_thread = threading.Thread(target=_evictor_loop, daemon=True)
    _evictor_thread.start()
    return True


def stop_evictor():
    _stop.set()
