"""
core/feature_flags.py — Dynamic feature-flag service (P3, Feb 2026).

A tiny, fast, dependency-light feature-flag engine that:

  • Stores flags in `core_db.feature_flags` (small / migrated to prod).
  • Caches the whole flag set in process memory for ``CACHE_TTL`` seconds.
  • Tracks a monotonic ``_version`` so ETag/304 conditional GETs work.
  • Supports environment scoping, percent rollout, and per-user overrides
    via a stable string hash (so the same user always gets the same bucket).
  • Seeds a default set on first read so the app always boots with a
    sensible baseline even if Mongo is empty.
  • Bumps a Prometheus counter (core/feature_flags_metrics) on every
    resolve so we can see flag usage in /api/metrics.

The shape of a stored flag document::

    {
        "_id": "hub.network_banner",
        "name": "hub.network_banner",
        "description": "Show offline banner on the hub screen.",
        "enabled":  true,
        "rollout":  100,                      # 0-100, applied if enabled
        "environments": ["dev", "staging", "production"],
        "overrides": {"user_123": True, ...}, # explicit per-user truth
        "updated_at": "...",
    }
"""
from __future__ import annotations

import hashlib
import os
import time
from typing import Any

from core.databases import core_db

try:
    from core import feature_flags_metrics as _metrics
except Exception:  # pragma: no cover
    _metrics = None  # type: ignore

ENVIRONMENT: str = os.environ.get("APP_ENV") or os.environ.get("ENVIRONMENT") or "dev"
COLLECTION = "feature_flags"
CACHE_TTL_S: float = float(os.environ.get("FEATURE_FLAGS_CACHE_TTL_S", "60"))

DEFAULT_FLAGS: list[dict[str, Any]] = [
    {"name": "hub.network_banner",        "description": "Show an offline/slow-network banner on the Hub screen.",      "enabled": True,  "rollout": 100, "environments": []},
    {"name": "hub.command_palette",       "description": "Enable the Cmd/Ctrl-K command palette overlay.",              "enabled": True,  "rollout": 100, "environments": []},
    {"name": "hub.lazy_modals",           "description": "Defer mounting heavy modal subtrees until they open.",        "enabled": True,  "rollout": 100, "environments": []},
    {"name": "boot.starfall_background",  "description": "Render the Starfall WebGL backdrop on the welcome screen.",    "enabled": True,  "rollout": 100, "environments": []},
    {"name": "experimental.live_collab_v2", "description": "Use the v2 live-collab engine (CRDT-based).",                "enabled": False, "rollout":  10, "environments": ["dev", "staging"]},
    {"name": "experimental.ai_pipeline_v3", "description": "Route AI pipeline calls through the new v3 orchestrator.",   "enabled": False, "rollout":   0, "environments": ["dev"]},
    {"name": "ux.reduce_motion_strict",   "description": "Disable every non-essential animation (stronger than OS RM).", "enabled": False, "rollout": 100, "environments": []},
    {"name": "observability.frontend_breadcrumbs", "description": "Ship the in-memory breadcrumb trail with error reports.", "enabled": True, "rollout": 100, "environments": []},
]


# ─────────────────────────────────────────────────────────────────────
# In-process cache + version counter for ETag support.
# ─────────────────────────────────────────────────────────────────────
_cache: dict[str, Any] = {
    "ts": 0.0,
    "flags": {},
    "version": 0,        # bumped on every mutation
}


def cache_version() -> int:
    """Used by route handlers to compute the ETag."""
    return int(_cache["version"])


def _bucket(user_id: str, name: str) -> int:
    h = hashlib.md5(f"{user_id}|{name}".encode()).hexdigest()
    return int(h[:8], 16) % 100


def _matches_env(doc: dict[str, Any]) -> bool:
    envs = doc.get("environments") or []
    return (not envs) or (ENVIRONMENT in envs)


def _resolve(doc: dict[str, Any], user_id: str | None) -> bool:
    if not doc.get("enabled"):           return False
    if not _matches_env(doc):            return False

    if user_id:
        overrides = doc.get("overrides") or {}
        if user_id in overrides:
            return bool(overrides[user_id])

    rollout = int(doc.get("rollout") or 100)
    if rollout >= 100: return True
    if rollout <= 0:   return False
    return _bucket(user_id or "_anon_", doc["name"]) < rollout


async def _seed_defaults() -> None:
    try:
        coll = core_db[COLLECTION]
        existing = set(await coll.distinct("name") or [])
        now = time.time()
        to_insert = [
            {"_id": f["name"], **f, "overrides": {}, "created_at": now, "updated_at": now}
            for f in DEFAULT_FLAGS if f["name"] not in existing
        ]
        if to_insert:
            await coll.insert_many(to_insert, ordered=False)
    except Exception as e:
        print(f"[feature_flags] seed error: {type(e).__name__}: {e}", flush=True)


async def _refresh_cache(force: bool = False) -> None:
    if not force and (time.time() - _cache["ts"]) < CACHE_TTL_S and _cache["flags"]:
        return
    try:
        coll = core_db[COLLECTION]
        if not await coll.estimated_document_count():
            await _seed_defaults()
        docs = await coll.find({}).to_list(length=500)
        _cache["flags"] = {(d.get("name") or d.get("_id")): d for d in docs}
        _cache["ts"] = time.time()
    except Exception as e:
        print(f"[feature_flags] refresh error: {type(e).__name__}: {e}", flush=True)
        if not _cache["flags"]:
            _cache["flags"] = {
                f["name"]: {"_id": f["name"], **f, "overrides": {}} for f in DEFAULT_FLAGS
            }
            _cache["ts"] = time.time()


def _bump_version() -> None:
    _cache["version"] = int(_cache.get("version", 0)) + 1


# ─────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────
async def list_flags(user_id: str | None = None, *, include_admin_fields: bool = False) -> list[dict[str, Any]]:
    await _refresh_cache()
    out: list[dict[str, Any]] = []
    for doc in _cache["flags"].values():
        resolved = _resolve(doc, user_id)
        # Best-effort metric — never blocks.
        if _metrics:
            try: _metrics.inc_resolved(doc.get("name") or "", ENVIRONMENT, resolved)
            except Exception: pass
        item = {
            "name": doc.get("name"),
            "description": doc.get("description") or "",
            "enabled": bool(doc.get("enabled")),
            "rollout": int(doc.get("rollout") or 0),
            "environments": list(doc.get("environments") or []),
            "resolved": resolved,
            "updated_at": doc.get("updated_at"),
        }
        if include_admin_fields:
            item["overrides"] = dict(doc.get("overrides") or {})
            item["created_at"] = doc.get("created_at")
        out.append(item)
    out.sort(key=lambda x: x["name"])
    return out


async def get_flag(name: str) -> dict[str, Any] | None:
    await _refresh_cache()
    return _cache["flags"].get(name)


async def is_enabled(name: str, user_id: str | None = None) -> bool:
    await _refresh_cache()
    doc = _cache["flags"].get(name)
    if not doc: return False
    val = _resolve(doc, user_id)
    if _metrics:
        try: _metrics.inc_resolved(name, ENVIRONMENT, val)
        except Exception: pass
    return val


def is_enabled_cached(name: str, user_id: str | None = None) -> bool:
    doc = _cache["flags"].get(name)
    if not doc: return False
    return _resolve(doc, user_id)


async def upsert_flag(
    name: str,
    *,
    enabled: bool | None = None,
    rollout: int | None = None,
    description: str | None = None,
    environments: list[str] | None = None,
    overrides: dict[str, bool] | None = None,
) -> dict[str, Any]:
    coll = core_db[COLLECTION]
    now = time.time()
    update: dict[str, Any] = {"updated_at": now, "name": name}
    if enabled is not None:         update["enabled"] = bool(enabled)
    if rollout is not None:         update["rollout"] = max(0, min(100, int(rollout)))
    if description is not None:     update["description"] = str(description)
    if environments is not None:    update["environments"] = list(environments)
    if overrides is not None:       update["overrides"] = {str(k): bool(v) for k, v in overrides.items()}

    await coll.update_one(
        {"_id": name},
        {"$set": update, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )
    await _refresh_cache(force=True)
    _bump_version()
    return _cache["flags"].get(name) or update


async def bulk_upsert(updates: list[dict[str, Any]]) -> int:
    """Apply a list of flag-update dicts in one DB round-trip."""
    if not updates: return 0
    coll = core_db[COLLECTION]
    now = time.time()
    from pymongo import UpdateOne
    ops = []
    for u in updates:
        name = u.get("name")
        if not name: continue
        body: dict[str, Any] = {"updated_at": now, "name": name}
        for k in ("enabled", "rollout", "description", "environments", "overrides"):
            if k in u and u[k] is not None:
                body[k] = u[k]
        ops.append(UpdateOne(
            {"_id": name},
            {"$set": body, "$setOnInsert": {"created_at": now}},
            upsert=True,
        ))
    if not ops: return 0
    r = await coll.bulk_write(ops, ordered=False)
    await _refresh_cache(force=True)
    _bump_version()
    return int((r.upserted_count or 0) + (r.modified_count or 0))


async def delete_flag(name: str) -> bool:
    coll = core_db[COLLECTION]
    r = await coll.delete_one({"_id": name})
    await _refresh_cache(force=True)
    if r.deleted_count:
        _bump_version()
    return bool(r.deleted_count)


async def health() -> dict[str, Any]:
    await _refresh_cache()
    total = len(_cache["flags"])
    on = sum(1 for d in _cache["flags"].values() if d.get("enabled"))
    return {
        "ok": True,
        "environment": ENVIRONMENT,
        "total_flags": total,
        "enabled_flags": on,
        "cache_age_s": round(time.time() - _cache["ts"], 2),
        "cache_ttl_s": CACHE_TTL_S,
        "version": cache_version(),
    }


async def ensure_indexes() -> None:
    """Idempotent — creates a fast lookup index on flag name."""
    try:
        await core_db[COLLECTION].create_index("name", unique=True)
        await core_db[COLLECTION].create_index([("updated_at", -1)])
    except Exception as e:
        print(f"[feature_flags] index error: {type(e).__name__}: {e}", flush=True)


async def warmup() -> None:
    await _refresh_cache(force=True)
    await ensure_indexes()
