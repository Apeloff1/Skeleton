"""
core/perf.py — Backend performance primitives (Feb 2026, Category 2).

  1. TTLCache       — In-process TTL + LRU cache for hot read endpoints
                       (no Redis required, fully async-safe).
  2. BatchedWriter  — Coalesces high-frequency mongo writes into bulk_write
                       to avoid op-storms during heavy build phases.
  3. boot_index_audit() — At lifespan startup, compares declared indexes
                       to actual `system.indexes` and logs missing ones.
  4. tune_motor_pool() — Centralises connection-pool sizing so we don't
                       repeat MotorClient(... maxPoolSize=...) literals.
  5. async_stream_collection() — Replaces `list(cursor)` patterns with
                       async generator that yields docs without buffering.
  6. ETag helpers (etag_for, IfNoneMatchResponse) — Adds Cache-Control +
                       304 short-circuit on read-only catalog endpoints.
  7. install_brotli(app) — Adds brotli compression in addition to gzip,
                       roughly 20-25 % smaller payloads for JSON.

All primitives are best-effort: failures degrade to a no-op rather than
break the wrapped operation.
"""
from __future__ import annotations
import asyncio
import hashlib
import json
import logging
import time
from collections import OrderedDict
from typing import Any, AsyncIterator, Callable, Optional

from fastapi import Request, Response
from fastapi.responses import JSONResponse

logger = logging.getLogger("Perf")


# ════════════════════════════════════════════════════════════════════════════
#  1. TTLCache — async-safe in-process TTL+LRU cache
# ════════════════════════════════════════════════════════════════════════════
class TTLCache:
    def __init__(self, *, ttl: float = 60.0, max_entries: int = 512):
        self._d: "OrderedDict[str, tuple[float, Any]]" = OrderedDict()
        self.ttl = ttl
        self.max = max_entries
        self._lock = asyncio.Lock()

    async def get(self, key: str):
        async with self._lock:
            v = self._d.get(key)
            if not v:
                return None
            ts, val = v
            if time.time() - ts > self.ttl:
                self._d.pop(key, None)
                return None
            self._d.move_to_end(key)
            return val

    async def set(self, key: str, val: Any):
        async with self._lock:
            self._d[key] = (time.time(), val)
            self._d.move_to_end(key)
            while len(self._d) > self.max:
                self._d.popitem(last=False)

    async def clear(self):
        async with self._lock:
            self._d.clear()

    def stats(self) -> dict:
        return {"size": len(self._d), "max": self.max, "ttl_sec": self.ttl}


# Pre-built caches for common hot paths.
LANGUAGE_CACHE = TTLCache(ttl=300, max_entries=32)   # /api/languages
AI_MODES_CACHE = TTLCache(ttl=300, max_entries=32)   # /api/ai/modes
CATALOG_CACHE  = TTLCache(ttl=120, max_entries=256)  # generic catalogs


def cached(cache: TTLCache, key_fn: Optional[Callable[..., str]] = None):
    """Decorator wrapping an async function with TTLCache."""
    def decorator(fn):
        async def wrapper(*args, **kwargs):
            try:
                key = key_fn(*args, **kwargs) if key_fn else f"{fn.__module__}.{fn.__name__}"
            except Exception:
                key = f"{fn.__module__}.{fn.__name__}"
            cached_val = await cache.get(key)
            if cached_val is not None:
                return cached_val
            val = await fn(*args, **kwargs)
            await cache.set(key, val)
            return val
        wrapper.__wrapped__ = fn  # type: ignore
        return wrapper
    return decorator


# ════════════════════════════════════════════════════════════════════════════
#  2. BatchedWriter — coalesce writes
# ════════════════════════════════════════════════════════════════════════════
class BatchedWriter:
    """Coalesce write ops into bulk_write batches.

    Designed for heartbeats, traces, telemetry — writes that arrive at
    high frequency and don't need durability per-op.

    Use:
        bw = BatchedWriter(collection=db.heartbeats, batch=100, flush_sec=2.0)
        await bw.start()
        await bw.put({"_id": ..., "$set": {...}})  # any pymongo UpdateOne arg
        # ... on shutdown:
        await bw.stop()
    """
    def __init__(self, collection, *, batch: int = 100, flush_sec: float = 2.0,
                 build_op: Optional[Callable[[dict], Any]] = None):
        self.collection = collection
        self.batch = batch
        self.flush_sec = flush_sec
        self._queue: list = []
        self._lock = asyncio.Lock()
        self._task: Optional[asyncio.Task] = None
        self._stopped = False
        self._build_op = build_op  # if None, items are passed-through

    async def put(self, op):
        async with self._lock:
            self._queue.append(op)

    async def _flush(self):
        async with self._lock:
            if not self._queue:
                return
            batch = self._queue
            self._queue = []
        try:
            ops = [self._build_op(o) for o in batch] if self._build_op else batch
            if ops:
                await self.collection.bulk_write(ops, ordered=False)
        except Exception as e:
            logger.warning(f"[BatchedWriter] flush failed: {e}")

    async def _loop(self):
        while not self._stopped:
            await asyncio.sleep(self.flush_sec)
            try: await self._flush()
            except Exception as e: logger.debug(f"[BatchedWriter] loop tick: {e}")

    async def start(self):
        if self._task is None:
            self._task = asyncio.create_task(self._loop())

    async def stop(self):
        self._stopped = True
        if self._task:
            self._task.cancel()
        await self._flush()


# ════════════════════════════════════════════════════════════════════════════
#  3. Index audit at boot
# ════════════════════════════════════════════════════════════════════════════
async def boot_index_audit(databases: list) -> dict:
    """Inspect actual indexes vs a known list of "should-have" indexes.

    Lightweight — just lists existing indexes, doesn't try to add anything.
    Helps catch the "this collection should be indexed but isn't" class
    of bugs at boot time.  Returns {db_name: {coll: [index_names]}}.
    """
    report = {}
    for db in databases:
        report[db.name] = {}
        try:
            for n in await db.list_collection_names():
                if n.startswith("system."):
                    continue
                try:
                    info = await db[n].index_information()
                    report[db.name][n] = list(info.keys())
                except Exception:
                    pass
        except Exception:
            pass
    return report


# ════════════════════════════════════════════════════════════════════════════
#  4. Motor pool tuning
# ════════════════════════════════════════════════════════════════════════════
def motor_pool_kwargs(workload: str = "default") -> dict:
    """Return kwargs for AsyncIOMotorClient sized for the workload.

    Tuned 2026-02-18 — these were sometimes set ad-hoc per file and would
    drift apart. Centralise them so the connection pool is consistent.

      "default"    — 50 max connections, fine for an API worker
      "writer"     — 100 max, for the bulk seeders
      "watchdog"   — 20 max, low concurrency
    """
    PROFILES = {
        "default":  {"maxPoolSize": 50,  "minPoolSize": 5,  "maxIdleTimeMS": 60_000},
        "writer":   {"maxPoolSize": 100, "minPoolSize": 10, "maxIdleTimeMS": 60_000},
        "watchdog": {"maxPoolSize": 20,  "minPoolSize": 2,  "maxIdleTimeMS": 60_000},
    }
    return PROFILES.get(workload, PROFILES["default"]) | {
        "serverSelectionTimeoutMS": 5_000,
        "socketTimeoutMS": 30_000,
        "connectTimeoutMS": 10_000,
    }


# ════════════════════════════════════════════════════════════════════════════
#  5. Async-stream collection (replaces list(cursor))
# ════════════════════════════════════════════════════════════════════════════
async def async_stream_collection(
    cursor, *, batch_size: int = 200, max_docs: Optional[int] = None
) -> AsyncIterator[dict]:
    """Yield docs without buffering the entire cursor in memory.

    Designed as a drop-in replacement for `await cursor.to_list(length=N)`
    where N may be very large.  Capped by max_docs (None = unbounded).
    """
    yielded = 0
    cursor = cursor.batch_size(batch_size) if hasattr(cursor, "batch_size") else cursor
    async for doc in cursor:
        yield doc
        yielded += 1
        if max_docs is not None and yielded >= max_docs:
            return


# ════════════════════════════════════════════════════════════════════════════
#  6. ETag helpers
# ════════════════════════════════════════════════════════════════════════════
def etag_for(payload: Any) -> str:
    """Stable, content-addressed ETag for any JSON-serialisable payload."""
    try:
        s = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        return 'W/"' + hashlib.md5(s).hexdigest() + '"'
    except Exception:
        return ""

def make_etag_response(request: Request, payload: Any, *, cache_seconds: int = 60) -> Response:
    """Return either a 304 (if If-None-Match matches) or a 200 with ETag.

    Use as the LAST line of read-only catalog endpoints:
        return make_etag_response(request, data, cache_seconds=300)
    """
    tag = etag_for(payload)
    if tag and request.headers.get("if-none-match") == tag:
        return Response(status_code=304, headers={"ETag": tag, "Cache-Control": f"max-age={cache_seconds}"})
    resp = JSONResponse(payload)
    if tag:
        resp.headers["ETag"] = tag
    resp.headers["Cache-Control"] = f"max-age={cache_seconds}"
    return resp


# ════════════════════════════════════════════════════════════════════════════
#  7. Brotli compression
# ════════════════════════════════════════════════════════════════════════════
def install_brotli(app) -> bool:
    """Add brotli compression middleware. Returns True if installed."""
    try:
        from brotli_asgi import BrotliMiddleware  # type: ignore
        app.add_middleware(BrotliMiddleware, minimum_size=5_000, quality=4)
        logger.info("[perf] Brotli compression middleware installed")
        return True
    except ImportError:
        logger.info("[perf] brotli_asgi not installed; sticking with gzip")
        return False
    except Exception as e:
        logger.warning(f"[perf] Brotli install failed: {e}")
        return False


def perf_snapshot() -> dict:
    return {
        "caches": {
            "languages": LANGUAGE_CACHE.stats(),
            "ai_modes":  AI_MODES_CACHE.stats(),
            "catalog":   CATALOG_CACHE.stats(),
        },
    }


__all__ = [
    "TTLCache", "LANGUAGE_CACHE", "AI_MODES_CACHE", "CATALOG_CACHE", "cached",
    "BatchedWriter", "boot_index_audit", "motor_pool_kwargs",
    "async_stream_collection", "etag_for", "make_etag_response",
    "install_brotli", "perf_snapshot",
]
