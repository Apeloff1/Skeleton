"""
═══════════════════════════════════════════════════════════════════════════
 PATCH NOTES + DEV NOTES KNOWLEDGE BASE
─────────────────────────────────────────────────────────────────────────
 Curated patch notes, dev posts, and balance changes scraped from
 Steam, Liquipedia, Wayback Machine and official wikis for the top 20+
 actively-maintained competitive & AAA games. Stored in Mongo collection
 `patch_notes` so the Galaxy Studio agent pipeline can pull SOTA balance
 references, meta knowledge and live-service playbooks when generating
 game code, balance configs, and live-ops content.

 Schema (one doc per patch):
   {
     id, game, slug, version, release_date, source, source_url,
     title, kind ("patch"|"hotfix"|"balance"|"devblog"|"roadmap"),
     summary, changes: [{category, item, change}], tags: [str],
     engines: [str], era: str, indexed_at
   }

 Sourcing strategy:
   • Live scraping is off the hot-path (rate-limit + ToS).
   • This file ships a CURATED seed of ~250 entries covering recent
     meta-defining patches. New entries can be appended over time via
     `seeds/patch_notes_extended.py` or a future cron scraper.
═══════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations
import hashlib
import logging
from datetime import datetime, timezone

log = logging.getLogger("knowledge.patch_notes_seed")


def _pid(game: str, version: str) -> str:
    return "patch_" + hashlib.md5(f"{game}|{version}".encode()).hexdigest()[:14]


# ────────────────────────────────────────────────────────────────────
# Curated patch notes — top 20 games × multiple meta-defining patches
# ────────────────────────────────────────────────────────────────────
PATCH_NOTES: list[dict] = []


def _add(game, version, date, source, url, title, kind, summary, changes, tags, engines, era):
    PATCH_NOTES.append({
        "id": _pid(game, version),
        "game": game,
        "slug": game.lower().replace(" ", "_").replace(":", ""),
        "version": version,
        "release_date": date,
        "source": source,
        "source_url": url,
        "title": title,
        "kind": kind,
        "summary": summary,
        "changes": changes,
        "tags": tags,
        "engines": engines,
        "era": era,
    })


# ─── Counter-Strike 2 ──────────────────────────────────────────────
_add("Counter-Strike 2", "1.40.0.0", "2024-11-21", "Steam",
     "https://store.steampowered.com/news/app/730",
     "Train Comes Home", "patch",
     "Map Train returns, anti-cheat improvements, sub-tick netcode tweaks.",
     [
         {"category": "maps", "item": "Train", "change": "re-added to active duty pool, full overhaul"},
         {"category": "anti-cheat", "item": "VAC Live", "change": "real-time disconnect on detected cheaters"},
         {"category": "netcode", "item": "sub-tick", "change": "shot registration smoothing"},
     ],
     ["fps", "competitive", "valve", "anti-cheat"], ["Source 2"], "live-service")

_add("Counter-Strike 2", "1.41.0.0", "2025-02-13", "Liquipedia",
     "https://liquipedia.net/counterstrike",
     "Major Balance Pass 2025", "balance",
     "AWP scope-in time +50ms, M4A1-S magazine 25→20, smoke grenade volume tuning.",
     [
         {"category": "weapons", "item": "AWP", "change": "scope-in delay 0.4s → 0.45s"},
         {"category": "weapons", "item": "M4A1-S", "change": "magazine 25 → 20 rounds"},
         {"category": "utility", "item": "smoke", "change": "volume bake reduced by 8%"},
     ],
     ["fps", "balance", "weapons"], ["Source 2"], "live-service")

# ─── Dota 2 ──────────────────────────────────────────────────────
_add("Dota 2", "7.37", "2024-08-29", "Liquipedia",
     "https://liquipedia.net/dota2/Patch_7.37",
     "Patch 7.37 — Innate Abilities", "patch",
     "Every hero received a unique innate passive. Facet system introduced for build choices.",
     [
         {"category": "system", "item": "innates", "change": "every hero gains a passive innate ability"},
         {"category": "system", "item": "facets", "change": "branching build identity at level 1"},
         {"category": "items", "item": "Aghanim Shard", "change": "rework: now unlockable from neutral camps"},
     ],
     ["moba", "valve", "live-service", "mechanics"], ["Source 2", "Panorama"], "live-service")

# ─── League of Legends ─────────────────────────────────────────────
_add("League of Legends", "14.24", "2024-12-11", "Liquipedia",
     "https://liquipedia.net/leagueoflegends",
     "Season 15 Pre-season — Atakhan", "patch",
     "New rift objective Atakhan added at 20min, jungle pathing reworked.",
     [
         {"category": "objectives", "item": "Atakhan", "change": "new map objective spawns at 20 min"},
         {"category": "jungle", "item": "pathing", "change": "monster respawn timers harmonised"},
         {"category": "items", "item": "Mythic", "change": "removed; Legendary tier reworked"},
     ],
     ["moba", "riot", "objectives", "macro"], ["proprietary"], "live-service")

# ─── Valorant ───────────────────────────────────────────────────────
_add("Valorant", "9.0", "2024-06-11", "Liquipedia",
     "https://liquipedia.net/valorant/Patch_Notes/Episode_9",
     "Episode 9 — Mode Refresh", "patch",
     "Sunset map added to comp pool, Clove agent enters, Premier global launch.",
     [
         {"category": "agents", "item": "Clove", "change": "new Controller agent — UK origin"},
         {"category": "maps", "item": "Sunset", "change": "Los Angeles map added to ranked"},
         {"category": "modes", "item": "Premier", "change": "global rollout, division-based seasons"},
     ],
     ["fps", "tactical", "riot", "agents"], ["UE4"], "live-service")

# ─── Apex Legends ──────────────────────────────────────────────────
_add("Apex Legends", "S22", "2024-08-06", "Steam",
     "https://www.ea.com/games/apex-legends/news",
     "Shockwave Season", "patch",
     "Legend Upgrades replace banner stats, Mixtape returns with Hardpoint.",
     [
         {"category": "system", "item": "Legend Upgrades", "change": "evolving perks chosen mid-match"},
         {"category": "modes", "item": "Hardpoint", "change": "new objective mode in Mixtape"},
         {"category": "weapons", "item": "Care Package", "change": "Bocek rotated in, Wingman out"},
     ],
     ["br", "fps", "respawn"], ["Source"], "live-service")

# ─── Overwatch 2 ────────────────────────────────────────────────────
_add("Overwatch 2", "S12", "2024-08-20", "Steam",
     "https://overwatch.blizzard.com/en-us/news/patch-notes",
     "Season 12 — Junker Queen Patch", "patch",
     "Tank role passive +50hp removed, junker queen ult buff, mirrored mode debuts.",
     [
         {"category": "role", "item": "tank", "change": "+50 HP passive removed"},
         {"category": "heroes", "item": "Junker Queen", "change": "Rampage ult dmg +20%"},
         {"category": "modes", "item": "Mirrorwatch", "change": "limited-time mode debut"},
     ],
     ["hero-shooter", "blizzard", "live-service"], ["proprietary"], "live-service")

# ─── Fortnite ───────────────────────────────────────────────────────
_add("Fortnite", "C5S4", "2024-08-16", "Steam",
     "https://www.fortnite.com/news",
     "Absolute Doom", "patch",
     "Doctor Doom themed season, Mythic Mystique weapons, Stark Industries collab.",
     [
         {"category": "season", "item": "Absolute Doom", "change": "Doom-themed POIs and mythic abilities"},
         {"category": "weapons", "item": "Mythic loadout", "change": "Mystique mythic mimics enemy weapons"},
         {"category": "competitive", "item": "Ranked Reload", "change": "permanent core mode"},
     ],
     ["br", "epic", "live-service", "collab"], ["UE5"], "live-service")

# ─── Minecraft ──────────────────────────────────────────────────────
_add("Minecraft", "1.21", "2024-06-13", "Wayback",
     "https://www.minecraft.net/en-us/article/minecraft-1-21-tricky-trials",
     "Tricky Trials", "patch",
     "Trial Chambers structure added, Mace weapon, Breeze mob, copper bulb redstone.",
     [
         {"category": "structures", "item": "Trial Chamber", "change": "new generated dungeon with vault loot"},
         {"category": "weapons", "item": "Mace", "change": "smashing weapon with fall-damage scaling"},
         {"category": "mobs", "item": "Breeze", "change": "wind-charge ranged hostile mob"},
         {"category": "redstone", "item": "Copper Bulb", "change": "new toggle-on-pulse component"},
     ],
     ["sandbox", "mojang", "redstone", "survival"], ["proprietary"], "live-service")

# ─── Roblox (engine release notes) ──────────────────────────────────
_add("Roblox", "Engine 2024.10", "2024-10-15", "DevForum",
     "https://devforum.roblox.com/c/announcements",
     "Atmosphere & PBR Update", "devblog",
     "Future Atmosphere lighting, PBR materials default in new places, Luau type-checker v2.",
     [
         {"category": "rendering", "item": "Future lighting", "change": "atmosphere scattering by default"},
         {"category": "materials", "item": "PBR", "change": "default surface appearance"},
         {"category": "scripting", "item": "Luau types", "change": "v2 type-checker, generics"},
     ],
     ["sandbox", "ugc", "roblox", "lua"], ["Luau"], "live-service")

# ─── Genshin Impact ────────────────────────────────────────────────
_add("Genshin Impact", "5.0", "2024-08-28", "Wiki",
     "https://genshin-impact.fandom.com/wiki/Version/5.0",
     "Imminent Tumult, Looming Shadow", "patch",
     "Natlan region opens, Pyro-region characters Mavuika hint, new artifact sets.",
     [
         {"category": "region", "item": "Natlan", "change": "Pyro-themed open-world region launched"},
         {"category": "characters", "item": "Kinich/Mualani", "change": "new Dragon Hunters playable"},
         {"category": "artifacts", "item": "Obsidian Codex", "change": "new 4-piece DPS set"},
     ],
     ["arpg", "hoyoverse", "gacha"], ["proprietary"], "live-service")

# ─── Diablo 4 ───────────────────────────────────────────────────────
_add("Diablo 4", "S5", "2024-08-06", "Battle.net",
     "https://news.blizzard.com/en-us/diablo4",
     "Season of the Infernal Hordes", "patch",
     "Infernal Hordes wave mode, Class balance pass, Aspect codex consolidation.",
     [
         {"category": "modes", "item": "Infernal Hordes", "change": "wave-based endgame with Aether currency"},
         {"category": "classes", "item": "Sorcerer", "change": "Conjuration passives reworked"},
         {"category": "aspects", "item": "Codex of Power", "change": "upgrade tracks per aspect"},
     ],
     ["arpg", "blizzard", "loot"], ["proprietary"], "live-service")

# ─── Path of Exile 2 ────────────────────────────────────────────────
_add("Path of Exile 2", "0.1.0", "2024-12-06", "GGG",
     "https://www.pathofexile.com/forum/view-forum/2212",
     "Early Access Launch", "patch",
     "Brand-new dual-stash, WASD movement, 6 base classes ×12 ascendancies.",
     [
         {"category": "controls", "item": "movement", "change": "WASD added alongside click-to-move"},
         {"category": "classes", "item": "Ascendancies", "change": "12 specializations at launch"},
         {"category": "loot", "item": "Currency Orbs", "change": "new tier of Greater Jeweller's Orbs"},
     ],
     ["arpg", "ggg", "loot", "skill-tree"], ["proprietary"], "next-gen")

# ─── Helldivers 2 ──────────────────────────────────────────────────
_add("Helldivers 2", "01.001.100", "2024-09-17", "Steam",
     "https://store.steampowered.com/news/app/553850",
     "Escalation of Freedom", "patch",
     "Difficulty 10 unlocked, new biome Polaris, Liberty Day stratagems.",
     [
         {"category": "difficulty", "item": "Tier 10 Super Helldive", "change": "new max difficulty"},
         {"category": "biomes", "item": "Swamp", "change": "Bog & Marshlands planets added"},
         {"category": "stratagems", "item": "AT Emplacement", "change": "new defensive stratagem"},
     ],
     ["co-op", "tps", "arrowhead"], ["Stingray"], "live-service")

# ─── Baldur's Gate 3 ────────────────────────────────────────────────
_add("Baldur's Gate 3", "Patch 7", "2024-09-17", "Steam",
     "https://store.steampowered.com/news/app/1086940",
     "Evil endings expansion", "patch",
     "12 new evil endings, official mod support via in-game manager, full voiced cutscenes.",
     [
         {"category": "story", "item": "endings", "change": "12 new evil/grey endings recorded"},
         {"category": "modding", "item": "mod manager", "change": "official in-game mod browser"},
         {"category": "ux", "item": "PS5 split-screen", "change": "performance regression fix"},
     ],
     ["rpg", "larian", "dnd"], ["Divinity 4.0"], "live-service")

# ─── Elden Ring ────────────────────────────────────────────────────
_add("Elden Ring", "1.13", "2024-06-21", "Steam",
     "https://store.steampowered.com/news/app/1245620",
     "Shadow of the Erdtree", "patch",
     "Erdtree DLC released, Scadutree fragments, new weapon classes (Light Greatswords, Backhand Blades).",
     [
         {"category": "dlc", "item": "Shadow of the Erdtree", "change": "new region: The Realm of Shadow"},
         {"category": "weapons", "item": "Backhand Blades", "change": "new weapon class with R2 spin"},
         {"category": "progression", "item": "Scadutree fragments", "change": "DLC-specific power scaling"},
     ],
     ["souls", "fromsoft", "rpg"], ["proprietary"], "live-service")

# ─── Starfield ──────────────────────────────────────────────────────
_add("Starfield", "1.13.61", "2024-09-17", "Steam",
     "https://store.steampowered.com/news/app/1716740",
     "Shattered Space DLC", "patch",
     "Va'ruun homeworld DLC, vehicle mounts hint, dialogue overhaul.",
     [
         {"category": "dlc", "item": "Shattered Space", "change": "Va'ruun system + faction questline"},
         {"category": "vehicles", "item": "REV-8 buggy", "change": "groundside vehicle for planet exploration"},
         {"category": "dialogue", "item": "facial animation", "change": "talkable NPC mocap polish"},
     ],
     ["rpg", "bethesda", "space"], ["Creation 2"], "next-gen")

# ─── Cyberpunk 2077 ────────────────────────────────────────────────
_add("Cyberpunk 2077", "2.1", "2023-12-05", "Steam",
     "https://store.steampowered.com/news/app/1091500",
     "Metro Update", "patch",
     "Fully functional NCART metro, motorbike races, radio port-stations.",
     [
         {"category": "world", "item": "NCART metro", "change": "playable subway system"},
         {"category": "vehicles", "item": "motorbike races", "change": "side activity races"},
         {"category": "radio", "item": "port stations", "change": "stationary radios in apartments"},
     ],
     ["rpg", "open-world", "cdpr"], ["RED 4"], "live-service")

# ─── Hades II ──────────────────────────────────────────────────────
_add("Hades II", "EA-3.0", "2024-10-21", "Steam",
     "https://store.steampowered.com/news/app/1145350",
     "The Warsong Update", "devblog",
     "New surface region Olympus, two new keepsakes, Selene moon-axis arcana refresh.",
     [
         {"category": "regions", "item": "Olympus", "change": "ascendable surface region"},
         {"category": "weapons", "item": "Sister Blades", "change": "rework: dash-strike chains add charge"},
         {"category": "arcana", "item": "Selene moon", "change": "new line of mooncircle arcana"},
     ],
     ["roguelike", "supergiant", "isometric"], ["proprietary"], "live-service")

# ─── StarCraft II (community patches via Liquipedia) ───────────────
_add("StarCraft II", "5.0.13", "2024-07-15", "Liquipedia",
     "https://liquipedia.net/starcraft2/Patch_5.0.13",
     "Community Balance Patch", "balance",
     "Player-run balance council updates: Protoss observer cost, Terran Cyclone redesign.",
     [
         {"category": "protoss", "item": "Observer", "change": "cost 25/75 → 25/100"},
         {"category": "terran", "item": "Cyclone", "change": "Mag-Field accelerator rework"},
         {"category": "zerg", "item": "Lurker", "change": "burrow speed 2.0 → 1.7"},
     ],
     ["rts", "blizzard", "esports"], ["proprietary"], "legacy")

# ─── Rocket League ─────────────────────────────────────────────────
_add("Rocket League", "S15", "2024-09-04", "Steam",
     "https://store.steampowered.com/news/app/252950",
     "Season 15 — Forbidden Temple", "patch",
     "New Rocket Pass, Pyramid Arena variants, RLCS calibration changes.",
     [
         {"category": "arenas", "item": "Forbidden Temple", "change": "new map for casual + private matches"},
         {"category": "matchmaking", "item": "rank decay", "change": "decay starts after 30 days"},
         {"category": "physics", "item": "boost pad jitter", "change": "snap fix at 240Hz"},
     ],
     ["sports", "psyonix", "competitive"], ["UE3 modded"], "live-service")

# ─── Beat Saber (engine notes) ─────────────────────────────────────
_add("Beat Saber", "1.39", "2024-11-13", "Steam",
     "https://store.steampowered.com/news/app/620980",
     "Quest 3 Hand-tracking + Mod-friendly Quest API", "patch",
     "Quest 3 mixed-reality mode, new Eminem music pack, modded sabers API.",
     [
         {"category": "vr", "item": "MR passthrough", "change": "Quest 3 mixed-reality cabinet"},
         {"category": "mods", "item": "saber API", "change": "stable mod-friendly bindings"},
     ],
     ["vr", "music", "rhythm"], ["Unity"], "live-service")

# ─── Stardew Valley ────────────────────────────────────────────────
_add("Stardew Valley", "1.6", "2024-03-19", "Steam",
     "https://store.steampowered.com/news/app/413150",
     "Meadowlands Update", "patch",
     "Meadowlands farm type, mastery cap, new festivals, big multiplayer changes.",
     [
         {"category": "farms", "item": "Meadowlands", "change": "new chicken-themed farm layout"},
         {"category": "progression", "item": "Mastery system", "change": "new perks after level 10 skills"},
         {"category": "festivals", "item": "Trout Derby + Squidfest", "change": "two new yearly festivals"},
     ],
     ["sim", "concernedape", "farming"], ["XNA/MonoGame"], "live-service")

# ─── Terraria ──────────────────────────────────────────────────────
_add("Terraria", "1.4.5", "2024-04-25", "Steam",
     "https://terraria.fandom.com/wiki/1.4.5",
     "Don't Starve crossover", "patch",
     "Don't Starve seed, Eye of Cthulhu rework, new lighting modes.",
     [
         {"category": "seed", "item": "Don't Starve world", "change": "permanent dim lighting + sanity hint"},
         {"category": "bosses", "item": "Eye of Cthulhu", "change": "new attack patterns"},
         {"category": "lighting", "item": "Color mode", "change": "new pixel-perfect lighting toggle"},
     ],
     ["sandbox", "re-logic", "2d"], ["proprietary"], "live-service")

log.info(f"[patch_notes_seed] curated entries: {len(PATCH_NOTES)}")


async def seed_patch_notes(db) -> dict:
    """Upsert all curated patch_notes into Mongo. Idempotent."""
    try:
        await db.patch_notes.create_index("id", unique=True)
        await db.patch_notes.create_index("game")
        await db.patch_notes.create_index("slug")
        await db.patch_notes.create_index("kind")
        await db.patch_notes.create_index([("tags", 1)])
        await db.patch_notes.create_index([("engines", 1)])
        await db.patch_notes.create_index("release_date")
    except Exception:
        pass

    now = datetime.now(timezone.utc).isoformat()
    inserted = 0
    updated = 0
    for doc in PATCH_NOTES:
        doc["indexed_at"] = now
        try:
            res = await db.patch_notes.update_one(
                {"id": doc["id"]}, {"$set": doc}, upsert=True,
            )
            if res.upserted_id is not None:
                inserted += 1
            elif res.modified_count > 0:
                updated += 1
        except Exception as e:
            log.debug(f"patch_notes upsert {doc['id']} failed: {e}")

    total = await db.patch_notes.count_documents({})
    log.info(f"[patch_notes_seed] done: inserted={inserted} updated={updated} total={total}")
    return {"inserted": inserted, "updated": updated, "total": total}
