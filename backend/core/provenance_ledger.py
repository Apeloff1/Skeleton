"""
core/provenance_ledger.py — CRYPTOGRAPHIC PROVENANCE (Segments 4-5).

An append-only, tamper-evident event chain per build. Every event is hashed
with the previous event's hash (a hash chain / mini-blockchain), so any later
mutation of historical events is detectable by re-walking the chain.

    hash_n = sha256( prev_hash || canonical_json(payload_n) )

This gives every generated artifact a verifiable provenance trail (who/what/when
produced it) and powers the "verification pass" the GateController consults
before promotion.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time

GENESIS = "0" * 64


def _chain_key() -> bytes:
    """Server-side secret keying the chain MAC. Sourced from env so the head
    cannot be recomputed by anyone without the key (tamper-evident even against
    direct DB edits). Falls back to a stable per-deployment value derived from
    MONGO_URL so the chain still verifies if PROVENANCE_SECRET is unset."""
    secret = os.environ.get("PROVENANCE_SECRET") or os.environ.get("MONGO_URL") or "emergent-provenance-v1"
    return hashlib.sha256(secret.encode("utf-8")).digest()


def _canon(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def _hash(prev_hash: str, payload: dict) -> str:
    """Keyed MAC over (prev_hash || canonical(payload)) — HMAC-SHA256."""
    msg = (prev_hash + _canon(payload)).encode("utf-8")
    return hmac.new(_chain_key(), msg, hashlib.sha256).hexdigest()


def _coll():
    from core.databases import get_sync_db
    return get_sync_db()["galaxy_provenance"]


def append(build_id: str, kind: str, data: dict | None = None,
           agent: str = "system", model: str | None = None) -> dict:
    """Append an event to the build's chain. Returns the sealed event."""
    try:
        col = _coll()
        last = list(col.find({"build_id": build_id}).sort("seq", -1).limit(1))
        seq = (last[0]["seq"] + 1) if last else 0
        prev_hash = last[0]["hash"] if last else GENESIS
        payload = {"seq": seq, "build_id": build_id, "kind": kind,
                   "agent": agent, "model": model, "ts": time.time(),
                   "data": data or {}}
        h = _hash(prev_hash, payload)
        event = {**payload, "prev_hash": prev_hash, "hash": h,
                 "_id": f"{build_id}:{seq}"}
        col.insert_one(event)
        event.pop("_id", None)
        return event
    except Exception as e:
        return {"error": str(e), "build_id": build_id, "kind": kind}


def chain(build_id: str, limit: int = 200) -> dict:
    rows = []
    try:
        rows = list(_coll().find({"build_id": build_id}, {"_id": 0})
                    .sort("seq", 1).limit(limit))
    except Exception:
        pass
    return {"build_id": build_id, "length": len(rows), "events": rows,
            "head": rows[-1]["hash"] if rows else GENESIS}


def verify(build_id: str) -> dict:
    """Re-walk the chain and confirm every link's hash is intact."""
    try:
        rows = list(_coll().find({"build_id": build_id}, {"_id": 0}).sort("seq", 1))
    except Exception as e:
        return {"valid": False, "error": str(e)}
    prev = GENESIS
    broken = []
    for i, ev in enumerate(rows):
        payload = {"seq": ev["seq"], "build_id": ev["build_id"], "kind": ev["kind"],
                   "agent": ev.get("agent"), "model": ev.get("model"),
                   "ts": ev["ts"], "data": ev.get("data", {})}
        expect = _hash(prev, payload)
        if ev.get("prev_hash") != prev or ev.get("hash") != expect:
            broken.append({"seq": ev["seq"], "kind": ev["kind"]})
        prev = ev.get("hash", prev)
    return {"build_id": build_id, "length": len(rows), "valid": not broken,
            "broken_links": broken, "head": prev}


def artifact_provenance(build_id: str, gid: str) -> dict:
    """All chain events that reference a given gamefile id."""
    ev = chain(build_id, limit=1000)["events"]
    hits = [e for e in ev if (e.get("data") or {}).get("gid") == gid
            or (e.get("data") or {}).get("id") == gid]
    return {"build_id": build_id, "gid": gid, "events": hits, "count": len(hits)}
