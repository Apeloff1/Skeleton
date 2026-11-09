"""
Admin / Ops observability — read-only at-a-glance dashboard data.

Surfaces counts for the platform's key collections plus headline KPIs (GMV, paid
transactions, active listings, live tournaments) and the most recent payment
transactions / listings. Optional gate: if OPS_TOKEN is set in env, callers must
pass ?token=<OPS_TOKEN>; otherwise the endpoint is open (read-only aggregates only).
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

from fastapi import APIRouter, Query

from core.databases import client as _SHARED_MONGO_CLIENT

router = APIRouter(prefix="/api/admin/ops", tags=["ops"])
_db = _SHARED_MONGO_CLIENT[os.environ.get("DB_NAME", "test_database")]

_COLLECTIONS = [
    "playables", "playable_jobs", "marketplace_listings", "marketplace_purchases",
    "payment_transactions", "tournaments", "tournament_rewards", "liveops_progress",
]


@router.get("/overview")
async def overview(token: str = Query("")):
    gate = os.environ.get("OPS_TOKEN", "")
    if gate and token != gate:
        return {"error": "unauthorized"}

    counts = {}
    for c in _COLLECTIONS:
        try:
            counts[c] = await _db[c].estimated_document_count()
        except Exception:
            counts[c] = 0

    paid = await _db.marketplace_purchases.aggregate([
        {"$match": {"payment_status": "paid"}},
        {"$group": {"_id": None, "gmv": {"$sum": {"$ifNull": ["$amount", 0]}}, "n": {"$sum": 1}}},
    ]).to_list(1)
    gmv = round((paid[0]["gmv"] if paid else 0) or 0, 2)
    paid_count = paid[0]["n"] if paid else 0

    active_listings = await _db.marketplace_listings.count_documents({"active": True})
    live_tournaments = await _db.tournaments.count_documents({"status": "live"})
    creators = len(await _db.marketplace_listings.distinct("creator_id"))

    recent_tx = await _db.payment_transactions.find(
        {}, {"_id": 0, "session_id": 1, "playable_id": 1, "buyer_id": 1, "amount": 1,
             "payment_status": 1, "created_at": 1},
    ).sort("created_at", -1).limit(10).to_list(10)
    for t in recent_tx:
        if t.get("session_id"):
            t["session_id"] = t["session_id"][:18] + "…"

    recent_listings = await _db.marketplace_listings.find(
        {}, {"_id": 0, "playable_id": 1, "creator_id": 1, "price_usd": 1, "sales": 1,
             "revenue_usd": 1, "active": 1, "created_at": 1},
    ).sort("created_at", -1).limit(10).to_list(10)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "kpis": {
            "gmv_usd": gmv,
            "paid_transactions": paid_count,
            "active_listings": active_listings,
            "live_tournaments": live_tournaments,
            "creators": creators,
            "games": counts.get("playables", 0),
        },
        "counts": counts,
        "recent_transactions": recent_tx,
        "recent_listings": recent_listings,
    }


@router.get("/metrics")
async def metrics(token: str = Query("")):
    """#13 Structured metrics + threshold alerts for the Ops Console. Lightweight
    health signals derived from the live collections."""
    gate = os.environ.get("OPS_TOKEN", "")
    if gate and token != gate:
        return {"error": "unauthorized"}

    games = await _db.playables.estimated_document_count()
    failed = await _db.playables.count_documents({"status": "failed"})
    ready = await _db.playables.count_documents({"status": "ready"})
    running_jobs = await _db.playable_jobs.count_documents({"job_status": "running"})
    open_disputes = await _db.marketplace_disputes.count_documents({"status": "open"})
    pending_payouts = await _db.payout_requests.count_documents({"status": "pending"})
    active_premium = await _db.premium_entitlements.count_documents(
        {"expires_at": {"$gt": datetime.now(timezone.utc).isoformat()}})

    fail_rate = round((failed / games) * 100, 1) if games else 0.0
    gauges = {
        "games_total": games, "games_ready": ready, "games_failed": failed,
        "fail_rate_pct": fail_rate, "jobs_running": running_jobs,
        "open_disputes": open_disputes, "pending_payouts": pending_payouts,
        "active_premium": active_premium,
    }
    # Threshold alerts (severity: warn/critical).
    alerts = []
    if fail_rate >= 25:
        alerts.append({"level": "critical", "metric": "fail_rate_pct", "value": fail_rate,
                       "msg": f"Game generation fail-rate is {fail_rate}% (≥25%)"})
    elif fail_rate >= 10:
        alerts.append({"level": "warn", "metric": "fail_rate_pct", "value": fail_rate,
                       "msg": f"Game generation fail-rate is {fail_rate}% (≥10%)"})
    if running_jobs >= 25:
        alerts.append({"level": "warn", "metric": "jobs_running", "value": running_jobs,
                       "msg": f"{running_jobs} generation jobs in flight"})
    if open_disputes > 0:
        alerts.append({"level": "warn", "metric": "open_disputes", "value": open_disputes,
                       "msg": f"{open_disputes} open dispute(s) need review"})
    if pending_payouts > 0:
        alerts.append({"level": "warn", "metric": "pending_payouts", "value": pending_payouts,
                       "msg": f"{pending_payouts} payout request(s) pending"})

    return {"generated_at": datetime.now(timezone.utc).isoformat(),
            "gauges": gauges, "alerts": alerts,
            "status": "critical" if any(a["level"] == "critical" for a in alerts)
                      else ("warn" if alerts else "ok")}
