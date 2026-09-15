"""
Creator Economy — follow graph + creator profiles + leaderboard (#5), revenue-split
earnings ledger + payout requests (#1), marketplace reviews & disputes (#9), and a
Premium Pass entitlement bought via the existing one-time Stripe rail (#3).

NOTE on #1/#3: the Emergent Stripe proxy supports ONLY one-time `mode='payment'`, so
there is no true Stripe Connect payout or recurring subscription here. Instead:
  • #1 — every paid sale credits the creator's earnings ledger (85% after a 15% fee);
         creators can file a payout request (settled out-of-band).
  • #3 — Premium is a TIME-BOXED entitlement purchased one-time (no auto-renew).
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

from core.databases import client as _SHARED_MONGO_CLIENT
from emergentintegrations.payments.stripe.checkout import StripeCheckout, CheckoutSessionRequest

router = APIRouter(prefix="/api", tags=["creator-economy"])
_db = _SHARED_MONGO_CLIENT[os.environ.get("DB_NAME", "test_database")]

STRIPE_API_KEY = os.environ.get("STRIPE_API_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "") or None
PLATFORM_FEE_PCT = 0.15

PREMIUM_PLANS = {
    "monthly": {"price": 4.99, "days": 30, "label": "Premium · 30 days"},
    "season": {"price": 12.99, "days": 90, "label": "Premium Season · 90 days"},
}

_GAME_LIGHT = {"_id": 0, "playable_id": 1, "title": 1, "genre": 1, "has_cover": 1,
               "plays": 1, "evaluation.overall": 1}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _checkout(host_url: str) -> StripeCheckout:
    return StripeCheckout(api_key=STRIPE_API_KEY,
                          webhook_url=f"{host_url.rstrip('/')}/api/webhook/stripe",
                          webhook_secret=STRIPE_WEBHOOK_SECRET)


# ════════════════════════ #5 FOLLOW GRAPH + PROFILES + LEADERBOARD ════════════════════════
class FollowBody(BaseModel):
    follower_id: str = ""


async def _creator_stats(cid: str) -> dict:
    rows = await _db.marketplace_listings.find(
        {"creator_id": cid}, {"_id": 0, "playable_id": 1, "sales": 1, "revenue_usd": 1,
                              "rating_avg": 1, "rating_count": 1, "active": 1}).to_list(300)
    ids = [r["playable_id"] for r in rows]
    plays = 0
    if ids:
        gs = await _db.playables.find({"playable_id": {"$in": ids}}, {"_id": 0, "plays": 1}).to_list(len(ids))
        plays = sum(g.get("plays") or 0 for g in gs)
    sales = sum(r.get("sales") or 0 for r in rows)
    revenue = round(sum(r.get("revenue_usd") or 0 for r in rows), 2)
    rated = [r for r in rows if r.get("rating_count")]
    avg = round(sum((r["rating_avg"] or 0) * r["rating_count"] for r in rated) /
                max(1, sum(r["rating_count"] for r in rated)), 2) if rated else None
    followers = await _db.creator_follows.count_documents({"creator_id": cid})
    return {"creator_id": cid, "games": len(rows), "active_games": sum(1 for r in rows if r.get("active")),
            "sales": sales, "revenue_usd": revenue, "plays": plays, "rating": avg, "followers": followers}


@router.post("/creators/{cid}/follow")
async def follow(cid: str, body: FollowBody):
    fid = (body.follower_id or "").strip()[:80]
    if not fid or fid == cid:
        return {"error": "invalid follower"}
    await _db.creator_follows.update_one(
        {"creator_id": cid, "follower_id": fid},
        {"$setOnInsert": {"creator_id": cid, "follower_id": fid, "at": _now()}}, upsert=True)
    return {"ok": True, "following": True, "followers": await _db.creator_follows.count_documents({"creator_id": cid})}


@router.post("/creators/{cid}/unfollow")
async def unfollow(cid: str, body: FollowBody):
    fid = (body.follower_id or "").strip()[:80]
    await _db.creator_follows.delete_one({"creator_id": cid, "follower_id": fid})
    return {"ok": True, "following": False, "followers": await _db.creator_follows.count_documents({"creator_id": cid})}


@router.get("/creators/{cid}")
async def creator_profile(cid: str, follower_id: str = Query("")):
    stats = await _creator_stats(cid)
    listings = await _db.marketplace_listings.find(
        {"creator_id": cid, "active": True}, {"_id": 0}).sort("created_at", -1).limit(50).to_list(50)
    ids = [l["playable_id"] for l in listings]
    games = {g["playable_id"]: g for g in
             await _db.playables.find({"playable_id": {"$in": ids}}, _GAME_LIGHT).to_list(len(ids) or 1)}
    for l in listings:
        g = games.get(l["playable_id"]) or {}
        l["title"] = g.get("title", "Untitled"); l["genre"] = g.get("genre", "arcade")
        l["has_cover"] = bool(g.get("has_cover")); l["plays"] = g.get("plays", 0)
    following = bool(follower_id) and bool(
        await _db.creator_follows.find_one({"creator_id": cid, "follower_id": follower_id}))
    return {"profile": stats, "listings": listings, "following": following}


@router.get("/creators")
async def creators_leaderboard(limit: int = Query(25, le=50)):
    rows = await _db.marketplace_listings.aggregate([
        {"$match": {"active": True}},
        {"$group": {"_id": "$creator_id", "sales": {"$sum": {"$ifNull": ["$sales", 0]}},
                    "revenue_usd": {"$sum": {"$ifNull": ["$revenue_usd", 0]}}, "games": {"$sum": 1},
                    "playable_ids": {"$push": "$playable_id"}}},
    ]).to_list(500)
    out = []
    for r in rows:
        if not r.get("_id"):
            continue
        ids = r.get("playable_ids", [])
        plays = 0
        if ids:
            gs = await _db.playables.find({"playable_id": {"$in": ids}}, {"_id": 0, "plays": 1}).to_list(len(ids))
            plays = sum(g.get("plays") or 0 for g in gs)
        followers = await _db.creator_follows.count_documents({"creator_id": r["_id"]})
        rev = round(r["revenue_usd"], 2)
        score = round(rev * 1.0 + r["sales"] * 2 + plays * 0.05 + followers * 3, 2)
        out.append({"creator_id": r["_id"], "sales": r["sales"], "revenue_usd": rev,
                    "games": r["games"], "plays": plays, "followers": followers, "score": score})
    out.sort(key=lambda x: (-x["score"], -x["revenue_usd"]))
    for i, c in enumerate(out):
        c["rank"] = i + 1
    return {"creators": out[:limit], "count": len(out)}


# ════════════════════════ #1 EARNINGS LEDGER + PAYOUTS ════════════════════════
async def credit_earnings(creator_id: str, gross: float, session_id: str, playable_id: str):
    """Called from the marketplace purchase finalizer. Idempotent per session."""
    if not creator_id or creator_id == "anon":
        return
    if await _db.creator_earnings_ledger.find_one({"session_id": session_id}):
        return
    net = round(gross * (1 - PLATFORM_FEE_PCT), 2)
    fee = round(gross - net, 2)
    await _db.creator_earnings_ledger.insert_one({
        "creator_id": creator_id, "session_id": session_id, "playable_id": playable_id,
        "gross": round(gross, 2), "fee": fee, "net": net, "at": _now()})
    await _db.creator_earnings.update_one(
        {"creator_id": creator_id},
        {"$inc": {"balance": net, "lifetime": net, "fees_paid": fee},
         "$set": {"updated_at": _now()}, "$setOnInsert": {"fee_pct": PLATFORM_FEE_PCT}}, upsert=True)


@router.get("/creators/{cid}/earnings")
async def earnings(cid: str):
    acct = await _db.creator_earnings.find_one({"creator_id": cid}, {"_id": 0}) or {
        "creator_id": cid, "balance": 0.0, "lifetime": 0.0, "fees_paid": 0.0, "fee_pct": PLATFORM_FEE_PCT}
    ledger = await _db.creator_earnings_ledger.find(
        {"creator_id": cid}, {"_id": 0}).sort("at", -1).limit(20).to_list(20)
    payouts = await _db.payout_requests.find(
        {"creator_id": cid}, {"_id": 0}).sort("requested_at", -1).limit(20).to_list(20)
    return {"account": {**acct, "fee_pct": acct.get("fee_pct", PLATFORM_FEE_PCT)},
            "ledger": ledger, "payouts": payouts}


class PayoutBody(BaseModel):
    amount: float = 0.0


@router.post("/creators/{cid}/payout-request")
async def payout_request(cid: str, body: PayoutBody):
    acct = await _db.creator_earnings.find_one({"creator_id": cid}, {"_id": 0})
    bal = round((acct or {}).get("balance", 0), 2)
    amt = round(body.amount or bal, 2)
    if bal <= 0:
        return {"error": "no balance to pay out"}
    if amt <= 0 or amt > bal:
        return {"error": f"amount must be between $0.01 and ${bal}"}
    pid = uuid.uuid4().hex
    await _db.payout_requests.insert_one({
        "payout_id": pid, "creator_id": cid, "amount": amt, "status": "pending", "requested_at": _now()})
    await _db.creator_earnings.update_one({"creator_id": cid}, {"$inc": {"balance": -amt}})
    return {"ok": True, "payout_id": pid, "amount": amt, "status": "pending",
            "remaining_balance": round(bal - amt, 2)}


# ════════════════════════ #9 REVIEWS + DISPUTES ════════════════════════
class ReviewBody(BaseModel):
    reviewer_id: str = ""
    rating: int = 0
    comment: str = ""


@router.post("/marketplace/{pid}/reviews")
async def add_review(pid: str, body: ReviewBody):
    if not await _db.marketplace_listings.find_one({"playable_id": pid}, {"_id": 1}):
        return {"error": "listing not found"}
    rid = (body.reviewer_id or "").strip()[:80]
    if not rid:
        return {"error": "reviewer_id required"}
    rating = int(body.rating or 0)
    if rating < 1 or rating > 5:
        return {"error": "rating must be 1-5"}
    verified = bool(await _db.marketplace_purchases.find_one(
        {"playable_id": pid, "buyer_id": rid, "payment_status": "paid"}))
    await _db.marketplace_reviews.update_one(
        {"playable_id": pid, "reviewer_id": rid},
        {"$set": {"playable_id": pid, "reviewer_id": rid, "rating": rating,
                  "comment": (body.comment or "").strip()[:500], "verified": verified, "at": _now()}},
        upsert=True)
    agg = await _db.marketplace_reviews.aggregate([
        {"$match": {"playable_id": pid}},
        {"$group": {"_id": None, "avg": {"$avg": "$rating"}, "n": {"$sum": 1}}},
    ]).to_list(1)
    avg = round(agg[0]["avg"], 2) if agg else rating
    n = agg[0]["n"] if agg else 1
    await _db.marketplace_listings.update_one({"playable_id": pid},
                                              {"$set": {"rating_avg": avg, "rating_count": n}})
    return {"ok": True, "rating_avg": avg, "rating_count": n, "verified": verified}


@router.get("/marketplace/{pid}/reviews")
async def get_reviews(pid: str, limit: int = Query(30, le=100)):
    rows = await _db.marketplace_reviews.find(
        {"playable_id": pid}, {"_id": 0}).sort("at", -1).limit(limit).to_list(limit)
    agg = await _db.marketplace_reviews.aggregate([
        {"$match": {"playable_id": pid}},
        {"$group": {"_id": None, "avg": {"$avg": "$rating"}, "n": {"$sum": 1}}},
    ]).to_list(1)
    return {"reviews": rows, "rating_avg": (round(agg[0]["avg"], 2) if agg else None),
            "rating_count": (agg[0]["n"] if agg else 0)}


class DisputeBody(BaseModel):
    buyer_id: str = ""
    reason: str = ""


@router.post("/marketplace/purchase/{session_id}/dispute")
async def dispute(session_id: str, body: DisputeBody):
    purchase = await _db.marketplace_purchases.find_one({"session_id": session_id}, {"_id": 0})
    if not purchase:
        return {"error": "purchase not found"}
    await _db.marketplace_disputes.update_one(
        {"session_id": session_id},
        {"$set": {"session_id": session_id, "playable_id": purchase.get("playable_id"),
                  "buyer_id": (body.buyer_id or purchase.get("buyer_id")),
                  "reason": (body.reason or "").strip()[:500], "status": "open", "at": _now()}},
        upsert=True)
    return {"ok": True, "status": "open", "detail": "dispute filed — our team will review"}


# ════════════════════════ #3 PREMIUM PASS (one-time, time-boxed) ════════════════════════
@router.get("/premium/plans")
async def premium_plans():
    return {"plans": [{"id": k, **v} for k, v in PREMIUM_PLANS.items()], "perks": [
        "⚡ 2× XP on every action", "🛠️ Priority finetune/bugsquash", "🏷️ Premium creator badge"]}


@router.get("/premium/status")
async def premium_status(visitor_id: str = Query(...)):
    ent = await _db.premium_entitlements.find_one(
        {"visitor_id": visitor_id}, {"_id": 0}, sort=[("expires_at", -1)])
    if not ent:
        return {"active": False}
    active = ent.get("expires_at", "") > _now()
    return {"active": active, "plan": ent.get("plan"), "expires_at": ent.get("expires_at")}


class PremiumCheckoutBody(BaseModel):
    visitor_id: str = ""
    plan: str = "monthly"
    origin_url: str = ""


@router.post("/premium/checkout")
async def premium_checkout(body: PremiumCheckoutBody, request: Request):
    if not STRIPE_API_KEY:
        return {"error": "payments not configured"}
    plan = body.plan if body.plan in PREMIUM_PLANS else "monthly"
    vid = (body.visitor_id or "anon").strip()[:80]
    cfg = PREMIUM_PLANS[plan]
    origin = (body.origin_url or "").rstrip("/") or str(request.base_url).rstrip("/")
    sc = _checkout(str(request.base_url))
    meta = {"source": "premium", "plan": plan, "visitor_id": vid, "days": str(cfg["days"])}
    req = CheckoutSessionRequest(
        amount=float(cfg["price"]), currency="usd",
        success_url=f"{origin}/premium?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{origin}/premium?cancelled=1", metadata=meta)
    try:
        session = await sc.create_checkout_session(req)
    except Exception as e:
        return {"error": f"stripe error: {str(e)[:200]}"}
    await _db.payment_transactions.insert_one({
        "session_id": session.session_id, "buyer_id": vid, "amount": float(cfg["price"]),
        "currency": "usd", "metadata": meta, "payment_status": "initiated", "status": "open",
        "processed": False, "created_at": _now()})
    return {"url": session.url, "session_id": session.session_id, "plan": plan}


@router.get("/premium/status/session/{session_id}")
async def premium_session_status(session_id: str, request: Request):
    txn = await _db.payment_transactions.find_one({"session_id": session_id}, {"_id": 0})
    if not txn:
        return {"error": "unknown session"}
    sc = _checkout(str(request.base_url))
    try:
        status = await sc.get_checkout_status(session_id)
    except Exception as e:
        return {"error": f"stripe error: {str(e)[:200]}", "payment_status": txn.get("payment_status")}
    await _db.payment_transactions.update_one(
        {"session_id": session_id},
        {"$set": {"status": status.status, "payment_status": status.payment_status, "updated_at": _now()}})
    granted = False
    if status.payment_status == "paid" and not txn.get("processed"):
        meta = txn.get("metadata", {})
        days = int(meta.get("days", 30))
        expires = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()
        await _db.premium_entitlements.update_one(
            {"session_id": session_id},
            {"$set": {"session_id": session_id, "visitor_id": meta.get("visitor_id", txn.get("buyer_id")),
                      "plan": meta.get("plan"), "expires_at": expires, "granted_at": _now()}}, upsert=True)
        await _db.payment_transactions.update_one({"session_id": session_id}, {"$set": {"processed": True}})
        granted = True
    return {"session_id": session_id, "payment_status": status.payment_status,
            "status": status.status, "premium_granted": granted}
