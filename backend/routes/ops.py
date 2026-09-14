"""
Admin / Ops observability — read-only at-a-glance dashboard data plus the
canonical governed product-control seam.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from core.charter_policy import Rule
from core.databases import client as _SHARED_MONGO_CLIENT
from core.durable_outbox import OutboxFullError
from core.execution_receipts import ReceiptIntegrityError
from core.product_control_plane import ProductControlPlane
from core.product_operations import OperationExecutionError, OperationRejected

router = APIRouter(prefix="/api/admin/ops", tags=["ops"])
_db = _SHARED_MONGO_CLIENT[os.environ.get("DB_NAME", "test_database")]
_COLLECTIONS = ["playables", "playable_jobs", "marketplace_listings", "marketplace_purchases",
                "payment_transactions", "tournaments", "tournament_rewards", "liveops_progress"]


def _authorized(token: str) -> bool:
    gate = os.environ.get("OPS_TOKEN", "")
    return not gate or token == gate


def _require_ops(token: str) -> None:
    if not _authorized(token):
        raise HTTPException(status_code=403, detail="unauthorized")


_CONTROL_PLANE: ProductControlPlane | None = None


def _control_plane() -> ProductControlPlane:
    global _CONTROL_PLANE
    if _CONTROL_PLANE is None:
        root = Path(os.environ.get("PRODUCT_CONTROL_ROOT", "data/product-control"))
        cap = int(os.environ.get("PRODUCT_CONTROL_OUTBOX_CAP", "4096"))
        bootstrap = os.environ.get("PRODUCT_CONTROL_BOOTSTRAP_POLICY", "1") not in {"0", "false", "False"}
        _CONTROL_PLANE = ProductControlPlane(root, outbox_cap=cap, bootstrap_policy=bootstrap)
    return _CONTROL_PLANE


class RuleInput(BaseModel):
    id: str = Field(min_length=1, max_length=128)
    action: str = Field(min_length=1, max_length=256)
    min_weight: int = Field(default=0, ge=0)
    requires_quorum: bool = False


class RatifyInput(BaseModel):
    domain: str = Field(min_length=1, max_length=128)
    rules: list[RuleInput] = Field(min_length=1, max_length=256)


class AdmitInput(BaseModel):
    capability_id: str = Field(min_length=1, max_length=128)
    domain: str = Field(min_length=1, max_length=128)
    action: str = Field(min_length=1, max_length=256)
    principal: str = Field(min_length=1, max_length=256)
    actor_weight: int = Field(ge=0)
    payload: dict = Field(default_factory=dict)
    quorum_approved: bool = False
    idempotency_key: str | None = Field(default=None, max_length=256)


@router.get("/overview")
async def overview(token: str = Query("")):
    if not _authorized(token): return {"error": "unauthorized"}
    counts = {}
    for c in _COLLECTIONS:
        try: counts[c] = await _db[c].estimated_document_count()
        except Exception: counts[c] = 0
    paid = await _db.marketplace_purchases.aggregate([
        {"$match": {"payment_status": "paid"}},
        {"$group": {"_id": None, "gmv": {"$sum": {"$ifNull": ["$amount", 0]}}, "n": {"$sum": 1}}},
    ]).to_list(1)
    gmv = round((paid[0]["gmv"] if paid else 0) or 0, 2)
    paid_count = paid[0]["n"] if paid else 0
    active_listings = await _db.marketplace_listings.count_documents({"active": True})
    live_tournaments = await _db.tournaments.count_documents({"status": "live"})
    creators = len(await _db.marketplace_listings.distinct("creator_id"))
    recent_tx = await _db.payment_transactions.find({}, {"_id": 0, "session_id": 1, "playable_id": 1,
        "buyer_id": 1, "amount": 1, "payment_status": 1, "created_at": 1}).sort("created_at", -1).limit(10).to_list(10)
    for t in recent_tx:
        if t.get("session_id"): t["session_id"] = t["session_id"][:18] + "…"
    recent_listings = await _db.marketplace_listings.find({}, {"_id": 0, "playable_id": 1, "creator_id": 1,
        "price_usd": 1, "sales": 1, "revenue_usd": 1, "active": 1, "created_at": 1}).sort("created_at", -1).limit(10).to_list(10)
    return {"generated_at": datetime.now(timezone.utc).isoformat(),
            "kpis": {"gmv_usd": gmv, "paid_transactions": paid_count, "active_listings": active_listings,
                     "live_tournaments": live_tournaments, "creators": creators, "games": counts.get("playables", 0)},
            "counts": counts, "recent_transactions": recent_tx, "recent_listings": recent_listings}


@router.get("/metrics")
async def metrics(token: str = Query("")):
    if not _authorized(token): return {"error": "unauthorized"}
    games = await _db.playables.estimated_document_count()
    failed = await _db.playables.count_documents({"status": "failed"})
    ready = await _db.playables.count_documents({"status": "ready"})
    running_jobs = await _db.playable_jobs.count_documents({"job_status": "running"})
    open_disputes = await _db.marketplace_disputes.count_documents({"status": "open"})
    pending_payouts = await _db.payout_requests.count_documents({"status": "pending"})
    active_premium = await _db.premium_entitlements.count_documents({"expires_at": {"$gt": datetime.now(timezone.utc).isoformat()}})
    fail_rate = round((failed / games) * 100, 1) if games else 0.0
    gauges = {"games_total": games, "games_ready": ready, "games_failed": failed, "fail_rate_pct": fail_rate,
              "jobs_running": running_jobs, "open_disputes": open_disputes, "pending_payouts": pending_payouts,
              "active_premium": active_premium}
    alerts = []
    if fail_rate >= 25: alerts.append({"level": "critical", "metric": "fail_rate_pct", "value": fail_rate, "msg": f"Game generation fail-rate is {fail_rate}% (≥25%)"})
    elif fail_rate >= 10: alerts.append({"level": "warn", "metric": "fail_rate_pct", "value": fail_rate, "msg": f"Game generation fail-rate is {fail_rate}% (≥10%)"})
    if running_jobs >= 25: alerts.append({"level": "warn", "metric": "jobs_running", "value": running_jobs, "msg": f"{running_jobs} generation jobs in flight"})
    if open_disputes > 0: alerts.append({"level": "warn", "metric": "open_disputes", "value": open_disputes, "msg": f"{open_disputes} open dispute(s) need review"})
    if pending_payouts > 0: alerts.append({"level": "warn", "metric": "pending_payouts", "value": pending_payouts, "msg": f"{pending_payouts} payout request(s) pending"})
    return {"generated_at": datetime.now(timezone.utc).isoformat(), "gauges": gauges, "alerts": alerts,
            "status": "critical" if any(a["level"] == "critical" for a in alerts) else ("warn" if alerts else "ok")}


@router.get("/product-control/status")
async def product_control_status(token: str = Query("")):
    _require_ops(token); return _control_plane().status()


@router.get("/product-control/pending")
async def product_control_pending(token: str = Query("")):
    _require_ops(token); pending = _control_plane().pending(); return {"count": len(pending), "operations": pending}


@router.get("/product-control/audit")
async def product_control_audit(limit: int = Query(50, ge=0, le=500), token: str = Query("")):
    _require_ops(token); return {"entries": _control_plane().audit_history(limit=limit)}


@router.get("/product-control/receipts")
async def product_control_receipts(limit: int = Query(50, ge=0, le=500), token: str = Query("")):
    _require_ops(token)
    try: return {"receipts": _control_plane().receipt_history(limit=limit)}
    except ReceiptIntegrityError as exc: raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/product-control/receipt/{operation_id}")
async def product_control_receipt(operation_id: str, token: str = Query("")):
    _require_ops(token)
    try: receipt = _control_plane().receipt(operation_id)
    except (ReceiptIntegrityError, ValueError) as exc: raise HTTPException(status_code=400, detail=str(exc)) from exc
    if receipt is None: raise HTTPException(status_code=404, detail="receipt not found")
    return receipt


@router.get("/product-control/receipt/{operation_id}/result")
async def product_control_receipt_result(operation_id: str, token: str = Query("")):
    _require_ops(token)
    try: return _control_plane().receipt_result(operation_id)
    except ValueError as exc: raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ReceiptIntegrityError as exc:
        status = 404 if "not found" in str(exc).lower() else 500
        raise HTTPException(status_code=status, detail=str(exc)) from exc


@router.post("/product-control/execute/{seq}")
async def product_control_execute(seq: int, token: str = Query("")):
    _require_ops(token)
    if seq < 0: raise HTTPException(status_code=400, detail="sequence cannot be negative")
    try: confirmed = await _control_plane().execute_registered(seq)
    except OperationExecutionError as exc: raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"outbox_seq": seq, "confirmed": confirmed, "status": "executed" if confirmed else "deferred_or_unbound"}


@router.post("/product-control/execute-pending")
async def product_control_execute_pending(limit: int = Query(32, ge=0, le=256), token: str = Query("")):
    _require_ops(token)
    try: confirmed = await _control_plane().execute_registered_pending(limit=limit)
    except OperationExecutionError as exc: raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"confirmed": confirmed, "remaining": len(_control_plane().pending())}


@router.post("/product-control/policy/ratify")
async def product_control_ratify(body: RatifyInput, token: str = Query("")):
    _require_ops(token)
    try: charter = _control_plane().ratify(body.domain, [Rule(r.id, r.action, r.min_weight, r.requires_quorum) for r in body.rules])
    except ValueError as exc: raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"charter_id": charter.id, "domain": charter.domain, "rules": len(charter.rules)}


@router.post("/product-control/admit")
async def product_control_admit(body: AdmitInput, token: str = Query("")):
    _require_ops(token)
    try:
        admitted = _control_plane().admit(capability_id=body.capability_id, domain=body.domain, action=body.action,
            principal=body.principal, actor_weight=body.actor_weight, payload=body.payload,
            quorum_approved=body.quorum_approved, idempotency_key=body.idempotency_key)
    except OutboxFullError as exc: raise HTTPException(status_code=503, detail=str(exc)) from exc
    except OperationRejected as exc: raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc: raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"operation_id": admitted.id, "capability_id": admitted.capability_id, "pillar": admitted.pillar,
            "outbox_seq": admitted.outbox_seq, "admitted_at": admitted.admitted_at, "audit_hash": admitted.audit_hash}
