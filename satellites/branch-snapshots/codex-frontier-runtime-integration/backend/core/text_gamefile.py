"""
core/text_gamefile.py — 10 TEXT → GAMEFILE-only systems.

Each system takes a free-text prompt and emits a structured GAMEFILE (a unit of
game content the engine can consume). They are crosswired to the SAME 14-gate
refinement engine (kind="gamefile") and use the SAME optional-LLM pattern as
the rest of the forge: deterministic by default, Claude-enriched when a key is
present and enrich=True.

Storage: galaxy_text_gamefiles (per build_id + gamefile id), so the gate engine
can resolve a gamefile target and score it through Refine→…→Consensus.
"""
from __future__ import annotations

import hashlib
import os
import re
import time

MAX_BRIEF_CHARS = 12000   # maxed brief per LLM call for maximal result

# ── text→gamefile generators (SOTA command palette). Each: key, label, icon,
#    gamefile "type", the deterministic field schema it fills from the prompt,
#    a UI "group" for palette sectioning, and an "advanced" flag (advanced
#    commands are hidden behind the Command-Center advanced toggle).
#    100 STANDARD + 50 ADVANCED = 150 distinct, hand-authored systems. ─────────
def _g(key: str, label: str, icon: str, gtype: str, fields: list[str],
       group: str, advanced: bool = False) -> dict:
    return {"key": key, "label": label, "icon": icon, "type": gtype,
            "fields": fields, "group": group, "advanced": advanced}


GENERATORS: list[dict] = [
    # ══════════════ STANDARD · NARRATIVE & WORLD ══════════════
    _g("quest_from_text", "Quest Gamefile", "🗺", "quest", ["title", "giver", "objectives", "stages", "rewards", "failure_states", "branch_hooks"], "Narrative & World"),
    _g("dialogue_from_text", "Dialogue Tree", "💬", "dialogue", ["speaker", "nodes", "choices", "conditions", "tone", "barks"], "Narrative & World"),
    _g("lore_from_text", "Lore / Codex Entry", "📜", "lore", ["title", "category", "body", "links", "discovery", "tone"], "Narrative & World"),
    _g("cutscene_from_text", "Cutscene Script", "🎬", "cutscene", ["title", "beats", "shots", "dialogue", "transitions", "skippable"], "Narrative & World"),
    _g("character_bio", "Character Bio", "🪪", "character", ["name", "role", "backstory", "motivation", "flaws", "voice", "arc"], "Narrative & World"),
    _g("faction_charter", "Faction Charter", "🏳", "faction", ["name", "ideology", "leadership", "goals", "rivals", "assets", "perks"], "Narrative & World"),
    _g("region_zone", "Region / Zone", "🗺", "region", ["name", "biome", "landmarks", "factions", "dangers", "resources", "mood"], "Narrative & World"),
    _g("biome_profile", "Biome Profile", "🌿", "biome", ["name", "climate", "flora", "fauna", "hazards", "palette", "ambience"], "Narrative & World"),
    _g("culture_people", "Culture / People", "🪅", "culture", ["name", "values", "customs", "language", "cuisine", "taboos", "dress"], "Narrative & World"),
    _g("religion_pantheon", "Religion / Pantheon", "⛩", "religion", ["name", "deities", "tenets", "rituals", "relics", "heresies"], "Narrative & World"),
    _g("timeline_event", "History Event", "📅", "history", ["title", "era", "cause", "consequence", "figures", "legacy"], "Narrative & World"),
    _g("myth_legend", "Myth / Legend", "🐉", "myth", ["title", "hero", "ordeal", "moral", "variants", "tone"], "Narrative & World"),
    _g("bestiary_entry", "Bestiary Entry", "📖", "bestiary", ["name", "classification", "habitat", "behavior", "weakness", "lore"], "Narrative & World"),
    _g("journal_entry", "Journal / Diary", "📓", "journal", ["author", "date", "body", "mood", "reveals", "next_clue"], "Narrative & World"),
    _g("in_world_letter", "In-World Letter", "✉", "letter", ["sender", "recipient", "body", "subtext", "seal", "hook"], "Narrative & World"),
    _g("rumor_gossip", "Rumor / Gossip", "🗣", "rumor", ["source", "claim", "truth", "spread", "reward_hook", "tone"], "Narrative & World"),
    _g("inscription_rune", "Inscription / Runestone", "🪨", "inscription", ["title", "language", "body", "warning", "discovery", "decay"], "Narrative & World"),
    _g("point_of_interest", "Point of Interest", "📍", "poi", ["name", "type", "draw", "secret", "encounter", "reward"], "Narrative & World"),
    _g("landmark", "Landmark", "🗽", "landmark", ["name", "silhouette", "history", "function", "visibility", "secret"], "Narrative & World"),
    _g("settlement_town", "Settlement / Town", "🏘", "settlement", ["name", "size", "economy", "factions", "services", "tensions", "secrets"], "Narrative & World"),
    _g("prophecy", "Prophecy", "🔮", "prophecy", ["title", "verse", "trigger", "interpretation", "twist", "payoff"], "Narrative & World"),
    _g("environmental_story", "Environmental Story Beat", "🩸", "env_story", ["location", "staging", "props", "implied_event", "discovery", "payoff"], "Narrative & World"),

    # ══════════════ STANDARD · CHARACTERS & NPCS ══════════════
    _g("enemy_from_text", "Enemy / NPC Statblock", "👹", "enemy", ["name", "archetype", "stats", "abilities", "ai_behavior", "telegraphs", "loot"], "Characters & NPCs"),
    _g("npc_persona", "NPC Persona", "🧑", "npc", ["name", "role", "personality", "dialogue_style", "needs", "schedule_hint", "barks"], "Characters & NPCs"),
    _g("companion_ally", "Companion / Ally", "🤝", "companion", ["name", "specialty", "combat_role", "banter", "loyalty", "command_skills"], "Characters & NPCs"),
    _g("villain_antagonist", "Villain / Antagonist", "😈", "villain", ["name", "scheme", "methods", "weakness", "presence", "downfall"], "Characters & NPCs"),
    _g("merchant_vendor", "Merchant / Vendor", "🧺", "merchant", ["name", "stock", "prices", "haggle", "restock", "personality"], "Characters & NPCs"),
    _g("npc_schedule", "NPC Daily Schedule", "🕗", "schedule", ["name", "slots", "locations", "activities", "interrupts", "fallback"], "Characters & NPCs"),
    _g("boss_design", "Boss Design", "👑", "boss", ["name", "phases", "moveset", "arena", "tells", "enrage", "reward"], "Characters & NPCs"),
    _g("boss_phase", "Boss Phase", "⚔", "boss_phase", ["name", "trigger", "attacks", "vulnerability", "adds", "transition"], "Characters & NPCs"),
    _g("minion_add", "Minion / Add", "🐀", "minion", ["name", "role", "stats", "behavior", "spawn", "threat"], "Characters & NPCs"),
    _g("crowd_archetype", "Crowd Archetype", "👥", "crowd", ["name", "appearance", "reactions", "density", "dialogue_pool", "flee_logic"], "Characters & NPCs"),
    _g("relationship_affinity", "Relationship / Affinity", "❤", "relationship", ["pair", "stages", "triggers", "rewards", "rupture", "repair"], "Characters & NPCs"),
    _g("rival", "Rival", "🥊", "rival", ["name", "domain", "escalation", "taunts", "rematch", "respect_arc"], "Characters & NPCs"),
    _g("mentor", "Mentor", "🧙", "mentor", ["name", "teaches", "lessons", "trials", "secret", "farewell"], "Characters & NPCs"),

    # ══════════════ STANDARD · COMBAT & ABILITIES ══════════════
    _g("ability_from_text", "Ability / Spell", "✨", "ability", ["name", "cost", "cooldown", "effect", "scaling", "counterplay", "vfx"], "Combat & Abilities"),
    _g("weapon_moveset", "Weapon Moveset", "🗡", "moveset", ["weapon", "light_chain", "heavy", "specials", "cancels", "frame_data"], "Combat & Abilities"),
    _g("combo_chain", "Combo / Chain", "💢", "combo", ["name", "inputs", "links", "damage", "scaling", "finisher"], "Combat & Abilities"),
    _g("status_effect", "Status Effect", "☠", "status", ["name", "type", "stacks", "duration", "tick", "cleanse", "interactions"], "Combat & Abilities"),
    _g("damage_type", "Damage Type", "🔥", "damage_type", ["name", "color", "strong_vs", "weak_vs", "on_hit", "resist_stat"], "Combat & Abilities"),
    _g("elemental_reaction", "Elemental Reaction", "⚗", "reaction", ["name", "inputs", "result", "scaling", "vfx", "counter"], "Combat & Abilities"),
    _g("ultimate_super", "Ultimate / Super", "🌟", "ultimate", ["name", "charge", "effect", "cinematic", "counterplay", "cooldown"], "Combat & Abilities"),
    _g("passive_trait", "Passive Trait", "🧬", "passive", ["name", "condition", "effect", "stacking", "synergies", "tradeoff"], "Combat & Abilities"),
    _g("combat_stance", "Combat Stance", "🧍", "stance", ["name", "bonuses", "penalties", "switch_cost", "ideal_use", "tells"], "Combat & Abilities"),
    _g("counter_parry", "Counter / Parry", "🛡", "counter", ["name", "window", "input", "reward", "risk", "feedback"], "Combat & Abilities"),
    _g("summon_pet", "Summon / Pet", "🐉", "summon", ["name", "stats", "commands", "duration", "ai", "recall"], "Combat & Abilities"),
    _g("trap_def", "Trap", "🪤", "trap", ["name", "trigger", "effect", "detection", "disarm", "reset"], "Combat & Abilities"),
    _g("hazard", "Environmental Hazard", "🌋", "hazard", ["name", "source", "effect", "warning", "safe_window", "exploit"], "Combat & Abilities"),

    # ══════════════ STANDARD · ITEMS & ECONOMY ══════════════
    _g("item_from_text", "Item Definition", "🗡", "item", ["name", "slot", "rarity", "stats", "affixes", "flavor", "value"], "Items & Economy"),
    _g("economy_from_text", "Shop / Loot Table", "🏷", "economy", ["name", "entries", "weights", "prices", "restock", "sinks"], "Items & Economy"),
    _g("weapon_def", "Weapon Definition", "🔫", "weapon", ["name", "class", "damage", "range", "handling", "mods", "flavor"], "Items & Economy"),
    _g("armor_gear", "Armor / Gear", "🦺", "armor", ["name", "slot", "defense", "resistances", "set_bonus", "weight", "flavor"], "Items & Economy"),
    _g("consumable_potion", "Consumable / Potion", "🧪", "consumable", ["name", "effect", "duration", "cooldown", "stack", "recipe"], "Items & Economy"),
    _g("crafting_recipe", "Crafting Recipe", "🛠", "recipe", ["name", "ingredients", "station", "time", "output", "yield", "skill_req"], "Items & Economy"),
    _g("crafting_material", "Crafting Material", "🪵", "material", ["name", "rarity", "sources", "uses", "stack", "value"], "Items & Economy"),
    _g("enchantment_rune", "Enchantment / Rune", "🔯", "enchant", ["name", "slot", "effect", "scaling", "conflicts", "removal"], "Items & Economy"),
    _g("gem_socket", "Gem / Socket", "💎", "gem", ["name", "color", "bonus", "socket_type", "fusion", "value"], "Items & Economy"),
    _g("loot_table", "Loot Table", "🎁", "loot", ["name", "entries", "weights", "guaranteed", "pity", "conditions"], "Items & Economy"),
    _g("rarity_tier", "Rarity Tier", "🌈", "rarity", ["name", "color", "drop_rate", "stat_budget", "affix_count", "vfx"], "Items & Economy"),
    _g("currency_def", "Currency", "🪙", "currency", ["name", "symbol", "sources", "sinks", "cap", "conversion"], "Items & Economy"),
    _g("vendor_inventory", "Vendor Inventory", "🏬", "inventory", ["vendor", "items", "stock", "prices", "rotation", "unlocks"], "Items & Economy"),
    _g("reward_bundle", "Reward Bundle", "📦", "bundle", ["name", "contents", "trigger", "rarity", "claim_rule", "expiry"], "Items & Economy"),
    _g("crafting_station", "Crafting Station", "🏭", "station", ["name", "recipes", "upgrades", "footprint", "power", "unlock"], "Items & Economy"),

    # ══════════════ STANDARD · LEVELS & ENCOUNTERS ══════════════
    _g("level_from_text", "Level / Encounter", "🏰", "level", ["name", "biome", "rooms", "encounters", "objectives", "secrets", "pacing"], "Levels & Encounters"),
    _g("dungeon_room", "Dungeon Room", "🚪", "room", ["name", "shape", "encounters", "loot", "puzzle", "exits", "mood"], "Levels & Encounters"),
    _g("arena", "Arena", "🏟", "arena", ["name", "layout", "hazards", "cover", "spawns", "objectives", "win_cond"], "Levels & Encounters"),
    _g("encounter_table", "Encounter Table", "🎲", "encounter", ["name", "entries", "weights", "scaling", "conditions", "respawn"], "Levels & Encounters"),
    _g("wave_horde", "Wave / Horde", "🌊", "wave", ["name", "composition", "timing", "ramp", "modifiers", "reward"], "Levels & Encounters"),
    _g("puzzle", "Puzzle", "🧩", "puzzle", ["name", "premise", "mechanic", "steps", "hint", "solution", "reward"], "Levels & Encounters"),
    _g("secret_easter_egg", "Secret / Easter Egg", "🥚", "secret", ["name", "trigger", "discovery", "reward", "obscurity", "nod"], "Levels & Encounters"),
    _g("checkpoint", "Checkpoint", "🚩", "checkpoint", ["name", "placement", "restore", "respawn", "autosave", "trigger"], "Levels & Encounters"),
    _g("spawn_point", "Spawn Point", "📌", "spawn", ["name", "faction", "conditions", "cooldown", "safety", "fairness"], "Levels & Encounters"),
    _g("patrol_route", "Patrol Route", "🚶", "patrol", ["name", "waypoints", "timing", "alert_logic", "investigate", "reinforce"], "Levels & Encounters"),
    _g("set_piece", "Set Piece", "🎆", "set_piece", ["name", "spectacle", "scripting", "player_agency", "fail_safe", "payoff"], "Levels & Encounters"),
    _g("world_map", "World Map", "🧭", "worldmap", ["name", "regions", "routes", "fog", "fast_travel", "discovery"], "Levels & Encounters"),
    _g("fast_travel_node", "Fast-Travel Node", "🌀", "fast_travel", ["name", "unlock", "cost", "network", "restrictions", "vfx"], "Levels & Encounters"),

    # ══════════════ STANDARD · PROGRESSION & META ══════════════
    _g("achievement_from_text", "Achievement / Objective", "🏆", "achievement", ["name", "trigger", "tiers", "reward", "hidden", "tracking"], "Progression & Meta"),
    _g("skill_node", "Skill-Tree Node", "🌳", "skill_node", ["name", "branch", "prereqs", "effect", "cost", "rank_cap"], "Progression & Meta"),
    _g("talent_perk", "Talent / Perk", "🎯", "perk", ["name", "category", "effect", "requirement", "synergies", "exclusions"], "Progression & Meta"),
    _g("class_archetype", "Class / Archetype", "🛡", "class", ["name", "fantasy", "stats", "core_skills", "playstyle", "weaknesses"], "Progression & Meta"),
    _g("xp_curve", "XP / Level Curve", "📈", "xp_curve", ["name", "formula", "milestones", "soft_cap", "rewards", "prestige"], "Progression & Meta"),
    _g("unlock_gate", "Unlock / Gate", "🔓", "unlock", ["name", "requirement", "grants", "soft_lock", "hint", "skip_cost"], "Progression & Meta"),
    _g("battle_pass_tier", "Battle-Pass Tier", "🎟", "bp_tier", ["tier", "free_reward", "premium_reward", "xp_req", "theme", "exclusive"], "Progression & Meta"),
    _g("daily_challenge", "Daily Challenge", "📆", "daily", ["name", "objective", "difficulty", "reward", "reset", "streak_bonus"], "Progression & Meta"),
    _g("mastery_track", "Mastery Track", "🥇", "mastery", ["subject", "levels", "rewards", "challenge_req", "cosmetic", "title"], "Progression & Meta"),
    _g("prestige_rebirth", "Prestige / Rebirth", "♻", "prestige", ["name", "reset_scope", "kept", "bonus", "new_unlocks", "cost"], "Progression & Meta"),
    _g("collection_set", "Collection Set", "🗂", "collection", ["name", "items", "completion_reward", "hints", "tracking", "trade"], "Progression & Meta"),

    # ══════════════ STANDARD · UI & UX ══════════════
    _g("hud_element", "HUD Element", "🖥", "hud", ["name", "anchor", "data", "states", "animation", "accessibility"], "UI & UX"),
    _g("menu_screen", "Menu Screen", "📋", "menu", ["name", "sections", "navigation", "actions", "back_behavior", "layout"], "UI & UX"),
    _g("tutorial_step", "Tutorial Step", "🎓", "tutorial", ["name", "teaches", "trigger", "prompt", "success_check", "skip"], "UI & UX"),
    _g("tooltip", "Tooltip", "💡", "tooltip", ["context", "body", "trigger", "delay", "rich_data", "length"], "UI & UX"),
    _g("notification", "Notification", "🔔", "notification", ["name", "trigger", "message", "priority", "dismiss", "action"], "UI & UX"),
    _g("loading_tip", "Loading Tip", "⏳", "loading_tip", ["body", "category", "weight", "spoiler_safe", "tone", "context"], "UI & UX"),
    _g("settings_option", "Settings Option", "⚙", "setting", ["name", "type", "default", "range", "tooltip", "apply"], "UI & UX"),
    _g("keybind_control", "Keybind / Control", "⌨", "keybind", ["action", "default", "context", "rebindable", "conflicts", "platform"], "UI & UX"),

    # ══════════════ STANDARD · AUDIO & VFX ══════════════
    _g("sfx_cue", "SFX Cue", "🔊", "sfx", ["name", "trigger", "layers", "variation", "spatial", "ducking"], "Audio & VFX"),
    _g("music_theme", "Music Theme", "🎵", "music", ["name", "mood", "instrumentation", "tempo", "loop", "stinger"], "Audio & VFX"),
    _g("ambient_soundscape", "Ambient Soundscape", "🌬", "ambient", ["name", "layers", "time_of_day", "weather_tie", "randomization", "mix"], "Audio & VFX"),
    _g("vfx_effect", "VFX / Particle", "🎇", "vfx", ["name", "emitter", "lifetime", "color_ramp", "forces", "lod"], "Audio & VFX"),
    _g("emote_gesture", "Emote / Gesture", "🙌", "emote", ["name", "animation", "trigger", "loop", "sound", "unlock"], "Audio & VFX"),

    # ══════════════ ADVANCED · AI & SIMULATION ══════════════
    _g("ai_behavior_tree", "AI Behavior Tree", "🌲", "ai_bt", ["name", "root", "selectors", "sequences", "conditions", "actions", "decorators"], "AI & Simulation", True),
    _g("ai_utility_curve", "AI Utility Curve", "📉", "ai_utility", ["name", "considerations", "curves", "weights", "scorers", "actions"], "AI & Simulation", True),
    _g("ai_blackboard", "AI Blackboard", "🗒", "ai_bb", ["name", "keys", "types", "writers", "readers", "ttl"], "AI & Simulation", True),
    _g("ai_perception", "AI Perception Model", "👁", "ai_perception", ["name", "senses", "ranges", "stimuli", "memory", "alert_states"], "AI & Simulation", True),
    _g("ai_squad_tactics", "AI Squad Tactics", "🪖", "ai_squad", ["name", "roles", "formations", "comms", "flank_logic", "retreat"], "AI & Simulation", True),
    _g("ai_director", "AI Director Rule", "🎚", "ai_director", ["name", "tension_model", "pacing", "spawn_rules", "intensity_curve", "relief"], "AI & Simulation", True),
    _g("crowd_sim", "Crowd Simulation", "🏟", "crowd_sim", ["name", "density", "goals", "avoidance", "panic_model", "lod"], "AI & Simulation", True),
    _g("flocking_boids", "Flocking / Boids", "🐦", "flocking", ["name", "separation", "alignment", "cohesion", "predators", "bounds"], "AI & Simulation", True),
    _g("pathfinding_profile", "Pathfinding Profile", "🧭", "pathfinding", ["name", "algorithm", "heuristic", "costs", "smoothing", "dynamic_avoid"], "AI & Simulation", True),
    _g("nav_mesh_rule", "NavMesh Rule", "🕸", "navmesh", ["name", "agent_radius", "step_height", "areas", "links", "carving"], "AI & Simulation", True),

    # ══════════════ ADVANCED · PROCEDURAL GENERATION ══════════════
    _g("procgen_ruleset", "Procedural Ruleset", "🎰", "procgen", ["name", "seed_inputs", "rules", "constraints", "validation", "fallback"], "Procedural Generation", True),
    _g("wfc_tileset", "Wave-Function-Collapse Tileset", "🔲", "wfc", ["name", "tiles", "adjacency", "weights", "constraints", "backtracking"], "Procedural Generation", True),
    _g("dungeon_grammar", "Dungeon Grammar", "🏛", "grammar", ["name", "symbols", "productions", "lock_key", "loops", "validation"], "Procedural Generation", True),
    _g("terrain_noise", "Terrain Noise Profile", "🏔", "terrain", ["name", "octaves", "frequency", "amplitude", "erosion", "biome_mask"], "Procedural Generation", True),
    _g("biome_blend", "Biome Blend Rule", "🌐", "biome_blend", ["name", "biomes", "transitions", "moisture", "temperature", "blend_width"], "Procedural Generation", True),
    _g("loot_weighting", "Procedural Loot Weighting", "⚖", "loot_weight", ["name", "tables", "luck_stat", "pity", "smoothing", "dedupe"], "Procedural Generation", True),
    _g("quest_generator", "Procedural Quest Template", "🧾", "quest_gen", ["name", "skeleton", "slots", "fillers", "constraints", "reward_scaling"], "Procedural Generation", True),
    _g("name_generator", "Procedural Name Grammar", "🔤", "name_gen", ["name", "syllables", "rules", "culture_bias", "filters", "uniqueness"], "Procedural Generation", True),
    _g("l_system", "L-System Foliage", "🌳", "lsystem", ["name", "axiom", "rules", "angle", "iterations", "variation"], "Procedural Generation", True),
    _g("city_layout", "Procedural City Layout", "🏙", "city_gen", ["name", "districts", "road_network", "density", "landmarks", "constraints"], "Procedural Generation", True),

    # ══════════════ ADVANCED · DEEP SYSTEMS & SIM ══════════════
    _g("economy_sim", "Economy Simulation Model", "💹", "economy_sim", ["name", "goods", "agents", "price_model", "shocks", "equilibrium"], "Deep Systems", True),
    _g("supply_demand", "Supply / Demand Curve", "📊", "supply_demand", ["good", "supply_fn", "demand_fn", "elasticity", "shocks", "clearing_price"], "Deep Systems", True),
    _g("faction_diplomacy", "Faction Diplomacy Matrix", "🤝", "diplomacy", ["factions", "relations", "treaties", "casus_belli", "decay", "events"], "Deep Systems", True),
    _g("reputation_system", "Reputation System", "⭐", "reputation", ["name", "axes", "thresholds", "gains", "decay", "consequences"], "Deep Systems", True),
    _g("ecosystem_food_web", "Ecosystem Food Web", "🦌", "ecosystem", ["name", "species", "predation", "population_model", "carrying_capacity", "collapse"], "Deep Systems", True),
    _g("weather_system", "Weather System Model", "🌦", "weather_sys", ["name", "states", "transitions", "gameplay_effects", "regional", "forecast"], "Deep Systems", True),
    _g("day_night_sim", "Day / Night Simulation", "🌗", "day_night", ["name", "cycle_length", "phases", "npc_effects", "spawn_effects", "lighting"], "Deep Systems", True),
    _g("crime_law_sim", "Crime & Law Sim", "👮", "crime_law", ["name", "crimes", "witness_model", "bounty", "enforcement", "redemption"], "Deep Systems", True),
    _g("needs_system", "Needs / Survival System", "🍖", "needs", ["name", "needs", "decay_rates", "fulfillment", "penalties", "buffs"], "Deep Systems", True),
    _g("dynamic_difficulty", "Dynamic Difficulty Adjustment", "🎛", "ddamodel", ["name", "signals", "adjustments", "bounds", "invisibility", "cooldown"], "Deep Systems", True),

    # ══════════════ ADVANCED · NETCODE & MULTIPLAYER ══════════════
    _g("netcode_model", "Netcode Model", "🛰", "netcode", ["name", "topology", "tick_rate", "serialization", "bandwidth", "fallback"], "Netcode & Multiplayer", True),
    _g("rollback_config", "Rollback Netcode Config", "⏪", "rollback", ["name", "input_delay", "max_rollback", "prediction", "desync_check", "recovery"], "Netcode & Multiplayer", True),
    _g("lag_compensation", "Lag Compensation Profile", "📡", "lag_comp", ["name", "rewind_window", "hit_validation", "interpolation", "extrapolation", "abuse_guard"], "Netcode & Multiplayer", True),
    _g("matchmaking_rule", "Matchmaking Ruleset", "🎯", "matchmaking", ["name", "skill_metric", "ranges", "expansion", "balance", "constraints"], "Netcode & Multiplayer", True),
    _g("anti_cheat_rule", "Anti-Cheat Rule", "🛡", "anticheat", ["name", "detection", "signals", "thresholds", "response", "false_positive_guard"], "Netcode & Multiplayer", True),
    _g("authoritative_state", "Authoritative State Sync", "🗃", "authoritative", ["name", "owned_state", "replication", "reconciliation", "priority", "delta_compress"], "Netcode & Multiplayer", True),
    _g("interest_management", "Interest Management", "🔭", "interest_mgmt", ["name", "relevance_model", "cells", "update_rates", "culling", "priority"], "Netcode & Multiplayer", True),
    _g("session_arch", "Session Architecture", "🧩", "session", ["name", "lifecycle", "host_model", "migration", "persistence", "scaling"], "Netcode & Multiplayer", True),

    # ══════════════ ADVANCED · RENDERING & TECH ART ══════════════
    _g("shader_graph", "Shader Graph", "🎨", "shader", ["name", "inputs", "nodes", "outputs", "variants", "cost"], "Rendering & Tech Art", True),
    _g("material_layer", "Material Layering", "🧱", "material", ["name", "layers", "masks", "blend_modes", "tiling", "detail_maps"], "Rendering & Tech Art", True),
    _g("post_fx_stack", "Post-FX Stack", "🌈", "post_fx", ["name", "passes", "order", "parameters", "platform_scaling", "cost"], "Rendering & Tech Art", True),
    _g("lighting_rig", "Lighting Rig", "💡", "lighting", ["name", "key_light", "fill", "rim", "bounce", "mood", "time_of_day"], "Rendering & Tech Art", True),
    _g("volumetric_profile", "Volumetrics Profile", "🌫", "volumetrics", ["name", "fog_density", "scattering", "god_rays", "clouds", "cost"], "Rendering & Tech Art", True),
    _g("lod_strategy", "LOD / Streaming Strategy", "📦", "lod", ["name", "lod_levels", "distances", "impostors", "streaming", "memory_budget"], "Rendering & Tech Art", True),
    _g("vfx_graph", "VFX Graph / Niagara", "✴", "vfx_graph", ["name", "emitters", "modules", "gpu_sim", "events", "budget"], "Rendering & Tech Art", True),

    # ══════════════ ADVANCED · LIVEOPS & DATA ══════════════
    _g("liveops_event", "LiveOps Event", "📡", "liveops", ["name", "schedule", "rewards", "modifiers", "leaderboard", "kpi"], "LiveOps & Data", True),
    _g("ab_test", "A/B Test Variant", "🧪", "ab_test", ["name", "hypothesis", "variants", "allocation", "metrics", "stop_rule"], "LiveOps & Data", True),
    _g("telemetry_event", "Telemetry Event Schema", "📶", "telemetry", ["name", "trigger", "properties", "types", "sampling", "pii_policy"], "LiveOps & Data", True),
    _g("season_model", "Season Model", "🗓", "season", ["name", "duration", "theme", "progression", "rewards", "soft_reset"], "LiveOps & Data", True),
    _g("monetization_offer", "Monetization Offer", "💳", "offer", ["name", "contents", "price_points", "targeting", "urgency", "value_framing"], "LiveOps & Data", True),

    # ══════════════ ADVANCED · DEFERRED FORGES (SOTA, 8) ══════════════
    # The 8 deferred forges from the SOTA blueprint. Each emits a rich, distinct
    # gamefile — churnable + 14-gate ready — with a tier-scaled depth ladder.
    _g("quality_forge", "Quality Forge", "💎", "quality_pass",
       ["scope", "juice_targets", "game_feel_fixes", "accessibility_audit", "bug_risk_list", "polish_checklist", "ship_gate"],
       "Deferred Forges", True),
    _g("fine_tuning_forge", "Fine-Tuning Forge", "🎚", "fine_tuning",
       ["scope", "tuned_curves", "drop_rates", "difficulty_knobs", "economy_balance", "ttk_targets", "telemetry_hooks"],
       "Deferred Forges", True),
    _g("critter_bestiary_forge", "Critter & Bestiary Forge", "🦎", "critter",
       ["species", "stat_block", "behavior_tree", "spawn_table", "habitat", "ecology_role", "loot_lore"],
       "Deferred Forges", True),
    _g("nature_forge", "Nature Forge", "🌲", "nature",
       ["biome", "flora", "fauna_overlap", "weather_system", "season_cycle", "ecology_rules", "ambient_life"],
       "Deferred Forges", True),
    _g("realism_forge", "Realism Forge", "🔬", "realism",
       ["domain", "lighting_rules", "material_response", "physical_plausibility", "scale_accuracy", "sensory_fidelity", "failure_modes"],
       "Deferred Forges", True),
    _g("fine_mechanic_forge", "Fine-Mechanic Forge", "⚙️", "fine_mechanic",
       ["mechanic", "input_buffering", "coyote_time", "hit_pause", "snap_assist", "tuning_window", "feel_metrics"],
       "Deferred Forges", True),
    _g("movement_forge", "Movement Forge", "🏃", "movement",
       ["locomotion", "acceleration", "jump_arc", "dash_dodge", "climb_swim", "momentum_rules", "traversal_feel"],
       "Deferred Forges", True),
    _g("city_forge", "City Forge", "🏙", "city",
       ["name", "districts", "road_network", "points_of_interest", "density_zones", "traffic_flow", "verticality"],
       "Deferred Forges", True),
]
_BY_KEY = {g["key"]: g for g in GENERATORS}

# ── 5-TIER CHOICE SYSTEM ─────────────────────────────────────────────────────
# Applicable generators expose a 5-step power/quality ladder (tier 1→5). The
# Command Center shows a tier selector for these; the chosen tier shapes the
# forged gamefile (stat budget, threat, rarity). Non-listed generators are tierless.
TIERS: dict[str, list[str]] = {
    "boss_design": ["Minion Boss", "Elite Boss", "Mini-Boss", "Main Boss", "Raid / World Boss"],
    "boss_phase": ["Opening", "Escalation", "Desperation", "Enrage", "Final Stand"],
    "enemy_from_text": ["Fodder", "Standard", "Veteran", "Elite", "Champion"],
    "minion_add": ["Swarm", "Grunt", "Brute", "Specialist", "Captain"],
    "item_from_text": ["Common", "Uncommon", "Rare", "Epic", "Legendary"],
    "weapon_def": ["Common", "Uncommon", "Rare", "Epic", "Legendary"],
    "armor_gear": ["Common", "Uncommon", "Rare", "Epic", "Legendary"],
    "consumable_potion": ["Minor", "Lesser", "Standard", "Greater", "Supreme"],
    "rarity_tier": ["Common", "Uncommon", "Rare", "Epic", "Legendary"],
    "ability_from_text": ["Basic", "Skilled", "Advanced", "Master", "Ultimate"],
    "ultimate_super": ["Tier I", "Tier II", "Tier III", "Tier IV", "Apex"],
    "level_from_text": ["Tutorial", "Easy", "Normal", "Hard", "Nightmare"],
    "dungeon_room": ["Trivial", "Easy", "Normal", "Hard", "Brutal"],
    "arena": ["Bronze", "Silver", "Gold", "Platinum", "Diamond"],
    "wave_horde": ["Wave I", "Wave II", "Wave III", "Wave IV", "Final Wave"],
    "encounter_table": ["Trivial", "Light", "Standard", "Heavy", "Deadly"],
    "achievement_from_text": ["Bronze", "Silver", "Gold", "Platinum", "Diamond"],
    "skill_node": ["Novice", "Apprentice", "Adept", "Expert", "Master"],
    "talent_perk": ["Tier I", "Tier II", "Tier III", "Tier IV", "Capstone"],
    "reward_bundle": ["Starter", "Standard", "Premium", "Deluxe", "Ultimate"],
    "battle_pass_tier": ["Free", "Standard", "Premium", "Elite", "Prestige"],
    "monetization_offer": ["Trial", "Value", "Standard", "Premium", "Whale"],
    # ── Deferred Forges depth/scope ladders ──
    "quality_forge": ["Smoke", "Standard", "Deep", "Exhaustive", "Ship-Grade"],
    "fine_tuning_forge": ["Rough", "Baseline", "Tuned", "Refined", "Competitive"],
    "critter_bestiary_forge": ["Critter", "Beast", "Predator", "Apex", "Mythic"],
    "nature_forge": ["Sparse", "Lush", "Wild", "Primeval", "Living World"],
    "realism_forge": ["Stylized", "Grounded", "Plausible", "Simulated", "Photoreal"],
    "fine_mechanic_forge": ["Raw", "Responsive", "Tight", "Buttery", "Frame-Perfect"],
    "movement_forge": ["Basic", "Agile", "Acrobatic", "Parkour", "Superhuman"],
    "city_forge": ["Hamlet", "Town", "City", "Metropolis", "Megacity"],
}


def list_generators() -> dict:
    gens = [{"key": g["key"], "label": g["label"], "icon": g["icon"],
             "type": g["type"], "fields": g["fields"],
             "group": g.get("group", "General"), "advanced": bool(g.get("advanced")),
             "tiers": TIERS.get(g["key"], [])}
            for g in GENERATORS]
    adv = sum(1 for g in gens if g["advanced"])
    tiered = sum(1 for g in gens if g["tiers"])
    groups: dict[str, int] = {}
    for g in gens:
        groups[g["group"]] = groups.get(g["group"], 0) + 1
    return {"count": len(gens), "standard_count": len(gens) - adv,
            "advanced_count": adv, "tiered_count": tiered,
            "group_counts": groups, "generators": gens}


def get_generator(key: str) -> dict | None:
    return _BY_KEY.get(key)


def _seed(text: str) -> int:
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest(), 16) % (2 ** 31)


def _sentences(text: str) -> list[str]:
    parts = re.split(r"[.!?\n]+", text or "")
    return [p.strip() for p in parts if p.strip()]


def _deterministic_fields(gen: dict, text: str) -> dict:
    """Genuinely DERIVE structured gamefile fields from the prompt text — not a
    stub: title from the lead clause, list-fields from clauses, numeric/dict
    fields from salient words, booleans from a stable hash. Broadened so the
    150-system field vocabulary all derives meaningfully (LLM enrich refines)."""
    sents = _sentences(text) or ["untitled"]
    words = re.findall(r"[A-Za-z][A-Za-z'-]+", text or "")
    title = " ".join(words[:5]).title() or gen["type"].title()

    NAME_F = {"title", "name", "speaker", "author", "sender", "pair", "good",
              "subject", "weapon", "vendor", "context", "action", "tier"}
    TEXT_F = {"body", "flavor", "effect", "ai_behavior", "backstory", "motivation",
              "premise", "scheme", "claim", "verse", "message", "hypothesis",
              "value_framing", "implied_event", "subtext", "behavior", "spectacle",
              "fantasy", "personality", "ideology", "mood", "tone", "ambience",
              "presence", "voice"}
    DICT_F = {"stats", "scaling", "weights", "prices", "damage", "supply_fn",
              "demand_fn", "curves", "costs", "ranges", "thresholds", "distances",
              "allocation", "tick_rate", "frequency", "amplitude", "defense",
              "price_model", "population_model", "decay_rates", "price_points",
              "resistances", "parameters", "update_rates"}
    BOOL_F = {"hidden", "skippable", "rebindable", "spoiler_safe", "repeatable",
              "exclusive", "guaranteed", "gpu_sim", "loop"}
    # explicit non-plural fields that are still genuine lists
    LIST_EXTRA = {"loot", "moveset", "comms", "senses", "stimuli", "fog",
                  "axiom", "root", "leadership", "core_skills", "instrumentation"}

    out: dict = {}
    for f in gen["fields"]:
        is_list = f in LIST_EXTRA or (f.endswith("s") and f not in DICT_F
                                      and f not in NAME_F and f not in BOOL_F)
        if f in NAME_F:
            out[f] = title
        elif f in DICT_F:
            out[f] = {w.lower(): (len(w) * 7 + _seed(f) % 13) % 100 for w in words[:5]} or {"value": 50}
        elif f in BOOL_F:
            out[f] = bool(_seed(text + f) % 2)
        elif f in TEXT_F:
            out[f] = " ".join(sents)[:600]
        elif is_list:
            n = min(6, max(2, len(sents)))
            stem = f[:-1] if f.endswith("s") else f
            out[f] = [f"{stem} {i + 1}: {sents[i % len(sents)][:80]}" for i in range(n)]
        else:
            out[f] = sents[_seed(text + f) % len(sents)][:120]
    return out


def _llm_enrich(gen: dict, text: str, fields: dict, contexts: dict | None = None) -> dict | None:
    """Optional Claude pass — uses the SAME maxed-brief pattern as the forge."""
    key = os.environ.get("EMERGENT_LLM_KEY")
    if not key:
        return None
    try:
        import asyncio
        import json as _json
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        from core import snowball_axes as _ax  # reuse creator-context block if any
        ctx_block = _ax._context_prompt_block(contexts) if contexts else ""
        sysmsg = (
            f"You are an elite AAA {gen['type']} designer. Turn the creator's "
            f"text into a precise, production-ready {gen['type']} GAMEFILE that "
            f"clears a >97 AAA bar. Be concrete, distinct and engine-ready.\n"
            f"Respond ONLY with compact JSON: {{\"brief\":str (a RICH, maximal "
            f"design brief up to ~{MAX_BRIEF_CHARS} characters — exhaustive, "
            f"specific, no filler), \"fields\":object (refine these keys: "
            f"{', '.join(gen['fields'])})}}."
        )
        prompt = (f"GAMEFILE TYPE: {gen['label']} ({gen['type']}).\n{ctx_block}"
                  f"CREATOR TEXT (authoritative — honor verbatim):\n\"\"\"{text[:8000]}\"\"\"\n"
                  f"DETERMINISTIC DRAFT FIELDS: {_json.dumps(fields)[:2000]}\n"
                  f"Produce the maximal, precise {gen['type']} gamefile.")

        async def _run():
            chat = LlmChat(api_key=key, session_id=f"tgf-{gen['key']}-{_seed(text)}",
                           system_message=sysmsg)
            chat.with_model("anthropic", "claude-sonnet-4-5-20250929")
            chat.with_max_tokens(8000)   # allow the maxed brief
            return await chat.send_message(UserMessage(text=prompt))
        raw = (asyncio.run(_run()) or "").strip()
        s, e = raw.find("{"), raw.rfind("}")
        if s >= 0 and e > s:
            data = _json.loads(raw[s:e + 1])
            return {"brief": (data.get("brief") or "")[:MAX_BRIEF_CHARS],
                    "fields": data.get("fields") or {}}
    except Exception:
        return None
    return None


def generate(key: str, build_id: str, text: str, enrich: bool = False,
             contexts: dict | None = None, store: bool = True,
             tier: str | None = None) -> dict:
    gen = get_generator(key)
    if not gen:
        return {"error": "unknown_generator", "key": key}
    if not build_id:
        return {"error": "missing_build_id"}
    if not (text or "").strip():
        return {"error": "empty_text"}
    # 5-tier choice system: a chosen tier shapes the derivation + is recorded.
    tier_ladder = TIERS.get(key, [])
    tier_label, tier_index = None, None
    if tier and tier_ladder:
        if tier in tier_ladder:
            tier_label, tier_index = tier, tier_ladder.index(tier) + 1
        elif str(tier).isdigit() and 1 <= int(tier) <= len(tier_ladder):
            tier_index = int(tier)
            tier_label = tier_ladder[tier_index - 1]
    eff_text = (f"[Power Tier {tier_index}/5 · {tier_label}] {text}"
                if tier_label else text)
    fields = _deterministic_fields(gen, eff_text)
    if tier_label:
        fields["tier"] = f"{tier_label} (tier {tier_index} of 5)"
    brief = (f"{gen['label']} derived from creator text ({len(text)} chars). "
             f"Type={gen['type']}; fields={', '.join(gen['fields'])}."
             + (f" Power tier: {tier_label} ({tier_index}/5)." if tier_label else ""))
    llm_used = False
    if enrich:
        ai = _llm_enrich(gen, eff_text, fields, contexts)
        if ai:
            fields.update({k: v for k, v in (ai.get("fields") or {}).items() if v})
            brief = ai.get("brief") or brief
            llm_used = True
    gid = f"gf_{key}_{_seed(text + build_id + (tier_label or '')) % 100000}"
    gamefile = {
        "id": gid, "build_id": build_id, "system": key, "kind": "gamefile",
        "label": (f"{gen['label']} · {tier_label}" if tier_label else gen["label"]),
        "type": gen["type"], "icon": gen["icon"],
        "tier": tier_label, "tier_index": tier_index, "tier_ladder": tier_ladder,
        "source_text": text[:4000], "fields": fields,
        # gate-compatible shape: gates read knobs + brief
        "knobs": {f: (", ".join(v) if isinstance(v, list) else str(v))[:120]
                  for f, v in fields.items()},
        "brief": brief[:MAX_BRIEF_CHARS], "llm_enriched": llm_used,
        "created": time.time(),
    }
    if store:
        try:
            from core.databases import get_sync_db
            from core import unbulk
            to_store = {"_id": f"{build_id}:{gid}", **gamefile}
            # Transparent compression of the large generated payload fields —
            # packed on write, unpacked on demand (get_gamefile / list_gamefiles).
            unbulk.compress_field(to_store, "fields")
            unbulk.compress_field(to_store, "brief")
            get_sync_db()["galaxy_text_gamefiles"].replace_one(
                {"_id": f"{build_id}:{gid}"}, to_store, upsert=True)
        except Exception:
            pass
        try:
            from core import build_ledger as bl
            bl.log(build_id, "gamefile_generated",
                   {"system": key, "type": gen["type"], "id": gid, "llm": llm_used})
        except Exception:
            pass
    return gamefile


def get_gamefile(build_id: str, gid: str) -> dict | None:
    try:
        from core.databases import get_sync_db
        from core import unbulk
        doc = get_sync_db()["galaxy_text_gamefiles"].find_one(
            {"_id": f"{build_id}:{gid}"}, {"_id": 0})
        return unbulk.decompress_doc(doc, ["fields", "brief"]) if doc else doc
    except Exception:
        return None


def list_gamefiles(build_id: str) -> dict:
    rows = []
    try:
        from core.databases import get_sync_db
        from core import unbulk
        rows = list(get_sync_db()["galaxy_text_gamefiles"]
                    .find({"build_id": build_id}, {"_id": 0, "source_text": 0}))
        for r in rows:
            unbulk.decompress_doc(r, ["fields", "brief"])
    except Exception:
        pass
    return {"build_id": build_id, "count": len(rows), "gamefiles": rows}


def prune_gamefiles(build_id: str | None = None) -> dict:
    """Delete already-made gamefiles (and their pipeline-run history). Scoped to
    one build when build_id is given, otherwise clears ALL forged gamefiles."""
    res = {"gamefiles_deleted": 0, "history_deleted": 0, "scope": build_id or "ALL"}
    try:
        from core.databases import get_sync_db
        db = get_sync_db()
        gq = {"build_id": build_id} if build_id else {}
        hq = ({"build_id": build_id} if build_id else {})
        res["gamefiles_deleted"] = db["galaxy_text_gamefiles"].delete_many(gq).deleted_count
        res["history_deleted"] = db["galaxy_pipeline_history"].delete_many(hq).deleted_count
    except Exception as e:
        res["error"] = str(e)
    return res
