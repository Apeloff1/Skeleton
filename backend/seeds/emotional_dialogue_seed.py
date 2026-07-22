"""
Emotional AI & Dynamic Dialogue Matrices.
Collection: `emotional_dialogue`
"""
import hashlib, logging, itertools
from datetime import datetime, timezone

EMOTIONS = ["joy","trust","fear","surprise","sadness","disgust","anger","anticipation",
            "love","submission","awe","disapproval","remorse","contempt","aggressiveness","optimism"]
INTENSITIES = ["trace","mild","moderate","strong","intense","overwhelming"]
CONTEXTS = ["combat","exploration","trade","romance","betrayal","loss","victory","defeat","mystery","comedy","crisis","reunion"]
RESPONSE_KINDS = ["verbal","non-verbal","action","posture","micro-expression","vocalization"]

def _did(*p): return "emo_" + hashlib.md5("|".join(p).encode()).hexdigest()[:14]

def build_emotional_dialogue():
    out = []
    for emo, inten, ctx in itertools.product(EMOTIONS, INTENSITIES, CONTEXTS):
        out.append({
            "id": _did(emo,inten,ctx),
            "emotion": emo,
            "intensity": inten,
            "context": ctx,
            "response_kinds": RESPONSE_KINDS,
            "sample_lines": [
                f"[{emo}/{inten}] character reaction during {ctx}",
                f"NPC bark conveying {inten} {emo} in {ctx} scenario",
                f"Player-targeted line scaling {emo} intensity to {inten}",
            ],
            "bias_matrix": {
                "approach":  round((0.5 + INTENSITIES.index(inten)*0.1) * (1 if emo in ("joy","trust","love","anticipation") else -1), 3),
                "avoid":     round((0.5 + INTENSITIES.index(inten)*0.1) * (1 if emo in ("fear","sadness","disgust") else 0), 3),
                "aggress":   round((0.5 + INTENSITIES.index(inten)*0.1) * (1 if emo in ("anger","aggressiveness","contempt") else 0), 3),
            },
            "description": f"{inten} {emo} reaction matrix in {ctx} context",
            "tags": [emo, inten, ctx, "emotion", "dialogue"],
        })
    return out

async def seed_emotional_dialogue(db):
    docs = build_emotional_dialogue()
    try:
        await db.emotional_dialogue.create_index("id", unique=True)
        await db.emotional_dialogue.create_index("emotion")
        await db.emotional_dialogue.create_index("context")
        await db.emotional_dialogue.create_index("intensity")
        await db.emotional_dialogue.create_index([("tags", 1)])
    except Exception: pass
    now = datetime.now(timezone.utc).isoformat(); inserted = 0
    for d in docs:
        d["indexed_at"] = now
        try:
            r = await db.emotional_dialogue.update_one({"id":d["id"]},{"$set":d},upsert=True)
            if r.upserted_id is not None: inserted += 1
        except Exception: pass
    return {"inserted": inserted, "total": await db.emotional_dialogue.count_documents({})}
