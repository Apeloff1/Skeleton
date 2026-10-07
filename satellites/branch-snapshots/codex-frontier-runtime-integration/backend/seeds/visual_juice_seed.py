"""
Advanced Visual Juice & Cinematics Glossaries.
Collection: `visual_juice`
"""
import hashlib, logging, itertools
from datetime import datetime, timezone

JUICE_EFFECTS = [
    ("screen-shake",    {"amp_px":4,"freq_hz":24,"dur_ms":120}),
    ("hit-stop",        {"freeze_ms":35,"slowdown_factor":0.05}),
    ("chromatic-aberration",{"strength":2.5}),
    ("radial-blur",     {"strength":0.45,"falloff_px":160}),
    ("vignette-pulse",  {"strength":0.7,"rate_hz":2}),
    ("motion-trail",    {"length_ms":160,"opacity_curve":"easeOut"}),
    ("particle-burst",  {"count":48,"speed_min":40,"speed_max":300}),
    ("floating-numbers",{"velocity_y":-120,"fade_ms":900}),
    ("sparkle-trail",   {"density":12,"size_curve":"easeInOut"}),
    ("ko-flash",        {"colour":"#fff","opacity":0.85,"fade_ms":120}),
    ("zoom-punch",      {"factor":1.04,"dur_ms":120,"easing":"easeOutQuad"}),
    ("shockwave",       {"radius_px":260,"thickness_px":12,"dur_ms":280}),
    ("slash-streak",    {"length_px":140,"width_px":6,"opacity":0.85}),
    ("ground-cracks",   {"branches":7,"length_px":120}),
    ("camera-bob-walk", {"amp_px":3,"freq_hz":1.4}),
    ("depth-of-field-pull",{"focus_in_ms":300,"focus_out_ms":300}),
    ("colour-grade-LUT",{"lut":"warm-action"}),
    ("bloom-pulse",     {"intensity":0.7,"threshold":0.85}),
    ("speed-line-overlay",{"density":24,"length_px":80}),
    ("impact-ripple",   {"layers":3,"interval_ms":40}),
]
CINEMATIC_BEATS = [
    ("cold-open-static",  "Pre-title still with diegetic sound"),
    ("title-card-drop",   "Title appears with rhythm-synced impact"),
    ("establishing-shot", "Wide drone-style flythrough of world"),
    ("character-intro",   "Slow-mo profile pan + name supers"),
    ("montage-progress",  "Quick-cut training/build sequence"),
    ("final-stand",       "Hero faces overwhelming odds; back-to-back"),
    ("sacrifice",         "Companion makes ultimate sacrifice"),
    ("twist-reveal",      "Earlier shot reframed with new context"),
    ("epilogue-vignette", "Multiple small scenes showing world state"),
    ("post-credits-tease","Single shot hinting at next chapter"),
]
INTENSITIES = ["subtle","medium","strong","explosive"]

def _vid(*p): return "juice_" + hashlib.md5("|".join(p).encode()).hexdigest()[:14]

def build_visual_juice():
    out = []
    for (name, params), inten in itertools.product(JUICE_EFFECTS, INTENSITIES):
        out.append({"id":_vid(name,inten,"juice"),"category":"juice","effect":name,"intensity":inten,
                    "params":params,"description":f"{inten} {name} juice effect",
                    "tags":[name,inten,"juice","vfx"]})
    for name, desc in CINEMATIC_BEATS:
        out.append({"id":_vid(name,"beat"),"category":"cinematic-beat","beat":name,
                    "description":desc,"tags":[name,"cinematic","beat"]})
    return out

async def seed_visual_juice(db):
    docs = build_visual_juice()
    try:
        await db.visual_juice.create_index("id", unique=True)
        await db.visual_juice.create_index("category")
        await db.visual_juice.create_index("effect")
        await db.visual_juice.create_index([("tags", 1)])
    except Exception: pass
    now = datetime.now(timezone.utc).isoformat(); inserted = 0
    for d in docs:
        d["indexed_at"] = now
        try:
            r = await db.visual_juice.update_one({"id":d["id"]},{"$set":d},upsert=True)
            if r.upserted_id is not None: inserted += 1
        except Exception: pass
    return {"inserted": inserted, "total": await db.visual_juice.count_documents({})}
