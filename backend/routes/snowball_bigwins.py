"""
🏆 SNOWBALL BIG WINS — a batch of high-value quality/engagement endpoints on top of the
13-signal audit + auto-improve loop.

Wins: quality leaderboard · embeddable quality badge (SVG) · audit diff (latest vs previous)
· quality stats/trend · ship-readiness checklist · polish-all (mark every stage stale + regen)
· vault digest (one-line brief per stage).
"""
from __future__ import annotations

import os

from fastapi import APIRouter, Query
from fastapi.responses import Response

from core.databases import client as _MONGO
from core.stage_vault import vault_brief, _STAGE_PROFILE
from routes.snowball_audit import snowball_audit, DELIVER_THRESHOLD

router = APIRouter(prefix="/api/snowball", tags=["snowball"])
_db = _MONGO[os.environ.get("DB_NAME", "test_database")]


@router.get("/leaderboard")
async def quality_leaderboard(limit: int = Query(20, ge=1, le=50)):
    """🏅 Top games by their best recorded gate-floor — a public quality ranking."""
    pipe = [{"$sort": {"gate_floor": -1}},
            {"$group": {"_id": "$game_id", "title": {"$first": "$title"},
                        "best": {"$max": "$gate_floor"},
                        "deliverable": {"$max": {"$cond": ["$deliverable", 1, 0]}}}},
            {"$sort": {"best": -1}}, {"$limit": limit}]
    rows = await _db.snowball_audits.aggregate(pipe).to_list(limit)
    board = [{"rank": i + 1, "game_id": r["_id"], "title": r.get("title", ""),
              "score": r.get("best", 0), "shipped": bool(r.get("deliverable"))}
             for i, r in enumerate(rows)]
    return {"count": len(board), "leaderboard": board}


@router.get("/{pid}/badge.svg")
async def quality_badge(pid: str):
    """🛡️ Embeddable shields-style quality badge (SVG)."""
    audit = await snowball_audit(pid, deep=False)
    score = audit.get("gate_floor", 0) if not audit.get("error") else 0
    ship = audit.get("deliverable") if not audit.get("error") else False
    color = "#4ade80" if ship else "#3b82f6" if score >= 70 else "#f59e0b" if score >= 40 else "#ef4444"
    label, value = "quality", (f"{score}/100 ✓" if ship else f"{score}/100")
    lw, vw = 56, 74
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{lw+vw}" height="20" role="img">
<linearGradient id="s" x2="0" y2="100%"><stop offset="0" stop-color="#bbb" stop-opacity=".1"/><stop offset="1" stop-opacity=".1"/></linearGradient>
<rect rx="3" width="{lw+vw}" height="20" fill="#555"/>
<rect rx="3" x="{lw}" width="{vw}" height="20" fill="{color}"/>
<rect rx="3" width="{lw+vw}" height="20" fill="url(#s)"/>
<g fill="#fff" text-anchor="middle" font-family="Verdana,Geneva,sans-serif" font-size="11">
<text x="{lw/2}" y="14">{label}</text><text x="{lw+vw/2}" y="14">{value}</text></g></svg>'''
    return Response(content=svg, media_type="image/svg+xml", headers={"Cache-Control": "no-store"})


@router.get("/{pid}/audit/diff")
async def audit_diff(pid: str):
    """🔀 Diff the two latest audits — per-level delta so creators see what improved/regressed."""
    rows = await _db.snowball_audits.find(
        {"game_id": pid}, {"_id": 0, "at": 1, "gate_floor": 1, "levels": 1}
    ).sort("at", -1).limit(2).to_list(2)
    if len(rows) < 2:
        return {"game_id": pid, "have": len(rows), "message": "Need at least two audits to diff."}
    cur, prev = rows[0], rows[1]
    pv = {l["key"]: l["score"] for l in prev.get("levels", [])}
    deltas = []
    for l in cur.get("levels", []):
        before = pv.get(l["key"], 0)
        deltas.append({"key": l["key"], "label": l["label"], "before": before,
                       "after": l["score"], "delta": l["score"] - before})
    return {"game_id": pid, "gate_before": prev.get("gate_floor"), "gate_after": cur.get("gate_floor"),
            "gate_delta": (cur.get("gate_floor", 0) - prev.get("gate_floor", 0)),
            "levels": deltas, "improved": sum(1 for d in deltas if d["delta"] > 0),
            "regressed": sum(1 for d in deltas if d["delta"] < 0)}


@router.get("/{pid}/audit/stats")
async def audit_stats(pid: str):
    """📊 Quality trend stats across all recorded audits."""
    rows = await _db.snowball_audits.find(
        {"game_id": pid}, {"_id": 0, "gate_floor": 1}).sort("at", 1).to_list(200)
    scores = [r.get("gate_floor", 0) for r in rows]
    if not scores:
        return {"game_id": pid, "count": 0}
    return {"game_id": pid, "count": len(scores), "first": scores[0], "latest": scores[-1],
            "best": max(scores), "worst": min(scores), "improvement": scores[-1] - scores[0],
            "average": round(sum(scores) / len(scores), 1)}


@router.get("/{pid}/ship-checklist")
async def ship_checklist(pid: str):
    """✅ Actionable ship-readiness checklist — every blocker as a checkable item."""
    audit = await snowball_audit(pid, deep=True)
    if audit.get("error"):
        return audit
    items = [{"item": l["label"], "score": l["score"], "done": l["pass"],
              "fix_route": l["fix_route"]} for l in audit["levels"]]
    return {"game_id": pid, "ship_ready": audit["deliverable"], "gate_floor": audit["gate_floor"],
            "threshold": DELIVER_THRESHOLD, "done": sum(1 for i in items if i["done"]),
            "total": len(items), "checklist": items}


@router.post("/{pid}/polish-all")
async def polish_all(pid: str):
    """🪄 Mark EVERY stage stale and kick a full GroupChat rebuild (deep polish pass)."""
    from routes.groupchat import run_groupchat
    g = await _db.playables.find_one({"playable_id": pid}, {"_id": 0, "playable_id": 1})
    if not g:
        return {"error": "game not found"}
    arts = ["core_specs", "lore_graph", "quest_db", "mechanics_config", "procedural_config",
            "asset_manifest", "qa_report", "build_manifest", "launch_manifest"]
    await _db.game_kb.update_one(
        {"game_id": pid}, {"$set": {"game_id": pid, **{f"stale.{a}": True for a in arts}}}, upsert=True)
    job = await run_groupchat(pid, only_missing=False, only_stale=True)
    return {"ok": True, "job_id": job.get("job_id"), "message": "Full polish pass started — all stages rebuilding."}


@router.get("/{pid}/vault-digest")
async def vault_digest(pid: str):
    """🧠 One-line vault brief per stage — quick reference card for a manual pass."""
    return {"game_id": pid,
            "digest": {s: vault_brief(s) for s in _STAGE_PROFILE.keys()}}
