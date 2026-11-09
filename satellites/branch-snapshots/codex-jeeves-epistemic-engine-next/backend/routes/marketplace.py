"""
VI.3 Creator Marketplace — MONETIZATION (one-time purchase via Stripe Checkout).

A creator LISTS a generated game for sale at a price; a buyer purchases one-time
access through Stripe Checkout. The price is ALWAYS resolved server-side from the
listing doc — the client never dictates the amount (anti-tamper).

Flow:
  POST /api/marketplace/list                 — creator lists a playable for sale
  GET  /api/marketplace/listings             — browse active listings (hydrated)
  GET  /api/marketplace/listing/{pid}        — single listing + ownership check
  POST /api/marketplace/checkout             — create a Stripe Checkout session
  GET  /api/marketplace/checkout/status/{sid}— poll status (records purchase on paid)
  POST /api/webhook/stripe                    — Stripe webhook (source of truth)
  GET  /api/marketplace/purchases            — a buyer's purchased games

Buyer/creator identity is a client-generated visitor id (no auth layer yet).
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

from core.databases import client as _SHARED_MONGO_CLIENT
from core.anti_farm import rate_ok
from emergentintegrations.payments.stripe.checkout import (
    StripeCheckout, CheckoutSessionRequest,
)

router = APIRouter(prefix="/api", tags=["marketplace"])
_db = _SHARED_MONGO_CLIENT[os.environ.get("DB_NAME", "test_database")]

STRIPE_API_KEY = os.environ.get("STRIPE_API_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "") or None
MIN_PRICE = 0.50
MAX_PRICE = 500.0

_GAME_LIGHT = {
    "_id": 0, "playable_id": 1, "title": 1, "genre": 1, "has_cover": 1, "asset_status": 1,
    "plays": 1, "playability_score": 1, "evaluation.overall": 1, "moderation_status": 1,
    "moderation_note": 1,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _checkout(host_url: str) -> StripeCheckout:
    """Build a StripeCheckout bound to our webhook endpoint."""
    webhook_url = f"{host_url.rstrip('/')}/api/webhook/stripe"
    return StripeCheckout(api_key=STRIPE_API_KEY, webhook_url=webhook_url,
                          webhook_secret=STRIPE_WEBHOOK_SECRET)


# ── Listings ──────────────────────────────────────────────────────────────────
class ListBody(BaseModel):
    playable_id: str = ""
    price_usd: float = 0.0
    creator_id: str = ""
    summary: str = ""


@router.post("/marketplace/list")
async def create_listing(body: ListBody, request: Request):
    """Creator lists a ready playable for one-time sale. Re-listing updates price.
    VII.5: blocks games hidden by moderation, and attaches a near-duplicate
    similarity warning (IP protection) without blocking the listing."""
    if not rate_ok(request, "mkt_list", rate_per_sec=0.2, burst=6):
        return {"error": "rate_limited", "detail": "Too many listing attempts — slow down."}
    pid = (body.playable_id or "").strip()
    game = await _db.playables.find_one(
        {"playable_id": pid}, {**_GAME_LIGHT, "moderation_status": 1, "html": 1})
    if not game:
        return {"error": "playable not found"}
    if game.get("status") == "failed":
        return {"error": "cannot list a non-runnable game"}
    if game.get("moderation_status") == "hidden":
        return {"error": "this game was hidden by moderation and cannot be listed"}
    price = round(float(body.price_usd or 0), 2)
    if price < MIN_PRICE or price > MAX_PRICE:
        return {"error": f"price must be between ${MIN_PRICE} and ${MAX_PRICE}"}
    # Near-duplicate IP check (non-blocking advisory).
    similarity_warning = None
    try:
        from routes.governance import _shingles, _jaccard, SIM_SIMILAR
        my_sh = _shingles(game.get("html") or "")
        others = await _db.playables.find(
            {"playable_id": {"$ne": pid}, "status": "ready"},
            {"_id": 0, "playable_id": 1, "title": 1, "html": 1}).to_list(500)
        best = {"similarity": 0.0}
        for o in others:
            sim = _jaccard(my_sh, _shingles(o.get("html") or ""))
            if sim > best["similarity"]:
                best = {"playable_id": o["playable_id"], "title": o.get("title", "Untitled"), "similarity": round(sim, 4)}
        if best["similarity"] >= SIM_SIMILAR:
            similarity_warning = best
    except Exception:
        pass
    doc = {
        "playable_id": pid,
        "price_usd": price,
        "currency": "usd",
        "creator_id": (body.creator_id or "anon").strip()[:80],
        "summary": (body.summary or "").strip()[:280],
        "active": True,
        "updated_at": _now(),
    }
    await _db.marketplace_listings.update_one(
        {"playable_id": pid},
        {"$set": doc, "$setOnInsert": {"created_at": _now(), "sales": 0, "revenue_usd": 0.0}},
        upsert=True,
    )
    listing = await _db.marketplace_listings.find_one({"playable_id": pid}, {"_id": 0})
    return {"ok": True, "listing": listing, "similarity_warning": similarity_warning}


@router.delete("/marketplace/list/{pid}")
async def unlist(pid: str):
    r = await _db.marketplace_listings.update_one(
        {"playable_id": pid}, {"$set": {"active": False, "updated_at": _now()}})
    return {"ok": r.matched_count > 0}


@router.get("/marketplace/listings")
async def listings(limit: int = Query(40, le=100), sort: str = Query("newest")):
    """Browse active listings, hydrated with light game metadata + cover flag."""
    rows = await _db.marketplace_listings.find(
        {"active": True}, {"_id": 0}).sort("created_at", -1).limit(200).to_list(200)
    ids = [r["playable_id"] for r in rows]
    games = {g["playable_id"]: g for g in
             await _db.playables.find({"playable_id": {"$in": ids}}, _GAME_LIGHT).to_list(len(ids) or 1)}
    out = []
    for r in rows:
        g = games.get(r["playable_id"]) or {}
        out.append({
            **r,
            "title": g.get("title", "Untitled"),
            "genre": g.get("genre", "arcade"),
            "has_cover": bool(g.get("has_cover")),
            "plays": g.get("plays", 0),
            "overall": (g.get("evaluation") or {}).get("overall"),
        })
    if sort == "price_low":
        out.sort(key=lambda x: x["price_usd"])
    elif sort == "price_high":
        out.sort(key=lambda x: -x["price_usd"])
    elif sort == "bestselling":
        out.sort(key=lambda x: -(x.get("sales") or 0))
    return {"listings": out[:limit], "count": len(out)}


@router.get("/marketplace/listing/{pid}")
async def listing_detail(pid: str, buyer_id: str = Query("")):
    r = await _db.marketplace_listings.find_one({"playable_id": pid}, {"_id": 0})
    if not r:
        return {"error": "not listed"}
    owned = False
    if buyer_id:
        owned = bool(await _db.marketplace_purchases.find_one(
            {"playable_id": pid, "buyer_id": buyer_id, "payment_status": "paid"}))
    g = await _db.playables.find_one({"playable_id": pid}, _GAME_LIGHT) or {}
    return {"listing": {**r, "title": g.get("title"), "genre": g.get("genre"),
                        "has_cover": bool(g.get("has_cover"))}, "owned": owned}


# ── Checkout ────────────────────────────────────────────────────────────────--
class CheckoutBody(BaseModel):
    playable_id: str = ""
    buyer_id: str = ""
    origin_url: str = ""


@router.post("/marketplace/checkout")
async def checkout(body: CheckoutBody, request: Request):
    """Create a Stripe Checkout session. Price is resolved from the listing
    server-side; the client cannot set the amount."""
    if not STRIPE_API_KEY:
        return {"error": "payments not configured"}
    pid = (body.playable_id or "").strip()
    listing = await _db.marketplace_listings.find_one(
        {"playable_id": pid, "active": True}, {"_id": 0})
    if not listing:
        return {"error": "listing not found or inactive"}
    buyer = (body.buyer_id or "anon").strip()[:80]
    # Already owned? short-circuit.
    if await _db.marketplace_purchases.find_one(
            {"playable_id": pid, "buyer_id": buyer, "payment_status": "paid"}):
        return {"error": "already_owned", "owned": True}

    amount = round(float(listing["price_usd"]), 2)
    if amount < MIN_PRICE or amount > MAX_PRICE:
        return {"error": "invalid listing price"}

    origin = (body.origin_url or "").rstrip("/") or str(request.base_url).rstrip("/")
    success_url = f"{origin}/marketplace?session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{origin}/marketplace?cancelled=1"

    host_url = str(request.base_url)
    sc = _checkout(host_url)
    metadata = {"playable_id": pid, "buyer_id": buyer, "source": "marketplace"}
    req = CheckoutSessionRequest(
        amount=amount, currency="usd",
        success_url=success_url, cancel_url=cancel_url, metadata=metadata,
    )
    try:
        session = await sc.create_checkout_session(req)
    except Exception as e:
        return {"error": f"stripe error: {str(e)[:200]}"}

    # Persist the transaction BEFORE returning (status=initiated).
    await _db.payment_transactions.insert_one({
        "session_id": session.session_id,
        "playable_id": pid,
        "buyer_id": buyer,
        "amount": amount,
        "currency": "usd",
        "metadata": metadata,
        "payment_status": "initiated",   # initiated → paid | failed | expired
        "status": "open",                # stripe session status
        "processed": False,              # purchase recorded idempotency guard
        "created_at": _now(),
    })
    return {"url": session.url, "session_id": session.session_id}


async def _finalize_purchase(txn: dict):
    """Idempotently record a paid purchase + bump listing aggregates."""
    if txn.get("processed"):
        return
    # Premium-pass sessions are finalized by the premium status endpoint, not here.
    if (txn.get("metadata") or {}).get("source") == "premium":
        return
    pid = txn.get("playable_id")
    buyer = txn.get("buyer_id", "anon")
    await _db.marketplace_purchases.update_one(
        {"session_id": txn["session_id"]},
        {"$set": {
            "session_id": txn["session_id"], "playable_id": pid, "buyer_id": buyer,
            "amount": txn.get("amount"), "currency": txn.get("currency", "usd"),
            "payment_status": "paid", "purchased_at": _now(),
        }},
        upsert=True,
    )
    await _db.marketplace_listings.update_one(
        {"playable_id": pid},
        {"$inc": {"sales": 1, "revenue_usd": float(txn.get("amount") or 0)}})
    await _db.payment_transactions.update_one(
        {"session_id": txn["session_id"]}, {"$set": {"processed": True}})
    # #1 revenue-split → credit the creator's earnings ledger (idempotent per session)
    try:
        listing = await _db.marketplace_listings.find_one({"playable_id": pid}, {"_id": 0, "creator_id": 1})
        from routes.creator_economy import credit_earnings
        await credit_earnings((listing or {}).get("creator_id", ""), float(txn.get("amount") or 0),
                              txn["session_id"], pid)
    except Exception:
        pass
    # #4 server-authoritative XP for a real purchase (cannot be farmed)
    try:
        from routes.liveops import grant_xp
        await grant_xp(buyer, "purchase")
    except Exception:
        pass


@router.get("/marketplace/checkout/status/{session_id}")
async def checkout_status(session_id: str, request: Request):
    """Poll Stripe for the session's payment status; record the purchase on first
    'paid'. Safe to poll repeatedly (idempotent)."""
    if not STRIPE_API_KEY:
        return {"error": "payments not configured"}
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
        {"$set": {"status": status.status, "payment_status": status.payment_status,
                  "updated_at": _now()}})
    if status.payment_status == "paid":
        txn = await _db.payment_transactions.find_one({"session_id": session_id}, {"_id": 0})
        await _finalize_purchase(txn)
    return {
        "session_id": session_id,
        "status": status.status,
        "payment_status": status.payment_status,
        "amount_total": status.amount_total,
        "currency": status.currency,
        "playable_id": txn.get("playable_id"),
    }


@router.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    """Stripe webhook — the source of truth. Marks the transaction paid + records
    the purchase on checkout.session.completed."""
    if not STRIPE_API_KEY:
        return {"received": False}
    body = await request.body()
    sig = request.headers.get("Stripe-Signature")
    sc = _checkout(str(request.base_url))
    try:
        ev = await sc.handle_webhook(body, sig)
    except Exception as e:
        return {"received": False, "error": str(e)[:200]}
    if ev.session_id:
        await _db.payment_transactions.update_one(
            {"session_id": ev.session_id},
            {"$set": {"payment_status": ev.payment_status or "unknown",
                      "webhook_event": ev.event_type, "updated_at": _now()}})
        if (ev.payment_status == "paid") or (ev.event_type == "checkout.session.completed"):
            txn = await _db.payment_transactions.find_one({"session_id": ev.session_id}, {"_id": 0})
            if txn:
                await _finalize_purchase(txn)
    return {"received": True}


@router.get("/marketplace/purchases")
async def purchases(buyer_id: str = Query(...), limit: int = Query(50, le=100)):
    rows = await _db.marketplace_purchases.find(
        {"buyer_id": buyer_id, "payment_status": "paid"}, {"_id": 0}
    ).sort("purchased_at", -1).limit(limit).to_list(limit)
    ids = [r["playable_id"] for r in rows]
    games = {g["playable_id"]: g for g in
             await _db.playables.find({"playable_id": {"$in": ids}}, _GAME_LIGHT).to_list(len(ids) or 1)}
    for r in rows:
        g = games.get(r["playable_id"]) or {}
        r["title"] = g.get("title", "Untitled")
        r["genre"] = g.get("genre", "arcade")
        r["has_cover"] = bool(g.get("has_cover"))
    return {"purchases": rows, "count": len(rows)}


@router.get("/marketplace/mine")
async def my_studio(creator_id: str = Query(...)):
    """Creator Dashboard data: a creator's listings (active + inactive) hydrated
    with game meta, plus aggregate KPIs (games / active / sales / revenue / plays)."""
    rows = await _db.marketplace_listings.find(
        {"creator_id": creator_id}, {"_id": 0}).sort("created_at", -1).to_list(200)
    ids = [r["playable_id"] for r in rows]
    games = {g["playable_id"]: g for g in
             await _db.playables.find({"playable_id": {"$in": ids}}, _GAME_LIGHT).to_list(len(ids) or 1)}
    listings, sales, revenue, plays = [], 0, 0.0, 0
    for r in rows:
        g = games.get(r["playable_id"]) or {}
        p = g.get("plays") or 0
        sales += r.get("sales") or 0
        revenue += r.get("revenue_usd") or 0
        plays += p
        listings.append({
            **r, "title": g.get("title", "Untitled"), "genre": g.get("genre", "arcade"),
            "has_cover": bool(g.get("has_cover")), "plays": p,
            "asset_status": g.get("asset_status"),
            "overall": (g.get("evaluation") or {}).get("overall"),
            "moderation_status": g.get("moderation_status", "ok"),
            "moderation_note": g.get("moderation_note", ""),
        })
    return {
        "listings": listings,
        "totals": {
            "games": len(rows),
            "active": sum(1 for r in rows if r.get("active")),
            "sales": sales,
            "revenue_usd": round(revenue, 2),
            "plays": plays,
        },
    }



@router.get("/marketplace/creators/trending")
async def trending_creators(limit: int = Query(20, le=50)):
    """Leaderboard of creators ranked by a composite of revenue + sales + plays.
    Powers the Creator Dashboard 'Trending Creators' rail."""
    rows = await _db.marketplace_listings.aggregate([
        {"$match": {"active": True}},
        {"$group": {
            "_id": "$creator_id",
            "sales": {"$sum": {"$ifNull": ["$sales", 0]}},
            "revenue_usd": {"$sum": {"$ifNull": ["$revenue_usd", 0]}},
            "games": {"$sum": 1},
            "playable_ids": {"$push": "$playable_id"},
        }},
    ]).to_list(500)
    out = []
    for r in rows:
        if not r.get("_id"):
            continue
        ids = r.get("playable_ids", [])
        plays = 0
        if ids:
            games = await _db.playables.find(
                {"playable_id": {"$in": ids}}, {"_id": 0, "plays": 1}).to_list(len(ids))
            plays = sum(g.get("plays") or 0 for g in games)
        rev = round(r["revenue_usd"], 2)
        score = round(rev * 1.0 + r["sales"] * 2 + plays * 0.05, 2)
        out.append({"creator_id": r["_id"], "sales": r["sales"], "revenue_usd": rev,
                    "games": r["games"], "plays": plays, "score": score})
    out.sort(key=lambda x: (-x["score"], -x["revenue_usd"], -x["plays"]))
    for i, c in enumerate(out):
        c["rank"] = i + 1
    return {"creators": out[:limit], "count": len(out)}

