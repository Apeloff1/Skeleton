"""
Galaxy Studio — static data constants (extracted Jun 2026, decomposition).

Pure, read-only configuration data moved out of the 12k-line
routes/galaxy_studio.py to shrink the monolith and give these structures a
clean, import-safe home. This module has NO dependencies on galaxy_studio, so
both galaxy_studio.py and the manifest/genres sub-router can import from it
without any circular-import risk.

Contents:
  - AGENT_MANIFEST   : the unified agent constellation manifest
  - GALAXY_GENRES    : 69 genres with sub-genres + per-genre codegen metadata
  - TOTAL_GENRES / TOTAL_SUBGENRES : derived counts
  - BUILD_PHASES     : 100 build phases organised into 10 batches of 10
  - SYNERGY_NETWORK  : how the agent constellations interconnect
"""

# ─── UNIFIED AGENT MANIFEST ───
AGENT_MANIFEST = {
    "game_factory_hexa_layer": {"agents": 1299700, "desc": "6-layer pipeline: Originals, Shadows, Ghosts, Angels, Seraphim, Cherubim"},
    "hyperscale_domains":      {"agents": 120000,  "desc": "300 domains × 8 specialists — every game dev discipline"},
    "mega_domains":            {"agents": 11600,   "desc": "29 core domains with 232 specialists and 99 synergy links"},
    "quantum_factory":         {"agents": 2800,    "desc": "7 ultra-deep domains × 8 specialists — core systems"},
    "aaa_pipeline":            {"agents": 10000,   "desc": "200-step AAA build pipeline — excruciating detail"},
    "deploy_forge":            {"agents": 600,    "desc": "12-platform deployment: APK, AAB, EXE, IPA, Steam, PS5, Xbox, Switch"},
    "total":                   {"agents": 1444700, "desc": "Galaxy Studio full agent constellation"},
}

# ─── ALL GENRES + SUB-GENRES (codegen metadata per genre) ───
GALAXY_GENRES = {
    "platformer_2d":       {"name": "2D Platformer", "icon": "🏃", "color": "#10B981", "screens": 10, "components": 12, "logic_files": 8, "desc": "Precision jumps, physics, collectibles, enemies, boss fights", "subgenres": ["precision_platformer", "puzzle_platformer", "auto_runner", "cinematic_platformer", "masocore"]},
    "platformer_3d":       {"name": "3D Platformer", "icon": "🎮", "color": "#059669", "screens": 12, "components": 14, "logic_files": 9, "desc": "3D movement, cameras, collectathon, obstacles", "subgenres": ["collectathon", "linear_3d", "obstacle_course", "sandbox_platformer"]},
    "rpg":                 {"name": "RPG", "icon": "⚔️", "color": "#8B5CF6", "screens": 14, "components": 16, "logic_files": 12, "desc": "Character progression, quests, inventory, combat, dialogue trees", "subgenres": ["jrpg", "wrpg", "action_rpg", "tactical_rpg", "dungeon_crawler", "crpg"]},
    "fps":                 {"name": "First Person Shooter", "icon": "🔫", "color": "#EF4444", "screens": 12, "components": 14, "logic_files": 10, "desc": "Weapons, aiming, enemies, waves, power-ups, multiplayer", "subgenres": ["arena_shooter", "tactical_shooter", "hero_shooter", "milsim", "boomer_shooter", "immersive_sim"]},
    "tps":                 {"name": "Third Person Shooter", "icon": "🎯", "color": "#DC2626", "screens": 12, "components": 14, "logic_files": 10, "desc": "Cover systems, action-adventure, looter mechanics", "subgenres": ["cover_shooter", "action_adventure", "looter_shooter"]},
    "battle_royale":       {"name": "Battle Royale", "icon": "🏆", "color": "#F59E0B", "screens": 11, "components": 14, "logic_files": 10, "desc": "Last-player-standing, shrinking zones, looting", "subgenres": ["classic_br", "builder_br", "extraction_br", "hero_br"]},
    "mmorpg":              {"name": "MMORPG", "icon": "🌐", "color": "#6366F1", "screens": 16, "components": 20, "logic_files": 14, "desc": "Massive multiplayer, guilds, raids, economy, PvP", "subgenres": ["theme_park_mmo", "sandbox_mmo", "action_mmo", "classic_mmo"]},
    "moba":                {"name": "MOBA", "icon": "⚡", "color": "#A855F7", "screens": 10, "components": 14, "logic_files": 10, "desc": "Team battles, heroes, lanes, towers, abilities", "subgenres": ["classic_moba", "arena_brawler", "auto_chess"]},
    "puzzle":              {"name": "Puzzle Game", "icon": "🧩", "color": "#3B82F6", "screens": 10, "components": 10, "logic_files": 8, "desc": "Logic, physics, word, match-3, escape rooms", "subgenres": ["logic_puzzle", "physics_puzzle", "word_puzzle", "match_3", "escape_room", "programming_puzzle"]},
    "strategy_rts":        {"name": "Real-Time Strategy", "icon": "🏰", "color": "#14B8A6", "screens": 12, "components": 14, "logic_files": 10, "desc": "Base building, armies, real-time tactics", "subgenres": ["classic_rts", "base_builder", "real_time_tactics"]},
    "turn_based_strategy": {"name": "Turn-Based Strategy", "icon": "♟️", "color": "#0D9488", "screens": 12, "components": 14, "logic_files": 10, "desc": "Tactical RPG, 4X, wargames", "subgenres": ["tactical_rpg", "4x", "grand_strategy", "wargame"]},
    "four_x":              {"name": "4X Strategy", "icon": "🗺️", "color": "#0891B2", "screens": 14, "components": 16, "logic_files": 12, "desc": "Explore, expand, exploit, exterminate", "subgenres": ["historical_4x", "space_4x", "fantasy_4x"]},
    "grand_strategy":      {"name": "Grand Strategy", "icon": "👑", "color": "#7C3AED", "screens": 14, "components": 16, "logic_files": 12, "desc": "Nation management, diplomacy, warfare", "subgenres": ["historical_gs", "fantasy_gs", "political_sim"]},
    "colony_sim":          {"name": "Colony Sim", "icon": "🏘️", "color": "#D97706", "screens": 12, "components": 14, "logic_files": 10, "desc": "Colony management, survival, construction", "subgenres": ["space_colony", "medieval_colony", "post_apocalyptic_colony"]},
    "automation":          {"name": "Automation / Factory", "icon": "⚙️", "color": "#EA580C", "screens": 12, "components": 14, "logic_files": 10, "desc": "Factory building, logistics, automation chains", "subgenres": ["factory_builder", "logistics_puzzler", "space_factory"]},
    "survival":            {"name": "Survival / Crafting", "icon": "🏕️", "color": "#CA8A04", "screens": 14, "components": 16, "logic_files": 12, "desc": "Resource gathering, crafting, building, day/night", "subgenres": ["survival_craft", "zombie_survival", "space_survival", "underwater_survival"]},
    "soulslike":           {"name": "Soulslike", "icon": "💀", "color": "#991B1B", "screens": 12, "components": 14, "logic_files": 10, "desc": "Punishing combat, stamina, bonfires, bosses", "subgenres": ["dark_fantasy_souls", "sci_fi_souls", "2d_souls"]},
    "metroidvania":        {"name": "Metroidvania", "icon": "🗝️", "color": "#7E22CE", "screens": 12, "components": 14, "logic_files": 10, "desc": "Interconnected world, ability gates, backtracking", "subgenres": ["action_metroidvania", "puzzle_metroidvania", "horror_metroidvania"]},
    "roguelike":           {"name": "Roguelike / Roguelite", "icon": "🎲", "color": "#F43F5E", "screens": 12, "components": 14, "logic_files": 10, "desc": "Procedural generation, permadeath, meta-progression", "subgenres": ["traditional_roguelike", "action_roguelite", "deckbuilder_roguelike", "auto_battler_rl"]},
    "deckbuilder":         {"name": "Deckbuilder", "icon": "🃏", "color": "#14B8A6", "screens": 10, "components": 12, "logic_files": 8, "desc": "Card collecting, deck construction, combos", "subgenres": ["ccg", "roguelike_deckbuilder", "lcg", "auto_battler"]},
    "fighting":            {"name": "Fighting Game", "icon": "🥊", "color": "#DC2626", "screens": 10, "components": 14, "logic_files": 10, "desc": "Combos, special moves, characters, arenas", "subgenres": ["2d_fighter", "3d_fighter", "platform_fighter", "anime_fighter", "arena_fighter"]},
    "racing":              {"name": "Racing Game", "icon": "🏎️", "color": "#06B6D4", "screens": 10, "components": 12, "logic_files": 8, "desc": "Vehicles, tracks, physics, drift, nitro", "subgenres": ["arcade_racing", "sim_racing", "kart_racing", "street_racing", "off_road"]},
    "horror":              {"name": "Horror", "icon": "👻", "color": "#EC4899", "screens": 12, "components": 14, "logic_files": 10, "desc": "Atmosphere, jump scares, stealth, sanity mechanics", "subgenres": ["survival_horror", "psychological_horror", "action_horror", "cosmic_horror", "found_footage"]},
    "stealth":             {"name": "Stealth Game", "icon": "🥷", "color": "#334155", "screens": 12, "components": 14, "logic_files": 10, "desc": "Infiltration, detection, gadgets, silent takedowns", "subgenres": ["immersive_sim", "tactical_stealth", "social_stealth", "stealth_action"]},
    "simulation":          {"name": "Life Simulation", "icon": "🏗️", "color": "#A855F7", "screens": 14, "components": 16, "logic_files": 12, "desc": "Life sim, dating sim, pet sim, god games", "subgenres": ["life_sim", "dating_sim", "pet_sim", "god_game"]},
    "city_builder":        {"name": "City Builder", "icon": "🏙️", "color": "#0EA5E9", "screens": 14, "components": 16, "logic_files": 12, "desc": "Urban planning, zones, infrastructure, economy", "subgenres": ["modern_city", "historical_city", "space_colony_builder", "post_apocalyptic_city"]},
    "farming_sim":         {"name": "Farming Sim", "icon": "🌾", "color": "#65A30D", "screens": 12, "components": 14, "logic_files": 10, "desc": "Crops, animals, seasons, relationships", "subgenres": ["classic_farm", "fantasy_farm", "space_farm", "cozy_farm"]},
    "sandbox":             {"name": "Sandbox / Open World", "icon": "🌍", "color": "#FBBF24", "screens": 16, "components": 18, "logic_files": 14, "desc": "Massive world, quests, NPCs, dynamic weather", "subgenres": ["survival_sandbox", "creative_sandbox", "space_sandbox"]},
    "visual_novel":        {"name": "Visual Novel", "icon": "📖", "color": "#E879F9", "screens": 10, "components": 10, "logic_files": 8, "desc": "Branching stories, choices, character portraits", "subgenres": ["romance_vn", "mystery_vn", "horror_vn", "comedy_vn", "sci_fi_vn"]},
    "rhythm":              {"name": "Rhythm Game", "icon": "🎵", "color": "#F472B6", "screens": 10, "components": 12, "logic_files": 8, "desc": "Beat-synced gameplay, music, combos, accuracy", "subgenres": ["classic_rhythm", "rhythm_rpg", "music_creator", "dance_game"]},
    "tower_defense":       {"name": "Tower Defense", "icon": "🏰", "color": "#F97316", "screens": 10, "components": 12, "logic_files": 8, "desc": "Tower placement, waves, upgrades, synergies", "subgenres": ["classic_td", "maze_td", "hero_td"]},
    "sports":              {"name": "Sports Game", "icon": "⚽", "color": "#22C55E", "screens": 12, "components": 14, "logic_files": 10, "desc": "Football, basketball, golf, management", "subgenres": ["football", "basketball", "golf", "tennis", "extreme_sports", "boxing", "wrestling"]},
    "extraction_shooter":  {"name": "Extraction Shooter", "icon": "💰", "color": "#B91C1C", "screens": 12, "components": 14, "logic_files": 10, "desc": "Loot, extract, survive, high-stakes", "subgenres": ["tactical_extraction", "sci_fi_extraction", "fantasy_extraction"]},
    "social_deduction":    {"name": "Social Deduction", "icon": "🎭", "color": "#7C3AED", "screens": 10, "components": 12, "logic_files": 8, "desc": "Hidden roles, voting, deception, discussion", "subgenres": ["classic_deduction", "online_deduction", "party_deduction", "narrative_deduction"]},
    "idle_clicker":        {"name": "Idle / Clicker", "icon": "👆", "color": "#FBBF24", "screens": 10, "components": 12, "logic_files": 8, "desc": "Incremental progress, prestige, automation", "subgenres": ["classic_idle", "idle_rpg", "idle_tycoon", "merge_game"]},
    "gacha":               {"name": "Gacha / Live Service", "icon": "🎰", "color": "#F59E0B", "screens": 14, "components": 16, "logic_files": 12, "desc": "Character collection, banners, events, PvP", "subgenres": ["anime_gacha", "hero_collector", "turn_based_gacha"]},
    "space_sim":           {"name": "Space Simulation", "icon": "🚀", "color": "#6366F1", "screens": 14, "components": 16, "logic_files": 12, "desc": "Space exploration, trading, combat, colonization", "subgenres": ["space_exploration", "space_trading", "space_combat", "space_colonization"]},
    "flight_sim":          {"name": "Flight Simulation", "icon": "✈️", "color": "#0284C7", "screens": 10, "components": 12, "logic_files": 8, "desc": "Realistic flying, cockpits, weather, procedures", "subgenres": ["civil_aviation", "military_flight", "arcade_flight"]},
    "naval_pirate":        {"name": "Naval / Pirate", "icon": "🏴‍☠️", "color": "#1E3A5F", "screens": 12, "components": 14, "logic_files": 10, "desc": "Ship combat, trading, exploration, crews", "subgenres": ["pirate_adventure", "naval_warfare", "trading_sim"]},
    "party_game":          {"name": "Party Game", "icon": "🎉", "color": "#E11D48", "screens": 10, "components": 14, "logic_files": 8, "desc": "Mini-games, multiplayer, fun, competition", "subgenres": ["mini_game_collection", "trivia", "cooperative_party", "competitive_party"]},
    "educational":         {"name": "Educational Game", "icon": "📚", "color": "#059669", "screens": 12, "components": 14, "logic_files": 10, "desc": "Learning through play, quizzes, adaptive difficulty", "subgenres": ["math_ed", "science_ed", "language_ed", "history_ed", "coding_ed"]},
    "cozy_game":           {"name": "Cozy Game", "icon": "☕", "color": "#D4A574", "screens": 10, "components": 12, "logic_files": 8, "desc": "Relaxing, decorating, collecting, no pressure", "subgenres": ["decorating", "gardening", "cafe_sim", "cozy_adventure"]},
    "hunting":             {"name": "Hunting Game", "icon": "🦌", "color": "#4D7C0F", "screens": 10, "components": 12, "logic_files": 8, "desc": "Tracking, stalking, realistic animals, environments", "subgenres": ["realistic_hunting", "fantasy_hunting", "monster_hunting"]},
    "fishing":             {"name": "Fishing Game", "icon": "🎣", "color": "#0369A1", "screens": 10, "components": 12, "logic_files": 8, "desc": "Casting, reeling, fish species, locations", "subgenres": ["sport_fishing", "fantasy_fishing", "deep_sea"]},
    "mech_robot":          {"name": "Mech / Robot Combat", "icon": "🤖", "color": "#475569", "screens": 12, "components": 14, "logic_files": 10, "desc": "Mech customization, combat, upgrades, missions", "subgenres": ["heavy_mech", "agile_robot", "mech_strategy"]},
    "bullet_hell":         {"name": "Bullet Hell / Shmup", "icon": "💥", "color": "#BE123C", "screens": 10, "components": 12, "logic_files": 8, "desc": "Intense projectiles, patterns, scoring, bombs", "subgenres": ["vertical_shmup", "horizontal_shmup", "twin_stick", "bullet_heaven"]},
    "walking_sim":         {"name": "Walking Simulator", "icon": "🚶", "color": "#6B7280", "screens": 10, "components": 10, "logic_files": 6, "desc": "Narrative exploration, atmosphere, environmental storytelling", "subgenres": ["narrative_walk", "atmospheric_walk", "horror_walk"]},
    "point_and_click":     {"name": "Point & Click Adventure", "icon": "🖱️", "color": "#B45309", "screens": 10, "components": 12, "logic_files": 8, "desc": "Puzzles, inventory, dialogue, classic adventure", "subgenres": ["classic_adventure", "modern_adventure", "comedy_adventure"]},
    "auto_battler":        {"name": "Auto Battler", "icon": "🤺", "color": "#9333EA", "screens": 10, "components": 12, "logic_files": 8, "desc": "Team composition, positioning, synergies, economy", "subgenres": ["classic_auto", "rpg_auto"]},
    "dating_sim":          {"name": "Dating Simulation", "icon": "💕", "color": "#F472B6", "screens": 10, "components": 12, "logic_files": 8, "desc": "Relationship building, choices, multiple endings", "subgenres": ["romance_dating", "comedy_dating", "horror_dating", "fantasy_dating"]},
    "vehicle_combat":      {"name": "Vehicle Combat", "icon": "🚗", "color": "#92400E", "screens": 10, "components": 12, "logic_files": 8, "desc": "Armed vehicles, arenas, power-ups, destruction", "subgenres": ["car_combat", "tank_combat", "aerial_combat"]},
    "immersive_sim":       {"name": "Immersive Sim", "icon": "🌀", "color": "#7C3AED", "screens": 14, "components": 16, "logic_files": 12, "desc": "Systems-driven, emergent gameplay, player choice", "subgenres": ["sci_fi_immersive", "fantasy_immersive", "modern_immersive"]},
    # ═══ Expansion — genres previously missing or hidden as sub-genres ═══
    "tycoon":              {"name": "Tycoon / Business Sim", "icon": "💼", "color": "#D97706", "screens": 14, "components": 16, "logic_files": 12, "desc": "Empire building, economy mgmt, supply chains, employee sim, corporate warfare", "subgenres": ["theme_park_tycoon", "transport_tycoon", "zoo_tycoon", "hospital_tycoon", "prison_tycoon", "restaurant_tycoon", "movie_studio_tycoon", "sport_team_tycoon", "space_tycoon", "crime_empire", "airline_tycoon", "hotel_tycoon"]},
    "management_sim":      {"name": "Management Sim", "icon": "📊", "color": "#0EA5E9", "screens": 12, "components": 14, "logic_files": 10, "desc": "Resource mgmt, staff, operations, KPI dashboards", "subgenres": ["hospital_mgmt", "stadium_mgmt", "studio_mgmt", "transport_mgmt", "fleet_mgmt"]},
    "mmo":                 {"name": "Massively Multiplayer (non-RPG)", "icon": "🧑‍🤝‍🧑", "color": "#6366F1", "screens": 16, "components": 20, "logic_files": 14, "desc": "Massive shared worlds: shooters, survival, social", "subgenres": ["mmo_shooter", "mmo_survival", "mmo_social", "mmo_sandbox"]},
    "action_adventure":    {"name": "Action Adventure", "icon": "🗡️", "color": "#B91C1C", "screens": 14, "components": 16, "logic_files": 12, "desc": "Cinematic combat, exploration, set-pieces, puzzles", "subgenres": ["linear_action", "open_world_action", "cinematic_aa", "mythic_aa"]},
    "open_world":          {"name": "Open World AAA", "icon": "🌎", "color": "#F59E0B", "screens": 18, "components": 22, "logic_files": 16, "desc": "Seamless continents, deep RPG systems, dynamic storylines", "subgenres": ["western_open_world", "urban_sandbox", "fantasy_open_world", "sci_fi_open_world", "post_apoc_open_world"]},
    "looter_shooter":      {"name": "Looter Shooter", "icon": "🪙", "color": "#DC2626", "screens": 14, "components": 16, "logic_files": 12, "desc": "Loot chase, builds, endgame, seasonal content", "subgenres": ["fps_looter", "third_person_looter", "sci_fi_looter", "fantasy_looter"]},
    "extraction_rpg":      {"name": "Extraction RPG", "icon": "🏴", "color": "#9F1239", "screens": 12, "components": 14, "logic_files": 10, "desc": "Raids, loot, permadeath risk, vendor economy", "subgenres": ["fantasy_extraction_rpg", "sci_fi_extraction_rpg", "horror_extraction_rpg"]},
    "card_game":           {"name": "Card Game (non-deckbuilder)", "icon": "🎴", "color": "#0F766E", "screens": 10, "components": 12, "logic_files": 8, "desc": "CCG, TCG, Solitaire, trick-taking, draft", "subgenres": ["ccg", "tcg", "solitaire", "trick_taking", "draft_card"]},
    "board_game":          {"name": "Board Game Adaptation", "icon": "🎲", "color": "#7C2D12", "screens": 10, "components": 12, "logic_files": 8, "desc": "Chess, Go, wargames, Euro games, Ameri-trash, 18xx", "subgenres": ["chess_like", "euro_board", "wargame_board", "party_board"]},
    "text_adventure":      {"name": "Text Adventure / Interactive Fiction", "icon": "📜", "color": "#525252", "screens": 6, "components": 8, "logic_files": 6, "desc": "Parser commands, branching prose, puzzles, atmosphere", "subgenres": ["classic_parser", "modern_if", "choice_based", "procedural_narrative"]},
    "roguelite_shooter":   {"name": "Roguelite Shooter", "icon": "🔥", "color": "#EF4444", "screens": 12, "components": 14, "logic_files": 10, "desc": "Run-based FPS/TPS with meta-progression", "subgenres": ["fps_roguelite", "tps_roguelite", "twin_stick_roguelite", "horde_shooter"]},
    "beat_em_up":          {"name": "Beat 'em Up / Brawler", "icon": "👊", "color": "#C2410C", "screens": 10, "components": 12, "logic_files": 8, "desc": "Side-scrolling combat, combos, co-op", "subgenres": ["classic_brawler", "3d_brawler", "rpg_brawler"]},
    "shoot_em_up":         {"name": "Shoot 'em Up (Shmup)", "icon": "🚀", "color": "#BE123C", "screens": 8, "components": 10, "logic_files": 6, "desc": "Scrolling shooters: vertical, horizontal, bullet-heaven", "subgenres": ["vertical_shmup", "horizontal_shmup", "euroshmup", "cave_style"]},
    "twin_stick":          {"name": "Twin-Stick Shooter", "icon": "🎯", "color": "#A21CAF", "screens": 8, "components": 10, "logic_files": 6, "desc": "360° shooting, arcade action, roguelike variants", "subgenres": ["classic_twin_stick", "roguelike_twin_stick", "arena_twin_stick"]},
    "stealth_action":      {"name": "Stealth Action", "icon": "🗡️", "color": "#1F2937", "screens": 12, "components": 14, "logic_files": 10, "desc": "Blended stealth + open combat, choice-driven", "subgenres": ["modern_stealth_action", "ninja_stealth", "spy_thriller"]},
    "tactics":             {"name": "Tactics / SRPG", "icon": "♟️", "color": "#0D9488", "screens": 12, "components": 14, "logic_files": 10, "desc": "Grid-based tactics, permadeath, class trees", "subgenres": ["classic_srpg", "xcom_like", "mecha_tactics", "fantasy_tactics"]},
    "metaverse_social":    {"name": "Metaverse / Social Hub", "icon": "🪩", "color": "#A855F7", "screens": 16, "components": 20, "logic_files": 14, "desc": "User-generated content, avatars, venues, events", "subgenres": ["ugc_platform", "virtual_concerts", "social_worlds", "creator_economy"]},
}

TOTAL_GENRES = len(GALAXY_GENRES)
TOTAL_SUBGENRES = sum(len(g["subgenres"]) for g in GALAXY_GENRES.values())

# ─── BUILD PHASES — 100 phases / 10 batches ───
BUILD_PHASES = [
    # ═══ BATCH 1: FOUNDATION (Phases 1-10) ═══
    {"id": "vision",           "name": "Vision & Concept",           "batch": 1, "agents": 20000,   "icon": "eye",              "color": "#8B5CF6"},
    {"id": "system",           "name": "System Design",              "batch": 1, "agents": 50000,  "icon": "desktop",          "color": "#0D9488"},
    {"id": "framework",        "name": "Framework Selection",        "batch": 1, "agents": 45000,   "icon": "layers",           "color": "#0891B2"},
    {"id": "engine",           "name": "Engine Core",                "batch": 1, "agents": 90000,  "icon": "cog",              "color": "#7C3AED"},
    {"id": "architecture",     "name": "Architecture Blueprint",     "batch": 1, "agents": 60000,  "icon": "git-branch",       "color": "#4F46E5"},
    {"id": "infrastructure",   "name": "Infrastructure",             "batch": 1, "agents": 55000,  "icon": "construct",        "color": "#475569"},
    {"id": "science",          "name": "Science & Simulation",       "batch": 1, "agents": 50000,  "icon": "flask",            "color": "#0EA5E9"},
    {"id": "plot_intrigue",    "name": "Plot & Intrigue",            "batch": 1, "agents": 50000,  "icon": "key",              "color": "#6366F1"},
    {"id": "lore",             "name": "Lore & Mythology",           "batch": 1, "agents": 40000,   "icon": "book",             "color": "#A78BFA"},
    {"id": "world_building",   "name": "World Building",             "batch": 1, "agents": 90000,  "icon": "globe",            "color": "#14B8A6"},
    # ═══ BATCH 2: CORE MECHANICS (Phases 11-20) ═══
    {"id": "mechanics",        "name": "Core Mechanics",             "batch": 2, "agents": 110000,  "icon": "game-controller",  "color": "#3B82F6"},
    {"id": "gameplay",         "name": "Gameplay Systems",           "batch": 2, "agents": 90000,  "icon": "trophy",           "color": "#2563EB"},
    {"id": "character",        "name": "Character & Progression",    "batch": 2, "agents": 80000,  "icon": "person",           "color": "#8B5CF6"},
    {"id": "economy",          "name": "Economy & Vendors",          "batch": 2, "agents": 70000,  "icon": "cash",             "color": "#F59E0B"},
    {"id": "combat",           "name": "Combat System",              "batch": 2, "agents": 100000,  "icon": "shield",           "color": "#EF4444"},
    {"id": "inventory",        "name": "Inventory & Items",          "batch": 2, "agents": 60000,  "icon": "cube",             "color": "#F97316"},
    {"id": "crafting",         "name": "Crafting & Resources",       "batch": 2, "agents": 55000,  "icon": "hammer",           "color": "#D97706"},
    {"id": "quests",           "name": "Quest Engine",               "batch": 2, "agents": 75000,  "icon": "map",              "color": "#10B981"},
    {"id": "dialogue",         "name": "Dialogue & Choice",          "batch": 2, "agents": 50000,  "icon": "chatbubbles",      "color": "#6D28D9"},
    {"id": "companions",       "name": "Party & Companions",         "batch": 2, "agents": 45000,   "icon": "people",           "color": "#0891B2"},
    # ═══ BATCH 3: WORLD & ENVIRONMENT (Phases 21-30) ═══
    {"id": "world_gen",        "name": "World Generation",           "batch": 3, "agents": 90000,  "icon": "globe",            "color": "#14B8A6"},
    {"id": "environment",      "name": "Environment & Ecology",      "batch": 3, "agents": 70000,  "icon": "leaf",             "color": "#059669"},
    {"id": "biomes",           "name": "Biomes & Terrain",           "batch": 3, "agents": 65000,  "icon": "trail-sign",       "color": "#15803D"},
    {"id": "weather",          "name": "Weather & Seasons",          "batch": 3, "agents": 50000,  "icon": "rainy",            "color": "#0284C7"},
    {"id": "day_night",        "name": "Day/Night Cycle",            "batch": 3, "agents": 40000,   "icon": "moon",             "color": "#1E3A5F"},
    {"id": "critters",         "name": "Critters & Animals",         "batch": 3, "agents": 60000,  "icon": "paw",              "color": "#B45309"},
    {"id": "flora",            "name": "Flora & Vegetation",         "batch": 3, "agents": 45000,   "icon": "flower",           "color": "#16A34A"},
    {"id": "water",            "name": "Water & Oceans",             "batch": 3, "agents": 50000,  "icon": "water",            "color": "#0369A1"},
    {"id": "underground",      "name": "Underground & Caves",        "batch": 3, "agents": 55000,  "icon": "flashlight",       "color": "#78350F"},
    {"id": "cities",           "name": "Cities & Settlements",       "batch": 3, "agents": 75000,  "icon": "business",         "color": "#7C3AED"},
    # ═══ BATCH 4: AUDIO & VISUAL (Phases 31-40) ═══
    {"id": "graphics",         "name": "Graphics & Rendering",       "batch": 4, "agents": 80000,  "icon": "color-palette",    "color": "#EC4899"},
    {"id": "vfx",              "name": "Visual Effects",             "batch": 4, "agents": 60000,  "icon": "sparkles",         "color": "#F472B6"},
    {"id": "animations",       "name": "Animations",                 "batch": 4, "agents": 70000,  "icon": "film",             "color": "#A855F7"},
    {"id": "cinematics",       "name": "Cinematics & Camera",        "batch": 4, "agents": 45000,   "icon": "videocam",         "color": "#8B5CF6"},
    {"id": "theatrics",        "name": "Theatrics & Drama",          "batch": 4, "agents": 50000,  "icon": "megaphone",        "color": "#DC2626"},
    {"id": "sound",            "name": "Sound Engine",               "batch": 4, "agents": 40000,   "icon": "musical-notes",    "color": "#D97706"},
    {"id": "sfx",              "name": "Sound Effects",              "batch": 4, "agents": 45000,   "icon": "volume-high",      "color": "#F59E0B"},
    {"id": "music",            "name": "Music & Soundtrack",         "batch": 4, "agents": 35000,   "icon": "disc",             "color": "#B45309"},
    {"id": "ambiance",         "name": "Ambiance & Atmosphere",      "batch": 4, "agents": 30000,   "icon": "cloudy-night",     "color": "#7C3AED"},
    {"id": "voice",            "name": "Voice & Narration",          "batch": 4, "agents": 40000,   "icon": "mic",              "color": "#6D28D9"},
    # ═══ BATCH 5: AI & BEHAVIOR (Phases 41-50) ═══
    {"id": "ai_behavior",      "name": "AI & Behavior",              "batch": 5, "agents": 70000,  "icon": "hardware-chip",    "color": "#EF4444"},
    {"id": "npc_intel",        "name": "NPC Intelligence",           "batch": 5, "agents": 60000,  "icon": "bulb",             "color": "#F59E0B"},
    {"id": "enemy_ai",         "name": "Enemy AI & Tactics",         "batch": 5, "agents": 75000,  "icon": "skull",            "color": "#DC2626"},
    {"id": "companion_ai",     "name": "Companion AI",               "batch": 5, "agents": 50000,  "icon": "heart",            "color": "#EC4899"},
    {"id": "wildlife_ai",      "name": "Wildlife AI",                "batch": 5, "agents": 45000,   "icon": "paw",              "color": "#B45309"},
    {"id": "crowd_sim",        "name": "Crowd Simulation",           "batch": 5, "agents": 55000,  "icon": "people",           "color": "#6366F1"},
    {"id": "pathfinding",      "name": "Pathfinding & Navigation",   "batch": 5, "agents": 65000,  "icon": "navigate",         "color": "#0EA5E9"},
    {"id": "decision_trees",   "name": "Decision Trees",             "batch": 5, "agents": 50000,  "icon": "git-branch",       "color": "#4F46E5"},
    {"id": "emotion_ai",       "name": "Emotion & Personality",      "batch": 5, "agents": 40000,   "icon": "happy",            "color": "#F472B6"},
    {"id": "social_dynamics",  "name": "Social Dynamics",            "batch": 5, "agents": 45000,   "icon": "chatbox",          "color": "#0891B2"},
    # ═══ BATCH 6: SYSTEMS & NETWORK (Phases 51-60) ═══
    {"id": "networking",       "name": "Networking & Multiplayer",   "batch": 6, "agents": 50000,  "icon": "cloud",            "color": "#8B5CF6"},
    {"id": "backend_phase",    "name": "Backend Systems",            "batch": 6, "agents": 70000,  "icon": "server",           "color": "#DC2626"},
    {"id": "middleware",       "name": "Middleware Layer",            "batch": 6, "agents": 55000,  "icon": "swap-horizontal",  "color": "#9333EA"},
    {"id": "frontend_phase",   "name": "Frontend UI",                "batch": 6, "agents": 65000,  "icon": "phone-portrait",   "color": "#0284C7"},
    {"id": "menu",             "name": "Menu System",                "batch": 6, "agents": 35000,   "icon": "menu",             "color": "#0EA5E9"},
    {"id": "settings",         "name": "Settings & Config",          "batch": 6, "agents": 30000,   "icon": "settings",         "color": "#64748B"},
    {"id": "save_load",        "name": "Save & Load System",         "batch": 6, "agents": 45000,   "icon": "save",             "color": "#10B981"},
    {"id": "cloud_sync",       "name": "Cloud Sync",                 "batch": 6, "agents": 40000,   "icon": "cloud-upload",     "color": "#3B82F6"},
    {"id": "leaderboards",     "name": "Leaderboards & Rankings",    "batch": 6, "agents": 35000,   "icon": "podium",           "color": "#F97316"},
    {"id": "achievements",     "name": "Achievement System",         "batch": 6, "agents": 30000,   "icon": "ribbon",           "color": "#FBBF24"},
    # ═══ BATCH 7: CONTENT & DEPTH (Phases 61-70) ═══
    {"id": "cutscenes",        "name": "Cutscenes & Story",          "batch": 7, "agents": 40000,   "icon": "film",             "color": "#6D28D9"},
    {"id": "tutorial",         "name": "Tutorial & Onboarding",      "batch": 7, "agents": 30000,   "icon": "school",           "color": "#10B981"},
    {"id": "easter_eggs",      "name": "Easter Eggs & Secrets",      "batch": 7, "agents": 25000,   "icon": "egg",              "color": "#FBBF24"},
    {"id": "minigames",        "name": "Mini-Games",                 "batch": 7, "agents": 50000,  "icon": "dice",             "color": "#A855F7"},
    {"id": "housing",          "name": "Housing & Decoration",       "batch": 7, "agents": 45000,   "icon": "home",             "color": "#F97316"},
    {"id": "mounts",           "name": "Mounts & Vehicles",          "batch": 7, "agents": 40000,   "icon": "car",              "color": "#0891B2"},
    {"id": "pets",             "name": "Pets & Familiars",           "batch": 7, "agents": 35000,   "icon": "paw",              "color": "#EC4899"},
    {"id": "guilds",           "name": "Guilds & Factions",          "batch": 7, "agents": 55000,  "icon": "flag",             "color": "#EF4444"},
    {"id": "pvp",              "name": "PvP & Arena",                "batch": 7, "agents": 60000,  "icon": "trophy",           "color": "#DC2626"},
    {"id": "seasonal",         "name": "Seasonal Events",            "batch": 7, "agents": 40000,   "icon": "calendar",         "color": "#22C55E"},
    # ═══ BATCH 8: POLISH & QUALITY (Phases 71-80) ═══
    {"id": "balancing",        "name": "Balancing & Tuning",         "batch": 8, "agents": 40000,   "icon": "options",          "color": "#F97316"},
    {"id": "complexity",       "name": "Complexity & Depth",         "batch": 8, "agents": 60000,  "icon": "git-network",      "color": "#6366F1"},
    {"id": "intricacy",        "name": "Intricacy & Detail",         "batch": 8, "agents": 50000,  "icon": "diamond",          "color": "#A855F7"},
    {"id": "permutations",     "name": "Unique Permutations",        "batch": 8, "agents": 150000,  "icon": "shuffle",          "color": "#A855F7"},
    {"id": "enhancement",      "name": "Enhancement & Optimization", "batch": 8, "agents": 45000,   "icon": "trending-up",      "color": "#22C55E"},
    {"id": "sota",             "name": "State of the Art",           "batch": 8, "agents": 200000,  "icon": "flash",            "color": "#FBBF24"},
    {"id": "immersion",        "name": "Advanced Immersion",         "batch": 8, "agents": 55000,  "icon": "glasses",          "color": "#7C3AED"},
    {"id": "psychology",       "name": "Advanced Psychology",        "batch": 8, "agents": 45000,   "icon": "body",             "color": "#EC4899"},
    {"id": "accessibility",    "name": "Accessibility",              "batch": 8, "agents": 35000,   "icon": "accessibility",    "color": "#0EA5E9"},
    {"id": "localization",     "name": "Localization",               "batch": 8, "agents": 30000,   "icon": "language",         "color": "#64748B"},
    # ═══ BATCH 9: TESTING & SECURITY (Phases 81-90) ═══
    {"id": "testing",          "name": "Testing & QA",               "batch": 9, "agents": 110000,  "icon": "shield-checkmark", "color": "#EF4444"},
    {"id": "perf_testing",     "name": "Performance Testing",        "batch": 9, "agents": 75000,  "icon": "speedometer",      "color": "#F97316"},
    {"id": "security",         "name": "Security & Anti-Cheat",      "batch": 9, "agents": 60000,  "icon": "lock-closed",      "color": "#DC2626"},
    {"id": "error_handling",   "name": "Error Handling",             "batch": 9, "agents": 45000,   "icon": "alert-circle",     "color": "#FBBF24"},
    {"id": "logging",          "name": "Logging & Monitoring",       "batch": 9, "agents": 40000,   "icon": "analytics",        "color": "#3B82F6"},
    {"id": "analytics",        "name": "Analytics & Telemetry",      "batch": 9, "agents": 35000,   "icon": "bar-chart",        "color": "#6366F1"},
    {"id": "crash_recovery",   "name": "Crash Recovery",             "batch": 9, "agents": 50000,  "icon": "refresh",          "color": "#10B981"},
    {"id": "memory_mgmt",      "name": "Memory Management",          "batch": 9, "agents": 55000,  "icon": "hardware-chip",    "color": "#0891B2"},
    {"id": "net_optimization",  "name": "Network Optimization",      "batch": 9, "agents": 45000,   "icon": "cellular",         "color": "#8B5CF6"},
    {"id": "platform_compat",  "name": "Platform Compatibility",     "batch": 9, "agents": 40000,   "icon": "desktop",          "color": "#475569"},
    # ═══ BATCH 10: FINAL ASSEMBLY (Phases 91-100) ═══
    {"id": "compilation",      "name": "Final Compilation",          "batch": 10, "agents": 1444700, "icon": "download",        "color": "#10B981"},
    {"id": "asset_pipeline",   "name": "Asset Pipeline",             "batch": 10, "agents": 100000,  "icon": "images",          "color": "#F59E0B"},
    {"id": "build_optimize",   "name": "Build Optimization",         "batch": 10, "agents": 75000,  "icon": "rocket",          "color": "#3B82F6"},
    {"id": "code_splitting",   "name": "Code Splitting",             "batch": 10, "agents": 60000,  "icon": "git-branch",      "color": "#6366F1"},
    {"id": "tree_shaking",     "name": "Tree Shaking",               "batch": 10, "agents": 50000,  "icon": "leaf",            "color": "#22C55E"},
    {"id": "bundle_analysis",  "name": "Bundle Analysis",            "batch": 10, "agents": 45000,   "icon": "pie-chart",       "color": "#A855F7"},
    {"id": "documentation",    "name": "Documentation",              "batch": 10, "agents": 40000,   "icon": "document-text",   "color": "#64748B"},
    {"id": "deploy_config",    "name": "Deployment Config",          "batch": 10, "agents": 35000,   "icon": "cloud-upload",    "color": "#0284C7"},
    {"id": "release_prep",     "name": "Release Preparation",        "batch": 10, "agents": 30000,   "icon": "flag",            "color": "#FBBF24"},
    {"id": "fine_tuning",      "name": "Fine Tuning",                "batch": 10, "agents": 1444700, "icon": "construct",       "color": "#FBBF24"},
]

# ─── SYNERGY NETWORK ───
SYNERGY_NETWORK = {
    "constellations": [
        {"id": "hexa", "name": "Game Factory Hexa-Layer", "agents": 1299700, "color": "#8B5CF6"},
        {"id": "hyper", "name": "Hyperscale Domains", "agents": 120000, "color": "#06B6D4"},
        {"id": "mega", "name": "Mega Domains", "agents": 11600, "color": "#EC4899"},
        {"id": "quantum", "name": "Quantum Factory", "agents": 2800, "color": "#F59E0B"},
        {"id": "pipeline", "name": "AAA Pipeline", "agents": 10000, "color": "#3B82F6"},
        {"id": "deploy", "name": "Deploy Forge", "agents": 600, "color": "#22C55E"},
    ],
    "links": [
        # Hexa ↔ everything (primary hub)
        {"from": "hexa", "to": "hyper", "type": "bidirectional", "strength": 0.95, "desc": "Domain expertise flows into Hexa-Layer code generation. Hexa outputs feed domain validation."},
        {"from": "hexa", "to": "mega", "type": "bidirectional", "strength": 0.88, "desc": "Core domain knowledge seeds Hexa patterns. Hexa validates against Mega specifications."},
        {"from": "hexa", "to": "quantum", "type": "bidirectional", "strength": 0.92, "desc": "Quantum deep-processing enriches Hexa code. Hexa submits complex problems to Quantum."},
        {"from": "hexa", "to": "pipeline", "type": "bidirectional", "strength": 0.97, "desc": "Pipeline orchestrates Hexa execution order. Hexa produces artifacts for each pipeline stage."},
        {"from": "hexa", "to": "deploy", "type": "downstream", "strength": 0.85, "desc": "Hexa outputs final build artifacts. Deploy packages and compiles them."},
        # Hyper ↔ others
        {"from": "hyper", "to": "mega", "type": "bidirectional", "strength": 0.90, "desc": "Hyperscale extends Mega domains 10x. Mega provides foundational patterns Hyperscale scales."},
        {"from": "hyper", "to": "quantum", "type": "bidirectional", "strength": 0.82, "desc": "Quantum deep-dives inform Hyperscale breadth. Hyperscale feeds Quantum edge-case scenarios."},
        {"from": "hyper", "to": "pipeline", "type": "upstream", "strength": 0.78, "desc": "Hyperscale specialists validate pipeline outputs at each of 200 steps."},
        {"from": "hyper", "to": "deploy", "type": "downstream", "strength": 0.70, "desc": "Hyperscale platform specialists guide Deploy target optimization."},
        # Mega ↔ others
        {"from": "mega", "to": "quantum", "type": "bidirectional", "strength": 0.86, "desc": "Mega core domains define Quantum processing targets. Quantum returns deep analysis."},
        {"from": "mega", "to": "pipeline", "type": "upstream", "strength": 0.80, "desc": "Mega domain specs gate pipeline phase transitions. Pipeline reports back compliance."},
        {"from": "mega", "to": "deploy", "type": "downstream", "strength": 0.65, "desc": "Mega deployment domain feeds Deploy configuration standards."},
        # Quantum ↔ others
        {"from": "quantum", "to": "pipeline", "type": "bidirectional", "strength": 0.88, "desc": "Quantum resolves pipeline bottlenecks. Pipeline prioritizes Quantum processing queue."},
        {"from": "quantum", "to": "deploy", "type": "downstream", "strength": 0.72, "desc": "Quantum optimizes final binary. Deploy triggers Quantum compression passes."},
        # Pipeline ↔ Deploy
        {"from": "pipeline", "to": "deploy", "type": "downstream", "strength": 0.99, "desc": "Pipeline's final phase hands off to Deploy. Deploy is the terminal stage."},
    ],
    "total_links": 15,
    "total_bidirectional": 8,
    "total_unidirectional": 7,
}

__all__ = [
    "AGENT_MANIFEST", "GALAXY_GENRES", "TOTAL_GENRES",
    "TOTAL_SUBGENRES", "BUILD_PHASES", "SYNERGY_NETWORK",
]
