"""
Human Cognitive & Playstyle Psychographics.
Collection: `cognitive_psychographics`
"""
import hashlib, logging, itertools
from datetime import datetime, timezone

ARCHETYPES = [
    ("achiever",     "Bartle: maximises completion, leaderboards, achievements"),
    ("explorer",     "Bartle: maps every corner, lore deep-diver"),
    ("socializer",   "Bartle: guilds, party play, in-game friendships"),
    ("killer",       "Bartle: dominates others, PvP, leaderboards"),
    ("casual",       "Plays for short sessions, easy on-ramps preferred"),
    ("hardcore",     "Plays for hours, tolerates grind & complexity"),
    ("completionist","100% trophies, every collectable"),
    ("speedrunner",  "Optimises route for time, breaks systems"),
    ("roleplayer",   "Inhabits character, narrative-first"),
    ("min-maxer",    "Optimises builds for theoretical maximum"),
    ("power-gamer",  "Stays at meta build at all times"),
    ("cosmetics-collector","Buys/earns every skin"),
    ("economist",    "Plays the trade-market layer"),
    ("griefer",      "Adversarial — needs containment in design"),
    ("streamer",     "Performative; needs entertaining feedback loops"),
    ("speedhater",   "Wants slow, contemplative play"),
]
COG_FACTORS = [
    ("working-memory",      "max 7±2 items tracked; minimise simultaneous mechanics"),
    ("reaction-time",       "avg 250 ms; design windows >= 350 ms for fairness"),
    ("reading-load",        "<60 chars per tutorial tip; reading test fail under stress"),
    ("colour-blindness",    "~8% males red-green deficient; never colour-only signal"),
    ("motor-precision",     "controller stick deadzone & curve impacts skill ceiling"),
    ("spatial-reasoning",   "3D minimaps + waypoint helps low-spatial players"),
    ("audio-processing",    "directional audio cues + subtitles parity"),
    ("attention-span",      "micro-rewards every 90s on casual modes"),
    ("frustration-recovery","die-and-restart loop must be <8s for tight games"),
    ("sense-of-progress",   "visible XP bar + level-up gates every 5-10 min early on"),
    ("social-cognition",    "team UI labels, pings & comms scaffolding"),
    ("learning-curve",      "tutorial budget 5-15 min before throwing real systems"),
]
INTENSITIES = ["low","medium","high"]

def _pid(*p): return "cog_" + hashlib.md5("|".join(p).encode()).hexdigest()[:14]

def build_cognitive():
    out = []
    for (name, desc), inten in itertools.product(ARCHETYPES, INTENSITIES):
        out.append({"id":_pid(name,inten,"arch"),"category":"archetype","archetype":name,"intensity":inten,
                    "description":desc,"tags":[name,inten,"archetype","psychographic"]})
    for name, desc in COG_FACTORS:
        out.append({"id":_pid(name,"factor"),"category":"cognitive-factor","factor":name,
                    "description":desc,"tags":[name,"cognitive","factor"]})
    return out

async def seed_cognitive(db):
    docs = build_cognitive()
    try:
        await db.cognitive_psychographics.create_index("id", unique=True)
        await db.cognitive_psychographics.create_index("category")
        await db.cognitive_psychographics.create_index([("tags", 1)])
    except Exception: pass
    now = datetime.now(timezone.utc).isoformat(); inserted = 0
    for d in docs:
        d["indexed_at"] = now
        try:
            r = await db.cognitive_psychographics.update_one({"id":d["id"]},{"$set":d},upsert=True)
            if r.upserted_id is not None: inserted += 1
        except Exception: pass
    return {"inserted": inserted, "total": await db.cognitive_psychographics.count_documents({})}
