"""
core/build_ledger.py — PER-BUILD CONTEXT DATABASE.

A single, queryable ledger that logs EVERYTHING that happens to one build:
  • spec (genre/era/dimension/seed)
  • every snowball choice (mirrored from game_choices)
  • every advanced axis selection + the concrete derived directives
  • every system generated/mounted (Systems Forge)
  • gate runs, forged items, and any other build event

Two Mongo collections:
  • galaxy_build_ledger   — append-only event stream (one doc per event)
  • galaxy_build_context  — one rolling summary doc per build (the "context")

Everything degrades gracefully to an in-memory mirror if the DB is unavailable,
so logging never breaks a build.
"""
from __future__ import annotations

import time
from typing import Any

_MEM: dict[str, list[dict]] = {}
_CTX: dict[str, dict] = {}

LEDGER_COL = "galaxy_build_ledger"
CONTEXT_COL = "galaxy_build_context"


def _db():
    from core.databases import get_sync_db
    return get_sync_db()


def log(build_id: str, kind: str, data: dict | None = None,
        step: str | None = None) -> dict:
    """Append one event to the build ledger and fold it into the build context.

    kind ∈ {spec, snowball_choice, axis_selection, system_generated,
            system_context, gate_run, item_forged, build_event, ...}
    """
    if not build_id:
        return {"error": "missing_build_id"}
    data = data or {}
    seq = len(_MEM.get(build_id, [])) + 1
    entry = {"build_id": build_id, "kind": kind, "step": step,
             "data": data, "ts": time.time(), "seq": seq}
    _MEM.setdefault(build_id, []).append(entry)
    _fold_context(build_id, kind, data)
    try:
        db = _db()
        col = db[LEDGER_COL]
        col.create_index([("build_id", 1), ("seq", 1)])
        col.insert_one({**entry})
        db[CONTEXT_COL].replace_one({"_id": build_id}, _CTX[build_id], upsert=True)
    except Exception:
        pass
    return entry


def _fold_context(build_id: str, kind: str, data: dict) -> None:
    ctx = _CTX.setdefault(build_id, {
        "_id": build_id, "build_id": build_id, "created": time.time(),
        "spec": {}, "snowball_choices": 0, "axis_selections": {},
        "axis_directives": {}, "systems": [], "systems_count": 0,
        "gate_runs": 0, "items_forged": 0, "events": 0, "kinds": {},
        "advanced_axes_picked": 0,
    })
    ctx["updated"] = time.time()
    ctx["events"] = ctx.get("events", 0) + 1
    ctx["kinds"][kind] = ctx["kinds"].get(kind, 0) + 1
    if kind == "spec":
        ctx["spec"].update({k: v for k, v in data.items() if v is not None})
    elif kind == "snowball_choice":
        ctx["snowball_choices"] += 1
        c = data.get("choice") or {}
        for key in ("era", "genre", "seed", "dimension"):
            if c.get(key) is not None:
                ctx["spec"][key] = c[key]
    elif kind == "axis_selection":
        applied = data.get("applied") or {}
        ctx["axis_selections"].update(applied)
        ctx["axis_directives"].update(data.get("directives") or {})
        ctx["advanced_axes_picked"] = ctx.get("advanced_axes_picked", 0) + int(data.get("advanced_count", 0))
    elif kind in ("system_generated", "system_mounted"):
        sysk = data.get("system")
        if sysk and sysk not in ctx["systems"]:
            ctx["systems"].append(sysk)
        ctx["systems_count"] = len(ctx["systems"])
    elif kind == "gate_run":
        ctx["gate_runs"] += 1
    elif kind == "item_forged":
        ctx["items_forged"] += 1


def get_ledger(build_id: str, limit: int = 1000, kind: str | None = None) -> dict:
    rows: list[dict] = []
    try:
        q: dict[str, Any] = {"build_id": build_id}
        if kind:
            q["kind"] = kind
        rows = list(_db()[LEDGER_COL].find(q, {"_id": 0}).sort("seq", 1).limit(limit))
    except Exception:
        rows = list(_MEM.get(build_id, []))
        if kind:
            rows = [r for r in rows if r["kind"] == kind]
        rows = rows[:limit]
    return {"build_id": build_id, "count": len(rows), "events": rows}


def get_context(build_id: str) -> dict:
    try:
        doc = _db()[CONTEXT_COL].find_one({"_id": build_id}, {"_id": 0})
        if doc:
            return doc
    except Exception:
        pass
    return _CTX.get(build_id, {"build_id": build_id, "events": 0, "spec": {}})


def list_builds(limit: int = 200) -> dict:
    builds: list[dict] = []
    try:
        builds = list(_db()[CONTEXT_COL].find({}, {"_id": 0})
                      .sort("updated", -1).limit(limit))
    except Exception:
        builds = list(_CTX.values())[:limit]
    return {"count": len(builds), "builds": builds}
