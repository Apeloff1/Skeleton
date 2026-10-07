"""
Deep Lore, Mythology & World-Building Ontologies.
Collection: `deep_lore`
"""
import hashlib, logging, itertools
from datetime import datetime, timezone

MYTHOLOGIES = ["Norse","Greek","Egyptian","Celtic","Hindu","Japanese","Mesoamerican","Slavic","Sumerian","Yoruba","Polynesian","Inuit","Native-American","Persian","Chinese","Korean","Aboriginal"]
ARCHETYPES = ["hero","trickster","mentor","shadow","mother","father","shapeshifter","threshold-guardian","messenger","ally","creator","destroyer","sage","fool","rebel","caregiver"]
COSMOLOGIES = ["flat-disc","spherical","world-tree","infinite-spiral","layered-realms","simulated","multiverse","void-with-islands","clockwork","living-organism"]
FACTIONS = ["empire","republic","theocracy","merchant-guild","nomad-clan","rebellion","academy","cult","corporation","federation","hivemind","tribe-confederacy"]
ELEMENTS = ["fire","water","earth","air","void","light","shadow","life","death","time","mind","chaos","order","nature"]

def _lid(*p): return "lore_" + hashlib.md5("|".join(p).encode()).hexdigest()[:14]

def build_deep_lore():
    out = []
    for myth, arch in itertools.product(MYTHOLOGIES, ARCHETYPES):
        out.append({"id":_lid(myth,arch,"figure"),"category":"figure","mythology":myth,"archetype":arch,
                    "description":f"{arch} figure within {myth} tradition","tags":[myth.lower(),arch,"mythology","figure"]})
    for cos, fac in itertools.product(COSMOLOGIES, FACTIONS):
        out.append({"id":_lid(cos,fac,"world"),"category":"world-building","cosmology":cos,"faction":fac,
                    "description":f"World with {cos} cosmology and dominant {fac}","tags":[cos,fac,"world","setting"]})
    for myth, el in itertools.product(MYTHOLOGIES, ELEMENTS):
        out.append({"id":_lid(myth,el,"element"),"category":"element-symbolism","mythology":myth,"element":el,
                    "description":f"Symbolism of {el} in {myth} tradition","tags":[myth.lower(),el,"element","symbol"]})
    return out

async def seed_deep_lore(db):
    docs = build_deep_lore()
    try:
        await db.deep_lore.create_index("id", unique=True)
        await db.deep_lore.create_index("category")
        await db.deep_lore.create_index("mythology")
        await db.deep_lore.create_index([("tags", 1)])
    except Exception: pass
    now = datetime.now(timezone.utc).isoformat(); inserted = 0
    for d in docs:
        d["indexed_at"] = now
        try:
            r = await db.deep_lore.update_one({"id":d["id"]},{"$set":d},upsert=True)
            if r.upserted_id is not None: inserted += 1
        except Exception: pass
    return {"inserted": inserted, "total": await db.deep_lore.count_documents({})}
