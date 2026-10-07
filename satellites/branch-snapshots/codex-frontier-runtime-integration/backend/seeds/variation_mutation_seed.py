"""
Variation, Mutation & Procedural Tweak data.
Collection: `variation_mutation`
"""
import hashlib, logging, itertools
from datetime import datetime, timezone

AXES = ["colour-hue","colour-saturation","colour-value","size-scale","size-aspect","speed","damage","hp",
        "crit-chance","projectile-count","spread-angle","cooldown","cost","weight","reload-time","range",
        "sound-pitch","sound-volume","visual-emission","trail-length","shader-tint","icon-frame","sprite-flip",
        "animation-speed","behaviour-aggression","behaviour-curiosity","behaviour-cooperation"]
DISTRIBUTIONS = [
    ("uniform",  {"min":-1.0,"max":1.0}),
    ("gaussian", {"mean":0.0,"sigma":0.5}),
    ("triangle", {"min":-1.0,"peak":0.0,"max":1.0}),
    ("power-law",{"alpha":2.0,"x_min":0.05}),
    ("bimodal",  {"mean1":-0.6,"mean2":0.6,"sigma":0.2}),
    ("stair",    {"steps":5}),
    ("perlin",   {"octaves":3,"persistence":0.5}),
]
INTENSITIES = ["subtle","noticeable","strong","dramatic","chaotic"]

def _vid(*p): return "var_" + hashlib.md5("|".join(p).encode()).hexdigest()[:14]

def build_variation():
    out = []
    for axis, (dist, params), intensity in itertools.product(AXES, DISTRIBUTIONS, INTENSITIES):
        out.append({"id":_vid(axis,dist,intensity),"axis":axis,"distribution":dist,"params":params,
                    "intensity":intensity,"description":f"{intensity} {dist} variation on {axis}",
                    "tags":[axis,dist,intensity,"variation","mutation"]})
    return out

async def seed_variation(db):
    docs = build_variation()
    try:
        await db.variation_mutation.create_index("id", unique=True)
        await db.variation_mutation.create_index("axis")
        await db.variation_mutation.create_index("distribution")
        await db.variation_mutation.create_index("intensity")
        await db.variation_mutation.create_index([("tags", 1)])
    except Exception: pass
    now = datetime.now(timezone.utc).isoformat(); inserted = 0
    for d in docs:
        d["indexed_at"] = now
        try:
            r = await db.variation_mutation.update_one({"id":d["id"]},{"$set":d},upsert=True)
            if r.upserted_id is not None: inserted += 1
        except Exception: pass
    return {"inserted": inserted, "total": await db.variation_mutation.count_documents({})}
