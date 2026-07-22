"""
Galaxy Studio — Mega Game Asset Databases
Seeds 200 themed MongoDB collections covering:
  games, mechanics, descriptors, models, renders, sprites, sounds, voices,
  names, graphics, ambiance, retention mechanics, and more.

Every collection:
  • ~1,000 deterministic docs (no user data — pure reference assets)
  • Common schema: {id, name, category, subcategory, tags[], keywords[],
                    era, genre_tags[], agent_ids[], virtual_asset_count,
                    summary, params{}, created_at}
  • Indexed on: category, subcategory, tags, keywords, era
  • Agent-queryable via POST /api/galaxy-studio/mega-dbs/query

Total: ~200,000 reference docs across 200 collections = massive + fully internal.
"""
from __future__ import annotations
import asyncio
import hashlib
import logging
import uuid
from datetime import datetime

log = logging.getLogger("GalaxyStudio.MegaSeeder")

# ═══════════════════════════════════════════════════════════════════════
# COLLECTION MANIFEST — 200 catalogs grouped by category
# ═══════════════════════════════════════════════════════════════════════
MEGA_CATEGORIES: dict = {
    "games": [
        "games_aaa_open_world", "games_indie_pixel", "games_soulslike", "games_metroidvania",
        "games_roguelike", "games_platformer_2d", "games_platformer_3d", "games_jrpg",
        "games_crpg", "games_rts", "games_turn_based", "games_moba",
        "games_battle_royale", "games_fps_arena", "games_horror_survival", "games_stealth",
    ],
    "mechanics": [
        "mechanics_combat_melee", "mechanics_combat_ranged", "mechanics_combat_magic",
        "mechanics_movement_parkour", "mechanics_movement_flight", "mechanics_movement_swim",
        "mechanics_inventory_grid", "mechanics_crafting_recipes", "mechanics_trading_market",
        "mechanics_stealth_detection", "mechanics_survival_hunger", "mechanics_base_building",
        "mechanics_procgen_dungeons", "mechanics_procgen_terrain", "mechanics_dialog_trees",
        "mechanics_ai_companions", "mechanics_ai_enemies", "mechanics_time_manipulation",
        "mechanics_summoning", "mechanics_alchemy_brewing",
    ],
    "descriptors": [
        "descriptors_mood", "descriptors_tone", "descriptors_art_style", "descriptors_pacing",
        "descriptors_difficulty_curve", "descriptors_scale", "descriptors_theme",
        "descriptors_narrative_structure", "descriptors_color_palette", "descriptors_era",
        "descriptors_setting", "descriptors_protagonist_archetype",
        "descriptors_antagonist_archetype", "descriptors_camera_style",
        "descriptors_perspective", "descriptors_interaction_style",
        "descriptors_progression_style", "descriptors_replay_value",
        "descriptors_story_arc_shape", "descriptors_tension_curve",
    ],
    "models": [
        "models_characters_humanoid", "models_characters_fantasy", "models_characters_scifi",
        "models_creatures_small", "models_creatures_medium", "models_creatures_giant",
        "models_weapons_melee", "models_weapons_ranged", "models_weapons_magical",
        "models_vehicles_ground", "models_vehicles_air", "models_vehicles_water",
        "models_vehicles_space", "models_buildings_medieval", "models_buildings_modern",
        "models_buildings_futuristic", "models_props_household", "models_props_industrial",
        "models_nature_trees", "models_nature_rocks",
    ],
    "renders": [
        "renders_environment", "renders_character_shaders", "renders_lighting_presets",
        "renders_weather_effects", "renders_particle_fx", "renders_post_process_fx",
        "renders_hdri_skies", "renders_skybox_cubemaps", "renders_decal_library",
        "renders_shader_library", "renders_volumetric_fog", "renders_reflection_probes",
        "renders_shadow_maps", "renders_bloom_presets", "renders_water_simulation",
        "renders_smoke_trails",
    ],
    "sprites": [
        "sprites_tiles_16x16", "sprites_tiles_32x32", "sprites_tiles_64x64",
        "sprites_character_8bit", "sprites_character_16bit", "sprites_character_32bit",
        "sprites_hud_icons", "sprites_weapon_icons", "sprites_item_icons",
        "sprites_cursor_sets", "sprites_emote_icons", "sprites_animation_frames",
        "sprites_particle_atlas", "sprites_ui_buttons", "sprites_loading_bars",
        "sprites_map_icons",
    ],
    "sounds": [
        "sounds_impacts", "sounds_explosions", "sounds_footsteps", "sounds_weather",
        "sounds_ambient_forest", "sounds_ambient_city", "sounds_ambient_cave",
        "sounds_ambient_space", "sounds_weapons_melee", "sounds_weapons_ranged",
        "sounds_ui_clicks", "sounds_notifications", "sounds_creature_calls",
        "sounds_engine_vehicles", "sounds_magic_casts", "sounds_doors_chests",
    ],
    "voices": [
        "voices_male_deep", "voices_male_heroic", "voices_male_villain", "voices_female_soft",
        "voices_female_warrior", "voices_child_male", "voices_child_female",
        "voices_elder_male", "voices_elder_female", "voices_narrator",
        "voices_creature_growl", "voices_creature_roar", "voices_alien",
        "voices_robot", "voices_ghost", "voices_announcer",
    ],
    "names": [
        "names_heroic_male", "names_heroic_female", "names_villainous",
        "names_fantasy_kingdoms", "names_cities", "names_taverns", "names_guilds",
        "names_spells", "names_weapons", "names_artifacts", "names_factions",
        "names_quests", "names_mountains", "names_rivers", "names_starships",
        "names_dragons",
    ],
    "graphics": [
        "graphics_textures_wood", "graphics_textures_stone", "graphics_textures_metal",
        "graphics_textures_fabric", "graphics_textures_skin", "graphics_textures_water",
        "graphics_textures_lava", "graphics_textures_ice", "graphics_palettes_warm",
        "graphics_palettes_cool", "graphics_palettes_neon", "graphics_palettes_pastel",
        "graphics_gradients", "graphics_normal_maps", "graphics_height_maps",
        "graphics_noise_maps",
    ],
    "ambiance": [
        "ambiance_tavern", "ambiance_dungeon", "ambiance_forest_day", "ambiance_forest_night",
        "ambiance_snowstorm", "ambiance_rain_heavy", "ambiance_city_day", "ambiance_city_night",
        "ambiance_space_station", "ambiance_cathedral", "ambiance_underwater",
        "ambiance_sewer", "ambiance_desert_wind", "ambiance_volcano",
        "ambiance_laboratory", "ambiance_battlefield",
    ],
    "retention": [
        "retention_daily_quests", "retention_login_streak", "retention_battle_pass",
        "retention_limited_events", "retention_weekly_challenges",
        "retention_guild_contribution", "retention_leaderboards",
        "retention_seasonal_rotation", "retention_achievement_meta", "retention_loot_tables",
        "retention_new_game_plus", "retention_cosmetic_unlocks",
    ],
    # ═════════════════════════════════════════════════════════════════════
    # ★ EXPANSION 2026-02 — 10 new categories × 12 collections × 3000 docs
    # = 360,000 additional reference docs. These fulfill the
    # forward-declared CONTENT_PREFIXES in core/databases.py and give the
    # agent swarms a richer source of game-world primitives.
    # ═════════════════════════════════════════════════════════════════════
    "enemies": [
        "enemies_humanoid", "enemies_beasts", "enemies_undead", "enemies_elementals",
        "enemies_robots", "enemies_aliens", "enemies_swarm", "enemies_corrupted",
        "enemies_mythical", "enemies_demonic", "enemies_celestial", "enemies_constructs",
    ],
    "npcs": [
        "npcs_villagers", "npcs_merchants", "npcs_guards", "npcs_nobles",
        "npcs_priests", "npcs_scholars", "npcs_rogues", "npcs_bards",
        "npcs_smiths", "npcs_explorers", "npcs_companions", "npcs_mentors",
    ],
    "quests": [
        "quests_main_story", "quests_side", "quests_fetch", "quests_escort",
        "quests_assassination", "quests_exploration", "quests_puzzle", "quests_dungeon",
        "quests_faction", "quests_romance", "quests_morality", "quests_recurring",
    ],
    "bosses": [
        "bosses_humanoid_warriors", "bosses_dragons", "bosses_demon_lords", "bosses_ancient_evils",
        "bosses_corrupted_heroes", "bosses_titans", "bosses_mechanical", "bosses_eldritch",
        "bosses_swarm_queens", "bosses_celestial", "bosses_undead_kings", "bosses_pirate_captains",
    ],
    "puzzles": [
        "puzzles_logic", "puzzles_pattern", "puzzles_sokoban", "puzzles_lock_combination",
        "puzzles_riddle", "puzzles_spatial", "puzzles_timing", "puzzles_environmental",
        "puzzles_arithmetic", "puzzles_chess_chains", "puzzles_mirror", "puzzles_sliding",
    ],
    "factions": [
        "factions_kingdoms", "factions_guilds", "factions_cults", "factions_corporations",
        "factions_rebels", "factions_pirates", "factions_nobles", "factions_assassins",
        "factions_merchants", "factions_clergy", "factions_secret_societies", "factions_mercenaries",
    ],
    "loot": [
        "loot_weapons", "loot_armor", "loot_potions", "loot_artifacts",
        "loot_currency", "loot_consumables", "loot_keys", "loot_relics",
        "loot_recipes", "loot_runes", "loot_scrolls", "loot_treasures",
    ],
    "lore": [
        "lore_history", "lore_mythology", "lore_creation_myths", "lore_prophecies",
        "lore_legendary_figures", "lore_lost_civilizations", "lore_artifacts_legendary",
        "lore_factions_history", "lore_pantheons", "lore_natural_phenomena",
        "lore_languages_dead", "lore_celestial_events",
    ],
    "worldgen": [
        "worldgen_biomes", "worldgen_climate_zones", "worldgen_terrain_layers",
        "worldgen_water_systems", "worldgen_settlement_patterns",
        "worldgen_resource_distribution", "worldgen_road_networks", "worldgen_dungeon_layouts",
        "worldgen_atmosphere_zones", "worldgen_ley_lines", "worldgen_economic_routes",
        "worldgen_political_borders",
    ],
    "ai_patterns": [
        "ai_patterns_pursuit", "ai_patterns_evasion", "ai_patterns_group_tactics",
        "ai_patterns_stealth", "ai_patterns_ambush", "ai_patterns_patrol",
        "ai_patterns_searchgrid", "ai_patterns_swarm", "ai_patterns_distress_call",
        "ai_patterns_morale", "ai_patterns_alpha_pack", "ai_patterns_decision_tree",
    ],
}


def _flat_manifest() -> list:
    """Return [(collection_name, category), ...]"""
    out = []
    for cat, names in MEGA_CATEGORIES.items():
        for n in names:
            out.append((n, cat))
    return out


MEGA_COLLECTIONS = _flat_manifest()
TOTAL_MEGA_COLLECTIONS = len(MEGA_COLLECTIONS)  # should be 200

ERAS = ["pong_1972", "atari_1977", "nes_1985", "snes_1990", "ps1_1995",
        "ps2_2000", "xbox360_2005", "ps4_2013", "ps5_2020", "singularity"]
GENRES = ["rpg", "shooter", "platformer", "horror", "simulation",
          "action", "puzzle", "sports", "strategy", "moba"]
AGENT_SWARMS = ["galaxy", "jeeves", "vee", "outcall", "vault", "compiler"]

DOCS_PER_COLLECTION = 3000   # Hyperscale target. Previous runs achieved ~3000 avg
                              # before disk pressure. Kept at this level to avoid
                              # over-filling the 10GB /data/db partition.


def _seed_hash(*parts: str) -> int:
    h = hashlib.md5("|".join(parts).encode()).hexdigest()
    return int(h[:8], 16)


def _build_doc(i: int, collection_name: str, category: str) -> dict:
    seed = _seed_hash(str(i), collection_name)
    era = ERAS[(seed >> 2) % len(ERAS)]
    genre = GENRES[(seed >> 4) % len(GENRES)]
    genre_tags = list({genre, GENRES[(seed >> 6) % len(GENRES)], GENRES[(seed >> 8) % len(GENRES)]})
    subcategory = f"{category}-{(seed % 50) + 1}"
    agent_count = 3 + (seed % 6)
    agent_ids = [f"{AGENT_SWARMS[(seed + k) % len(AGENT_SWARMS)]}-agent-{(seed + k * 31) % 100000}" for k in range(agent_count)]
    virtual_asset_count = 500 + (seed % 5000)
    base_name = f"{collection_name.replace('_', '-')}-asset-{i:06d}"
    keywords = [category, collection_name.split("_", 1)[1] if "_" in collection_name else collection_name, era, genre]
    # Simulated params for agent consumption
    params = {
        "intensity": (seed % 8),
        "rarity_tier": ["common", "uncommon", "rare", "epic", "legendary", "mythic"][(seed >> 3) % 6],
        "polygon_count": (seed % 250000) + 100 if category in ("models",) else None,
        "resolution": ["16x16", "32x32", "64x64", "128x128", "256x256", "512x512", "1024x1024", "2048x2048", "4096x4096"][(seed >> 5) % 9] if category in ("sprites", "graphics", "renders") else None,
        "duration_ms": (seed % 60000) + 200 if category in ("sounds", "voices", "ambiance") else None,
        "difficulty_delta": (seed % 10) - 5 if category == "mechanics" else None,
        "popularity_score": (seed % 1000),
    }
    summary = f"{category.capitalize()} asset for {genre} ({era}) — variant {i}"
    return {
        "id": f"{collection_name}-{uuid.uuid5(uuid.NAMESPACE_OID, f'{collection_name}:{i}').hex[:14]}",
        "name": base_name,
        "category": category,
        "subcategory": subcategory,
        "collection_name": collection_name,
        "era": era,
        "genre": genre,
        "genre_tags": genre_tags,
        "tags": [category, era, genre, collection_name],
        "keywords": keywords,
        "agent_ids": agent_ids,
        "virtual_asset_count": virtual_asset_count,
        "summary": summary,
        "params": {k: v for k, v in params.items() if v is not None},
        "created_at": datetime.utcnow().isoformat(),
    }


async def _seed_one_collection(db, collection_name: str, category: str) -> dict:
    """Top-up seeder — if collection has fewer than DOCS_PER_COLLECTION, generate more."""
    try:
        existing = await db[collection_name].count_documents({})
    except Exception as e:
        return {"name": collection_name, "error": f"count: {str(e)[:80]}"}

    if existing >= DOCS_PER_COLLECTION:
        return {"name": collection_name, "status": "already_full", "docs": existing}

    # Indexes — safe to re-run
    try:
        await db[collection_name].create_index("id", unique=True)
        await db[collection_name].create_index("category")
        await db[collection_name].create_index("era")
        await db[collection_name].create_index("genre")
        await db[collection_name].create_index([("tags", 1)])
        await db[collection_name].create_index([("keywords", 1)])
        await db[collection_name].create_index([("agent_ids", 1)])
        await db[collection_name].create_index([("params.rarity_tier", 1)])
    except Exception:
        pass

    BATCH = 1000
    buffer = []
    inserted = 0
    # Start from `existing` so we don't duplicate IDs from a prior seed
    for i in range(existing, DOCS_PER_COLLECTION):
        buffer.append(_build_doc(i, collection_name, category))
        if len(buffer) >= BATCH:
            try:
                await db[collection_name].insert_many(buffer, ordered=False)
                inserted += len(buffer)
            except Exception:
                inserted += len(buffer)
            buffer = []
    if buffer:
        try:
            await db[collection_name].insert_many(buffer, ordered=False)
            inserted += len(buffer)
        except Exception:
            pass
    return {"name": collection_name, "status": "topped_up", "docs_added": inserted, "total": existing + inserted}


async def seed_all_mega_dbs(db, concurrency: int = 4) -> dict:
    """Seed all 200 mega collections with bounded concurrency so we don't blow Mongo.
    Concurrency reduced from 10 → 4 (2026-05) because we observed Mongo OOM-restarts
    at higher concurrency on a 16GB pod. 4 parallel workers fully saturate the disk
    without tripping the OOM-killer."""
    log.info(f"Mega-seed start: {TOTAL_MEGA_COLLECTIONS} collections × {DOCS_PER_COLLECTION} docs")
    sem = asyncio.Semaphore(concurrency)
    results = []

    async def _worker(name: str, cat: str):
        async with sem:
            r = await _seed_one_collection(db, name, cat)
            results.append(r)

    await asyncio.gather(*(_worker(n, c) for n, c in MEGA_COLLECTIONS))
    seeded_count = sum(1 for r in results if r.get("status") == "seeded")
    already = sum(1 for r in results if r.get("status") == "already_seeded")
    total_docs = sum(r.get("docs", 0) for r in results)
    log.info(f"Mega-seed done: {seeded_count} seeded, {already} already, {total_docs} total docs")
    return {
        "total_collections": TOTAL_MEGA_COLLECTIONS,
        "seeded": seeded_count,
        "already_seeded": already,
        "total_docs": total_docs,
        "categories": list(MEGA_CATEGORIES.keys()),
    }
