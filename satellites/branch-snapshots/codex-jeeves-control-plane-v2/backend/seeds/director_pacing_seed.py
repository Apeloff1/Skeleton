"""
Procedural Director & Pacing Oracles.
Collection: `director_pacing`
"""
import hashlib, logging, itertools
from datetime import datetime, timezone

BEATS = [
    ("intro-calm",      {"duration_min":2,"tension":0.2,"density":0.1}),
    ("rising-action",   {"duration_min":6,"tension":0.5,"density":0.4}),
    ("climax",          {"duration_min":3,"tension":0.95,"density":0.9}),
    ("falling-action",  {"duration_min":4,"tension":0.4,"density":0.3}),
    ("resolution",      {"duration_min":2,"tension":0.1,"density":0.05}),
    ("twist",           {"duration_min":1,"tension":0.85,"density":0.4}),
    ("breather",        {"duration_min":3,"tension":0.15,"density":0.1}),
    ("buildup-stealth", {"duration_min":4,"tension":0.55,"density":0.2}),
]
DIRECTOR_RULES = [
    ("L4D-director",       "Spawn intensity based on player stress + last-event distance"),
    ("AI-rubberband",      "Bring losing player closer without obvious cheat"),
    ("dynamic-difficulty", "Continuously tune challenge to skill estimate"),
    ("narrative-budget",   "Reserve story beats to fire at lull thresholds"),
    ("event-cooldowns",    "Per-event-type cooldown prevents repetition"),
    ("setpiece-pacing",    "Setpieces gated by minutes-since-last"),
    ("failure-recovery",   "Easier mob after player wipes 2x in 5 min"),
    ("discovery-bias",     "Bias spawns toward unexplored zones for >5min idle players"),
    ("social-proof-trigger","Stream social events when other party members hit milestones"),
    ("long-tail-engagement","Schedule small rewards every 90s on calm beats"),
]
GENRES = ["co-op","rpg","horror","roguelike","sandbox","shooter","survival","action","arpg","adventure"]

def _did(*p): return "director_" + hashlib.md5("|".join(p).encode()).hexdigest()[:14]

def build_director_pacing():
    out = []
    for (b, params), genre in itertools.product(BEATS, GENRES):
        out.append({"id":_did(b,genre,"beat"),"category":"beat","beat":b,"genre":genre,"params":params,
                    "description":f"{b} beat tuned for {genre}","tags":[b,genre,"beat","pacing"]})
    for (rule, desc), genre in itertools.product(DIRECTOR_RULES, GENRES):
        out.append({"id":_did(rule,genre,"rule"),"category":"director-rule","rule":rule,"genre":genre,
                    "description":desc,"tags":[rule,genre,"director","pacing"]})
    return out

async def seed_director_pacing(db):
    docs = build_director_pacing()
    try:
        await db.director_pacing.create_index("id", unique=True)
        await db.director_pacing.create_index("category")
        await db.director_pacing.create_index("genre")
        await db.director_pacing.create_index([("tags", 1)])
    except Exception: pass
    now = datetime.now(timezone.utc).isoformat(); inserted = 0
    for d in docs:
        d["indexed_at"] = now
        try:
            r = await db.director_pacing.update_one({"id":d["id"]},{"$set":d},upsert=True)
            if r.upserted_id is not None: inserted += 1
        except Exception: pass
    return {"inserted": inserted, "total": await db.director_pacing.count_documents({})}
