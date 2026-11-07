"""
╔════════════════════════════════════════════════════════════════════════╗
║  GAME CHOICES — the per-game decision ledger every agent is aware of.    ║
║  ────────────────────────────────────────────────────────────────────  ║
║  Every choice made for a game (era, genre, seed, per-stage grade floor,  ║
║  storage spend …) is LOGGED here and PARSED into an awareness context    ║
║  that the agents read on EVERY step — so each forge is consistent with    ║
║  every prior decision. Deterministic + best-effort persisted.            ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import time
from typing import Any

# In-process fallback ledger (used when no DB / persist=False).
_MEM: dict[str, list[dict]] = {}


def record(build_id: str, step: str, kind: str, choice: dict,
           persist: bool = True) -> dict:
    """Log one choice/decision for a game at a given step."""
    entry = {
        "build_id": build_id, "step": step, "kind": kind,
        "choice": choice, "ts": time.time(),
        "seq": len(_MEM.get(build_id, [])) + 1,
    }
    _MEM.setdefault(build_id, []).append(entry)
    if persist:
        try:
            from core.databases import get_sync_db
            col = get_sync_db()["galaxy_game_choices"]
            col.create_index([("build_id", 1), ("seq", 1)])
            col.insert_one({**entry})
        except Exception:
            pass
    try:
        from core import build_ledger as _bl
        _bl.log(build_id, "snowball_choice",
                {"step": step, "choice_kind": kind, "choice": choice})
    except Exception:
        pass
    return entry


def get_choices(build_id: str, limit: int = 500) -> list[dict]:
    """Full choice ledger (DB first, memory fallback), oldest → newest."""
    try:
        from core.databases import get_sync_db
        rows = list(get_sync_db()["galaxy_game_choices"]
                    .find({"build_id": build_id}, {"_id": 0})
                    .sort("seq", 1).limit(max(1, min(limit, 2000))))
        if rows:
            return rows
    except Exception:
        pass
    return list(_MEM.get(build_id, []))[:limit]


def parse_context(build_id: str) -> dict:
    """Parse the ledger into the AWARENESS context agents read every step:
    the era + genre + seed locked for the game, which stages are done, the
    running grade floors and cumulative storage spend."""
    ledger = get_choices(build_id)
    ctx: dict[str, Any] = {
        "build_id": build_id, "choices_logged": len(ledger),
        "era": None, "genre": None, "seed": None,
        "stages_done": [], "grade_floors": {}, "storage_used_bytes": 0,
        "assets_made": 0, "gamefiles_made": 0, "last_step": None,
    }
    for e in ledger:
        c = e.get("choice") or {}
        if e["kind"] == "game_setup":
            ctx["era"] = c.get("era", ctx["era"])
            ctx["genre"] = c.get("genre", ctx["genre"])
            ctx["seed"] = c.get("seed", ctx["seed"])
        elif e["kind"] == "stage_forge":
            stage = c.get("stage")
            if stage and stage not in ctx["stages_done"]:
                ctx["stages_done"].append(stage)
            ctx["grade_floors"][stage] = c.get("grade_floor")
            ctx["storage_used_bytes"] += int(c.get("storage_bytes", 0))
            ctx["assets_made"] += int(c.get("assets", 0))
            ctx["gamefiles_made"] += int(c.get("accepted", 0))
        ctx["last_step"] = e.get("step")
    return ctx


def clear(build_id: str) -> None:
    _MEM.pop(build_id, None)
    try:
        from core.databases import get_sync_db
        get_sync_db()["galaxy_game_choices"].delete_many({"build_id": build_id})
    except Exception:
        pass
