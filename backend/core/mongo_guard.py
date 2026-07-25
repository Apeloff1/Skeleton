"""
core/mongo_guard.py — Idempotency + optimistic-concurrency helpers (Stage B4).

Two primitives that make critical Mongo writes safe under retries and
concurrent writers, without forcing a rewrite of every call site:

  * ``idempotent_insert(coll, key, doc)`` — insert-once keyed by an
    idempotency key. A duplicate key is a no-op (returns ``already=True``)
    instead of creating a second row. Backed by a unique index on ``_idem``.

  * ``optimistic_update(coll, filter, updates, expected_version)`` — compare-
    and-swap: the update only applies if the stored ``_ver`` matches
    ``expected_version``; on success ``_ver`` is bumped. A version mismatch
    (a concurrent writer won) returns ``ok=False`` so the caller can retry.

Both accept a *synchronous* pymongo collection (``core.databases.get_sync_db``)
and are safe to call from anywhere. They never raise on transient DB errors —
they return a status dict so callers can decide policy.
"""
from __future__ import annotations

import time
import uuid
from typing import Any, Dict, Optional


def new_idempotency_key() -> str:
    """Mint a fresh idempotency key (callers may also supply their own)."""
    return uuid.uuid4().hex


def idempotent_insert(coll, key: str, doc: Dict[str, Any]) -> Dict[str, Any]:
    """Insert ``doc`` exactly once for ``key``. Duplicate → no-op.

    A unique index on ``_idem`` is ensured lazily (idempotent, cheap after the
    first call). Returns ``{ok, already, key, id?}``.
    """
    try:
        coll.create_index("_idem", unique=True, sparse=True)
    except Exception:  # noqa: BLE001 — index may already exist / DB cold
        pass
    payload = {**doc, "_idem": key, "_idem_at": time.time()}
    try:
        res = coll.insert_one(payload)
        return {"ok": True, "already": False, "key": key, "id": str(res.inserted_id)}
    except Exception as e:  # noqa: BLE001
        # DuplicateKeyError (E11000) → the write already happened.
        if "E11000" in str(e) or "duplicate key" in str(e).lower():
            return {"ok": True, "already": True, "key": key}
        return {"ok": False, "already": False, "key": key, "error": str(e)}


def optimistic_update(coll, filter: Dict[str, Any], updates: Dict[str, Any],
                      expected_version: Optional[int] = None) -> Dict[str, Any]:
    """Compare-and-swap update guarded by a ``_ver`` field.

    If ``expected_version`` is given, the write only applies when the stored
    ``_ver`` equals it, then bumps ``_ver`` by 1. If ``None``, the current
    version is read first (read-modify-write). Returns
    ``{ok, version, conflict}``.
    """
    try:
        if expected_version is None:
            cur = coll.find_one(filter, {"_ver": 1})
            expected_version = int((cur or {}).get("_ver", 0))
        guarded = {**filter, "_ver": expected_version}
        res = coll.update_one(
            guarded,
            {"$set": {**updates, "_ver_at": time.time()}, "$inc": {"_ver": 1}},
            upsert=False,
        )
        if res.matched_count == 0:
            # either the doc doesn't exist yet, or another writer bumped _ver
            exists = coll.count_documents(filter, limit=1) > 0
            if not exists:
                # first write: create with _ver = 1
                try:
                    coll.update_one(filter, {"$set": {**updates, "_ver": 1, "_ver_at": time.time()}},
                                    upsert=True)
                    return {"ok": True, "version": 1, "conflict": False, "created": True}
                except Exception as e:  # noqa: BLE001
                    return {"ok": False, "version": expected_version, "conflict": False, "error": str(e)}
            return {"ok": False, "version": expected_version, "conflict": True}
        return {"ok": True, "version": expected_version + 1, "conflict": False}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "version": expected_version or 0, "conflict": False, "error": str(e)}


__all__ = ["new_idempotency_key", "idempotent_insert", "optimistic_update"]
