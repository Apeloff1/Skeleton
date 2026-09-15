"""
╔══════════════════════════════════════════════════════════════════════════╗
║  ANTI-CHEAT / ANTI-ABUSE — score & XP submission validation (2026-06)     ║
║                                                                            ║
║  Centralised guardrails for client-supplied score/XP values that feed     ║
║  the leaderboards, streaks and gamification profile. Any endpoint that     ║
║  accepts a *trusted-from-client* number (XP amount, challenge score,       ║
║  correct/total counts) MUST route it through these validators so a         ║
║  tampered request can't inflate ranks or farm unlimited XP.                ║
║                                                                            ║
║  Two layers of defence:                                                    ║
║    1. VALUE CLAMPING  — impossible / out-of-range numbers are clamped to   ║
║       a server-authoritative ceiling (never trust the client's number).   ║
║    2. RATE LIMITING   — a sliding window per (user, action) blocks rapid   ║
║       grind/replay farming.                                                ║
║                                                                            ║
║  Every adjustment / block is recorded in `anticheat_log` for audit, and    ║
║  helpers NEVER raise — a DB blip must not break a legitimate submission.   ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from fastapi import APIRouter, Query
from datetime import datetime, timezone
from core.databases import client as _SHARED_MONGO_CLIENT
import os

router = APIRouter(prefix="/api/anticheat", tags=["anticheat"])
_db = _SHARED_MONGO_CLIENT[os.environ.get("DB_NAME", "codedock")]
PROJ = {"_id": 0}

# ── Tunable ceilings ───────────────────────────────────────────────────────
XP_ABS_CAP = int(os.environ.get("ANTICHEAT_XP_ABS_CAP", "1000"))   # max XP per single award
XP_TABLE_MULT = int(os.environ.get("ANTICHEAT_XP_MULT", "3"))      # custom amount may be ≤ table*mult
MAX_QUESTIONS = int(os.environ.get("ANTICHEAT_MAX_QUESTIONS", "50"))
PER_Q_MAX = int(os.environ.get("ANTICHEAT_PER_Q_MAX", "100"))      # max points per question


def validate_xp_award(activity: str, amount, table: dict) -> tuple:
    """Clamp a client-supplied XP amount to a server-authoritative ceiling.

    Returns (clean_amount:int, flags:list[str]). When `amount` is None the
    table value is used as-is (server-trusted). A non-positive amount falls
    back to the table value. Anything above the per-activity cap is clamped.
    """
    flags = []
    base = int(table.get(activity, 5))
    if amount is None:
        return base, flags
    try:
        a = int(amount)
    except (TypeError, ValueError):
        flags.append("invalid_amount_type")
        return base, flags
    if a <= 0:
        flags.append("nonpositive_amount")
        return base, flags
    cap = min(XP_ABS_CAP, max(base * XP_TABLE_MULT, 100))
    if a > cap:
        flags.append(f"amount_capped:{a}->{cap}")
        a = cap
    return a, flags


def validate_challenge_score(score, correct, total) -> tuple:
    """Clamp client-supplied challenge results to physically-possible bounds.

    Returns (clean:dict{score,correct,total,accuracy}, flags:list[str]).
    Guards against: correct>total, negative values, oversized question counts,
    and arbitrarily-inflated scores (capped at total*PER_Q_MAX).
    """
    flags = []
    try:
        total_i = int(total)
    except (TypeError, ValueError):
        total_i, flags = 10, flags + ["invalid_total"]
    try:
        correct_i = int(correct)
    except (TypeError, ValueError):
        correct_i, flags = 0, flags + ["invalid_correct"]
    try:
        score_i = int(score)
    except (TypeError, ValueError):
        score_i, flags = 0, flags + ["invalid_score"]

    if total_i < 1 or total_i > MAX_QUESTIONS:
        flags.append(f"total_clamped:{total_i}")
        total_i = max(1, min(total_i, MAX_QUESTIONS))
    if correct_i < 0 or correct_i > total_i:
        flags.append(f"correct_clamped:{correct_i}->[0,{total_i}]")
        correct_i = max(0, min(correct_i, total_i))
    if score_i < 0:
        flags.append("negative_score")
        score_i = 0
    score_cap = total_i * PER_Q_MAX
    if score_i > score_cap:
        flags.append(f"score_capped:{score_i}->{score_cap}")
        score_i = score_cap
    clean = {
        "score": score_i,
        "correct": correct_i,
        "total": total_i,
        "accuracy": round(correct_i / max(total_i, 1) * 100, 1),
    }
    return clean, flags


async def check_rate_limit(user_id: str, action: str, max_per_window: int,
                           window_seconds: int = 60) -> tuple:
    """Sliding-window rate limit per (user, action). Returns (allowed, count, retry_after).

    Fail-OPEN: any DB error returns allowed=True so a storage blip never blocks
    a legitimate user. Window is reset lazily when the first request after the
    window's expiry arrives.
    """
    try:
        now = datetime.now(timezone.utc)
        key = f"{user_id}:{action}"
        doc = await _db.anticheat_rl.find_one({"_id": key})
        if not doc:
            await _db.anticheat_rl.update_one(
                {"_id": key},
                {"$set": {"window_start": now.isoformat(), "count": 1}},
                upsert=True,
            )
            return True, 1, 0
        try:
            ws = datetime.fromisoformat(doc.get("window_start"))
        except Exception:
            ws = now
        if (now - ws).total_seconds() >= window_seconds:
            await _db.anticheat_rl.update_one(
                {"_id": key},
                {"$set": {"window_start": now.isoformat(), "count": 1}},
            )
            return True, 1, 0
        count = int(doc.get("count", 0))
        if count >= max_per_window:
            retry_after = int(window_seconds - (now - ws).total_seconds())
            return False, count, max(1, retry_after)
        await _db.anticheat_rl.update_one({"_id": key}, {"$inc": {"count": 1}})
        return True, count + 1, 0
    except Exception:
        return True, 0, 0


async def log_violation(user_id: str, action: str, flags: list, raw: dict = None) -> None:
    """Persist a flagged submission for audit. Never raises."""
    if not flags:
        return
    try:
        await _db.anticheat_log.insert_one({
            "user_id": user_id,
            "action": action,
            "flags": flags,
            "raw": raw or {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
    except Exception:
        pass


@router.get("/violations")
async def list_violations(user_id: str = Query(None), limit: int = Query(50, le=200)):
    """Audit feed of recent anti-cheat adjustments / blocks."""
    q = {"user_id": user_id} if user_id else {}
    logs = await _db.anticheat_log.find(q, PROJ).sort("timestamp", -1).limit(limit).to_list(limit)
    total = await _db.anticheat_log.count_documents(q)
    return {"violations": logs, "count": len(logs), "total": total}


@router.get("/config")
async def get_config():
    """Expose the active anti-cheat ceilings (read-only, for transparency)."""
    return {
        "xp_abs_cap": XP_ABS_CAP,
        "xp_table_multiplier": XP_TABLE_MULT,
        "max_questions": MAX_QUESTIONS,
        "per_question_max": PER_Q_MAX,
    }


@router.get("/stats")
async def stats():
    """Aggregated anti-cheat dashboard feed — totals, top flag reasons, top
    flagged users, and a per-action breakdown. All aggregations are tolerant
    (empty collection → zeros / empty lists)."""
    total = await _db.anticheat_log.count_documents({})
    flagged_users = len(await _db.anticheat_log.distinct("user_id"))
    rate_limit_blocks = await _db.anticheat_log.count_documents({"flags": "rate_limited"})

    # Top flag KINDS (strip the ":detail" suffix so "amount_capped:999->100"
    # rolls up under "amount_capped").
    top_flags = await _db.anticheat_log.aggregate([
        {"$unwind": "$flags"},
        {"$project": {"kind": {"$arrayElemAt": [{"$split": ["$flags", ":"]}, 0]}}},
        {"$group": {"_id": "$kind", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 12},
    ]).to_list(12)

    top_users = await _db.anticheat_log.aggregate([
        {"$group": {"_id": "$user_id", "count": {"$sum": 1},
                    "actions": {"$addToSet": "$action"}}},
        {"$sort": {"count": -1}},
        {"$limit": 10},
    ]).to_list(10)

    by_action = await _db.anticheat_log.aggregate([
        {"$group": {"_id": "$action", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]).to_list(20)

    return {
        "total_violations": total,
        "flagged_users": flagged_users,
        "rate_limit_blocks": rate_limit_blocks,
        "top_flags": [{"flag": f["_id"] or "unknown", "count": f["count"]} for f in top_flags],
        "top_users": [{"user_id": u["_id"], "count": u["count"],
                       "actions": sorted(u.get("actions", []))} for u in top_users],
        "by_action": [{"action": a["_id"] or "unknown", "count": a["count"]} for a in by_action],
    }
