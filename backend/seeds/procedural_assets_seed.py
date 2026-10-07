"""
Procedural assets + content catalogues. ~6000 rows of recipes/seeds the
agent can roll for any generated game.

Collections:
  • procgen_recipes        — noise/dungeon/name/loot/quest generators
  • content_catalogues     — items, enemies, biomes, weapons, classes, etc.
"""
from __future__ import annotations
import hashlib, logging, itertools
from datetime import datetime, timezone

log = logging.getLogger("knowledge.procedural_assets")

RECIPE_KINDS = [
    ("perlin-terrain",   "octaves=4 persistence=0.5 lacunarity=2.0 — classic biome heightmap"),
    ("simplex-cave",     "3D simplex thresholded at 0.6 — cellular cave system"),
    ("wfc-dungeon",      "Wave-Function-Collapse on hand-authored tile set"),
    ("bsp-dungeon",      "Binary Space Partition dungeon with corridor stitching"),
    ("voronoi-region",   "Voronoi cells → political region map"),
    ("l-system-tree",    "L-system grammar for procedural foliage"),
    ("markov-name",      "Markov-chain name generator (n=3 chars)"),
    ("loot-table",       "Weighted-tier loot table with affixes"),
    ("quest-grammar",    "Linear quest grammar with substitution slots"),
    ("dialogue-tree",    "Branching dialogue with mood + skill checks"),
    ("music-procedural", "Markov-chain melody with mode constraints"),
    ("npc-schedule",     "24h NPC schedule from goal-action grammar"),
]

VARIANT_KEYS = ["low-poly", "realistic", "pixel", "voxel", "stylized", "sci-fi", "medieval", "horror", "fantasy", "cyberpunk"]

CATALOGUE_KINDS = {
    "weapons":   ["sword","axe","hammer","dagger","bow","crossbow","staff","wand","shield","spear","halberd","katana","scythe","mace","flail","club","rifle","pistol","shotgun","sniper","smg","lmg","plasma","laser","railgun","flamethrower","grenade-launcher","rocket-launcher"],
    "enemies":   ["goblin","orc","troll","giant","skeleton","zombie","vampire","werewolf","slime","dragon","wyvern","phoenix","golem","demon","angel","abyss","voidling","mecha","drone","alien-hivelord"],
    "biomes":    ["forest","jungle","desert","tundra","swamp","plains","mountain","volcano","ocean","underwater-trench","cavern","sky-island","void-rift","crystal-grotto"],
    "items":     ["potion","elixir","gem","orb","rune","scroll","key","map","compass","ration","torch","rope","grappling-hook","medkit"],
    "armors":    ["leather","chainmail","plate","mythril","adamantite","dragonscale","shadowweave","ceramic","nano-fiber","powered-suit"],
    "classes":   ["warrior","mage","rogue","cleric","paladin","ranger","druid","warlock","monk","barbarian","necromancer","summoner","engineer","medic","sniper","infiltrator"],
    "magic":     ["fire","ice","lightning","earth","wind","water","holy","shadow","arcane","void","blood","time","gravity","sound","mind"],
    "status-fx": ["poison","burn","freeze","stun","silence","blind","slow","haste","shield","regen","bleed","shock","weakness","vulnerability","reflect","thorns"],
    "npc-roles": ["blacksmith","alchemist","merchant","innkeeper","questgiver","trainer","healer","guard","thief","assassin","oracle","librarian"],
}

RARITY = ["common","uncommon","rare","epic","legendary","mythic"]
ERAS = ["medieval","renaissance","industrial","modern","near-future","far-future","post-apoc","fantasy","steampunk","cyberpunk"]


def _hid(*parts): return hashlib.md5("|".join(parts).encode()).hexdigest()[:14]


def build_procgen_recipes():
    out = []
    for (k, desc), variant in itertools.product(RECIPE_KINDS, VARIANT_KEYS):
        out.append({
            "id": f"recipe_{_hid(k, variant)}",
            "kind": k,
            "variant": variant,
            "description": f"{desc} (variant: {variant})",
            "params": {"octaves": 4, "persistence": 0.5, "lacunarity": 2.0, "seed_hint": "agent-derived"},
            "tags": [k, variant, "procgen"],
        })
    return out


def build_catalogues():
    out = []
    for cat, items in CATALOGUE_KINDS.items():
        for it, rarity, era in itertools.product(items, RARITY, ERAS):
            out.append({
                "id": f"cat_{_hid(cat, it, rarity, era)}",
                "category": cat,
                "item": it,
                "rarity": rarity,
                "era": era,
                "name": f"{rarity.title()} {era.title()} {it.replace('-', ' ').title()}",
                "stats": {"power": RARITY.index(rarity) * 25 + ERAS.index(era) * 5, "weight": 5},
                "tags": [cat, it, rarity, era, "catalogue"],
            })
    return out


async def seed_procedural_assets(db) -> dict:
    recipes = build_procgen_recipes()
    catalogues = build_catalogues()
    try:
        await db.procgen_recipes.create_index("id", unique=True)
        await db.procgen_recipes.create_index("kind")
        await db.procgen_recipes.create_index([("tags", 1)])
        await db.content_catalogues.create_index("id", unique=True)
        await db.content_catalogues.create_index("category")
        await db.content_catalogues.create_index("rarity")
        await db.content_catalogues.create_index("era")
        await db.content_catalogues.create_index([("tags", 1)])
    except Exception:
        pass
    now = datetime.now(timezone.utc).isoformat()
    r_in = 0; c_in = 0
    for d in recipes:
        d["indexed_at"] = now
        try:
            r = await db.procgen_recipes.update_one({"id": d["id"]}, {"$set": d}, upsert=True)
            if r.upserted_id is not None: r_in += 1
        except Exception: pass
    BATCH = 500
    for i in range(0, len(catalogues), BATCH):
        for d in catalogues[i:i+BATCH]:
            d["indexed_at"] = now
            try:
                r = await db.content_catalogues.update_one({"id": d["id"]}, {"$set": d}, upsert=True)
                if r.upserted_id is not None: c_in += 1
            except Exception: pass
    return {
        "recipes_inserted": r_in, "recipes_total": await db.procgen_recipes.count_documents({}),
        "catalogues_inserted": c_in, "catalogues_total": await db.content_catalogues.count_documents({}),
    }
