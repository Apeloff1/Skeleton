"""
Emergent Ecosystems & Simulated Biology Matrices.
Collection: `ecosystems_biology`
"""
import hashlib, logging, itertools
from datetime import datetime, timezone

SPECIES = [
    ("prey-herbivore-small",  {"diet":"plants","speed":3.2,"reproduction":"litter","life_y":2}),
    ("prey-herbivore-large",  {"diet":"plants","speed":4.8,"reproduction":"single","life_y":15}),
    ("predator-stalker",      {"diet":"prey-small","speed":7.5,"reproduction":"litter","life_y":6}),
    ("predator-apex",         {"diet":"prey-large","speed":9.0,"reproduction":"single","life_y":20}),
    ("scavenger",             {"diet":"carrion","speed":5.0,"reproduction":"swarm","life_y":3}),
    ("insect-pollinator",     {"diet":"nectar","speed":1.0,"reproduction":"swarm","life_y":0.1}),
    ("flora-fast-grow",       {"diet":"sun+water","speed":0,"reproduction":"spore","life_y":1}),
    ("flora-slow-grow",       {"diet":"sun+water","speed":0,"reproduction":"seed","life_y":80}),
    ("fungus",                {"diet":"decay","speed":0,"reproduction":"spore","life_y":5}),
    ("aquatic-filter-feeder", {"diet":"plankton","speed":0.5,"reproduction":"broadcast","life_y":0.5}),
    ("aquatic-predator",      {"diet":"fish-small","speed":6.0,"reproduction":"clutch","life_y":12}),
    ("flying-omnivore",       {"diet":"varied","speed":8.0,"reproduction":"clutch","life_y":10}),
    ("underground-burrower",  {"diet":"roots+insects","speed":2.0,"reproduction":"litter","life_y":4}),
    ("bioluminescent-deep",   {"diet":"plankton","speed":0.3,"reproduction":"broadcast","life_y":3}),
    ("colonial-insect",       {"diet":"varied","speed":0.5,"reproduction":"queen-based","life_y":0.2}),
]
INTERACTIONS = ["predation","competition","symbiosis-mutualistic","symbiosis-commensal","parasitism",
                "pollination","seed-dispersal","decomposition","herbivory","territorial","mating","kin-selection"]
BIOMES = ["forest-temperate","forest-tropical","desert","tundra","savanna","wetland","coral-reef","deep-ocean",
          "alpine","chaparral","grassland","taiga","mangrove","cave-system","volcanic","arctic-ice"]

def _eid(*p): return "eco_" + hashlib.md5("|".join(p).encode()).hexdigest()[:14]

def build_ecosystems():
    out = []
    for (sp, params), biome in itertools.product(SPECIES, BIOMES):
        out.append({"id":_eid(sp,biome,"species"),"category":"species","species":sp,"biome":biome,
                    "params":params,"description":f"{sp} adapted to {biome}","tags":[sp,biome,"species","ecology"]})
    for inter, biome in itertools.product(INTERACTIONS, BIOMES):
        out.append({"id":_eid(inter,biome,"interaction"),"category":"interaction","interaction":inter,"biome":biome,
                    "description":f"{inter} interaction common in {biome}","tags":[inter,biome,"interaction","ecology"]})
    return out

async def seed_ecosystems(db):
    docs = build_ecosystems()
    try:
        await db.ecosystems_biology.create_index("id", unique=True)
        await db.ecosystems_biology.create_index("category")
        await db.ecosystems_biology.create_index("biome")
        await db.ecosystems_biology.create_index([("tags", 1)])
    except Exception: pass
    now = datetime.now(timezone.utc).isoformat(); inserted = 0
    for d in docs:
        d["indexed_at"] = now
        try:
            r = await db.ecosystems_biology.update_one({"id":d["id"]},{"$set":d},upsert=True)
            if r.upserted_id is not None: inserted += 1
        except Exception: pass
    return {"inserted": inserted, "total": await db.ecosystems_biology.count_documents({})}
