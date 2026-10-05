"""
VII.5 Governance & Safety.

A safety/trust layer for the generated-game catalogue:

  POST /api/governance/scan/{pid}        — deterministic content-policy scan
  GET  /api/governance/plagiarism/{pid}  — IP / near-duplicate similarity gating
  POST /api/governance/report            — community content report
  GET  /api/governance/reports           — moderation queue (hydrated)
  POST /api/governance/moderate/{rid}    — resolve a report (hide/warn/dismiss)
  GET  /api/governance/status/{pid}      — combined safety status for a game
  GET  /api/governance/audit             — immutable audit trail

No auth layer yet (single-tenant dev sandbox); reporter/actor identity is a
client-supplied visitor id. Everything here is deterministic + fast (no LLM) so
it is trivially testable and never blocks the event loop.
"""
from __future__ import annotations

import os
import re
import uuid
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

from core.databases import client as _SHARED_MONGO_CLIENT
from core.anti_farm import allow as _allow

router = APIRouter(prefix="/api/governance", tags=["governance"])
_db = _SHARED_MONGO_CLIENT[os.environ.get("DB_NAME", "test_database")]

# Reports threshold at which a game is auto-escalated to the review queue.
AUTO_REVIEW_REPORTS = 3
# Jaccard similarity thresholds for IP / plagiarism gating.
SIM_NEAR_DUPLICATE = 0.80
SIM_SIMILAR = 0.50

_GAME_LIGHT = {
    "_id": 0, "playable_id": 1, "title": 1, "genre": 1, "has_cover": 1,
    "moderation_status": 1, "reports_count": 1,
}

# Deterministic content-policy lexicon. Word-boundary matched, case-insensitive.
# Categories map to severities; the scan never calls an LLM.
_POLICY = {
    "hate": (["slur", "bigot", "racial hatred", "ethnic cleansing"], "block"),
    "sexual_minors": (["child porn", "csam", "underage sex"], "block"),
    "extreme_violence": (["bomb making", "build a bomb", "mass shooting", "genocide"], "block"),
    "self_harm": (["how to kill yourself", "suicide method", "self-harm guide"], "review"),
    "malware": (["keylogger", "ransomware", "steal credentials", "exfiltrate data"], "review"),
}
_VERDICT_RANK = {"pass": 0, "review": 1, "block": 2}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _audit(action: str, target_id: str, actor: str, detail: dict | None = None) -> None:
    """Append an immutable governance audit-trail entry."""
    await _db.governance_audit.insert_one({
        "audit_id": uuid.uuid4().hex,
        "action": action,
        "target_id": target_id,
        "actor": (actor or "anon")[:80],
        "detail": detail or {},
        "at": _now(),
    })


def _tokens(text: str) -> List[str]:
    """Lowercased alphanumeric word tokens."""
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def _shingles(text: str, k: int = 5) -> set:
    """Set of k-word shingles for Jaccard similarity (order-sensitive n-grams)."""
    toks = _tokens(text)
    if len(toks) < k:
        return set(toks)
    return {" ".join(toks[i:i + k]) for i in range(len(toks) - k + 1)}


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def _policy_scan(text: str) -> dict:
    """Deterministic content-policy scan → verdict + flags + score (0-100, higher=safer)."""
    low = (text or "").lower()
    flags = []
    verdict = "pass"
    for category, (terms, severity) in _POLICY.items():
        for term in terms:
            if re.search(r"\b" + re.escape(term) + r"\b", low):
                flags.append({"category": category, "term": term, "severity": severity})
                if _VERDICT_RANK[severity] > _VERDICT_RANK[verdict]:
                    verdict = severity
    # Score: start 100, subtract per flag weighted by severity.
    penalty = sum(40 if f["severity"] == "block" else 18 for f in flags)
    score = max(0, 100 - penalty)
    return {"verdict": verdict, "score": score, "flags": flags}


async def _hydrate(ids: List[str]) -> dict:
    if not ids:
        return {}
    docs = await _db.playables.find(
        {"playable_id": {"$in": ids}}, _GAME_LIGHT).to_list(len(ids))
    return {d["playable_id"]: d for d in docs}


# ── Content-policy scan ─────────────────────────────────────────────────────
@router.post("/scan/{pid}")
async def scan(pid: str):
    """Run the deterministic content-policy scan on a game's title + brief + html."""
    g = await _db.playables.find_one(
        {"playable_id": pid}, {"_id": 0, "title": 1, "brief": 1, "html": 1})
    if not g:
        return {"error": "not found"}
    corpus = " ".join([g.get("title") or "", g.get("brief") or "", g.get("html") or ""])
    result = _policy_scan(corpus)
    await _db.playables.update_one(
        {"playable_id": pid},
        {"$set": {"policy_scan": {**result, "scanned_at": _now()}}})
    await _audit("scan", pid, "system", {"verdict": result["verdict"], "flags": len(result["flags"])})
    return {"playable_id": pid, **result}


# ── IP / plagiarism gating ──────────────────────────────────────────────────
@router.get("/plagiarism/{pid}")
async def plagiarism(pid: str, top: int = Query(5, le=20)):
    """Token-shingle Jaccard similarity of this game vs every other ready game.
    Surfaces near-duplicates so original creators can be credited / flagged."""
    me = await _db.playables.find_one({"playable_id": pid}, {"_id": 0, "html": 1, "title": 1})
    if not me:
        return {"error": "not found"}
    my_sh = _shingles(me.get("html") or "")
    others = await _db.playables.find(
        {"playable_id": {"$ne": pid}, "status": "ready"},
        {"_id": 0, "playable_id": 1, "title": 1, "genre": 1, "html": 1}).to_list(500)
    matches = []
    for o in others:
        sim = _jaccard(my_sh, _shingles(o.get("html") or ""))
        if sim <= 0:
            continue
        matches.append({
            "playable_id": o["playable_id"], "title": o.get("title", "Untitled"),
            "genre": o.get("genre", "arcade"), "similarity": round(sim, 4),
        })
    matches.sort(key=lambda m: -m["similarity"])
    top_sim = matches[0]["similarity"] if matches else 0.0
    if top_sim >= SIM_NEAR_DUPLICATE:
        verdict = "near_duplicate"
    elif top_sim >= SIM_SIMILAR:
        verdict = "similar"
    else:
        verdict = "original"
    return {
        "playable_id": pid, "verdict": verdict, "top_similarity": top_sim,
        "matches": matches[:top], "compared": len(others),
    }


# ── Community reporting ─────────────────────────────────────────────────────
_REASONS = {"inappropriate", "copyright", "broken", "spam", "offensive", "other"}


class ReportBody(BaseModel):
    playable_id: str = ""
    reason: str = "other"
    detail: str = ""
    reporter_id: str = ""


@router.post("/report")
async def report(body: ReportBody, request: Request):
    pid = (body.playable_id or "").strip()
    if not pid:
        return {"error": "playable_id required"}
    # Anti-abuse: throttle reports per client IP (~1 every 10s, burst 5).
    ip = (request.headers.get("x-forwarded-for", "").split(",")[0].strip()
          or (request.client.host if request.client else "anon"))
    if not _allow(f"gov_report:{ip}", rate_per_sec=0.1, burst=5):
        return {"error": "rate_limited", "detail": "Too many reports — please slow down."}
    g = await _db.playables.find_one({"playable_id": pid}, {"_id": 0, "playable_id": 1})
    if not g:
        return {"error": "not found"}
    reason = body.reason if body.reason in _REASONS else "other"
    rid = uuid.uuid4().hex
    await _db.content_reports.insert_one({
        "report_id": rid, "playable_id": pid, "reason": reason,
        "detail": (body.detail or "")[:1000],
        "reporter_id": (body.reporter_id or "anon")[:80],
        "status": "open", "created_at": _now(),
    })
    # bump count + auto-escalate
    res = await _db.playables.find_one_and_update(
        {"playable_id": pid}, {"$inc": {"reports_count": 1}},
        return_document=True, projection={"_id": 0, "reports_count": 1, "moderation_status": 1})
    count = (res or {}).get("reports_count", 1)
    escalated = False
    if count >= AUTO_REVIEW_REPORTS and (res or {}).get("moderation_status") in (None, "ok"):
        await _db.playables.update_one(
            {"playable_id": pid}, {"$set": {"moderation_status": "review"}})
        escalated = True
    await _audit("report", pid, body.reporter_id, {"reason": reason, "count": count})
    return {"report_id": rid, "playable_id": pid, "reports_count": count, "escalated": escalated}


@router.get("/reports")
async def reports(status: str = Query("open"), limit: int = Query(50, le=200)):
    q: dict = {} if status == "all" else {"status": status}
    rows = await _db.content_reports.find(q, {"_id": 0}).sort("created_at", -1).to_list(limit)
    games = await _hydrate([r["playable_id"] for r in rows])
    for r in rows:
        g = games.get(r["playable_id"]) or {}
        r["title"] = g.get("title", "Untitled")
        r["genre"] = g.get("genre", "arcade")
        r["moderation_status"] = g.get("moderation_status", "ok")
    open_count = await _db.content_reports.count_documents({"status": "open"})
    return {"reports": rows, "count": len(rows), "open_total": open_count}


# ── Moderation actions ──────────────────────────────────────────────────────
_ACTIONS = {"dismiss": "ok", "warn": "warned", "hide": "hidden", "restore": "ok"}


class ModerateBody(BaseModel):
    action: str = "dismiss"
    note: str = ""
    actor: str = "moderator"


@router.post("/moderate/{rid}")
async def moderate(rid: str, body: ModerateBody):
    rep = await _db.content_reports.find_one({"report_id": rid}, {"_id": 0})
    if not rep:
        return {"error": "not found"}
    action = body.action if body.action in _ACTIONS else "dismiss"
    new_mod = _ACTIONS[action]
    pid = rep["playable_id"]
    note = (body.note or "").strip()
    if new_mod == "ok":
        mod_fields = {"moderation_status": new_mod, "moderation_note": "", "moderation_reason": ""}
    else:
        mod_fields = {"moderation_status": new_mod,
                      "moderation_note": note or f"Flagged as '{rep.get('reason', 'other')}'.",
                      "moderation_reason": rep.get("reason", "other")}
    await _db.playables.update_one({"playable_id": pid}, {"$set": mod_fields})
    await _db.content_reports.update_one(
        {"report_id": rid},
        {"$set": {"status": "resolved" if action != "dismiss" else "dismissed",
                  "resolution": action, "note": (body.note or "")[:500],
                  "resolved_at": _now(), "resolved_by": (body.actor or "moderator")[:80]}})
    await _audit("moderate", pid, body.actor,
                 {"report_id": rid, "action": action, "moderation_status": new_mod})
    return {"report_id": rid, "playable_id": pid, "action": action, "moderation_status": new_mod}


# ── Creator appeals (bidirectional trust loop) ──────────────────────────────
class AppealBody(BaseModel):
    playable_id: str = ""
    reason: str = ""
    creator_id: str = ""


@router.post("/appeal")
async def appeal(body: AppealBody):
    """A creator requests re-review of a game that moderation has restricted."""
    pid = (body.playable_id or "").strip()
    reason = (body.reason or "").strip()
    if not pid:
        return {"error": "playable_id required"}
    if len(reason) < 10:
        return {"error": "please explain your appeal (min 10 chars)"}
    g = await _db.playables.find_one(
        {"playable_id": pid}, {"_id": 0, "moderation_status": 1, "title": 1})
    if not g:
        return {"error": "not found"}
    if g.get("moderation_status", "ok") not in ("hidden", "warned", "review"):
        return {"error": "this game is not restricted — nothing to appeal"}
    # one open appeal per game
    existing = await _db.content_appeals.find_one({"playable_id": pid, "status": "open"}, {"_id": 0})
    if existing:
        return {"error": "an appeal is already pending for this game", "appeal_id": existing["appeal_id"]}
    aid = uuid.uuid4().hex
    await _db.content_appeals.insert_one({
        "appeal_id": aid, "playable_id": pid, "reason": reason[:1000],
        "creator_id": (body.creator_id or "anon")[:80],
        "moderation_status": g.get("moderation_status", "ok"),
        "status": "open", "created_at": _now(),
    })
    await _audit("appeal", pid, body.creator_id, {"appeal_id": aid})
    return {"appeal_id": aid, "playable_id": pid, "status": "open"}


APPEAL_SLA_DAYS = 7  # open appeals older than this auto-resolve as 'expired'


@router.get("/appeals")
async def appeals(status: str = Query("open"), limit: int = Query(50, le=200)):
    # Lazy SLA enforcement: auto-expire stale open appeals (treated as denied;
    # the game stays restricted, but the appeal no longer blocks the queue).
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(days=APPEAL_SLA_DAYS)).isoformat()
    await _db.content_appeals.update_many(
        {"status": "open", "created_at": {"$lt": cutoff}},
        {"$set": {"status": "expired", "resolution": "expired",
                  "resolved_at": _now(), "resolved_by": "system-sla"}})
    q: dict = {} if status == "all" else {"status": status}
    rows = await _db.content_appeals.find(q, {"_id": 0}).sort("created_at", -1).to_list(limit)
    games = await _hydrate([r["playable_id"] for r in rows])
    now = datetime.now(timezone.utc)
    for r in rows:
        g = games.get(r["playable_id"]) or {}
        r["title"] = g.get("title", "Untitled")
        r["genre"] = g.get("genre", "arcade")
        r["current_status"] = g.get("moderation_status", "ok")
        try:
            created = datetime.fromisoformat(r["created_at"])
            age_h = max(0.0, (now - created).total_seconds() / 3600.0)
        except Exception:
            age_h = 0.0
        r["age_hours"] = round(age_h, 1)
        r["sla_days"] = APPEAL_SLA_DAYS
        r["sla_breached"] = r.get("status") == "open" and age_h >= APPEAL_SLA_DAYS * 24
    return {"appeals": rows, "count": len(rows),
            "open_total": await _db.content_appeals.count_documents({"status": "open"}),
            "sla_days": APPEAL_SLA_DAYS}


class AppealResolveBody(BaseModel):
    action: str = "uphold"   # uphold (deny) | restore (grant)
    note: str = ""
    actor: str = "moderator"


@router.post("/appeal/{aid}/resolve")
async def resolve_appeal(aid: str, body: AppealResolveBody):
    ap = await _db.content_appeals.find_one({"appeal_id": aid}, {"_id": 0})
    if not ap:
        return {"error": "not found"}
    action = body.action if body.action in ("uphold", "restore") else "uphold"
    pid = ap["playable_id"]
    if action == "restore":
        await _db.playables.update_one({"playable_id": pid}, {"$set": {"moderation_status": "ok"}})
    await _db.content_appeals.update_one(
        {"appeal_id": aid},
        {"$set": {"status": "granted" if action == "restore" else "denied",
                  "resolution": action, "note": (body.note or "")[:500],
                  "resolved_at": _now(), "resolved_by": (body.actor or "moderator")[:80]}})
    await _audit("appeal_resolve", pid, body.actor, {"appeal_id": aid, "action": action})
    return {"appeal_id": aid, "playable_id": pid, "action": action,
            "moderation_status": "ok" if action == "restore" else ap.get("moderation_status")}


# ── Creator appeal-outcome notifications ────────────────────────────────────
@router.get("/notifications/{creator_id}")
async def notifications(creator_id: str):
    """Resolved (granted/denied) appeals for a creator not yet acknowledged."""
    rows = await _db.content_appeals.find(
        {"creator_id": creator_id, "status": {"$in": ["granted", "denied"]},
         "acknowledged": {"$ne": True}},
        {"_id": 0, "appeal_id": 1, "playable_id": 1, "status": 1, "resolution": 1,
         "note": 1, "resolved_at": 1}).sort("resolved_at", -1).to_list(50)
    games = await _hydrate([r["playable_id"] for r in rows])
    for r in rows:
        r["title"] = (games.get(r["playable_id"]) or {}).get("title", "Untitled")
    return {"creator_id": creator_id, "notifications": rows, "count": len(rows)}


@router.post("/notifications/{creator_id}/ack")
async def ack_notifications(creator_id: str):
    res = await _db.content_appeals.update_many(
        {"creator_id": creator_id, "status": {"$in": ["granted", "denied"]},
         "acknowledged": {"$ne": True}},
        {"$set": {"acknowledged": True}})
    return {"creator_id": creator_id, "acknowledged": res.modified_count}


# ── Combined safety status ──────────────────────────────────────────────────
@router.get("/status/{pid}")
async def status(pid: str):
    g = await _db.playables.find_one(
        {"playable_id": pid},
        {"_id": 0, "moderation_status": 1, "reports_count": 1, "policy_scan": 1, "title": 1,
         "moderation_note": 1, "moderation_reason": 1})
    if not g:
        return {"error": "not found"}
    open_reports = await _db.content_reports.count_documents(
        {"playable_id": pid, "status": "open"})
    return {
        "playable_id": pid, "title": g.get("title", "Untitled"),
        "moderation_status": g.get("moderation_status", "ok"),
        "moderation_note": g.get("moderation_note", ""),
        "moderation_reason": g.get("moderation_reason", ""),
        "reports_count": g.get("reports_count", 0),
        "open_reports": open_reports,
        "policy_scan": g.get("policy_scan"),
        "visible": g.get("moderation_status", "ok") != "hidden",
    }


# ── Audit trail ─────────────────────────────────────────────────────────────
@router.get("/audit")
async def audit(limit: int = Query(100, le=500), target_id: str = Query("")):
    q = {"target_id": target_id} if target_id else {}
    rows = await _db.governance_audit.find(q, {"_id": 0}).sort("at", -1).to_list(limit)
    return {"entries": rows, "count": len(rows)}


# ── Platform safety overview ────────────────────────────────────────────────
@router.get("/overview")
async def overview():
    total = await _db.playables.count_documents({"status": "ready"})
    hidden = await _db.playables.count_documents({"moderation_status": "hidden"})
    warned = await _db.playables.count_documents({"moderation_status": "warned"})
    review = await _db.playables.count_documents({"moderation_status": "review"})
    open_reports = await _db.content_reports.count_documents({"status": "open"})
    open_appeals = await _db.content_appeals.count_documents({"status": "open"})
    audit_total = await _db.governance_audit.count_documents({})
    return {
        "games": total, "hidden": hidden, "warned": warned, "in_review": review,
        "open_reports": open_reports, "open_appeals": open_appeals, "audit_entries": audit_total,
    }
